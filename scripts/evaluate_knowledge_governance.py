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
from app.ingestion.metadata.governance import GovernanceClassifier, GovernanceMetadata
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import MockDenseProvider, RetrievalResult
from app.retrieval.reranker_provider import BGERerankerProvider
from app.retrieval.shadow_precision import PrecisionIntent, analyze_precision_intent, optimize_ranking
from scripts.evaluate_precision_optimization import _run_candidates
from scripts.evaluate_shadow_retrieval import (
    COLLECTION_NAME,
    GOLD_PATH,
    SHADOW_DIR,
    _load_shadow_chunks,
    _metrics,
)


PRECISION_BASELINE_WEIGHTS = {
    "rrf": 0.15,
    "reranker": 0.80,
    "metadata": 0.03,
    "document_type": 0.02,
    "governance": 0.0,
}

GOVERNANCE_PROFILES = {
    "governance_light": {
        "rrf": 0.15,
        "reranker": 0.75,
        "metadata": 0.03,
        "document_type": 0.02,
        "governance": 0.05,
    },
    "governance_safe": {
        "rrf": 0.10,
        "reranker": 0.83,
        "metadata": 0.02,
        "document_type": 0.02,
        "governance": 0.03,
    },
    "governance_balanced": {
        "rrf": 0.20,
        "reranker": 0.70,
        "metadata": 0.03,
        "document_type": 0.02,
        "governance": 0.05,
    },
    "role_priority_focus": {
        "rrf": 0.15,
        "reranker": 0.68,
        "metadata": 0.03,
        "document_type": 0.02,
        "governance": 0.12,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Shadow knowledge governance ranking.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    args = parser.parse_args()
    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; governance evaluation stopped.")
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

    governance_classifier = GovernanceClassifier()
    governance_by_chunk = {
        chunk.chunk_id: governance_classifier.classify(
            file_name=chunk.file_name,
            source_path=chunk.source_path,
            heading_path=chunk.heading_path,
            text=chunk.text,
            metadata=metadata_by_chunk.get(chunk.chunk_id, {}),
        )
        for chunk in chunks
    }
    bm25 = BM25Index(Path("data") / "shadow" / "governance_eval_bm25.json")
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

    intents = [analyze_precision_intent(question.question) for question in questions]
    precision_baseline = _build_ranked_results(
        questions,
        reranker_candidates,
        metadata_by_chunk,
        intents,
        PRECISION_BASELINE_WEIGHTS,
    )
    baseline_metrics = _metrics(questions, precision_baseline)

    profile_results: dict[str, list[RetrievalResult]] = {}
    profile_metrics: dict[str, Any] = {}
    profile_governance_metrics: dict[str, dict[str, float]] = {}
    for name, weights in GOVERNANCE_PROFILES.items():
        results = _build_ranked_results(
            questions,
            reranker_candidates,
            metadata_by_chunk,
            intents,
            weights,
            governance_by_chunk=governance_by_chunk,
        )
        profile_results[name] = results
        profile_metrics[name] = _metrics(questions, results)
        profile_governance_metrics[name] = _governance_metrics(
            questions, results, intents, governance_by_chunk
        )

    baseline_governance = _governance_metrics(
        questions, precision_baseline, intents, governance_by_chunk
    )
    eligible = [
        name
        for name, metrics in profile_metrics.items()
        if _retrieval_not_lower(metrics, baseline_metrics)
        and _governance_not_lower(profile_governance_metrics[name], baseline_governance)
        and _has_governance_gain(profile_governance_metrics[name], baseline_governance)
    ]
    if eligible:
        selected_profile = max(
            eligible,
            key=lambda name: (
                profile_governance_metrics[name]["role_top1"] ,
                profile_governance_metrics[name]["role_top5"],
                profile_metrics[name].recall_at_5,
                profile_metrics[name].mrr,
            ),
        )
        optimized_results = profile_results[selected_profile]
    else:
        selected_profile = "precision_baseline_fallback"
        optimized_results = precision_baseline

    optimized_metrics = _metrics(questions, optimized_results)
    optimized_governance = _governance_metrics(
        questions, optimized_results, intents, governance_by_chunk
    )
    report = _build_report(
        settings=settings,
        questions=questions,
        chunks=chunks,
        collection_count=collection_count,
        governance_by_chunk=governance_by_chunk,
        baseline_metrics=baseline_metrics,
        baseline_governance=baseline_governance,
        optimized_metrics=optimized_metrics,
        optimized_governance=optimized_governance,
        profile_metrics=profile_metrics,
        profile_governance_metrics=profile_governance_metrics,
        selected_profile=selected_profile,
        optimized_results=optimized_results,
        query_elapsed=query_elapsed,
        rerank_elapsed=rerank_elapsed,
    )
    report_path = Path("docs") / "KNOWLEDGE_GOVERNANCE_OPTIMIZATION_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def _build_ranked_results(
    questions: list[GoldQuestion],
    candidates: list[list[Any]],
    metadata_by_chunk: dict[str, dict[str, Any]],
    intents: list[PrecisionIntent],
    weights: dict[str, float],
    *,
    governance_by_chunk: dict[str, GovernanceMetadata] | None = None,
) -> list[RetrievalResult]:
    results: list[RetrievalResult] = []
    for index, (question, intent) in enumerate(zip(questions, intents, strict=True)):
        ranking = optimize_ranking(
            candidates[index][:5],
            metadata_by_chunk,
            intent,
            final_limit=5,
            weights=weights,
            governance_by_chunk=governance_by_chunk,
        )
        results.append(
            RetrievalResult(
                analysis=None,  # type: ignore[arg-type]
                hits=ranking.hits,
                debug={"governance_profile": weights.get("governance", 0.0)},
            )
        )
    return results


def _retrieval_not_lower(candidate: Any, baseline: Any) -> bool:
    return (
        candidate.recall_at_1 >= baseline.recall_at_1
        and candidate.recall_at_3 >= baseline.recall_at_3
        and candidate.recall_at_5 >= baseline.recall_at_5
        and candidate.mrr >= baseline.mrr
    )


def _governance_not_lower(candidate: dict[str, float], baseline: dict[str, float]) -> bool:
    return all(candidate[key] >= baseline[key] for key in ("role_top1", "role_top5", "authority_top1", "scene_top1"))


def _has_governance_gain(candidate: dict[str, float], baseline: dict[str, float]) -> bool:
    return any(candidate[key] > baseline[key] for key in ("role_top1", "role_top5", "authority_top1", "scene_top1"))


def _governance_metrics(
    questions: list[GoldQuestion],
    results: list[RetrievalResult],
    intents: list[PrecisionIntent],
    governance_by_chunk: dict[str, GovernanceMetadata],
) -> dict[str, float]:
    role_top1 = role_top5 = authority_top1 = scene_top1 = 0
    policy_priority = policy_total = case_role = case_total = template_role = template_total = 0
    for question, result, intent in zip(questions, results, intents, strict=True):
        if not result.hits:
            continue
        top_roles = [governance_by_chunk[hit.chunk.chunk_id].document_role for hit in result.hits]
        top = governance_by_chunk[result.hits[0].chunk.chunk_id]
        role_top1 += int(bool(question.expected_document_role) and top.document_role == question.expected_document_role)
        role_top5 += int(bool(question.expected_document_role) and question.expected_document_role in top_roles)
        authority_top1 += int(bool(question.expected_authority_level) and top.authority_level == question.expected_authority_level)
        scene_top1 += int(bool(question.expected_usage_scene) and top.usage_scene == question.expected_usage_scene)
        if intent.question_type == "POLICY_QUERY":
            policy_total += 1
            policy_priority += int(top.document_role in {"正式制度", "管理指南"})
        if intent.question_type == "CASE_QUERY":
            case_total += 1
            case_role += int(top.document_role == "项目案例")
        if intent.question_type == "TEMPLATE_QUERY":
            template_total += 1
            template_role += int(top.document_role == "标准模板")
    total = len(questions)
    return {
        "role_top1": role_top1 / total,
        "role_top5": role_top5 / total,
        "authority_top1": authority_top1 / total,
        "scene_top1": scene_top1 / total,
        "policy_priority_top1": policy_priority / policy_total if policy_total else 0.0,
        "case_role_top1": case_role / case_total if case_total else 0.0,
        "template_role_top1": template_role / template_total if template_total else 0.0,
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


def _governance_distribution(governance_by_chunk: dict[str, GovernanceMetadata]) -> dict[str, dict[str, int]]:
    return {
        "document_role": dict(Counter(item.document_role for item in governance_by_chunk.values())),
        "authority_level": dict(Counter(item.authority_level for item in governance_by_chunk.values())),
        "usage_scene": dict(Counter(item.usage_scene for item in governance_by_chunk.values())),
    }


def _build_report(
    *,
    settings: Settings,
    questions: list[GoldQuestion],
    chunks: list[Any],
    collection_count: int,
    governance_by_chunk: dict[str, GovernanceMetadata],
    baseline_metrics: Any,
    baseline_governance: dict[str, float],
    optimized_metrics: Any,
    optimized_governance: dict[str, float],
    profile_metrics: dict[str, Any],
    profile_governance_metrics: dict[str, dict[str, float]],
    selected_profile: str,
    optimized_results: list[RetrievalResult],
    query_elapsed: float,
    rerank_elapsed: float,
) -> dict[str, Any]:
    summary = {
        "gold_questions": len(questions),
        "shadow_collection_points": collection_count,
        "shadow_chunks": len(chunks),
        "selected_profile": selected_profile,
        "precision_baseline": _metric_dict(baseline_metrics),
        "governance_optimized": _metric_dict(optimized_metrics),
        "baseline_governance": baseline_governance,
        "optimized_governance": optimized_governance,
        "gold_role_distribution": dict(Counter(q.expected_document_role for q in questions)),
        "gold_authority_distribution": dict(Counter(q.expected_authority_level for q in questions)),
        "gold_scene_distribution": dict(Counter(q.expected_usage_scene for q in questions)),
        "corpus_governance_distribution": _governance_distribution(governance_by_chunk),
        "profile_metrics": {name: _metric_dict(value) for name, value in profile_metrics.items()},
        "profile_governance_metrics": profile_governance_metrics,
        "intent_counts": dict(Counter(analyze_precision_intent(q.question).question_type for q in questions)),
        "query_elapsed_seconds": round(query_elapsed, 3),
        "reranker_elapsed_seconds": round(rerank_elapsed, 3),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0),
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
    }
    return {"summary": summary, "optimized_metrics": optimized_metrics}


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    baseline = summary["precision_baseline"]
    optimized = summary["governance_optimized"]
    base_gov = summary["baseline_governance"]
    opt_gov = summary["optimized_governance"]
    rows = [
        "# Knowledge Governance Optimization Report",
        "",
        "> 本报告在独立 `full_corpus_shadow_bge_m3` 上评估文档角色、权威等级和使用场景治理。",
        "> 不修改正式 Retriever、8000 服务或正式 Qdrant；治理字段在 Shadow 读取阶段派生。",
        "",
        "## 1. Schema 与规则",
        "",
        "新增字段：",
        "- `document_role`：正式制度、管理指南、标准模板、项目案例、培训材料、汇报材料、其他。",
        "- `authority_level`：L1 至 L6，分别对应正式制度到汇报材料；无法判断为 UNKNOWN。",
        "- `usage_scene`：制度执行、管理指导、标准复用、项目复盘、模板填报、培训学习、汇报交流、专业设计、其他。",
        "",
        "Document Priority：正式制度 > 管理指南 > 标准模板 > 项目案例 > 培训材料 > 汇报材料。",
        "",
        "## 2. 评估范围",
        "",
        f"- Gold Questions：`{summary['gold_questions']}` 题，已补充三个 expected 治理字段，状态仍为 provisional。",
        f"- Shadow Collection：`{summary['shadow_collection_points']}` 点。",
        f"- Shadow Chunk：`{summary['shadow_chunks']}`。",
        f"- GPU：`{summary['gpu_name']}`，CUDA：`{summary['cuda_available']}`。",
        f"- 查询向量耗时：`{summary['query_elapsed_seconds']}` 秒；Reranker：`{summary['reranker_elapsed_seconds']}` 秒。",
        "",
        "## 3. 检索指标对比",
        "",
        "| 模式 | Recall@1 | Recall@3 | Recall@5 | MRR | Citation完整率 | 未命中题数 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| TASK-012.10 Precision baseline | {baseline['recall_at_1']:.2%} | {baseline['recall_at_3']:.2%} | {baseline['recall_at_5']:.2%} | {baseline['mrr']:.3f} | {baseline['citation_completeness']:.2%} | {baseline['failure_count']} |",
        f"| TASK-012.11 Governance optimized | {optimized['recall_at_1']:.2%} | {optimized['recall_at_3']:.2%} | {optimized['recall_at_5']:.2%} | {optimized['mrr']:.3f} | {optimized['citation_completeness']:.2%} | {optimized['failure_count']} |",
        "",
        "## 4. 治理命中指标",
        "",
        "| 指标 | Precision baseline | Governance optimized |",
        "|---|---:|---:|",
        f"| document_role Top-1 精确匹配 | {base_gov['role_top1']:.2%} | {opt_gov['role_top1']:.2%} |",
        f"| document_role Top-5 覆盖 | {base_gov['role_top5']:.2%} | {opt_gov['role_top5']:.2%} |",
        f"| authority_level Top-1 匹配 | {base_gov['authority_top1']:.2%} | {opt_gov['authority_top1']:.2%} |",
        f"| usage_scene Top-1 匹配 | {base_gov['scene_top1']:.2%} | {opt_gov['scene_top1']:.2%} |",
        f"| 制度问题 Top-1 命中正式制度/管理指南 | {base_gov['policy_priority_top1']:.2%} | {opt_gov['policy_priority_top1']:.2%} |",
        f"| 案例问题 Top-1 命中项目案例 | {base_gov['case_role_top1']:.2%} | {opt_gov['case_role_top1']:.2%} |",
        f"| 模板问题 Top-1 命中标准模板 | {base_gov['template_role_top1']:.2%} | {opt_gov['template_role_top1']:.2%} |",
        "",
        "## 5. 角色分布",
        "",
        f"- Gold document_role：`{json.dumps(summary['gold_role_distribution'], ensure_ascii=False)}`。",
        f"- Gold authority_level：`{json.dumps(summary['gold_authority_distribution'], ensure_ascii=False)}`。",
        f"- Gold usage_scene：`{json.dumps(summary['gold_scene_distribution'], ensure_ascii=False)}`。",
        f"- Shadow Corpus document_role：`{json.dumps(summary['corpus_governance_distribution']['document_role'], ensure_ascii=False)}`。",
        f"- Intent 分布：`{json.dumps(summary['intent_counts'], ensure_ascii=False)}`。",
        "",
        "## 6. 候选配置结果",
        "",
        "| 配置 | Recall@1 | Recall@3 | Recall@5 | MRR | role Top-1 | role Top-5 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metric in summary["profile_metrics"].items():
        governance = summary["profile_governance_metrics"][name]
        rows.append(
            f"| {name} | {metric['recall_at_1']:.2%} | {metric['recall_at_3']:.2%} | {metric['recall_at_5']:.2%} | {metric['mrr']:.3f} | {governance['role_top1']:.2%} | {governance['role_top5']:.2%} |"
        )
    rows.extend(
        [
            f"| selected: {summary['selected_profile']} | {optimized['recall_at_1']:.2%} | {optimized['recall_at_3']:.2%} | {optimized['recall_at_5']:.2%} | {optimized['mrr']:.3f} | {opt_gov['role_top1']:.2%} | {opt_gov['role_top5']:.2%} |",
            "",
            "## 7. 是否进入正式 Retriever",
            "",
        ]
    )
    retrieval_not_lower = all(
        optimized[key] >= baseline[key]
        for key in ("recall_at_1", "recall_at_3", "recall_at_5", "mrr")
    )
    governance_gain = any(
        opt_gov[key] > base_gov[key]
        for key in ("role_top1", "role_top5", "authority_top1", "scene_top1")
    )
    if retrieval_not_lower and governance_gain and summary["selected_profile"] != "precision_baseline_fallback":
        rows.append("当前结论：可进入下一轮 Shadow/小流量验证，但不建议直接替换正式 Retriever。")
    else:
        rows.append("当前结论：暂不进入正式 Retriever；治理排序未同时满足检索指标不下降和治理指标提升门槛。")
    rows.extend(
        [
            "",
            "## 8. 边界说明",
            "",
            "- Gold 治理字段是基于 expected_files 和治理规则的候选复核结果，仍需内容负责人确认。",
            "- Shadow 治理字段在读取 Qdrant Payload 时派生，未回写 Shadow Qdrant，也未执行全库 Embedding。",
            "- 未修改正式 `app/retriever.py`、`app/main.py`，未影响 8000 端口。",
            f"- BGE-M3：`{summary['embedding_model']}`。",
            f"- Reranker：`{summary['reranker_model']}`。",
            "",
        ]
    )
    return "\n".join(rows)


if __name__ == "__main__":
    raise SystemExit(main())
