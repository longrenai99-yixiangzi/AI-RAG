from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from qdrant_client import QdrantClient, models

from app.config import Settings
from app.domain import Chunk
from app.ingestion.pipeline import PipelineResult, run_document_pipeline
from app.parsers import iter_source_files
from app.retrieval.dense_provider import BGEM3DenseProvider


COLLECTION_NAME = "full_corpus_shadow_bge_m3"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the isolated full-corpus BGE-M3 Shadow Qdrant index.")
    parser.add_argument("--vault", type=Path, default=Path(r"D:\设计管理"))
    parser.add_argument(
        "--shadow-dir",
        type=Path,
        default=Path("data") / "shadow" / "full_corpus_qdrant",
    )
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: torch.cuda.is_available() is False; Shadow Embedding stopped.")
        return 2
    if not args.vault.is_dir():
        print(f"ERROR: vault does not exist: {args.vault}")
        return 2

    started = time.perf_counter()
    scan_errors: list[str] = []
    files = iter_source_files(args.vault, scan_errors=scan_errors)
    pipeline = _run_pipeline_resilient(args.vault, files, scan_errors)
    chunks = [chunk for document in pipeline.documents for chunk in document.chunks]
    metadata_by_chunk = {
        chunk_id: metadata
        for document in pipeline.documents
        for chunk_id, metadata in document.chunk_metadata.items()
    }

    args.shadow_dir.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(args.shadow_dir))
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=1_024, distance=models.Distance.COSINE),
    )

    provider = BGEM3DenseProvider(
        settings.embedding_model,
        collection_name="unused_in_memory_collection",
        use_fp16=True,
        batch_size=args.batch_size,
    )
    provider.load()
    torch.cuda.synchronize()
    embedding_started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    embedded_count = 0
    embedding_failures: list[dict[str, Any]] = []

    try:
        for start in range(0, len(chunks), args.batch_size):
            batch = chunks[start : start + args.batch_size]
            try:
                vectors = provider.embed_documents([chunk.text for chunk in batch])
                points = [
                    models.PointStruct(
                        id=chunk.chunk_id,
                        vector=vector,
                        payload=_payload(chunk, metadata_by_chunk.get(chunk.chunk_id, {})),
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ]
                if points:
                    client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)
                    embedded_count += len(points)
            except Exception as error:
                embedding_failures.extend(
                    {
                        "chunk_id": chunk.chunk_id,
                        "source_path": chunk.source_path,
                        "file_name": chunk.file_name,
                        "error": f"{type(error).__name__}: {error}",
                    }
                    for chunk in batch
                )
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            processed = min(start + len(batch), len(chunks))
            print(f"embedding_progress={processed}/{len(chunks)} indexed={embedded_count}", flush=True)

        torch.cuda.synchronize()
    finally:
        provider.close()
        client.close()

    embedding_elapsed = time.perf_counter() - embedding_started
    total_elapsed = time.perf_counter() - started
    report = _build_report(
        args=args,
        settings=settings,
        pipeline=pipeline,
        files=files,
        chunks=chunks,
        embedded_count=embedded_count,
        embedding_failures=embedding_failures,
        scan_errors=scan_errors,
        embedding_elapsed=embedding_elapsed,
        total_elapsed=total_elapsed,
    )
    report_path = Path("docs") / "FULL_CORPUS_EMBEDDING_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0 if not embedding_failures else 1


def _run_pipeline_resilient(
    root: Path, files: list[Path], scan_errors: list[str]
) -> PipelineResult:
    try:
        return run_document_pipeline(root, files=files)
    except Exception as error:
        scan_errors.append(f"pipeline_batch_error: {type(error).__name__}: {error}")
        documents = []
        for path in files:
            try:
                single = run_document_pipeline(root, files=[path])
                documents.extend(single.documents)
                scan_errors.extend(single.scan_errors)
            except Exception as file_error:
                scan_errors.append(
                    f"{path}: {type(file_error).__name__}: {file_error}"
                )
        return PipelineResult(
            root=root,
            documents=documents,
            scan_errors=scan_errors,
            scanned_files=len(files),
        )


def _payload(chunk: Chunk, metadata: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "source_path": chunk.source_path,
        "file_name": chunk.file_name,
        "heading_path": chunk.heading_path,
        "location": chunk.location,
        "text": chunk.text,
        "metadata": metadata,
    }
    for key in (
        "file_type",
        "board",
        "knowledge_type",
        "discipline",
        "building_type",
        "project_stage",
        "topic",
        "document_level",
        "source_organization",
        "publish_date",
        "project_name",
    ):
        payload[key] = metadata.get(key)
    return payload


def _build_report(
    *,
    args: argparse.Namespace,
    settings: Settings,
    pipeline: PipelineResult,
    files: list[Path],
    chunks: list[Chunk],
    embedded_count: int,
    embedding_failures: list[dict[str, Any]],
    scan_errors: list[str],
    embedding_elapsed: float,
    total_elapsed: float,
) -> dict[str, Any]:
    abnormal_files = [
        {
            "path": str(document.path),
            "status": document.status,
            "error": document.error,
            "chunks": len(document.chunks),
        }
        for document in pipeline.documents
        if document.status not in {"parsed", "empty"} or document.error
    ]
    abnormal_files.extend(
        {"path": item, "status": "scan_error", "error": item, "chunks": 0}
        for item in scan_errors
        if not item.startswith("pipeline_batch_error:")
    )
    summary = {
        "vault": str(args.vault),
        "shadow_qdrant": str(args.shadow_dir.resolve()),
        "collection": COLLECTION_NAME,
        "files": len(files),
        "documents": len(pipeline.documents),
        "chunks": len(chunks),
        "embedding_vectors": embedded_count,
        "embedding_failures": len(embedding_failures),
        "abnormal_files": len(abnormal_files),
        "scan_errors": len(scan_errors),
        "embedding_elapsed_seconds": round(embedding_elapsed, 3),
        "total_elapsed_seconds": round(total_elapsed, 3),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "gpu_peak_memory_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "gpu_peak_memory_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        "metadata_complete_chunks": pipeline.metadata_complete_chunk_count(),
        "location_valid_chunks": pipeline.location_valid_chunk_count(),
        "status_counts": pipeline.status_counts(),
        "file_type_counts": pipeline.file_type_counts(),
    }
    return {
        "summary": summary,
        "model_path": settings.embedding_model,
        "abnormal_files_detail": abnormal_files,
        "embedding_failures": embedding_failures,
    }


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = [
        "# Full Corpus Shadow Embedding Report",
        "",
        "> 本报告仅记录 Document Pipeline → Chunk/Metadata → BGE-M3 CUDA → 独立 Shadow Qdrant 构建结果。",
        "> 未写入正式 `data\\qdrant`，未影响 8000 端口服务，未执行最终 Evaluation。",
        "",
        "## 1. 构建摘要",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 知识库路径 | `{summary['vault']}` |",
        f"| Shadow Qdrant 路径 | `{summary['shadow_qdrant']}` |",
        f"| Collection | `{summary['collection']}` |",
        f"| 文件数量 | {summary['files']} |",
        f"| Document 数量 | {summary['documents']} |",
        f"| Chunk 数量 | {summary['chunks']} |",
        f"| Embedding 数量 | {summary['embedding_vectors']} |",
        f"| Embedding 失败数量 | {summary['embedding_failures']} |",
        f"| 异常文件数量 | {summary['abnormal_files']} |",
        f"| 扫描/流水线错误数量 | {summary['scan_errors']} |",
        "",
        "## 2. CUDA 与耗时",
        "",
        f"- CUDA 可用：`{summary['cuda_available']}`",
        f"- GPU：`{summary['gpu_name']}`",
        f"- Torch：`{summary['torch']}`，CUDA Runtime：`{summary['torch_cuda']}`",
        f"- Embedding 阶段耗时：`{summary['embedding_elapsed_seconds']}` 秒",
        f"- 全流程耗时：`{summary['total_elapsed_seconds']}` 秒",
        f"- GPU 峰值 allocated：`{summary['gpu_peak_memory_allocated_bytes']}` bytes",
        f"- GPU 峰值 reserved：`{summary['gpu_peak_memory_reserved_bytes']}` bytes",
        "",
        "## 3. 模型与索引",
        "",
        f"- BGE-M3 路径：`{report['model_path']}`",
        f"- Qdrant 向量维度：`{1024}`",
        f"- Qdrant Collection：`{summary['collection']}`",
        f"- 写入向量数：`{summary['embedding_vectors']}`",
        "- Payload 包含：chunk_id、document_id、source_path、file_name、heading_path、location、text 和 Metadata。",
        "",
        "## 4. Document Pipeline 统计",
        "",
        f"- Metadata 完整 Chunk：`{summary['metadata_complete_chunks']}`",
        f"- location 有效 Chunk：`{summary['location_valid_chunks']}`",
        f"- 状态分布：`{json.dumps(summary['status_counts'], ensure_ascii=False)}`",
        f"- 文件类型分布：`{json.dumps(summary['file_type_counts'], ensure_ascii=False)}`",
        "",
        "## 5. 异常文件",
        "",
        "| 文件 | 状态 | Chunk | 错误 |",
        "|---|---|---:|---|",
    ]
    abnormal = report["abnormal_files_detail"]
    if abnormal:
        rows.extend(
            f"| `{item['path']}` | {item['status']} | {item['chunks']} | {item.get('error') or ''} |"
            for item in abnormal
        )
    else:
        rows.append("| 无 | - | 0 | - |")
    rows.extend(["", "## 6. Embedding 失败 Chunk", "", "| Chunk | 文件 | 错误 |", "|---|---|---|"])
    if report["embedding_failures"]:
        rows.extend(
            f"| `{item['chunk_id']}` | `{item['source_path']}` | {item['error']} |"
            for item in report["embedding_failures"]
        )
    else:
        rows.append("| 无 | - | - |")
    rows.extend(
        [
            "",
            "## 7. 边界与后续",
            "",
            "1. 本索引仅供 Shadow Retrieval 使用，未替换旧 Retriever。",
            "2. 本任务只完成全库 Embedding 与 Shadow Qdrant 构建；最终 Evaluation 按任务要求未执行。",
            "3. 正式切换前仍需单独完成 Shadow Retrieval Evaluation、Metadata Filter 验证和发布审批。",
            "",
        ]
    )
    return "\n".join(rows)


if __name__ == "__main__":
    raise SystemExit(main())
