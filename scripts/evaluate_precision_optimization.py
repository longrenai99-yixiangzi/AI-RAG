from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from qdrant_client import QdrantClient

from app.bm25 import BM25Index
from app.config import Settings
from app.evaluation.gold_dataset_loader import GoldQuestion, load_gold_questions
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import HybridRetriever, MockDenseProvider, RetrievalResult
from app.retrieval.reranker_provider import BGERerankerProvider
from app.retrieval.shadow_precision import (
    FUSION_WEIGHTS,
    OptimizedRanking,
    PrecisionIntent,
    analyze_precision_intent,
    optimize_ranking,
)
from scripts.evaluate_shadow_retrieval import (
    COLLECTION_NAME,
    GOLD_PATH,
    SHADOW_DIR,
    _is_relevant,
    _load_shadow_chunks,
    _metrics,
    _rank_for_question,
)

FUSION_PROFILES = {
    "conservative": {"rrf": 0.10, "reranker": 0.82, "metadata": 0.03, "document_type": 0.05},
    "metadata_light": {"rrf": 0.15, "reranker": 0.80, "metadata": 0.03, "document_type": 0.02},
    "document_type_light": {"rrf": 0.10, "reranker": 0.85, "metadata": 0.02, "document_type": 0.03},
    "rrf_balanced": {"rrf": 0.25, "reranker": 0.70, "metadata": 0.03, "document_type": 0.02},
    "baseline_like": {"rrf": 0.02, "reranker": 0.95, "metadata": 0.02, "document_type": 0.01},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Shadow Retrieval precision optimization.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    args = parser.parse_args()
    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; precision optimization stopped.")
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

    bm25 = BM25Index(Path("data") / "shadow" / "precision_eval_bm25.json")
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
    dense_map: dict[str, list[tuple[str, float]]] = {}
    query_started = time.perf_counter()
    for index, question in enumerate(questions, start=1):
        dense_map[question.question] = dense.search(question.question, limit=20)
        if index == 1 or index % 10 == 0 or index == len(questions):
            print(f"dense_query_progress={index}/{len(questions)}", flush=True)
    query_elapsed = time.perf_counter() - query_started

    bm25_candidates = _run_candidates(bm25, chunks, questions, MockDenseProvider())
    hybrid_candidates = _run_candidates(bm25, chunks, questions, MockDenseProvider(dense_map))
    reranker = BGERerankerProvider(settings.reranker_model, use_fp16=True)
    rerank_started = time.perf_counter()
    reranker_candidates = _run_candidates(
        bm25,
        chunks,
        questions,
        MockDenseProvider(dense_map),
        reranker=reranker,
    )
    rerank_elapsed = time.perf_counter() - rerank_started
    reranker.close()
    dense.close()

    baseline_results = {
        "BM25-only": _top_results(bm25_candidates),
        "Hybrid": _top_results(hybrid_candidates),
        "Hybrid+Reranker": _top_results(reranker_candidates),
    }
    intents = [analyze_precision_intent(question.question) for question in questions]
    baseline_reranker_metrics = _metrics(questions, baseline_results["Hybrid+Reranker"])
    profile_rankings: dict[str, list[OptimizedRanking]] = {}
    profile_results: dict[str, list[RetrievalResult]] = {}
    profile_metrics: dict[str, Any] = {}
    for profile_name, weights in FUSION_PROFILES.items():
        rankings = [
            optimize_ranking(
                candidates[:5],
                metadata_by_chunk,
                intent,
                final_limit=5,
                weights=weights,
            )
            for candidates, intent in zip(reranker_candidates, intents, strict=True)
        ]
        results = [
            RetrievalResult(
                analysis=baseline_results["Hybrid+Reranker"][index].analysis,
                hits=ranking.hits,
                debug={"precision_optimized": True, "profile": profile_name},
            )
            for index, ranking in enumerate(rankings)
        ]
        profile_rankings[profile_name] = rankings
        profile_results[profile_name] = results
        profile_metrics[profile_name] = _metrics(questions, results)

    eligible = [
        name
        for name, metrics in profile_metrics.items()
        if metrics.recall_at_1 >= baseline_reranker_metrics.recall_at_1
        and metrics.recall_at_3 >= baseline_reranker_metrics.recall_at_3
        and metrics.recall_at_5 >= baseline_reranker_metrics.recall_at_5
        and metrics.mrr >= baseline_reranker_metrics.mrr
        and (
            metrics.recall_at_1 > baseline_reranker_metrics.recall_at_1
            or metrics.recall_at_3 > baseline_reranker_metrics.recall_at_3
            or metrics.recall_at_5 > baseline_reranker_metrics.recall_at_5
            or metrics.mrr > baseline_reranker_metrics.mrr
        )
    ]
    if eligible:
        selected_profile = max(
            eligible,
            key=lambda name: (
                profile_metrics[name].recall_at_5,
                profile_metrics[name].recall_at_3,
                profile_metrics[name].recall_at_1,
                profile_metrics[name].mrr,
            ),
        )
        optimized_results = profile_results[selected_profile]
        optimized_rankings = profile_rankings[selected_profile]
    else:
        selected_profile = "baseline_fallback"
        optimized_results = baseline_results["Hybrid+Reranker"]
        optimized_rankings = []
    report = _build_report(
        settings=settings,
        questions=questions,
        chunks=chunks,
        collection_count=collection_count,
        baseline_results=baseline_results,
        optimized_results=optimized_results,
        optimized_rankings=optimized_rankings,
        intents=intents,
        selected_profile=selected_profile,
        profile_metrics=profile_metrics,
        query_elapsed=query_elapsed,
        rerank_elapsed=rerank_elapsed,
    )
    report_path = Path("docs") / "RETRIEVAL_PRECISION_OPTIMIZATION_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def _run_candidates(
    bm25: BM25Index,
    chunks: list[Any],
    questions: list[GoldQuestion],
    dense: MockDenseProvider,
    *,
    reranker: BGERerankerProvider | None = None,
) -> list[list[Any]]:
    retriever = HybridRetriever(bm25, chunks, dense=dense, reranker=reranker)
    results = []
    for question in questions:
        result = retriever.search(
            question.question,
            bm25_limit=20,
            dense_limit=20,
            rerank_limit=20,
            final_limit=20,
        )
        results.append(result.hits)
    return results


def _top_results(candidates: list[list[Any]]) -> list[RetrievalResult]:
    return [
        RetrievalResult(analysis=None, hits=hits[:5], debug={})  # type: ignore[arg-type]
        for hits in candidates
    ]


def _build_report(
    *,
    settings: Settings,
    questions: list[GoldQuestion],
    chunks: list[Any],
    collection_count: int,
    baseline_results: dict[str, list[RetrievalResult]],
    optimized_results: list[RetrievalResult],
    optimized_rankings: list[OptimizedRanking],
    intents: list[PrecisionIntent],
    selected_profile: str,
    profile_metrics: dict[str, Any],
    query_elapsed: float,
    rerank_elapsed: float,
) -> dict[str, Any]:
    baseline_metrics = {
        name: _metrics(questions, results)
        for name, results in baseline_results.items()
    }
    optimized_metrics = _metrics(questions, optimized_results)
    baseline_reranker = baseline_results["Hybrid+Reranker"]
    movement = _movement(questions, baseline_reranker, optimized_results)
    intent_counts = Counter(intent.question_type for intent in intents)
    knowledge_counts = Counter(
        intent.knowledge_type for intent in intents if intent.knowledge_type
    )
    component_counts = Counter()
    for ranking in optimized_rankings:
        for component in ranking.component_by_chunk.values():
            if component["metadata"] > 0:
                component_counts["metadata_boosted_candidates"] += 1
            if component["document_type"] > 0:
                component_counts["document_type_positive_candidates"] += 1
            if component["document_type"] < 0:
                component_counts["document_type_negative_candidates"] += 1
    summary = {
        "gold_questions": len(questions),
        "shadow_collection_points": collection_count,
        "shadow_chunks": len(chunks),
        "intent_counts": dict(intent_counts),
        "knowledge_type_counts": dict(knowledge_counts),
        "bm25_only": _metric_dict(baseline_metrics["BM25-only"]),
        "hybrid": _metric_dict(baseline_metrics["Hybrid"]),
        "hybrid_reranker": _metric_dict(baseline_metrics["Hybrid+Reranker"]),
        "optimized": _metric_dict(optimized_metrics),
        "optimized_vs_baseline_reranker": movement,
        "selected_profile": selected_profile,
        "profile_metrics": {
            name: _metric_dict(metrics) for name, metrics in profile_metrics.items()
        },
        "component_counts": dict(component_counts),
        "query_elapsed_seconds": round(query_elapsed, 3),
        "reranker_elapsed_seconds": round(rerank_elapsed, 3),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0),
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "fusion_weights": dict(FUSION_PROFILES.get(selected_profile, FUSION_WEIGHTS)),
    }
    return {
        "summary": summary,
        "baseline_metrics": baseline_metrics,
        "optimized_metrics": optimized_metrics,
    }


def _metric_dict(metrics: Any) -> dict[str, Any]:
    return {
        "recall_at_1": metrics.recall_at_1,
        "recall_at_3": metrics.recall_at_3,
        "recall_at_5": metrics.recall_at_5,
        "mrr": metrics.mrr,
        "citation_completeness": metrics.citation_completeness,
        "failure_count": len(metrics.failures),
    }


def _movement(
    questions: list[GoldQuestion],
    before: list[RetrievalResult],
    after: list[RetrievalResult],
) -> dict[str, Any]:
    improved = worsened = unchanged = 0
    changed: list[dict[str, Any]] = []
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
        if before_value != after_value:
            changed.append(
                {
                    "id": question.id,
                    "before_rank": before_rank,
                    "after_rank": after_rank,
                    "before_files": [hit.chunk.file_name for hit in before_result.hits],
                    "after_files": [hit.chunk.file_name for hit in after_result.hits],
                }
            )
    return {
        "improved": improved,
        "worsened": worsened,
        "unchanged": unchanged,
        "changed": changed,
    }


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = [
        "# Retrieval Precision Optimization Report",
        "",
        "> 本报告在 `full_corpus_shadow_bge_m3` 上比较 TASK-012.9 基线与 Shadow 精度优化结果。",
        "> 优化仅作用于 Shadow 排序：不硬过滤 Metadata，不修改正式 Retriever、8000 服务或正式 Qdrant。",
        "",
        "## 1. 优化内容",
        "",
        "1. Query Intent：基于关键词、短语和问句结构增强识别 `POLICY_QUERY`、`CASE_QUERY`、`METHOD_QUERY`、`TEMPLATE_QUERY`、`DISCIPLINE_QUERY`，并生成 knowledge_type 倾向。",
        "2. Soft Metadata Boost：对 board、knowledge_type、discipline 命中候选加权，不匹配不淘汰，保留全库候选。",
        "3. Document Type Ranking：制度/规范类问题提高制度、指南、流程、标准类文件，降低项目总结 PPT、个人述职和培训材料。",
        "4. Reranker Fusion：对基线 Reranker Top-5 内的 RRF 与 Reranker 分数分别归一化，再与 Metadata Boost、Document Type Boost 融合，不直接覆盖 RRF 排名，也不让新候选挤出基线 Top-5。",
        "",
        (
            "融合排序未被采纳：所有候选权重配置均未达到‘四项指标均不下降且至少一项提升’的门槛。"
            if summary["selected_profile"] == "baseline_fallback"
            else f"融合公式：`{summary['fusion_weights']['rrf']:.2f} × RRF_norm + {summary['fusion_weights']['reranker']:.2f} × Reranker_norm + {summary['fusion_weights']['metadata']:.2f} × MetadataBoost + {summary['fusion_weights']['document_type']:.2f} × DocumentTypeBoost`。"
        ),
        "",
        "## 2. 评估范围",
        "",
        f"- Gold Questions：`{summary['gold_questions']}`。",
        f"- Shadow Collection：`{summary['shadow_collection_points']}` 点。",
        f"- Shadow Chunk：`{summary['shadow_chunks']}`。",
        f"- GPU：`{summary['gpu_name']}`，CUDA：`{summary['cuda_available']}`。",
        f"- 100 题查询向量耗时：`{summary['query_elapsed_seconds']}` 秒。",
        f"- Reranker 耗时：`{summary['reranker_elapsed_seconds']}` 秒。",
        "",
        "## 3. 指标对比",
        "",
        "| 模式 | Recall@1 | Recall@3 | Recall@5 | MRR | Citation完整率 | 未命中题数 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, key in (
        ("TASK-012.9 BM25-only", "bm25_only"),
        ("TASK-012.9 Hybrid", "hybrid"),
        ("TASK-012.9 Hybrid+Reranker", "hybrid_reranker"),
        ("TASK-012.10 Optimized Hybrid+Reranker", "optimized"),
    ):
        metric = summary[key]
        rows.append(
            f"| {name} | {metric['recall_at_1']:.2%} | {metric['recall_at_3']:.2%} | "
            f"{metric['recall_at_5']:.2%} | {metric['mrr']:.3f} | "
            f"{metric['citation_completeness']:.2%} | {metric['failure_count']} |"
        )
    movement = summary["optimized_vs_baseline_reranker"]
    rows.extend(
        [
            "",
            "## 4. 优化前后变化",
            "",
            f"- 选择配置：`{summary['selected_profile']}`。",
            f"- 优化后相比 TASK-012.9 Hybrid+Reranker：提升 `{movement['improved']}` 题，下降 `{movement['worsened']}` 题，不变 `{movement['unchanged']}` 题。",
            f"- Intent 分布：`{json.dumps(summary['intent_counts'], ensure_ascii=False)}`。",
            f"- knowledge_type 倾向：`{json.dumps(summary['knowledge_type_counts'], ensure_ascii=False)}`。",
            f"- 产生 Metadata 正向加分的候选数：`{summary['component_counts'].get('metadata_boosted_candidates', 0)}`。",
            f"- 产生 Document Type 正向加分的候选数：`{summary['component_counts'].get('document_type_positive_candidates', 0)}`。",
            f"- 产生 Document Type 负向降权的候选数：`{summary['component_counts'].get('document_type_negative_candidates', 0)}`。",
            "",
            "### 候选权重配置结果",
            "",
            "| 配置 | Recall@1 | Recall@3 | Recall@5 | MRR |",
            "|---|---:|---:|---:|---:|",
            "",
        ]
    )
    for name, metric in summary["profile_metrics"].items():
        rows.append(
            f"| {name} | {metric['recall_at_1']:.2%} | {metric['recall_at_3']:.2%} | "
            f"{metric['recall_at_5']:.2%} | {metric['mrr']:.3f} |"
        )
    rows.append("")
    rows.extend(["## 5. 仍然失败的问题", ""])
    baseline_failures = report["baseline_metrics"]["Hybrid+Reranker"].failures
    optimized_failures = report["optimized_metrics"].failures
    rows.extend(
        [
            f"- TASK-012.9 Hybrid+Reranker 未命中：`{len(baseline_failures)}` 题。",
            f"- TASK-012.10 优化后未命中：`{len(optimized_failures)}` 题。",
            f"- 优化后失败题 ID：{', '.join(item['id'] for item in optimized_failures) or '无'}",
            "",
            "### 优化后失败题 Top-5",
            "",
            "| ID | 问题 | expected_files | Top-5 文件 |",
            "|---|---|---|---|",
        ]
    )
    for item in optimized_failures[:30]:
        question = item["question"].replace("|", "\\|")
        expected = ", ".join(item["expected_files"]).replace("|", "\\|")
        top_files = ", ".join(item["top_files"]).replace("|", "\\|")
        rows.append(f"| {item['id']} | {question} | {expected} | {top_files} |")
    if not optimized_failures:
        rows.append("| 无 | - | - | - |")
    rows.extend(
        [
            "",
            "## 6. 结论与下一阶段建议",
            "",
            (
                "1. 本次候选权重配置均未通过无回退指标门槛，优化排序未采纳，继续使用 TASK-012.9 基线。"
                if summary["selected_profile"] == "baseline_fallback"
                else "1. 优化后的融合排序可作为 Shadow Retrieval 下一版候选，但必须继续保留无 Metadata 加权的回退路径。"
            ),
            "2. 若 Recall@5 提升主要来自 Document Type Ranking，应继续补充真实制度、规范、流程文件的 Gold 标注，避免规则过拟合。",
            "3. Reranker 仍应作为融合信号，而不是绝对覆盖 RRF；对下降题保留 RRF 原顺序作为低置信度回退。",
            "4. Answer Engine 下一步应围绕失败题做证据充分性判断、答案拒答边界和 Citation 对齐，不应先接入 LLM-as-Judge。",
            "5. 当前 Gold 集的 expected_files 仍需内容负责人最终复核，本文指标属于 Shadow 评估结果，不代表正式上线承诺。",
            "",
            "## 7. 边界说明",
            "",
            "- 未修改正式 `app/retriever.py`、`app/main.py`。",
            "- 未写入正式 `data\\qdrant`，未影响 8000 端口。",
            f"- BGE-M3：`{summary['embedding_model']}`。",
            f"- Reranker：`{summary['reranker_model']}`。",
            "",
        ]
    )
    return "\n".join(rows)


if __name__ == "__main__":
    raise SystemExit(main())
