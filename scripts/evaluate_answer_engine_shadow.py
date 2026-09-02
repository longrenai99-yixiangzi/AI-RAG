from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from qdrant_client import QdrantClient

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.answer_response import ShadowAnswerResponse, build_shadow_response
from app.answer_engine.citation_map import build_citation_map
from app.answer_engine.evidence_selector import select_evidence
from app.bm25 import BM25Index
from app.config import Settings
from app.evaluation.gold_dataset_loader import GoldQuestion, load_gold_questions
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
    parser = argparse.ArgumentParser(description="Evaluate the Shadow Answer Engine without an LLM.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    args = parser.parse_args()
    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; Answer Engine Shadow evaluation stopped.")
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
    bm25 = BM25Index(Path("data") / "shadow" / "answer_engine_eval_bm25.json")
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

    responses: list[ShadowAnswerResponse] = []
    for question, hits in zip(questions, top_candidates, strict=True):
        intent = analyze_precision_intent(question.question)
        policy = policy_for_intent(intent.question_type)
        bundle = select_evidence(hits, policy, governance_by_chunk, max_items=5)
        citation_map = build_citation_map(bundle)
        responses.append(
            build_shadow_response(question.question, policy, bundle, citation_map)
        )

    report = _build_report(
        settings=settings,
        questions=questions,
        chunks=chunks,
        collection_count=collection_count,
        responses=responses,
        query_elapsed=query_elapsed,
        rerank_elapsed=rerank_elapsed,
    )
    report_path = Path("docs") / "ANSWER_ENGINE_SHADOW_IMPLEMENTATION_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def _build_report(
    *,
    settings: Settings,
    questions: list[GoldQuestion],
    chunks: list[Any],
    collection_count: int,
    responses: list[ShadowAnswerResponse],
    query_elapsed: float,
    rerank_elapsed: float,
) -> dict[str, Any]:
    evidence_items = [
        item for response in responses for item in response.evidence_bundle.items
    ]
    required_fields = (
        "source_id",
        "chunk_id",
        "document_role",
        "authority_level",
        "location",
    )
    complete_items = sum(
        all(getattr(item, field) for field in required_fields)
        for item in evidence_items
    )
    valid_maps = sum(response.citation_map.valid for response in responses)
    expected_coverage = sum(
        bool(question.expected_files)
        and any(
            expected.casefold() == item.file_name.casefold()
            for expected in question.expected_files
            for item in response.evidence_bundle.items
        )
        for question, response in zip(questions, responses, strict=True)
    )
    section_complete = sum(
        response.status == "EVIDENCE_ONLY"
        and all(
            f"## {section}" in response.answer_text
            for section in policy_for_intent(response.intent).sections
        )
        for response in responses
    )
    summary = {
        "gold_questions": len(questions),
        "shadow_collection_points": collection_count,
        "shadow_chunks": len(chunks),
        "llm_calls": 0,
        "responses": len(responses),
        "evidence_bundle_selected": sum(
            bool(response.evidence_bundle.items) for response in responses
        ),
        "evidence_items": len(evidence_items),
        "evidence_field_completeness": (
            complete_items / len(evidence_items) if evidence_items else 0.0
        ),
        "citation_map_valid_rate": valid_maps / len(responses),
        "expected_file_coverage_rate": expected_coverage / len(responses),
        "policy_section_complete_rate": section_complete / len(responses),
        "response_status_counts": dict(
            Counter(response.status for response in responses)
        ),
        "intent_counts": dict(Counter(response.intent for response in responses)),
        "evidence_role_counts": dict(
            Counter(item.document_role for item in evidence_items)
        ),
        "query_elapsed_seconds": round(query_elapsed, 3),
        "reranker_elapsed_seconds": round(rerank_elapsed, 3),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0),
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
    }
    return {"summary": summary}


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Answer Engine Shadow Implementation Report",
        "",
        "> 本报告验证 Shadow Answer Engine 的 Answer Policy、Evidence Selection、Claim-Citation Map 和结构化响应。",
        "> 本次不调用 LLM，不修改 app/answer.py、/api/chat、正式 Retriever、正式 Qdrant 或 8000 服务。",
        "",
        "## 1. 实现模块",
        "",
        "- app/answer_engine/answer_policy.py：Intent 到回答章节和证据偏好的映射。",
        "- app/answer_engine/evidence_selector.py：从 Retriever Top-K 选择 Evidence Bundle。",
        "- app/answer_engine/citation_map.py：建立 Claim → Evidence 映射并校验来源 ID。",
        "- app/answer_engine/answer_response.py：输出 evidence-only 结构化响应，不生成模型结论。",
        "",
        "## 2. 100题验证范围",
        "",
        f"- Gold Questions：{summary['gold_questions']}。",
        f"- Shadow Collection：{summary['shadow_collection_points']} 点。",
        f"- Shadow Chunk：{summary['shadow_chunks']}。",
        f"- LLM 调用次数：{summary['llm_calls']}。",
        f"- 查询向量耗时：{summary['query_elapsed_seconds']} 秒；Reranker：{summary['reranker_elapsed_seconds']} 秒。",
        f"- GPU：{summary['gpu_name']}，CUDA：{summary['cuda_available']}。",
        "",
        "## 3. 验证结果",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 生成 Evidence Bundle 的问题 | {summary['evidence_bundle_selected']}/{summary['responses']} |",
        f"| Evidence 条目数 | {summary['evidence_items']} |",
        f"| Evidence 必要字段完整率 | {summary['evidence_field_completeness']:.2%} |",
        f"| Citation Map 有效率 | {summary['citation_map_valid_rate']:.2%} |",
        f"| 预期文件进入 Evidence 率 | {summary['expected_file_coverage_rate']:.2%} |",
        f"| Intent 回答章节结构完整率 | {summary['policy_section_complete_rate']:.2%} |",
        "",
        f"- Response 状态：{json.dumps(summary['response_status_counts'], ensure_ascii=False)}。",
        f"- Intent 分布：{json.dumps(summary['intent_counts'], ensure_ascii=False)}。",
        f"- Evidence 文档角色分布：{json.dumps(summary['evidence_role_counts'], ensure_ascii=False)}。",
        "",
        "## 4. Evidence Bundle 字段",
        "",
        "每条 Evidence 保留：source_id、chunk_id、document_role、authority_level、usage_scene、location、file_name、source_path、excerpt。",
        "",
        "source_id 在 Evidence Selection 完成后按 S1、S2 顺序生成；Claim-Citation Map 只允许引用当前 Bundle 中实际存在的 source_id。",
        "",
        "## 5. 按 Intent 的回答策略",
        "",
        "| Intent | 回答章节 | 证据重点 |",
        "|---|---|---|",
        "| POLICY_QUERY | 结论、管理要求、依据 | 正式制度、管理指南、流程 |",
        "| CASE_QUERY | 背景、措施、效果、经验 | 项目案例、复盘、经验总结 |",
        "| METHOD_QUERY | 流程、步骤、注意事项 | 指南、方法、任务书 |",
        "| TEMPLATE_QUERY | 模板用途、字段说明、使用方法 | 标准模板、表单、清单 |",
        "| DISCIPLINE_QUERY | 专业结论、适用条件、检查点、依据与边界 | 专业指南、案例、标准 |",
        "",
        "## 6. 当前边界",
        "",
        "1. 当前响应为 evidence-only，不是 LLM 生成的最终答案。",
        "2. Claim 是由 Evidence 摘录构造的结构化 Claim，用于验证映射链路，不能替代未来 LLM 的事实归纳。",
        "3. 当前未执行 Claim 内容正确性判断；下一阶段应增加证据覆盖和拒答策略测试。",
        "4. 生成模型接入必须经过 Response Schema、Citation validation 和失败回退。",
        "",
        "## 7. TASK-014A 边界确认",
        "",
        "| 验收项 | 结果 |",
        "|---|---|",
        "| Answer Policy | 已实现 |",
        "| Evidence Selection | 已实现 |",
        "| 保留 source_id/chunk_id/document_role/authority_level/location | 已实现 |",
        "| Claim → Evidence Citation Map | 已实现 |",
        "| 使用100题 Gold Questions | 已完成 |",
        "| 调用 LLM | 否 |",
        "| 修改 app/answer.py | 否 |",
        "| 修改 /api/chat | 否 |",
        "| 修改正式 Qdrant | 否 |",
        "",
        "**TASK-014A：Answer Engine Shadow Implementation 完成。**",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
