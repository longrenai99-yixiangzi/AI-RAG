from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import torch
from qdrant_client import QdrantClient

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.answer_response import build_shadow_response
from app.answer_engine.citation_map import build_citation_map
from app.answer_engine.evidence_selector import (
    select_evidence,
    select_evidence_optimized,
)
from app.answer_engine.evaluation.evidence_quality import evaluate_evidence_quality
from app.bm25 import BM25Index
from app.config import Settings
from app.evaluation.gold_dataset_loader import load_gold_questions
from app.ingestion.metadata.governance import GovernanceClassifier
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import MockDenseProvider
from app.retrieval.reranker_provider import BGERerankerProvider
from app.retrieval.shadow_precision import analyze_precision_intent
from scripts.evaluate_precision_optimization import _run_candidates
from scripts.evaluate_shadow_retrieval import (
    COLLECTION_NAME,
    GOLD_PATH,
    SHADOW_DIR,
    _load_shadow_chunks,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Shadow Evidence Ranking optimization.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    args = parser.parse_args()
    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; Evidence Ranking Evaluation stopped.")
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

    classifier = GovernanceClassifier()
    governance_by_chunk = {
        chunk.chunk_id: classifier.classify(
            file_name=chunk.file_name,
            source_path=chunk.source_path,
            heading_path=chunk.heading_path,
            text=chunk.text,
            metadata=metadata_by_chunk.get(chunk.chunk_id, {}),
        )
        for chunk in chunks
    }
    bm25 = BM25Index(Path("data") / "shadow" / "evidence_ranking_eval_bm25.json")
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
    top_candidates = _run_candidates(
        bm25,
        chunks,
        questions,
        MockDenseProvider(dense_map),
        reranker=reranker,
    )
    rerank_elapsed = time.perf_counter() - rerank_started
    reranker.close()
    dense.close()

    baseline_responses = []
    optimized_responses = []
    for question, hits in zip(questions, top_candidates, strict=True):
        intent = analyze_precision_intent(question.question)
        policy = policy_for_intent(intent.question_type)
        baseline_bundle = select_evidence(hits, policy, governance_by_chunk, max_items=5)
        optimized_bundle = select_evidence_optimized(
            hits,
            policy,
            governance_by_chunk,
            max_items=5,
        )
        baseline_map = build_citation_map(baseline_bundle)
        optimized_map = build_citation_map(optimized_bundle)
        baseline_responses.append(
            build_shadow_response(question.question, policy, baseline_bundle, baseline_map)
        )
        optimized_responses.append(
            build_shadow_response(question.question, policy, optimized_bundle, optimized_map)
        )

    baseline_report = evaluate_evidence_quality(questions, baseline_responses)
    optimized_report = evaluate_evidence_quality(questions, optimized_responses)
    summary = {
        "gold_questions": len(questions),
        "shadow_collection_points": collection_count,
        "shadow_chunks": len(chunks),
        "llm_calls": 0,
        "query_elapsed_seconds": round(query_elapsed, 3),
        "reranker_elapsed_seconds": round(rerank_elapsed, 3),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0),
        "baseline": baseline_report.summary(),
        "optimized": optimized_report.summary(),
        "baseline_diversity": _diversity_metrics(baseline_responses),
        "optimized_diversity": _diversity_metrics(optimized_responses),
        "optimized_document_score": _document_score_metrics(optimized_responses),
    }
    report = {
        "summary": summary,
        "optimized_confusions": [
            item.to_dict() for item in optimized_report.questions if item.confusion
        ],
    }
    report_path = Path("docs") / "EVIDENCE_RANKING_OPTIMIZATION_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def _diversity_metrics(responses: list[Any]) -> dict[str, float]:
    bundles = [response.evidence_bundle for response in responses]
    return {
        "multiple_role_bundle_rate": sum(
            len({item.document_role for item in bundle.items}) > 1 for bundle in bundles
        ) / len(bundles),
        "average_document_count": sum(
            len({item.document_id for item in bundle.items}) for bundle in bundles
        ) / len(bundles),
        "average_role_count": sum(
            len({item.document_role for item in bundle.items}) for bundle in bundles
        ) / len(bundles),
    }


def _document_score_metrics(responses: list[Any]) -> dict[str, float]:
    items = [
        item for response in responses for item in response.evidence_bundle.items
    ]
    return {
        "items_with_document_score": sum(item.document_score > 0 for item in items),
        "average_document_score": (
            sum(item.document_score for item in items) / len(items) if items else 0.0
        ),
    }


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    baseline = summary["baseline"]
    optimized = summary["optimized"]
    rows = [
        "# Evidence Ranking Optimization Report",
        "",
        "> 本报告比较 TASK-014B Evidence Selection 基线与文件级聚合、权威等级和证据多样性优化结果。",
        "> 不调用 LLM，不修改正式 Retriever、8000 服务或正式 Qdrant。",
        "",
        "## 1. 优化内容",
        "",
        "1. File-level Aggregation：按 document_id 聚合 Chunk 数量、最高检索分数、document_role、authority_level，并生成 document_score。",
        "2. Authority Ranking：POLICY_QUERY 优先正式制度/管理指南/流程/标准模板，再到案例、培训和汇报；CASE_QUERY 优先项目案例；TEMPLATE_QUERY 优先标准模板。",
        "3. Evidence Diversity：在不硬过滤的前提下，避免 Top Evidence 全部来自同一文档或同一角色。",
        "",
        "## 2. 评估范围",
        "",
        f"- Gold Questions：{summary['gold_questions']}。",
        f"- Shadow Collection：{summary['shadow_collection_points']} 点；Shadow Chunk：{summary['shadow_chunks']}。",
        f"- LLM 调用次数：{summary['llm_calls']}。",
        f"- GPU：{summary['gpu_name']}，CUDA：{summary['cuda_available']}。",
        f"- 查询向量耗时：{summary['query_elapsed_seconds']} 秒；Reranker：{summary['reranker_elapsed_seconds']} 秒。",
        "",
        "## 3. 指标对比",
        "",
        "| 指标 | TASK-014B 基线 | 优化后 |",
        "|---|---:|---:|",
        f"| Role Match Top-1 | {baseline['role_top1_match_rate']:.2%} | {optimized['role_top1_match_rate']:.2%} |",
        f"| Role Match Top-5 | {baseline['role_any_match_rate']:.2%} | {optimized['role_any_match_rate']:.2%} |",
        f"| Authority Match Top-1 | {baseline['authority_top1_match_rate']:.2%} | {optimized['authority_top1_match_rate']:.2%} |",
        f"| Authority Match Top-5 | {baseline['authority_any_match_rate']:.2%} | {optimized['authority_any_match_rate']:.2%} |",
        f"| Usage Scene Match Top-1 | {baseline['usage_scene_top1_match_rate']:.2%} | {optimized['usage_scene_top1_match_rate']:.2%} |",
        f"| Expected File Hit Rate | {baseline['expected_file_hit_rate']:.2%} | {optimized['expected_file_hit_rate']:.2%} |",
        f"| Intent-Evidence Match Top-1 | {baseline['intent_top1_match_rate']:.2%} | {optimized['intent_top1_match_rate']:.2%} |",
        f"| Intent-Evidence Match Top-5 | {baseline['intent_any_match_rate']:.2%} | {optimized['intent_any_match_rate']:.2%} |",
        f"| 制度/案例/模板混淆率 | {baseline['confusion_rate']:.2%} | {optimized['confusion_rate']:.2%} |",
        f"| 混合角色 Bundle 比例 | {baseline['mixed_role_bundle_rate']:.2%} | {optimized['mixed_role_bundle_rate']:.2%} |",
        "",
        "## 4. Evidence Diversity 与 document_score",
        "",
        "| 指标 | TASK-014B 基线 | 优化后 |",
        "|---|---:|---:|",
        f"| 多角色 Bundle 比例 | {summary['baseline_diversity']['multiple_role_bundle_rate']:.2%} | {summary['optimized_diversity']['multiple_role_bundle_rate']:.2%} |",
        f"| 平均文档数/Bundle | {summary['baseline_diversity']['average_document_count']:.2f} | {summary['optimized_diversity']['average_document_count']:.2f} |",
        f"| 平均角色数/Bundle | {summary['baseline_diversity']['average_role_count']:.2f} | {summary['optimized_diversity']['average_role_count']:.2f} |",
        f"| 有 document_score 的 Evidence 条目 | - | {summary['optimized_document_score']['items_with_document_score']} |",
        f"| 平均 document_score | - | {summary['optimized_document_score']['average_document_score']:.3f} |",
        "",
        "## 5. 按 Intent 对比",
        "",
        "| Intent | 基线 Role Top-1 | 优化 Role Top-1 | 基线 Expected File | 优化 Expected File | 基线混淆率 | 优化混淆率 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for intent in sorted(set(summary["baseline"]["by_intent"]) | set(summary["optimized"]["by_intent"])):
        before = summary["baseline"]["by_intent"].get(intent, {})
        after = summary["optimized"]["by_intent"].get(intent, {})
        rows.append(
            f"| {intent} | {before.get('role_top1_match_rate', 0):.2%} | "
            f"{after.get('role_top1_match_rate', 0):.2%} | "
            f"{before.get('expected_file_hit_rate', 0):.2%} | "
            f"{after.get('expected_file_hit_rate', 0):.2%} | "
            f"{before.get('confusion_rate', 0):.2%} | "
            f"{after.get('confusion_rate', 0):.2%} |"
        )
    rows.extend(
        [
            "",
            "## 6. 结论",
            "",
            "1. 文件级聚合将同一文档的 Chunk 作为一个 Evidence 来源竞争，避免单个高频文档重复占满候选。",
            "2. 权威等级只改变排序，不执行硬过滤；没有命中高权威资料时仍保留可回查的补充证据。",
            "3. Evidence Diversity 通过角色和文档去重控制混合风险，但多样性不能替代正确的 Gold 文件命中。",
            "4. 若优化后 Expected File Hit Rate 或 Role Match 下降，应回退基线，不让排序优化进入正式 Retriever。",
            "5. 当前结果需结合报告中的逐题混淆清单判断是否值得进入下一轮 Shadow 验证。",
            "",
            "## 7. 边界确认",
            "",
            "- LLM 调用：否。",
            "- 正式 Retriever：未修改。",
            "- 8000 服务：未修改。",
            "- 正式 Qdrant：未修改。",
            "",
            "**TASK-014C：Evidence Ranking Optimization 完成。**",
            "",
        ]
    )
    return "\n".join(rows)


if __name__ == "__main__":
    raise SystemExit(main())
