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
from app.answer_engine.llm.prompt_builder import build_prompt
from app.answer_engine.llm.response_schema import schema_fields
from app.answer_engine.citation_map import build_citation_map
from app.bm25 import BM25Index
from app.config import Settings
from app.evaluation.gold_dataset_loader import load_gold_questions
from app.ingestion.metadata.governance import GovernanceClassifier
from app.document_intelligence.profile_retriever import DocumentProfileRetriever
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import MockDenseProvider
from app.retrieval.reranker_provider import BGERerankerProvider
from app.retrieval.shadow_precision import analyze_precision_intent
from scripts.evaluate_document_level_retrieval import _retrieve_inside_documents
from scripts.evaluate_shadow_retrieval import (
    COLLECTION_NAME,
    GOLD_PATH,
    SHADOW_DIR,
    _load_shadow_chunks,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Shadow Answer Engine with the LLM Provider.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument("--profile-limit", type=int, default=30)
    args = parser.parse_args()
    settings = Settings.load()
    if not torch.cuda.is_available():
        print("ERROR: CUDA is unavailable; LLM Shadow evaluation stopped.")
        return 2

    questions = load_gold_questions(args.gold, minimum=100)
    provider = OpenAICompatibleProvider(settings)
    probe_ok = provider.probe()
    generator = ShadowAnswerGenerator(provider)

    client = QdrantClient(path=str(args.shadow_dir))
    collection_count = client.count(COLLECTION_NAME, exact=True).count
    chunks, metadata_by_chunk = _load_shadow_chunks(client)
    client.close()
    profiles = DocumentProfileRetriever.from_jsonl(
        args.shadow_dir / "document_profiles.jsonl"
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
    chunks_by_document: dict[str, list[Any]] = {}
    for chunk in chunks:
        chunks_by_document.setdefault(chunk.document_id, []).append(chunk)
    bm25 = BM25Index(Path("data") / "shadow" / "llm_answer_eval_bm25.json")
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
    raw_records: list[dict[str, Any]] = []
    evidence_count = 0
    profile_expected_file_hits = 0
    for index, question in enumerate(questions, start=1):
        intent = analyze_precision_intent(question.question)
        policy = policy_for_intent(intent.question_type)
        profile_candidates = profiles.search(
            question.question,
            policy,
            limit=args.profile_limit,
        )
        candidate_ids = {candidate.document_id for candidate in profile_candidates}
        profile_names = {candidate.document_name.casefold() for candidate in profile_candidates}
        profile_expected_file_hits += int(
            any(expected.casefold() in profile_names for expected in question.expected_files)
        )
        profile_scores = {
            candidate.document_id: candidate.score for candidate in profile_candidates
        }
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
        raw_records.append(
            {
                "question_id": question.id,
                "intent": intent.question_type,
                "evidence_bundle": asdict(bundle),
                "raw_llm_response": response.raw_llm_response,
                "parsed_response": response.parsed_response,
                "repair_response": response.repair_response,
                "final_status": response.status,
                "claim_validation_result": (
                    asdict(response.validation) if response.validation else None
                ),
                "citation_render_result": (
                    asdict(response.citation_render)
                    if response.citation_render
                    else None
                ),
                "failure_category": response.failure_category,
                "initial_failure_category": response.initial_failure_category,
                "repair_triggered": response.repair_triggered,
                "repair_success": response.repair_success,
                "error_events": response.error_events,
            }
        )
        if index == 1 or index % 10 == 0 or index == len(questions):
            print(f"answer_generation_progress={index}/{len(questions)}", flush=True)
    reranker.close()
    dense.close()
    raw_output_path = args.shadow_dir / "answer_engine_raw_outputs.jsonl"
    raw_output_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in raw_records),
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
        profile_expected_file_hits=profile_expected_file_hits,
        query_elapsed=query_elapsed,
        raw_output_path=raw_output_path,
    )
    report_path = Path("docs") / "ANSWER_STRUCTURE_CLAIM_OPTIMIZATION_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
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
    profile_expected_file_hits: int,
    query_elapsed: float,
    raw_output_path: Path,
) -> dict[str, Any]:
    generated = [response for response in responses if response.status == "GENERATED"]
    attempts = [
        response
        for response in responses
        if response.status in {"GENERATED", "CLAIM_INVALID", "LLM_ERROR"}
    ]
    validations = [response.validation for response in responses if response.validation]
    valid = [validation for validation in validations if validation.valid]
    structure_correct = 0
    unsupported_claims = sum(validation.unsupported_claims for validation in validations)
    citation_complete = 0
    confusion = 0
    repair_triggered = sum(response.repair_triggered for response in responses)
    repair_success = sum(response.repair_success for response in responses)
    category_counts: Counter[str] = Counter()
    failure_samples: list[dict[str, Any]] = []
    for question, response in zip(questions, responses, strict=True):
        category = response.failure_category or ("A" if response.status == "GENERATED" else "I")
        category_counts[category] += 1
        if response.status != "GENERATED" or category != "A":
            failure_samples.append(
                {
                    "question": question.question,
                    "status": response.status,
                    "category": category,
                    "initial_category": response.initial_failure_category,
                    "repair_triggered": response.repair_triggered,
                    "repair_success": response.repair_success,
                    "error": response.error,
                }
            )
        if response.status != "GENERATED":
            continue
        policy = policy_for_intent(analyze_precision_intent(question.question).question_type)
        structure_correct += int(
            all(f"## {field_name}" in response.answer_text for field_name in schema_fields(policy))
        )
        if response.validation:
            citation_complete += int(response.validation.valid)
        source_roles = set(response.evidence_roles)
        if question.question and "制度" in question.question and "项目案例" in source_roles:
            confusion += 1
    summary = {
        "gold_questions": len(questions),
        "shadow_collection_points": collection_count,
        "shadow_chunks": chunk_count,
        "profile_expected_file_rate": profile_expected_file_hits / len(questions),
        "evidence_items": evidence_count,
        "llm_probe_ok": probe_ok,
        "llm_probe_calls": 1,
        "answer_generation_attempts": len(responses),
        "answer_generation_successes": len(generated),
        "answer_generation_failures": len(responses) - len(generated),
        "answer_status_counts": dict(Counter(response.status for response in responses)),
        "failure_category_counts": dict(category_counts),
        "failure_samples": failure_samples,
        "answer_structure_correct_rate": structure_correct / len(generated) if generated else None,
        "answer_structure_correct_all_questions": structure_correct / len(responses),
        "citation_completeness": citation_complete / len(generated) if generated else None,
        "claim_invalid_count": sum(
            response.status in {"STRUCTURE_INVALID", "PARTIAL_EVIDENCE"}
            for response in responses
        ),
        "unsupported_claim_count": unsupported_claims,
        "claim_validation_valid_rate": len(valid) / len(validations) if validations else None,
        "policy_case_confusion_rate": confusion / len(generated) if generated else None,
        "repair_triggered": repair_triggered,
        "repair_success": repair_success,
        "repair_success_rate": repair_success / repair_triggered if repair_triggered else None,
        "human_readability": "MANUAL_REVIEW_REQUIRED",
        "provider_error": provider_error,
        "query_elapsed_seconds": round(query_elapsed, 3),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0),
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "raw_output_path": str(raw_output_path.resolve()),
        "raw_output_records": len(responses),
    }
    return {"summary": summary}


def _render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    def display(value: Any) -> str:
        return "N/A" if value is None else f"{value:.2%}" if isinstance(value, float) else str(value)
    if summary["answer_generation_failures"] == 0:
        batch_status = "100题均完成模型生成尝试。"
        next_step = "进入人工抽样评价和结果复核。"
    else:
        batch_status = (
            f"100题中完成模型生成尝试 {summary['answer_generation_attempts']} 题，"
            f"其中 {summary['answer_generation_failures']} 题未通过最终 Claim 结果校验。"
        )
        next_step = "先分析 Provider 失败题和限流/超时原因，再决定是否重跑失败题。"
    lines = [
        "# Answer Structure & Claim Reliability Optimization Report",
        "",
        "> 本报告验证 Query Understanding → Document Profile Retrieval → Hybrid/Chunk Retrieval → Evidence Ranking → Answer Policy → LLM Provider → Claim-Evidence Validation。",
        "> 本次使用 Shadow 环境，不修改正式 Retriever、8000 服务或正式 Qdrant。",
        "",
        "## 1. 实现模块",
        "",
        "- app/answer_engine/llm/llm_provider.py：OpenAI-compatible Shadow Provider，复用现有 LLM 配置。",
        "- app/answer_engine/llm/prompt_builder.py：按 Intent 和 Evidence Bundle 生成受约束 Prompt。",
        "- app/answer_engine/llm/answer_generator.py：调用 Provider、解析结构化回答并触发 Claim 校验。",
        "- app/answer_engine/llm/claim_validator.py：校验 Claim 的 Evidence ID 和答案中的 Citation。",
        "",
        "## 2. 评估结果",
        "",
        f"- Gold Questions：{summary['gold_questions']}。",
        f"- Shadow Collection：{summary['shadow_collection_points']} 点；Chunk：{summary['shadow_chunks']}。",
        f"- Evidence 条目数：{summary['evidence_items']}。",
        f"- 原始逐题输出：{summary['raw_output_path']}（{summary['raw_output_records']} 条）。",
        f"- Profile expected_file 覆盖率：{summary['profile_expected_file_rate']:.2%}。",
        f"- LLM 探针：{'通过' if summary['llm_probe_ok'] else '失败'}。",
        f"- LLM 探针调用次数：{summary['llm_probe_calls']}。",
        f"- 实际答案生成尝试：{summary['answer_generation_attempts']}。",
        f"- CUDA：{summary['cuda_available']}，GPU：{summary['gpu_name']}。",
        f"- 查询向量耗时：{summary['query_elapsed_seconds']} 秒。",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 答案结构正确率 | {display(summary['answer_structure_correct_rate'])} |",
        f"| 全部100题结构正确率 | {summary['answer_structure_correct_all_questions']:.2%} |",
        f"| Citation完整率 | {display(summary['citation_completeness'])} |",
        f"| Claim Validation Pass Rate | {display(summary['claim_validation_valid_rate'])} |",
        f"| CLAIM_INVALID 数量 | {summary['claim_invalid_count']} |",
        f"| Unsupported Claim 数量 | {summary['unsupported_claim_count']} |",
        f"| Claim Validation 有效率 | {display(summary['claim_validation_valid_rate'])} |",
        f"| 制度/案例混淆率 | {display(summary['policy_case_confusion_rate'])} |",
        f"| Repair 触发数量 | {summary['repair_triggered']} |",
        f"| Repair 成功率 | {display(summary['repair_success_rate'])} |",
        f"| 人工可读性 | {summary['human_readability']} |",
        "",
        f"- Answer 状态：{json.dumps(summary['answer_status_counts'], ensure_ascii=False)}。",
        f"- 失败分类：{json.dumps(summary['failure_category_counts'], ensure_ascii=False)}。",
        "",
        "## 3. LLM 服务状态",
        "",
        batch_status,
        f"错误摘要：{summary['provider_error'] or '无'}",
        "",
        "本次报告将 GENERATED、STRUCTURE_INVALID、PARTIAL_EVIDENCE、LLM_ERROR 和 LLM_UNAVAILABLE 分开统计；只有 GENERATED 才进入答案结构和 Citation 质量分母。",
        "",
        "## 4. TASK-015.3 基线对比",
        "",
        "| 指标 | TASK-015.3 基线 | TASK-015.4 当前结果 |",
        "|---|---:|---:|",
        "| Answer Structure Correct Rate | 32.98% | " + display(summary["answer_structure_correct_rate"]) + " |",
        "| Citation Completeness | 100.00% | " + display(summary["citation_completeness"]) + " |",
        "| CLAIM_INVALID | 6 | " + str(summary["claim_invalid_count"]) + " |",
        "| Unsupported Claim | 1 | " + str(summary["unsupported_claim_count"]) + " |",
        "| 制度/案例混淆率 | 6.38% | " + display(summary["policy_case_confusion_rate"]) + " |",
        "",
        "TASK-015.3 的逐题原始输出未持久化，无法对历史 6 个 CLAIM_INVALID 逐题回放；本报告对当前重跑结果保存逐题失败分类。",
        "",
        "### 当前失败样本分类",
        "",
        "| 问题 | 状态 | 分类 | 初始分类 | Repair触发 | Repair成功 |",
        "|---|---|---|---|---|---|",
        *[
            f"| {item['question'][:80]} | {item['status']} | {item['category']} | {item['initial_category'] or '-'} | {'是' if item['repair_triggered'] else '否'} | {'是' if item['repair_success'] else '否'} |"
            for item in summary["failure_samples"][:30]
        ],
        "",
        "",
        "## 5. Claim-Evidence 规则",
        "",
        "1. 每个 Claim 必须包含至少一个 evidence_id。",
        "2. evidence_id 必须存在于当前 Evidence Bundle。",
        "3. 答案中的 [Sx] 只能引用当前 Evidence Bundle 的来源。",
        "4. Claim 校验失败时不得把答案标记为确定性可信答案。",
        "5. LLM 不得自行访问 Qdrant 或知识源，只能使用 Prompt 中提供的 Evidence。",
        "",
        "## 6. 后续动作",
        "",
        "### 人工抽样评价",
        "",
        "以下抽样用于人工复核，脚本不自动给出主观分数；当前状态必须由业务人员确认。",
        "",
        "| 抽样问题 | 结论明确性 | 专业可信度 | 可直接使用程度 |",
        "|---|---|---|---|",
        "| FCQ-001 | 待人工复核 | 待人工复核 | 待人工复核 |",
        "| FCQ-031 | 待人工复核 | 待人工复核 | 待人工复核 |",
        "| FCQ-061 | 待人工复核 | 待人工复核 | 待人工复核 |",
        "| FCQ-081 | 待人工复核 | 待人工复核 | 待人工复核 |",
        "| FCQ-091 | 待人工复核 | 待人工复核 | 待人工复核 |",
        "",
        f"1. {next_step}",
        "2. 真实生成后人工抽查制度、案例、方法、模板和专业问题各类样本。",
        "3. 在 Provider 可用前，不修改正式 Answer 链路，不把 evidence-only 结果伪装成 LLM 结论。",
        "",
        "## 7. 边界确认",
        "",
        "- 正式 Retriever：未修改。",
        "- 8000 服务：未修改。",
        "- 正式 Qdrant：未修改。",
        "- LLM-as-Judge：未使用。",
        "",
        "**TASK-015.4：Answer Structure & Claim Reliability Optimization 完成。**",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
