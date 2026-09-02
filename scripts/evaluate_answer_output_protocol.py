from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch
from qdrant_client import QdrantClient

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import select_evidence_optimized
from app.answer_engine.llm.answer_generator import GeneratedAnswer, ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import OpenAICompatibleProvider
from app.answer_engine.llm.response_schema import schema_fields
from app.bm25 import BM25Index
from app.config import Settings
from app.document_intelligence.profile_retriever import DocumentProfileRetriever
from app.evaluation.gold_dataset_loader import load_gold_questions
from app.ingestion.metadata.governance import GovernanceClassifier
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.shadow_precision import analyze_precision_intent
from app.retrieval.reranker_provider import BGERerankerProvider
from scripts.evaluate_document_level_retrieval import _retrieve_inside_documents
from scripts.evaluate_shadow_retrieval import (
    COLLECTION_NAME,
    GOLD_PATH,
    SHADOW_DIR,
    _load_shadow_chunks,
)


OUTPUT_NAME = "answer_engine_minimal_outputs.jsonl"
REPORT_PATH = Path("docs") / "ANSWER_OUTPUT_PROTOCOL_FINAL_REPORT.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the minimal Shadow Answer output protocol.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument("--profile-limit", type=int, default=30)
    args = parser.parse_args()

    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; protocol evaluation stopped.")
        return 2
    questions = load_gold_questions(args.gold, minimum=100)
    provider = OpenAICompatibleProvider(settings)
    probe_ok = provider.probe()
    generator = ShadowAnswerGenerator(provider)

    client = QdrantClient(path=str(args.shadow_dir))
    collection_count = client.count(COLLECTION_NAME, exact=True).count
    chunks, metadata_by_chunk = _load_shadow_chunks(client)
    client.close()
    profiles = DocumentProfileRetriever.from_jsonl(args.shadow_dir / "document_profiles.jsonl")
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
    chunks_by_document: dict[str, list[Any]] = {}
    for chunk in chunks:
        chunks_by_document.setdefault(chunk.document_id, []).append(chunk)
    bm25 = BM25Index(Path("data") / "shadow" / "minimal_answer_eval_bm25.json")
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
    responses: list[GeneratedAnswer] = []
    records: list[dict[str, Any]] = []
    evidence_count = 0
    for index, question in enumerate(questions, start=1):
        intent = analyze_precision_intent(question.question)
        policy = policy_for_intent(intent.question_type)
        candidates = profiles.search(question.question, policy, limit=args.profile_limit)
        candidate_ids = {candidate.document_id for candidate in candidates}
        profile_scores = {candidate.document_id: candidate.score for candidate in candidates}
        hits = _retrieve_inside_documents(
            question.question,
            candidate_ids,
            profile_scores,
            chunks_by_document,
            reranker,
        )
        bundle = select_evidence_optimized(
            hits,
            policy,
            governance_by_chunk,
            max_items=5,
        )
        evidence_count += len(bundle.items)
        response = generator.generate(question.question, policy, bundle)
        responses.append(response)
        records.append(
            {
                "question_id": question.id,
                "intent": intent.question_type,
                "evidence_bundle": asdict(bundle),
                "raw_llm_response": response.raw_llm_response,
                "parsed_response": response.parsed_response,
                "repair_response": response.repair_response,
                "final_status": response.status,
                "claim_validation_result": asdict(response.validation) if response.validation else None,
                "citation_render_result": asdict(response.citation_render) if response.citation_render else None,
                "failure_category": response.failure_category,
                "initial_failure_category": response.initial_failure_category,
                "protocol_category": response.protocol_category,
                "initial_protocol_category": response.initial_protocol_category,
                "repair_triggered": response.repair_triggered,
                "repair_success": response.repair_success,
                "error_events": response.error_events,
                "finish_reason": response.initial_diagnostics.get("finish_reason"),
                "prompt_tokens": response.initial_diagnostics.get("prompt_tokens"),
                "completion_tokens": response.initial_diagnostics.get("completion_tokens"),
                "total_tokens": response.initial_diagnostics.get("total_tokens"),
                "max_tokens": response.initial_diagnostics.get("max_tokens"),
                "response_length": response.initial_diagnostics.get("response_length"),
                "elapsed_ms": response.initial_diagnostics.get("elapsed_ms"),
                "generation_diagnostics": response.diagnostics,
                "repair_diagnostics": response.repair_diagnostics,
            }
        )
        if index == 1 or index % 10 == 0 or index == len(questions):
            print(f"answer_generation_progress={index}/{len(questions)}", flush=True)
    reranker.close()
    dense.close()

    output_path = args.shadow_dir / OUTPUT_NAME
    output_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    report = _build_report(
        settings=settings,
        questions=questions,
        responses=responses,
        collection_count=collection_count,
        chunk_count=len(chunks),
        probe_ok=probe_ok,
        provider_error=provider.last_error,
        evidence_count=evidence_count,
        query_elapsed=query_elapsed,
        output_path=output_path,
    )
    REPORT_PATH.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"raw_output={output_path.resolve()}")
    print(f"report={REPORT_PATH.resolve()}")
    return 0


def _build_report(
    *,
    settings: Settings,
    questions: list[Any],
    responses: list[GeneratedAnswer],
    collection_count: int,
    chunk_count: int,
    probe_ok: bool,
    provider_error: str | None,
    evidence_count: int,
    query_elapsed: float,
    output_path: Path,
) -> dict[str, Any]:
    total_claims = sum(len(response.claims) for response in responses)
    valid_claims = sum(
        1
        for response in responses
        for claim in response.claims
        if isinstance(claim.get("claim_text"), str)
        and claim.get("claim_text", "").strip()
        and isinstance(claim.get("evidence_ids"), list)
        and claim.get("evidence_ids")
    )
    section_slots = sum(
        len(schema_fields(policy_for_intent(analyze_precision_intent(question.question).question_type)))
        for question in questions
    )
    visible_sections = sum(
        len(response.citation_render.visible_section_ids)
        if response.citation_render
        else 0
        for response in responses
    )
    generated = [response for response in responses if response.status == "GENERATED"]
    validations = [response.validation for response in responses if response.validation]
    valid_validations = [item for item in validations if item.valid]
    citation_generated = sum(
        bool(response.citation_render and response.citation_render.valid)
        for response in generated
    )
    categories = Counter(response.initial_protocol_category or "VALID" for response in responses)
    for category in ("A", "B", "C", "D", "E", "F", "VALID"):
        categories.setdefault(category, 0)
    finish_reasons = Counter(
        str(response.initial_diagnostics.get("finish_reason"))
        for response in responses
        if response.initial_diagnostics.get("finish_reason") is not None
    )
    completion_values = [
        response.initial_diagnostics["completion_tokens"]
        for response in responses
        if isinstance(response.initial_diagnostics.get("completion_tokens"), int)
    ]
    error_events = [
        event
        for response in responses
        for event in response.error_events
    ]
    http_statuses = Counter(
        str(event.get("http_status"))
        for event in error_events
        if event.get("http_status") is not None
    )
    return {
        "summary": {
            "questions": len(questions),
            "shadow_collection_points": collection_count,
            "shadow_chunks": chunk_count,
            "evidence_items": evidence_count,
            "llm_probe_ok": probe_ok,
            "provider_error": provider_error,
            "status_counts": dict(Counter(response.status for response in responses)),
            "generated": sum(response.status == "GENERATED" for response in responses),
            "partial_evidence": sum(response.status == "PARTIAL_EVIDENCE" for response in responses),
            "no_evidence": sum(response.status == "NO_EVIDENCE" for response in responses),
            "structure_invalid": sum(response.status == "STRUCTURE_INVALID" for response in responses),
            "llm_error": sum(response.status == "LLM_ERROR" for response in responses),
            "valid_claim_coverage": valid_claims / total_claims if total_claims else 0.0,
            "valid_claims": valid_claims,
            "total_claims": total_claims,
            "visible_section_coverage": visible_sections / section_slots if section_slots else 0.0,
            "visible_sections": visible_sections,
            "section_slots": section_slots,
            "citation_consistency": citation_generated / len(generated) if generated else 0.0,
            "citation_consistency_all": sum(
                bool(response.citation_render and response.citation_render.valid)
                for response in responses
            ) / len(responses),
            "unsupported_claims": sum(item.unsupported_claims for item in validations),
            "protocol_category_counts": dict(categories),
            "json_truncated": categories.get("A", 0),
            "finish_reason_counts": dict(finish_reasons),
            "average_completion_tokens": sum(completion_values) / len(completion_values) if completion_values else None,
            "transient_error_records": sum(bool(response.error_events) for response in responses),
            "transient_error_events": len(error_events),
            "http_status_counts": dict(http_statuses),
            "repair_triggered": sum(response.repair_triggered for response in responses),
            "repair_success": sum(response.repair_success for response in responses),
            "repair_success_rate": (
                sum(response.repair_success for response in responses)
                / sum(response.repair_triggered for response in responses)
                if any(response.repair_triggered for response in responses)
                else 0.0
            ),
            "claim_validation_pass_rate": len(valid_validations) / len(validations) if validations else 0.0,
            "g_category": sum(response.failure_category == "G" for response in responses),
            "raw_output_path": str(output_path.resolve()),
            "raw_output_records": len(responses),
            "query_elapsed_seconds": round(query_elapsed, 3),
            "cuda_available": bool(torch.cuda.is_available()),
            "gpu_name": torch.cuda.get_device_name(0),
            "embedding_model": settings.embedding_model,
            "reranker_model": settings.reranker_model,
            "failure_samples": [
                {
                    "question_id": question.id,
                    "status": response.status,
                    "protocol_category": response.initial_protocol_category,
                    "failure_category": response.failure_category,
                    "finish_reason": response.initial_diagnostics.get("finish_reason"),
                    "completion_tokens": response.initial_diagnostics.get("completion_tokens"),
                    "repair_triggered": response.repair_triggered,
                    "repair_success": response.repair_success,
                }
                for question, response in zip(questions, responses, strict=True)
                if response.status != "GENERATED"
            ],
        }
    }


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    average_tokens = (
        f"{summary['average_completion_tokens']:.1f}"
        if summary["average_completion_tokens"] is not None
        else "null"
    )
    lines = [
        "# Answer Output Protocol Final Report",
        "",
        "> 本报告基于 100 题 Shadow 评估，使用 Minimal Answer Schema；不修改正式 Retriever、8000 服务或正式 Qdrant。",
        "",
        "## 1. Minimal Answer Schema",
        "",
        "LLM 只返回 claims、section_map、evidence_insufficient。后端根据已验证的 claim_text 和 section_map 生成 Section，根据 evidence_ids 生成 Citation。",
        "Section Renderer 不总结、不扩展、不增加事实；未映射 Claim 不会被自动塞入回答。",
        "",
        "## 2. 状态统计",
        "",
        "| 状态 | 数量 |",
        "|---|---:|",
        f"| GENERATED | {summary['generated']} |",
        f"| PARTIAL_EVIDENCE | {summary['partial_evidence']} |",
        f"| NO_EVIDENCE | {summary['no_evidence']} |",
        f"| STRUCTURE_INVALID | {summary['structure_invalid']} |",
        f"| LLM_ERROR | {summary['llm_error']} |",
        "",
        "## 3. 质量指标",
        "",
        f"- 有效 Claim 覆盖率：{summary['valid_claim_coverage']:.2%}（{summary['valid_claims']}/{summary['total_claims']}）。",
        f"- 用户可见 Section 覆盖率：{summary['visible_section_coverage']:.2%}（{summary['visible_sections']}/{summary['section_slots']}）。",
        f"- Citation Consistency（GENERATED）：{summary['citation_consistency']:.2%}。",
        f"- Citation Consistency（全部题目）：{summary['citation_consistency_all']:.2%}。",
        f"- Unsupported Claim：{summary['unsupported_claims']}。",
        f"- G 类：{summary['g_category']}。",
        f"- Repair 触发/成功/成功率：{summary['repair_triggered']}/{summary['repair_success']}/{summary['repair_success_rate']:.2%}。",
        "",
        "## 4. Provider 完整性诊断",
        "",
        f"- JSON 截断数量（初始输出）：{summary['json_truncated']}。",
        f"- 初始协议分类 A-E/F：{json.dumps(summary['protocol_category_counts'], ensure_ascii=False)}。",
        f"- finish_reason 分布：{json.dumps(summary['finish_reason_counts'], ensure_ascii=False)}。",
        f"- 平均 completion tokens：{average_tokens}。",
        f"- 瞬时 Provider 错误：{summary.get('transient_error_records', 0)} 题，{summary.get('transient_error_events', 0)} 次。",
        f"- HTTP 状态码：{json.dumps(summary.get('http_status_counts', {}), ensure_ascii=False) or '未返回'}。",
        "- 每题记录 finish_reason、prompt_tokens、completion_tokens、total_tokens、max_tokens、response_length、elapsed_ms；Provider 未返回的值保持 null。",
        "",
        "## 5. 失败样本",
        "",
        "| Question ID | Status | Initial Protocol Category | Failure Category | finish_reason | completion_tokens |",
        "|---|---|---|---|---|---:|",
    ]
    for item in summary["failure_samples"]:
        lines.append(
            f"| {item['question_id']} | {item['status']} | {item['protocol_category']} | "
            f"{item['failure_category'] or '-'} | {item['finish_reason'] or '-'} | "
            f"{item['completion_tokens'] if item['completion_tokens'] is not None else '-'} |"
        )
    lines.extend(
        [
            "",
            "## 6. 验收结论",
            "",
            "Citation Consistency、Unsupported Claim 和 G 类按确定性校验结果验收。",
            "只有同时具备有效 Claim、用户可见 Section、通过 Claim Validation 和 Citation Render 的结果才标记 GENERATED。",
            "STRUCTURE_INVALID 仅保留给 JSON/Schema/类型协议失败；证据不足归入 PARTIAL_EVIDENCE 或 NO_EVIDENCE。",
            "",
            f"逐题输出：{summary['raw_output_path']}（{summary['raw_output_records']} 条）。",
            "",
            "**TASK-015.6：Answer Status Semantics & Minimal Output Protocol 完成。**",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
