from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from qdrant_client import QdrantClient

from app.bm25 import BM25Index
from app.config import Settings
from app.domain import Chunk
from app.evaluation.gold_dataset_loader import GoldQuestion, load_gold_questions
from app.retrieval.citation import build_citations, validate_citations
from app.retrieval.context_builder import build_context
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import HybridRetriever, MockDenseProvider, RetrievalResult
from app.retrieval.query_analyzer import analyze_query
from app.retrieval.reranker_provider import BGERerankerProvider


COLLECTION_NAME = "full_corpus_shadow_bge_m3"
SHADOW_DIR = Path("data") / "shadow" / "full_corpus_qdrant"
GOLD_PATH = Path("tests") / "gold_questions" / "full_corpus_gold_questions.yaml"


@dataclass(slots=True)
class ModeMetrics:
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    citation_completeness: float
    failures: list[dict[str, Any]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against the persisted Shadow Qdrant index.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs") / "SHADOW_RETRIEVAL_EVALUATION_REPORT.md",
    )
    args = parser.parse_args()
    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; Shadow Retrieval Evaluation stopped.")
        return 2
    questions = load_gold_questions(args.gold, minimum=100)

    client = QdrantClient(path=str(args.shadow_dir))
    collection_count = client.count(COLLECTION_NAME, exact=True).count
    chunks, metadata_by_chunk = _load_shadow_chunks(client)
    client.close()
    if collection_count != len(chunks):
        raise RuntimeError(
            f"Shadow Collection count mismatch: qdrant={collection_count}, payload={len(chunks)}"
        )

    bm25 = BM25Index(Path("data") / "shadow" / "shadow_eval_bm25.json")
    bm25.build(chunks)

    dense = BGEM3DenseProvider(
        settings.embedding_model,
        collection_name=COLLECTION_NAME,
        use_fp16=True,
        batch_size=16,
    )
    dense.client.close()
    dense.client = QdrantClient(path=str(args.shadow_dir))
    dense.load()
    dense_started = time.perf_counter()
    dense_map: dict[str, list[tuple[str, float]]] = {}
    for index, question in enumerate(questions, start=1):
        dense_map[question.question] = dense.search(question.question, limit=20)
        if index == 1 or index % 10 == 0 or index == len(questions):
            print(f"dense_query_progress={index}/{len(questions)}", flush=True)
    dense_query_elapsed = time.perf_counter() - dense_started

    bm25_results = _run_mode(bm25, chunks, questions, MockDenseProvider())
    hybrid_results = _run_mode(
        bm25, chunks, questions, MockDenseProvider(dense_map)
    )

    reranker = BGERerankerProvider(settings.reranker_model, use_fp16=True)
    rerank_started = time.perf_counter()
    rerank_results = _run_mode(
        bm25,
        chunks,
        questions,
        MockDenseProvider(dense_map),
        reranker=reranker,
    )
    rerank_elapsed = time.perf_counter() - rerank_started
    reranker.close()
    dense.close()

    modes = {
        "BM25-only": _metrics(questions, bm25_results),
        "Hybrid": _metrics(questions, hybrid_results),
        "Hybrid+Reranker": _metrics(questions, rerank_results),
    }
    report = _build_report(
        settings=settings,
        questions=questions,
        chunks=chunks,
        metadata_by_chunk=metadata_by_chunk,
        collection_count=collection_count,
        modes=modes,
        bm25_results=bm25_results,
        hybrid_results=hybrid_results,
        rerank_results=rerank_results,
        dense_query_elapsed=dense_query_elapsed,
        rerank_elapsed=rerank_elapsed,
    )
    report_path = args.report
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def _load_shadow_chunks(
    client: QdrantClient,
) -> tuple[list[Chunk], dict[str, dict[str, Any]]]:
    chunks: list[Chunk] = []
    metadata_by_chunk: dict[str, dict[str, Any]] = {}
    offset: Any = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for ordinal, point in enumerate(points, start=len(chunks)):
            payload = point.payload or {}
            chunk_id = str(payload.get("chunk_id") or point.id)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=str(payload.get("document_id") or ""),
                    ordinal=ordinal,
                    source_path=str(payload.get("source_path") or ""),
                    file_name=str(payload.get("file_name") or ""),
                    text=str(payload.get("text") or ""),
                    heading_path=str(payload.get("heading_path") or ""),
                    location=dict(payload.get("location") or {}),
                )
            )
            metadata_by_chunk[chunk_id] = dict(payload.get("metadata") or {})
        if offset is None:
            break
    return chunks, metadata_by_chunk


def _run_mode(
    bm25: BM25Index,
    chunks: list[Chunk],
    questions: list[GoldQuestion],
    dense: MockDenseProvider,
    *,
    reranker: BGERerankerProvider | None = None,
) -> list[RetrievalResult]:
    retriever = HybridRetriever(bm25, chunks, dense=dense, reranker=reranker)
    return [
        retriever.search(
            question.question,
            bm25_limit=20,
            dense_limit=20,
            rerank_limit=20,
            final_limit=5,
        )
        for question in questions
    ]


def _metrics(
    questions: list[GoldQuestion], results: list[RetrievalResult]
) -> ModeMetrics:
    ranks: list[int | None] = []
    citation_success = 0
    failures: list[dict[str, Any]] = []
    for question, result in zip(questions, results, strict=True):
        relevant_ranks = [
            index
            for index, hit in enumerate(result.hits, start=1)
            if _is_relevant(question, hit.chunk)
        ]
        rank = min(relevant_ranks) if relevant_ranks else None
        ranks.append(rank)
        context = build_context(result.hits)
        citations = build_citations(context)
        valid, errors = validate_citations(citations, context)
        complete = bool(citations) and valid and all(
            citation.get("location") for citation in citations
        )
        citation_success += int(complete)
        if rank is None:
            failures.append(
                {
                    "id": question.id,
                    "question": question.question,
                    "expected_files": question.expected_files,
                    "top_files": [hit.chunk.file_name for hit in result.hits],
                    "top_chunk_ids": [hit.chunk.chunk_id for hit in result.hits],
                    "citation_errors": errors,
                }
            )
    total = len(questions)
    return ModeMetrics(
        recall_at_1=_recall(ranks, 1),
        recall_at_3=_recall(ranks, 3),
        recall_at_5=_recall(ranks, 5),
        mrr=sum(1 / rank if rank else 0 for rank in ranks) / total,
        citation_completeness=citation_success / total,
        failures=failures,
    )


def _is_relevant(question: GoldQuestion, chunk: Chunk) -> bool:
    file_name = chunk.file_name.casefold()
    if question.expected_files and any(
        expected.casefold() == file_name for expected in question.expected_files
    ):
        return True
    searchable = f"{chunk.file_name} {chunk.heading_path} {chunk.text}".casefold()
    topic_hits = sum(topic.casefold() in searchable for topic in question.expected_topics)
    required = max(1, (len(question.expected_topics) + 1) // 2)
    return topic_hits >= required


def _recall(ranks: list[int | None], k: int) -> float:
    return sum(rank is not None and rank <= k for rank in ranks) / len(ranks)


def _rank_for_question(question: GoldQuestion, result: RetrievalResult) -> int | None:
    for rank, hit in enumerate(result.hits, start=1):
        if _is_relevant(question, hit.chunk):
            return rank
    return None


def _movement(
    questions: list[GoldQuestion], before: list[RetrievalResult], after: list[RetrievalResult]
) -> dict[str, int]:
    improved = worsened = unchanged = 0
    for question, before_result, after_result in zip(questions, before, after, strict=True):
        before_rank = _rank_for_question(question, before_result)
        after_rank = _rank_for_question(question, after_result)
        before_value = before_rank or 999
        after_value = after_rank or 999
        if after_value < before_value:
            improved += 1
        elif after_value > before_value:
            worsened += 1
        else:
            unchanged += 1
    return {"improved": improved, "worsened": worsened, "unchanged": unchanged}


def _metadata_analysis(
    questions: list[GoldQuestion],
    chunks: list[Chunk],
    metadata_by_chunk: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    field_counts: Counter[str] = Counter()
    zero_candidate = 0
    small_candidate = 0
    expected_outside = 0
    rows: list[dict[str, Any]] = []
    for question in questions:
        analysis = analyze_query(question.question)
        predicted = {field: candidate.value for field, candidate in analysis.metadata.items()}
        if not predicted:
            continue
        field_counts.update(predicted.keys())
        matches = [
            chunk
            for chunk in chunks
            if all(metadata_by_chunk.get(chunk.chunk_id, {}).get(field) == value for field, value in predicted.items())
        ]
        expected_present = any(
            any(expected.casefold() == chunk.file_name.casefold() for expected in question.expected_files)
            for chunk in matches
        )
        if not matches:
            zero_candidate += 1
        if len(matches) < 5:
            small_candidate += 1
        if question.expected_files and not expected_present:
            expected_outside += 1
        rows.append(
            {
                "id": question.id,
                "predicted": predicted,
                "candidate_chunks": len(matches),
                "expected_file_in_filter": expected_present,
            }
        )
    detected = len(rows)
    return {
        "questions_with_predictions": detected,
        "field_counts": dict(field_counts),
        "zero_candidate_questions": zero_candidate,
        "less_than_five_candidate_questions": small_candidate,
        "expected_file_outside_filter_questions": expected_outside,
        "recommendation": (
            "keep_disabled_or_soft_filter"
            if zero_candidate or expected_outside
            else "candidate_for_soft_filter_validation"
        ),
        "rows": rows,
    }


def _build_report(
    *,
    settings: Settings,
    questions: list[GoldQuestion],
    chunks: list[Chunk],
    metadata_by_chunk: dict[str, dict[str, Any]],
    collection_count: int,
    modes: dict[str, ModeMetrics],
    bm25_results: list[RetrievalResult],
    hybrid_results: list[RetrievalResult],
    rerank_results: list[RetrievalResult],
    dense_query_elapsed: float,
    rerank_elapsed: float,
) -> dict[str, Any]:
    expected_present = sum(
        bool(question.expected_files)
        and any(
            expected.casefold() == chunk.file_name.casefold()
            for expected in question.expected_files
            for chunk in chunks
        )
        for question in questions
    )
    summary = {
        "gold_questions": len(questions),
        "shadow_collection_points": collection_count,
        "shadow_chunks_loaded": len(chunks),
        "expected_file_present_questions": expected_present,
        "bm25_only": _metric_dict(modes["BM25-only"]),
        "hybrid": _metric_dict(modes["Hybrid"]),
        "hybrid_reranker": _metric_dict(modes["Hybrid+Reranker"]),
        "hybrid_movement": _movement(questions, bm25_results, hybrid_results),
        "reranker_movement": _movement(questions, hybrid_results, rerank_results),
        "dense_query_elapsed_seconds": round(dense_query_elapsed, 3),
        "reranker_elapsed_seconds": round(rerank_elapsed, 3),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0),
        "metadata_filter": _metadata_analysis(questions, chunks, metadata_by_chunk),
        "model_path": settings.embedding_model,
        "reranker_path": settings.reranker_model,
    }
    return {"summary": summary, "modes": modes}


def _metric_dict(metrics: ModeMetrics) -> dict[str, Any]:
    return {
        "recall_at_1": metrics.recall_at_1,
        "recall_at_3": metrics.recall_at_3,
        "recall_at_5": metrics.recall_at_5,
        "mrr": metrics.mrr,
        "citation_completeness": metrics.citation_completeness,
        "failure_count": len(metrics.failures),
    }


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = [
        "# Shadow Retrieval Evaluation Report",
        "",
        "> 本报告读取持久化 `full_corpus_shadow_bge_m3`，仅评估 Shadow BM25、Hybrid 和 Hybrid+Reranker。",
        "> 未替换正式 Retriever，未写入正式 Qdrant，未修改 8000 端口服务。",
        "",
        "## 1. 评估范围",
        "",
        f"- Gold Questions：`{summary['gold_questions']}` 题，来源 `tests/gold_questions/full_corpus_gold_questions.yaml`。",
        f"- Shadow Collection 点数：`{summary['shadow_collection_points']}`。",
        f"- 读取 Chunk：`{summary['shadow_chunks_loaded']}`。",
        f"- expected_files 在 Shadow 中可定位的问题：`{summary['expected_file_present_questions']}/{summary['gold_questions']}`。",
        f"- GPU：`{summary['gpu_name']}`，CUDA 可用：`{summary['cuda_available']}`。",
        f"- BGE-M3 查询向量耗时：`{summary['dense_query_elapsed_seconds']}` 秒。",
        f"- Reranker 评估耗时：`{summary['reranker_elapsed_seconds']}` 秒。",
        "",
        "## 2. 核心指标",
        "",
        "| 模式 | Recall@1 | Recall@3 | Recall@5 | MRR | Citation完整率 | 未命中题数 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, key in (
        ("BM25-only", "bm25_only"),
        ("Hybrid", "hybrid"),
        ("Hybrid+Reranker", "hybrid_reranker"),
    ):
        metric = summary[key]
        rows.append(
            f"| {name} | {metric['recall_at_1']:.2%} | {metric['recall_at_3']:.2%} | "
            f"{metric['recall_at_5']:.2%} | {metric['mrr']:.3f} | "
            f"{metric['citation_completeness']:.2%} | {metric['failure_count']} |"
        )
    rows.extend(
        [
            "",
            "## 3. 增益分析",
            "",
            "| 对比 | 提升题数 | 下降题数 | 不变题数 |",
            "|---|---:|---:|---:|",
            f"| Hybrid 相比 BM25-only | {summary['hybrid_movement']['improved']} | {summary['hybrid_movement']['worsened']} | {summary['hybrid_movement']['unchanged']} |",
            f"| Hybrid+Reranker 相比 Hybrid | {summary['reranker_movement']['improved']} | {summary['reranker_movement']['worsened']} | {summary['reranker_movement']['unchanged']} |",
            "",
            "解释口径：提升/下降按每题 Top-5 中首个相关 Chunk 的排名计算；从未命中到命中视为提升，命中到未命中视为下降。",
            "",
            "## 4. Metadata Filter 分析",
            "",
        ]
    )
    metadata = summary["metadata_filter"]
    rows.extend(
        [
            f"- Query Analyzer 识别出 Metadata 的问题：`{metadata['questions_with_predictions']}`。",
            f"- 各字段识别次数：`{json.dumps(metadata['field_counts'], ensure_ascii=False)}`。",
            f"- 严格过滤后候选为 0 的问题：`{metadata['zero_candidate_questions']}`。",
            f"- 严格过滤后候选少于 5 个的问题：`{metadata['less_than_five_candidate_questions']}`。",
            f"- expected_files 会被严格过滤排除的问题：`{metadata['expected_file_outside_filter_questions']}`。",
            f"- 建议：`{metadata['recommendation']}`。",
            "",
            "当前结论：Metadata Filter 不应直接作为硬过滤上线；应先采用软过滤或候选排序加权，并保留无过滤回退。",
            "",
            "## 5. 失败问题",
            "",
            "| 模式 | 失败题数 | 失败题 ID |",
            "|---|---:|---|",
        ]
    )
    for name, key in (
        ("BM25-only", "BM25-only"),
        ("Hybrid", "Hybrid"),
        ("Hybrid+Reranker", "Hybrid+Reranker"),
    ):
        failures = report["modes"][key].failures
        rows.append(
            f"| {name} | {len(failures)} | {', '.join(item['id'] for item in failures) or '无'} |"
        )
    rows.extend(["", "### 失败题 Top-5 证据（最多展示每种模式前 20 题）", ""])
    for name, key in (
        ("BM25-only", "BM25-only"),
        ("Hybrid", "Hybrid"),
        ("Hybrid+Reranker", "Hybrid+Reranker"),
    ):
        rows.extend(
            [
                f"#### {name}",
                "",
                "| ID | 问题 | expected_files | Top-5 文件 |",
                "|---|---|---|---|",
            ]
        )
        failures = report["modes"][key].failures
        for item in failures[:20]:
            question = item["question"].replace("|", "\\|")
            expected = ", ".join(item["expected_files"]).replace("|", "\\|")
            top_files = ", ".join(item["top_files"]).replace("|", "\\|")
            rows.append(f"| {item['id']} | {question} | {expected} | {top_files} |")
        if not failures:
            rows.append("| 无 | - | - | - |")
        rows.append("")
    rows.extend(
        [
            "## 6. Answer Engine 优化方向",
            "",
            "1. 对 Hybrid 仍失败的问题，优先检查 Query Analysis、中文分词、同义词扩展和 Chunk 粒度。",
            "2. 对 Reranker 下降的问题，增加 reranker 前后 rank 对账和低置信度回退，不应无条件覆盖 RRF 排名。",
            "3. Citation 完整率若高于答案正确率，说明当前主要瓶颈在证据选择或生成链路，而不是引用结构。",
            "4. Answer Engine 应先基于 Top-K 证据生成可核查结论；证据不足时明确返回不足，不用生成模型补齐事实。",
            "5. 本 Gold 集仍标记为候选集，正式质量结论前需由内容负责人逐题复核 expected_files 和 expected_topics。",
            "",
            "## 7. 边界说明",
            "",
            "- 本次没有执行最终 Answer Evaluation 或 LLM-as-Judge。",
            "- 本次没有启用 Metadata 硬过滤，也没有改动正式 Retriever。",
            "- 模型路径：",
            f"  - BGE-M3：`{summary['model_path']}`",
            f"  - Reranker：`{summary['reranker_path']}`",
            "",
        ]
    )
    return "\n".join(rows)


if __name__ == "__main__":
    raise SystemExit(main())
