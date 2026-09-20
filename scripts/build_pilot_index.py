"""分批试点建库脚本（T11）—— 将 [LOCAL_PATH_REDACTED]�公司技术部 的 2026 + EPC 两个子目录纳入检索索引。

设计原则：
1. **完全隔离**：不修改任何现有生产 Shadow 目录。
   - 现有 `full_corpus_qdrant` / `document_intelligence_v2` / `hierarchical_retrieval_v1_stabilization` 一律只读。
   - 新产物写入 `*_expanded` / `pilot_2026_epc` 目录。
2. **可断点续跑**：嵌入是最耗时环节（CPU 约 8~9 小时），进度按文件粒度落盘，中断后重跑自动跳过。
3. **分阶段**：atomic -> v2 -> embed -> merge -> index，任一阶段可单独重跑。

用法：
    python scripts/build_pilot_index.py --stage atomic
    python scripts/build_pilot_index.py --stage v2
    python scripts/build_pilot_index.py --stage embed --batch-size 8
    python scripts/build_pilot_index.py --stage merge
    python scripts/build_pilot_index.py --stage index
    python scripts/build_pilot_index.py --stage all --limit 40   # 冒烟测试
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402
from qdrant_client import QdrantClient, models  # noqa: E402

from app.config import Settings  # noqa: E402
from app.ingestion.atomic_evidence import ATOMIC_EXTENSIONS, build_atomic_evidence  # noqa: E402
from app.ingestion.pipeline import run_document_pipeline  # noqa: E402
from app.parsers import SUPPORTED_EXTENSIONS, iter_source_files  # noqa: E402
from app.retrieval.dense_provider import BGEM3DenseProvider, _qdrant_point_id  # noqa: E402

# ---- 试点范围 ---------------------------------------------------------------
SOURCE_ROOT = Path(r"[LOCAL_PATH_REDACTED]�公司技术部")
SUBS = ["2026", "EPC"]

# ---- 输出目录（全部为新建，不动现有目录）-------------------------------------
PILOT_DIR = ROOT / "data" / "shadow" / "pilot_2026_epc"
PILOT_V2_DIR = PILOT_DIR / "v2"
PILOT_ATOMIC = PILOT_DIR / "atomic_records.jsonl"
CHUNKS_PATH = PILOT_DIR / "chunks.jsonl"
PROGRESS_PATH = PILOT_DIR / "embed_progress.json"

EXISTING_QDRANT = ROOT / "data" / "shadow" / "full_corpus_qdrant"
EXPANDED_QDRANT = ROOT / "data" / "shadow" / "full_corpus_qdrant_expanded"
COLLECTION = "full_corpus_shadow_bge_m3"

EXISTING_V2 = ROOT / "data" / "shadow" / "document_intelligence_v2"
EXPANDED_V2 = ROOT / "data" / "shadow" / "document_intelligence_v2_expanded"
ROOT2_QDRANT = ROOT / "data" / "shadow" / "root002_import" / "qdrant"
ROOT2_COLLECTION = "root002_shadow_bge_m3"
EXPANDED_INDEX = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_expanded"

V2_KEYS = ("documents", "headings", "sections", "paragraphs", "tables", "table_rows", "lineage", "metadata_conflicts")
AUDIT_DIR = ROOT / "evaluation" / "knowledge_os_system_audit" / "t11_pilot"

# BGE-M3 模型目录。
# 注意：models/bge-m3 的 pytorch_model.bin 在 torch 2.13 + Windows 下用默认的
# weights_only=True 反序列化会段错误（EXIT=139），已由 scripts/fix_bge_m3_checkpoint.py
# 转为 safetensors 到 models/bge-m3-st。两者向量数值等价（余弦 0.999999）。
BGE_MODEL_DIR = ROOT / "models" / "bge-m3-st"
if not BGE_MODEL_DIR.is_dir():
    BGE_MODEL_DIR = ROOT / "models" / "bge-m3"

# v2 结构构建的分批大小（一次 build 全量会 MemoryError，详见 stage_v2 注释）
V2_BATCH = 150


def collect_files(subs: list[str], limit: int | None = None) -> list[Path]:
    files: list[Path] = []
    for sub in subs:
        files.extend(iter_source_files(SOURCE_ROOT / sub))
    files = sorted({Path(p) for p in files if p.suffix.casefold() in SUPPORTED_EXTENSIONS}, key=lambda p: str(p).casefold())
    return files[:limit] if limit else files


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]], mode: str = "w") -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open(mode, encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# =========================== Stage: atomic ===================================
def stage_atomic(files: list[Path]) -> dict[str, Any]:
    """生成试点的 atomic evidence 原始记录（证据层来源）。"""
    started = time.perf_counter()
    PILOT_ATOMIC.parent.mkdir(parents=True, exist_ok=True)
    statuses: Counter = Counter()
    records = 0
    errors: list[dict[str, Any]] = []
    granularities: Counter = Counter()
    with PILOT_ATOMIC.open("w", encoding="utf-8", newline="\n") as output:
        for index, path in enumerate(files, start=1):
            if path.suffix.casefold() not in ATOMIC_EXTENSIONS:
                continue
            try:
                result = build_atomic_evidence(path, SOURCE_ROOT)
                statuses[result["status"]] += 1
                if result.get("error"):
                    errors.append({"path": result["path"], "error": result["error"]})
                for record in result.get("records", []):
                    output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                    records += 1
                    granularities[record["granularity"]] += 1
            except Exception as error:  # noqa: BLE001
                statuses["EXCEPTION"] += 1
                errors.append({"path": str(path), "error": f"{type(error).__name__}: {error}"})
            if index % 100 == 0:
                print(f"[atomic] {index}/{len(files)} records={records}", flush=True)
    report = {
        "stage": "atomic",
        "files": len(files),
        "atomic_records": records,
        "status_counts": dict(statuses),
        "granularity_counts": dict(granularities),
        "errors": errors[:50],
        "error_count": len(errors),
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }
    (AUDIT_DIR / "stage_atomic.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# ============================= Stage: v2 =====================================
def _document_char_count(document: dict[str, Any]) -> int:
    """v2 文档对象以 `_text` 列表累积正文（见 hierarchical_v1._document_record）。"""
    parts = document.get("_text") or []
    if not parts:
        return len(str(document.get("document_content_text") or ""))
    return sum(len(str(part)) for part in parts)


def stage_v2(files: list[Path], batch_size: int = V2_BATCH) -> dict[str, Any]:
    """生成试点的 Document -> Section -> Table 结构 bundle，并富化 atomic 证据。

    分批构建的原因：一次性 build 2964 个文件会产生约 340 万个段落对象，
    在 32GB 机器上与 ComfyUI 等进程并存时实测 MemoryError。
    `_attach_parent_links` 按 document_id 分组，故分批与一次性构建语义等价。
    """
    import gc

    from app.document_intelligence.v2 import DocumentIntelligenceV2Builder, document_id as v2_document_id
    from scripts.build_document_intelligence_v2 import _write_enriched_atomic

    started = time.perf_counter()
    if PILOT_V2_DIR.exists():
        shutil.rmtree(PILOT_V2_DIR)
    PILOT_V2_DIR.mkdir(parents=True, exist_ok=True)

    builder = DocumentIntelligenceV2Builder(SOURCE_ROOT)
    handles = {key: (PILOT_V2_DIR / f"{key}.jsonl").open("w", encoding="utf-8", newline="\n") for key in V2_KEYS}
    atomic_out = (PILOT_V2_DIR / "atomic_evidence.jsonl").open("w", encoding="utf-8", newline="\n")
    legacy_out = (PILOT_V2_DIR / "legacy_evidence_id_map.jsonl").open("w", encoding="utf-8", newline="\n")
    tmp_atomic = PILOT_DIR / "_atomic_batch.jsonl"
    tmp_out = PILOT_DIR / "_atomic_out.jsonl"
    tmp_legacy = PILOT_DIR / "_atomic_legacy.jsonl"

    totals = {key: 0 for key in V2_KEYS}
    atomic_count = atomic_mapped = atomic_located = 0
    doc_chars: list[int] = []
    root_counter: Counter = Counter()
    print(f"[v2] building bundle for {len(files)} files, batch={batch_size} ...", flush=True)
    try:
        for start in range(0, len(files), batch_size):
            batch = files[start : start + batch_size]
            bundle = builder.build(batch)
            for key in V2_KEYS:
                rows = bundle[key]
                if rows:
                    handles[key].write("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows))
                totals[key] += len(rows)
            root_counter.update(d.get("knowledge_root_id") for d in bundle["documents"])
            doc_chars.extend(_document_char_count(d) for d in bundle["documents"])

            if PILOT_ATOMIC.is_file():
                wanted = {v2_document_id(p) for p in batch}
                with PILOT_ATOMIC.open(encoding="utf-8") as src, tmp_atomic.open("w", encoding="utf-8", newline="\n") as dst:
                    for line in src:
                        try:
                            if json.loads(line).get("document_id") in wanted:
                                dst.write(line)
                        except json.JSONDecodeError:
                            continue
                metrics = _write_enriched_atomic(tmp_atomic, tmp_out, tmp_legacy, bundle)
                atomic_count += metrics["count"]
                atomic_mapped += metrics.get("mapped", 0)
                atomic_located += metrics.get("located", 0)
                with tmp_out.open(encoding="utf-8") as src:
                    shutil.copyfileobj(src, atomic_out)
                with tmp_legacy.open(encoding="utf-8") as src:
                    shutil.copyfileobj(src, legacy_out)

            del bundle
            gc.collect()
            done = min(start + batch_size, len(files))
            print(f"[v2] {done}/{len(files)} docs={totals['documents']} paragraphs={totals['paragraphs']} atomic={atomic_count}", flush=True)
    finally:
        for handle in handles.values():
            handle.close()
        atomic_out.close()
        legacy_out.close()
        for temp in (tmp_atomic, tmp_out, tmp_legacy):
            if temp.exists():
                temp.unlink()

    # 试点文档不参与既有 Gold 回放，lineage 默认 NOT_APPLICABLE
    _write_jsonl(PILOT_V2_DIR / "compatibility_samples.jsonl", [])
    short_ratio = round(sum(1 for c in doc_chars if c < 500) / max(1, len(doc_chars)), 4)
    report = {
        "stage": "v2",
        "documents": totals["documents"],
        "headings": totals["headings"],
        "sections": totals["sections"],
        "paragraphs": totals["paragraphs"],
        "tables": totals["tables"],
        "atomic_evidence": atomic_count,
        "atomic_mapped": atomic_mapped,
        "atomic_located": atomic_located,
        "short_document_ratio_lt_500": short_ratio,
        "median_document_chars": sorted(doc_chars)[len(doc_chars) // 2] if doc_chars else 0,
        "knowledge_root_ids": dict(root_counter),
        "batch_size": batch_size,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }
    (AUDIT_DIR / "stage_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# ============================ Stage: embed ===================================
def _prepare_expanded_qdrant() -> None:
    """复制现有向量库到 expanded 目录（62MB，一次性），后续只写副本。"""
    if EXPANDED_QDRANT.is_dir():
        print(f"[embed] expanded qdrant already exists: {EXPANDED_QDRANT}", flush=True)
        return
    if not EXISTING_QDRANT.is_dir():
        raise SystemExit(f"ERROR: existing qdrant not found: {EXISTING_QDRANT}")
    print(f"[embed] copying {EXISTING_QDRANT} -> {EXPANDED_QDRANT} ...", flush=True)
    shutil.copytree(EXISTING_QDRANT, EXPANDED_QDRANT)
    print("[embed] copy done", flush=True)


def _load_progress() -> dict[str, Any]:
    if PROGRESS_PATH.is_file():
        try:
            return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"done_files": [], "embedded_chunks": 0, "skipped_empty": 0, "failures": []}


def _save_progress(progress: dict[str, Any]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def stage_embed(files: list[Path], batch_size: int, file_batch: int, limit: int | None, fp16: bool = True) -> dict[str, Any]:
    """流式解析 + BGE-M3 CPU 嵌入，写入 expanded Qdrant。按文件粒度续跑。"""
    _prepare_expanded_qdrant()
    progress = _load_progress()
    done = set(progress["done_files"])
    pending = [f for f in files if str(f) not in done]
    print(f"[embed] total={len(files)} done={len(done)} pending={len(pending)} batch_size={batch_size}", flush=True)

    provider = BGEM3DenseProvider(
        BGE_MODEL_DIR,
        collection_name="pilot_embed_only",
        use_fp16=fp16,
        batch_size=batch_size,
    )
    provider.load()
    print(f"[embed] model loaded (cuda={torch.cuda.is_available()}, fp16={fp16})", flush=True)

    client = QdrantClient(path=str(EXPANDED_QDRANT))
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(size=1_024, distance=models.Distance.COSINE),
        )

    started = time.perf_counter()
    embedded = 0
    skipped_empty = 0
    failures: list[dict[str, Any]] = list(progress.get("failures", []))
    chunks_handle = CHUNKS_PATH.open("a", encoding="utf-8", newline="\n")

    try:
        processed_files = 0
        for start in range(0, len(pending), file_batch):
            group = pending[start : start + file_batch]
            try:
                result = run_document_pipeline(SOURCE_ROOT, files=group)
                documents = result.documents
            except Exception as error:  # noqa: BLE001  # 整批失败时降级为逐文件
                print(f"[embed] batch error, falling back per-file: {error}", flush=True)
                documents = []
                for path in group:
                    try:
                        documents.extend(run_document_pipeline(SOURCE_ROOT, files=[path]).documents)
                    except Exception as single_error:  # noqa: BLE001
                        failures.append({"source_path": str(path), "error": f"{type(single_error).__name__}: {single_error}"})

            chunks = [c for d in documents for c in d.chunks]
            metadata_by_chunk = {cid: m for d in documents for cid, m in d.chunk_metadata.items()}
            pending_chunks = [c for c in chunks if (c.text or "").strip()]
            skipped_empty += len(chunks) - len(pending_chunks)

            for path in group:
                done.add(str(path))
            processed_files += len(group)

            for sub in range(0, len(pending_chunks), batch_size):
                batch = pending_chunks[sub : sub + batch_size]
                try:
                    vectors = provider.embed_documents([c.text for c in batch])
                except Exception as error:  # noqa: BLE001
                    failures.append({"error": f"{type(error).__name__}: {error}", "batch_start": sub})
                    continue
                points = []
                for chunk, vector in zip(batch, vectors, strict=True):
                    metadata = metadata_by_chunk.get(chunk.chunk_id, {})
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
                    for key in ("file_type", "board", "knowledge_type", "discipline", "building_type", "project_stage", "topic", "document_level", "source_organization", "publish_date", "project_name"):
                        payload[key] = metadata.get(key)
                    points.append(models.PointStruct(id=_qdrant_point_id(chunk.chunk_id), vector=vector, payload=payload))
                    chunks_handle.write(json.dumps({"chunk_id": chunk.chunk_id, "source_path": chunk.source_path, "file_name": chunk.file_name, "heading_path": chunk.heading_path, "location": chunk.location, "chars": len(chunk.text or "")}, ensure_ascii=False, default=str) + "\n")
                if points:
                    client.upsert(collection_name=COLLECTION, points=points, wait=True)
                    embedded += len(points)
            chunks_handle.flush()
            if processed_files % (file_batch * 5) == 0 or start + file_batch >= len(pending):
                elapsed = time.perf_counter() - started
                rate = embedded / elapsed if elapsed else 0
                remain = (len(pending) - processed_files) * (elapsed / max(1, processed_files)) / 3600
                print(f"[embed] files={processed_files}/{len(pending)} chunks={embedded} rate={rate:.2f}/s eta_h={remain:.2f}", flush=True)
                progress.update(done_files=sorted(done), embedded_chunks=progress.get("embedded_chunks", 0) + embedded, skipped_empty=skipped_empty, failures=failures[-200:])
                _save_progress(progress)
    finally:
        chunks_handle.close()
        progress.update(done_files=sorted(done), embedded_chunks=progress.get("embedded_chunks", 0) + embedded, skipped_empty=skipped_empty, failures=failures[-200:])
        _save_progress(progress)
        try:
            provider.close()
        except Exception:  # noqa: BLE001
            pass
        client.close()

    elapsed = time.perf_counter() - started
    report = {
        "stage": "embed",
        "files_total": len(files),
        "files_done": len(done),
        "embedded_this_run": embedded,
        "embedded_total": progress.get("embedded_chunks", 0),
        "skipped_empty_chunks": skipped_empty,
        "failure_count": len(failures),
        "failures": failures[:50],
        "elapsed_seconds": round(elapsed, 1),
        "chunks_per_second": round(embedded / elapsed, 3) if elapsed else 0,
    }
    (AUDIT_DIR / "stage_embed.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# ============================ Stage: merge ===================================
def stage_merge() -> dict[str, Any]:
    """合并旧 + 试点的 v2 bundle 到 expanded 目录。"""
    EXPANDED_V2.mkdir(parents=True, exist_ok=True)
    counts: dict[str, dict[str, int]] = {}
    for name in (*V2_KEYS, "atomic_evidence", "legacy_evidence_id_map", "compatibility_samples"):
        old = _read_jsonl(EXISTING_V2 / f"{name}.jsonl")
        new = _read_jsonl(PILOT_V2_DIR / f"{name}.jsonl")
        _write_jsonl(EXPANDED_V2 / f"{name}.jsonl", old + new)
        counts[name] = {"existing": len(old), "pilot": len(new), "merged": len(old) + len(new)}
    # 试点文件的 source_path 不得与既有文档冲突
    old_paths = {str(d.get("source_path", "")).casefold() for d in _read_jsonl(EXISTING_V2 / "documents.jsonl")}
    new_paths = {str(d.get("source_path", "")).casefold() for d in _read_jsonl(PILOT_V2_DIR / "documents.jsonl")}
    overlap = old_paths & new_paths
    report = {"stage": "merge", "counts": counts, "source_path_overlap": len(overlap), "overlap_examples": sorted(overlap)[:10]}
    (AUDIT_DIR / "stage_merge.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# ============================ Stage: index ===================================
def stage_index() -> dict[str, Any]:
    """用合并后的 v2 + expanded 向量库构建扩展层级索引。"""
    from app.retrieval.hierarchical_v1 import build_shadow_index

    started = time.perf_counter()
    build = build_shadow_index(
        v2_dir=EXPANDED_V2,
        output_dir=EXPANDED_INDEX,
        root1_qdrant=EXPANDED_QDRANT,
        root1_collection=COLLECTION,
        root2_qdrant=ROOT2_QDRANT,
        root2_collection=ROOT2_COLLECTION,
    )
    report = {"stage": "index", **{k: v for k, v in build.items() if k != "section_dense_audit"}, "elapsed_seconds": round(time.perf_counter() - started, 1)}
    (AUDIT_DIR / "stage_index.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="分批试点建库：2026 + EPC")
    parser.add_argument("--stage", choices=["atomic", "v2", "embed", "merge", "index", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 个文件（冒烟测试）")
    parser.add_argument("--batch-size", type=int, default=8, help="BGE-M3 嵌入批大小（CPU 内存敏感）")
    parser.add_argument("--file-batch", type=int, default=20, help="每轮解析的文件数")
    parser.add_argument(
        "--fp16",
        dest="fp16",
        action="store_true",
        default=True,
        help="BGE-M3 使用 fp16（默认开启，提速约 3 倍；与既有索引一致，余弦 0.99998+）",
    )
    parser.add_argument("--no-fp16", dest="fp16", action="store_false", help="改用 fp32")
    parser.add_argument("--subs", type=str, default=",".join(SUBS))
    args = parser.parse_args()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    files = collect_files([s.strip() for s in args.subs.split(",") if s.strip()], args.limit)
    print(json.dumps({"stage": args.stage, "files": len(files), "subs": args.subs, "limit": args.limit}, ensure_ascii=False), flush=True)

    results: dict[str, Any] = {}
    stages = ["atomic", "v2", "embed", "merge", "index"] if args.stage == "all" else [args.stage]
    for stage in stages:
        print(f"\n===== STAGE {stage} =====", flush=True)
        if stage == "atomic":
            results[stage] = stage_atomic(files)
        elif stage == "v2":
            results[stage] = stage_v2(files)
        elif stage == "embed":
            results[stage] = stage_embed(files, args.batch_size, args.file_batch, args.limit, args.fp16)
        elif stage == "merge":
            results[stage] = stage_merge()
        elif stage == "index":
            results[stage] = stage_index()
        print(json.dumps(results[stage], ensure_ascii=False, indent=2)[:3000], flush=True)

    (AUDIT_DIR / "build_pilot_summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n===== SUMMARY =====", flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2)[:4000], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
