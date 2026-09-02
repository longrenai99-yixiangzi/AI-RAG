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
from app.answer_engine.evaluation.evidence_quality import evaluate_evidence_quality
from app.answer_engine.evidence_selector import select_evidence
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
    parser = argparse.ArgumentParser(description="Evaluate Shadow Answer Engine Evidence quality.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    args = parser.parse_args()
    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; Evidence Quality Evaluation stopped.")
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
    bm25 = BM25Index(Path("data") / "shadow" / "evidence_quality_eval_bm25.json")
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

    responses = []
    for question, hits in zip(questions, top_candidates, strict=True):
        intent = analyze_precision_intent(question.question)
        policy = policy_for_intent(intent.question_type)
        bundle = select_evidence(hits, policy, governance_by_chunk, max_items=5)
        citation_map = build_citation_map(bundle)
        responses.append(
            build_shadow_response(question.question, policy, bundle, citation_map)
        )

    quality = evaluate_evidence_quality(questions, responses)
    report = {
        "summary": {
            "gold_questions": len(questions),
            "shadow_collection_points": collection_count,
            "shadow_chunks": len(chunks),
            "llm_calls": 0,
            "query_elapsed_seconds": round(query_elapsed, 3),
            "reranker_elapsed_seconds": round(rerank_elapsed, 3),
            "cuda_available": bool(torch.cuda.is_available()),
            "gpu_name": torch.cuda.get_device_name(0),
            "metrics": quality.summary(),
        },
        "question_results": [item.to_dict() for item in quality.questions],
    }
    report_path = Path("docs") / "EVIDENCE_QUALITY_EVALUATION_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    metrics = summary["metrics"]
    rows = [
        "# Evidence Quality Evaluation Report",
        "",
        "> 本报告评价 TASK-014A Evidence Selection 是否满足 100 个 Gold Questions 的回答需求。",
        "> 不调用 LLM，不修改正式 Retriever、8000 服务或 Qdrant。",
        "",
        "## 1. 评估范围",
        "",
        f"- Gold Questions：{summary['gold_questions']}。",
        f"- Shadow Collection：{summary['shadow_collection_points']} 点。",
        f"- Shadow Chunk：{summary['shadow_chunks']}。",
        f"- LLM 调用次数：{summary['llm_calls']}。",
        f"- GPU：{summary['gpu_name']}，CUDA：{summary['cuda_available']}。",
        f"- 查询向量耗时：{summary['query_elapsed_seconds']} 秒；Reranker：{summary['reranker_elapsed_seconds']} 秒。",
        "",
        "## 2. 核心指标",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| Evidence Role Match Top-1 | {metrics['role_top1_match_rate']:.2%} |",
        f"| Evidence Role Match Top-5 | {metrics['role_any_match_rate']:.2%} |",
        f"| Authority Level Match Top-1 | {metrics['authority_top1_match_rate']:.2%} |",
        f"| Authority Level Match Top-5 | {metrics['authority_any_match_rate']:.2%} |",
        f"| Usage Scene Match Top-1 | {metrics['usage_scene_top1_match_rate']:.2%} |",
        f"| Usage Scene Match Top-5 | {metrics['usage_scene_any_match_rate']:.2%} |",
        f"| Expected File Hit Rate | {metrics['expected_file_hit_rate']:.2%} |",
        f"| Intent-Evidence Match Top-1 | {metrics['intent_top1_match_rate']:.2%} |",
        f"| Intent-Evidence Match Top-5 | {metrics['intent_any_match_rate']:.2%} |",
        f"| 制度/案例/模板混淆率 | {metrics['confusion_rate']:.2%} |",
        f"| 混合角色 Evidence Bundle 比例 | {metrics['mixed_role_bundle_rate']:.2%} |",
        "",
        "## 3. 按 Intent 分析",
        "",
        "| Intent | 题数 | Role Top-1 | Role Top-5 | Authority Top-1 | Expected File | Intent Match | 混淆率 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for intent, item in metrics["by_intent"].items():
        rows.append(
            f"| {intent} | {item['questions']} | {item['role_top1_match_rate']:.2%} | "
            f"{item['role_any_match_rate']:.2%} | {item['authority_top1_match_rate']:.2%} | "
            f"{item['expected_file_hit_rate']:.2%} | {item['intent_top1_match_rate']:.2%} | "
            f"{item['confusion_rate']:.2%} |"
        )
    rows.extend(
        [
            "",
            "### 重点问题",
            "",
            "- POLICY_QUERY：检查 Top-1 是否为正式制度或管理指南；案例、培训和汇报材料出现在 Top-1 时计为制度证据混淆。",
            "- CASE_QUERY：检查 Top-1 是否为项目案例；正式制度、培训和汇报材料出现在 Top-1 时计为案例证据混淆。",
            "- TEMPLATE_QUERY：检查 Top-1 是否为标准模板；项目案例、培训和汇报材料出现在 Top-1 时计为模板证据混淆。",
            "",
            "## 4. 混淆问题清单",
            "",
            "| 问题 ID | Intent | Expected Role | Top Role | Selected Roles | Expected File Hit |",
            "|---|---|---|---|---|---|",
        ]
    )
    confusion_items = [item for item in report["question_results"] if item["confusion"]]
    for item in confusion_items:
        rows.append(
            f"| {item['question_id']} | {item['intent']} | {item['expected_role']} | "
            f"{item['top_role']} | {', '.join(item['selected_roles'])} | "
            f"{'是' if item['expected_file_hit'] else '否'} |"
        )
    if not confusion_items:
        rows.append("| 无 | - | - | - | - | - |")
    rows.extend(
        [
            "",
            "## 5. 结论",
            "",
            "1. Evidence Quality 评价只验证证据选择和可回查性，不代表最终答案事实正确性。",
            "2. 如果 Expected File Hit Rate 低而 Intent Match 高，说明策略选到了同角色资料，但没有选中 Gold 指定文件，需要继续优化 Chunk/文件级排序。",
            "3. 如果制度问题混入项目案例、培训或汇报材料，应提升正式制度/管理指南证据门槛，并保留证据不足降级。",
            "4. 如果案例或模板问题的 Top-1 角色不匹配，不应由 LLM 在生成阶段自行纠正，应该先修正 Evidence Selection。",
            "5. 本报告不修改正式链路；是否进入正式 Retriever 前，还需通过 Claim-Citation 覆盖和拒答策略评估。",
            "",
            "## 6. 边界确认",
            "",
            "- LLM 调用：否。",
            "- 正式 Retriever：未修改。",
            "- 8000 服务：未修改。",
            "- 正式 Qdrant：未修改。",
            "",
            "**TASK-014B：Evidence Quality Evaluation 完成。**",
            "",
        ]
    )
    return "\n".join(rows)


if __name__ == "__main__":
    raise SystemExit(main())
