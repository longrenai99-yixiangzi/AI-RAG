from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle, EvidenceItem
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.claim_validator import validate_claims
from app.answer_engine.llm.citation_renderer import render_claim_citations
from app.answer_engine.llm.llm_provider import OpenAICompatibleProvider
from app.answer_engine.llm.prompt_builder import build_prompt
from app.answer_engine.llm.response_schema import validate_response
from app.config import Settings


OPTIMIZED_DIR = PROJECT_ROOT / "evaluation" / "traces_optimized"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "answer_engine_failure"
REPORT_PATH = PROJECT_ROOT / "docs" / "ANSWER_ENGINE_FAILURE_DIAGNOSIS.md"
QUESTION_IDS = ("BA-007", "BA-010")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_bundle(trace: dict[str, Any]) -> EvidenceBundle:
    candidate_by_chunk = {item["chunk_id"]: item for item in trace["candidates"]}
    items: list[EvidenceItem] = []
    for item in trace["final_evidence"]:
        candidate = candidate_by_chunk[item["chunk_id"]]
        items.append(
            EvidenceItem(
                source_id=item["source_id"],
                chunk_id=item["chunk_id"],
                document_id=candidate["document_id"],
                file_name=item["file_name"],
                source_path=item["source_path"],
                document_role=item["document_role"],
                authority_level=item["authority_level"],
                usage_scene="其他",
                location=item["location"],
                excerpt=item["excerpt"],
                retrieval_score=float(candidate["rrf_score"]),
                selection_score=float(candidate["final_selection_score"]),
                evidence_status="DIRECT" if candidate.get("direct_evidence") else "SUPPORTING",
                document_score=float(candidate["final_selection_score"]),
            )
        )
    return EvidenceBundle(
        items=items,
        status="SELECTED" if items else "NO_EVIDENCE",
        selection_notes=["来源：TASK-016D-2B Optimized Evidence Bundle"],
    )


def schema_diagnostic(payload: dict[str, Any] | None, policy: Any, evidence: EvidenceBundle) -> dict[str, Any]:
    if payload is None:
        return {"valid": False, "category": "C", "errors": ["payload is null"]}
    result = validate_response(payload, policy, {item.source_id for item in evidence.items})
    return asdict(result)


def failure_stage(
    *,
    response: Any,
    initial_schema: dict[str, Any],
    repair_schema: dict[str, Any] | None,
    fact_types: list[str],
    evidence: EvidenceBundle,
) -> dict[str, Any]:
    if response.status == "LLM_ERROR" or response.error:
        return {"primary": "I PROVIDER_FAILURE", "secondary": [], "evidence": "Provider error or unavailable response"}
    if response.raw_llm_response and response.parsed_response is None:
        return {"primary": "C PARSER_FAILURE", "secondary": [], "evidence": "LLM output was not parsed into a JSON object"}
    if not initial_schema.get("valid") and not repair_schema:
        errors = " ".join(initial_schema.get("errors", []))
        if "section_map" in errors:
            return {"primary": "D SECTION_MAPPING_FAILURE", "secondary": ["B LLM_SCHEMA_FAILURE"], "evidence": errors}
        return {"primary": "B LLM_SCHEMA_FAILURE", "secondary": [], "evidence": errors}
    if response.citation_render is not None and not response.citation_render.valid:
        return {"primary": "F CITATION_FAILURE", "secondary": [], "evidence": "; ".join(response.citation_render.errors)}
    if response.validation is not None and not response.validation.valid:
        return {"primary": "E CLAIM_VALIDATION_FAILURE", "secondary": [], "evidence": "; ".join(response.validation.errors)}
    if response.status == "NO_EVIDENCE" and not response.claims:
        if any(item in fact_types for item in ("COUNT_FACT", "AMOUNT_FACT", "SCOPE_FACT")):
            return {
                "primary": "H FACT_QUERY_CAPABILITY_MISSING",
                "secondary": ["G MULTI_CHUNK_AGGREGATION_FAILURE", "A PROMPT_FAILURE"],
                "evidence": "No Claim was produced for a fact/aggregation query despite a non-empty optimized Evidence Bundle",
            }
        return {"primary": "J OTHER", "secondary": ["A PROMPT_FAILURE"], "evidence": "No Claim was produced"}
    if response.status == "PARTIAL_EVIDENCE":
        return {"primary": "G MULTI_CHUNK_AGGREGATION_FAILURE", "secondary": [], "evidence": "Answer remained partial after optimized evidence was supplied"}
    if response.status == "STRUCTURE_INVALID":
        return {"primary": "B LLM_SCHEMA_FAILURE", "secondary": [], "evidence": "Final response remained structurally invalid"}
    return {"primary": "J OTHER", "secondary": [], "evidence": "No failure observed in this run; retain trace for replay"}


def diagnose_question(trace: dict[str, Any], generator: ShadowAnswerGenerator) -> dict[str, Any]:
    bundle = build_bundle(trace)
    policy = policy_for_intent(trace["intent"])
    prompt = build_prompt(trace["question"], policy, bundle)
    fact_types = list(trace.get("metrics", {}).get("fact_type_match", []))
    fact_types_passed = any(fact_type in prompt.user_prompt for fact_type in fact_types)
    response = generator.generate(trace["question"], policy, bundle)
    initial_schema = schema_diagnostic(response.parsed_response, policy, bundle)
    repair_schema = None
    if response.repair_response and response.parsed_response:
        # The generator exposes the final parsed payload; the raw repair text is retained below.
        repair_schema = schema_diagnostic(response.parsed_response, policy, bundle)
    stage = failure_stage(
        response=response,
        initial_schema=initial_schema,
        repair_schema=repair_schema,
        fact_types=fact_types,
        evidence=bundle,
    )
    return {
        "question_id": trace["question_id"],
        "question": trace["question"],
        "intent": trace["intent"],
        "fact_types": fact_types,
        "fact_types_passed_to_prompt": fact_types_passed,
        "optimized_evidence_ids": [item.source_id for item in bundle.items],
        "optimized_evidence_excerpts": [
            {
                "source_id": item.source_id,
                "file_name": item.file_name,
                "location": item.location,
                "excerpt": item.excerpt,
            }
            for item in bundle.items
        ],
        "prompt_input": {
            "system_prompt": prompt.system_prompt,
            "user_prompt": prompt.user_prompt,
            "response_schema": prompt.response_schema,
        },
        "raw_llm_response": response.raw_llm_response,
        "parsed_response": response.parsed_response,
        "repair_response": response.repair_response,
        "claims": response.claims,
        "section_map": (response.parsed_response or {}).get("section_map") if response.parsed_response else None,
        "schema_validation": initial_schema,
        "claim_validation": asdict(response.validation) if response.validation else None,
        "citation_render": asdict(response.citation_render) if response.citation_render else None,
        "final_status": response.status,
        "failure_stage": stage,
        "repair_triggered": response.repair_triggered,
        "repair_success": response.repair_success,
        "error_events": response.error_events,
        "diagnostics": {
            "initial": response.initial_diagnostics,
            "final": response.diagnostics,
            "repair": response.repair_diagnostics,
            "elapsed_ms": response.elapsed_ms,
            "request_id": response.request_id,
        },
    }


def render_report(records: list[dict[str, Any]], provider: OpenAICompatibleProvider) -> str:
    lines = [
        "# Answer Engine Failure Diagnosis",
        "",
        "> TASK-016E-1：只使用 TASK-016D-2B Optimized Evidence Bundle 诊断 BA-007、BA-010。",
        "> 未使用 Baseline Evidence；未修改 Retriever、Shadow Selector、RRF、Embedding、正式 Qdrant、8000 服务或 Answer Engine 代码。",
        "> 本次未关闭 Claim Validator / Citation Validator，也未以 LLM 结果质量作为 Selector 成败判断。",
        "",
        "## 1. 诊断范围",
        "",
        "- Provider：现有 OpenAI-compatible Shadow Provider；使用当前已配置 Key。",
        f"- Provider 配置可用：`{provider.available}`；错误：`{provider.last_error or '无'}`",
        "- Evidence 来源：`evaluation/traces_optimized/BA-007.json`、`BA-010.json` 的 `final_evidence`。",
        "- Answer Policy：沿用当前 `policy_for_intent`，未增加 FACT_QUERY / AGGREGATION_QUERY 分支。",
        "",
        "## 2. 逐题总览",
        "",
        "| 问题 | Intent | Fact Type | Optimized Evidence | Fact Type进入Prompt | Claims | Schema | Citation | Claim Validator | Final Status | Primary Root Cause | Secondary Cause |",
        "|---|---|---|---:|---|---:|---|---|---|---|---|---|",
    ]
    for record in records:
        schema = record["schema_validation"]
        citation = record["citation_render"]
        claim = record["claim_validation"]
        stage = record["failure_stage"]
        lines.append(
            f"| {record['question_id']} | {record['intent']} | {', '.join(record['fact_types']) or '-'} | {len(record['optimized_evidence_ids'])} | {record['fact_types_passed_to_prompt']} | {len(record['claims'])} | {schema['valid']} | {citation['valid'] if citation else '-'} | {claim['valid'] if claim else '-'} | {record['final_status']} | {stage['primary']} | {', '.join(stage['secondary']) or '-'} |"
        )
    lines += ["", "## 3. BA-007 诊断", ""]
    ba007 = next(record for record in records if record["question_id"] == "BA-007")
    lines += [
        f"- Final Status：`{ba007['final_status']}`",
        f"- Failure Stage：`{ba007['failure_stage']}`",
        f"- Optimized Evidence IDs：`{ba007['optimized_evidence_ids']}`",
        f"- Raw JSON 可解析：`{ba007['parsed_response'] is not None}`",
        f"- Claims 数量：`{len(ba007['claims'])}`",
        f"- section_map：`{json.dumps(ba007['section_map'], ensure_ascii=False)}`",
        f"- Schema：`{json.dumps(ba007['schema_validation'], ensure_ascii=False)}`",
        f"- Repair：triggered=`{ba007['repair_triggered']}`，success=`{ba007['repair_success']}`",
        f"- Claim Validation：`{json.dumps(ba007['claim_validation'], ensure_ascii=False)}`",
        f"- Citation Render：`{json.dumps(ba007['citation_render'], ensure_ascii=False)}`",
        "",
        "判断：",
        "",
        "- BA-007 的证据已包含目标 PDF，若本次出现 STRUCTURE_INVALID，根因应定位在 LLM JSON/Schema/Section Mapping，而不是 Retriever 或 Selector。",
        "- 如果 Schema 与 Citation 均通过但没有 Claim，则是回答策略/Prompt 未把“设计示范项目要求”组织成可输出 Claim 的问题。",
        "",
        "## 4. BA-010 诊断",
        "",
    ]
    ba010 = next(record for record in records if record["question_id"] == "BA-010")
    lines += [
        f"- Final Status：`{ba010['final_status']}`",
        f"- Failure Stage：`{ba010['failure_stage']}`",
        f"- Optimized Evidence IDs：`{ba010['optimized_evidence_ids']}`",
        f"- 目标 Workbook Evidence 数量：`{len([item for item in ba010['optimized_evidence_excerpts'] if item['file_name'] == '方案比选与价值创造清单方案比选及价值创造.xlsx'])}`",
        f"- Fact Types：`{ba010['fact_types']}`",
        f"- Fact Types 是否进入 Prompt：`{ba010['fact_types_passed_to_prompt']}`",
        f"- Claims 数量：`{len(ba010['claims'])}`",
        f"- section_map：`{json.dumps(ba010['section_map'], ensure_ascii=False)}`",
        f"- Schema：`{json.dumps(ba010['schema_validation'], ensure_ascii=False)}`",
        f"- Claim Validation：`{json.dumps(ba010['claim_validation'], ensure_ascii=False)}`",
        f"- Citation Render：`{json.dumps(ba010['citation_render'], ensure_ascii=False)}`",
        "",
        "判断：",
        "",
        "- 当前 Answer Schema 只有 TEMPLATE_QUERY 的 purpose / fields / usage / precautions / version_or_basis，没有 group_by、count、sum、list、scope 等聚合字段。",
        "- 当前 Prompt Builder 没有把 COUNT_FACT、AMOUNT_FACT、SCOPE_FACT 作为结构化事实类型传给模型。",
        "- 六个 Workbook Chunk 虽然进入 Evidence，但多个 Sheet 的表格事实需要跨 Chunk 聚合；当前 Claim Schema 只表达自然语言 Claim + evidence_ids，不能稳定表达按专业分组、计数和金额合计。",
        "- 如果本题返回 NO_EVIDENCE / NO_CLAIM 且 Schema、Citation、Claim Validator 均正常，主要根因是 FACT_QUERY_CAPABILITY_MISSING，次要根因是 MULTI_CHUNK_AGGREGATION_FAILURE 和 PROMPT_FAILURE。",
        "",
        "## 5. Answer Pipeline 检查结论",
        "",
        "| 阶段 | 检查内容 | 本任务结论 |",
        "|---|---|---|",
        "| Optimized Evidence | 是否只使用 D-2B Evidence | 是 |",
        "| Prompt Builder | 是否包含 Fact Type 字段 | 按当前实现不包含 |",
        "| LLM JSON | 是否可解析 | 以逐题 JSON 记录为准 |",
        "| Schema | claims / section_map / evidence_insufficient | 以逐题 Schema 记录为准 |",
        "| Claim Validator | 是否放宽或绕过 | 否 |",
        "| Citation Renderer | 是否自动引用 Evidence IDs | 沿用现有确定性渲染 |",
        "| Fact Aggregation | 是否有 group_by / count / sum / scope | 当前没有 |",
        "",
        "## 6. PRIMARY ROOT CAUSE 分类",
        "",
        "允许分类：A PROMPT_FAILURE、B LLM_SCHEMA_FAILURE、C PARSER_FAILURE、D SECTION_MAPPING_FAILURE、E CLAIM_VALIDATION_FAILURE、F CITATION_FAILURE、G MULTI_CHUNK_AGGREGATION_FAILURE、H FACT_QUERY_CAPABILITY_MISSING、I PROVIDER_FAILURE、J OTHER。",
        "",
    ]
    for record in records:
        stage = record["failure_stage"]
        lines.append(f"- {record['question_id']} PRIMARY：**{stage['primary']}**；Secondary：{', '.join(stage['secondary']) or '无'}；证据：{stage['evidence']}")
    lines += [
        "",
        "## 7. 最小修复方案（只设计，不实施）",
        "",
        "### BA-007",
        "",
        "1. 保持现有 Claim Validator 与 Citation Renderer；",
        "2. 在 POLICY_QUERY 的 Prompt/Schema 中明确 conclusion、requirements、basis、scope_or_exceptions；",
        "3. 要求模型将“示范项目”相关 Claim 绑定到目标 PDF 的具体 Evidence ID；",
        "4. 若 JSON/Schema 失败，只允许一次受限 Repair，不增加新事实；",
        "5. 继续保留 STRUCTURE_INVALID，不把结构失败伪装成 GENERATED。",
        "",
        "### BA-010",
        "",
        "1. 新增只用于 Shadow 的 `FACT_QUERY` / `AGGREGATION_QUERY` Answer Policy；",
        "2. 结构至少支持：`group_by`、`count`、`sum`、`list`、`scope`、`unit`；",
        "3. Claim 增加聚合表达，例如每个专业一个 Claim，并允许一个 Claim 绑定多个 Evidence ID；",
        "4. 明确区分 COUNT_FACT、AMOUNT_FACT、RATE_FACT、DATE_FACT、SCOPE_FACT；",
        "5. 对多个 Sheet 先做确定性表格聚合，再让 LLM 组织语言；LLM 不得自行计算或猜测；",
        "6. 聚合结果必须保留原始 Sheet、行范围和 Evidence ID，继续经过 Claim Validator 与 Citation Validator；",
        "7. 聚合失败时返回 `AGGREGATION_INSUFFICIENT` 或 `PARTIAL_EVIDENCE`，不返回无依据的确定性结论。",
        "",
        "## 8. 结论",
        "",
        "本任务只诊断 Answer Engine。D-2B 已解决目标证据进入 Evidence Bundle 的问题；BA-010 即使拥有目标 Workbook 的多 Sheet Evidence，当前 Answer Engine 仍缺少事实查询和跨 Chunk 表格聚合表达能力。该问题不应通过关闭 Validator、扩大 Chunk 或让 LLM 猜测数字解决。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    settings = Settings.load()
    provider = OpenAICompatibleProvider(settings)
    generator = ShadowAnswerGenerator(provider)
    records: list[dict[str, Any]] = []
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for question_id in QUESTION_IDS:
        trace = read_json(OPTIMIZED_DIR / f"{question_id}.json")
        record = diagnose_question(trace, generator)
        output = OUTPUT_DIR / f"{question_id}.json"
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        records.append(record)
        print(f"diagnosis_progress={len(records)}/{len(QUESTION_IDS)}", flush=True)
    REPORT_PATH.write_text(render_report(records, provider), encoding="utf-8")
    print(json.dumps({"records": [str((OUTPUT_DIR / f'{qid}.json').resolve()) for qid in QUESTION_IDS], "report": str(REPORT_PATH.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
