from __future__ import annotations

import copy
import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.llm.claim_validator import validate_claims
from app.answer_engine.llm.citation_renderer import render_claim_citations
from app.answer_engine.llm.llm_provider import OpenAICompatibleProvider
from app.answer_engine.llm.prompt_builder import build_prompt
from app.answer_engine.llm.response_schema import response_schema, schema_fields, validate_response
from app.config import Settings
from scripts.diagnose_answer_engine_failure import build_bundle


TRACE = PROJECT_ROOT / "evaluation" / "traces_optimized" / "BA-007.json"
BASELINE_FAILURE = PROJECT_ROOT / "evaluation" / "answer_stability" / "BA-007" / "run_05.json"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "section_mapping_stability" / "BA-007"
REPORT = PROJECT_ROOT / "docs" / "SECTION_MAPPING_STABILITY_REPORT.md"
RUNS = 30


def parse_json_payload(content: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not content:
        return None, "empty response"
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        return None, f"invalid JSON: {error}"
    return (payload, None) if isinstance(payload, dict) else (None, "JSON root is not object")


def validate_section_map(payload: dict[str, Any] | None, claims: list[dict[str, Any]], evidence_ids: set[str]) -> dict[str, Any]:
    available_claim_ids = [str(claim.get("claim_id")) for claim in claims if isinstance(claim, dict) and claim.get("claim_id")]
    available_claim_set = set(available_claim_ids)
    invalid: list[dict[str, Any]] = []
    section_map = payload.get("section_map") if isinstance(payload, dict) else None
    if not isinstance(section_map, dict):
        return {
            "valid": False,
            "available_claim_ids": available_claim_ids,
            "available_evidence_ids": sorted(evidence_ids),
            "invalid_section_references": [{"field": None, "id": None, "error": "SECTION_MAP_NOT_OBJECT"}],
            "errors": ["SECTION_MAP_NOT_OBJECT"],
        }
    for field_name, values in section_map.items():
        if not isinstance(values, list):
            invalid.append({"field": field_name, "id": None, "error": "SECTION_MAP_VALUE_NOT_ARRAY"})
            continue
        for value in values:
            value = str(value)
            if value in evidence_ids:
                invalid.append({"field": field_name, "id": value, "error": "EVIDENCE_ID_IN_SECTION_MAP"})
            elif value not in available_claim_set:
                invalid.append({"field": field_name, "id": value, "error": "UNKNOWN_CLAIM_ID"})
    return {
        "valid": not invalid,
        "available_claim_ids": available_claim_ids,
        "available_evidence_ids": sorted(evidence_ids),
        "invalid_section_references": invalid,
        "errors": sorted({item["error"] for item in invalid}),
    }


def structural_schema_validation(payload: dict[str, Any] | None, policy: Any, evidence_ids: set[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"valid": False, "category": "C", "errors": ["payload is not an object"]}
    probe = copy.deepcopy(payload)
    section_map = probe.get("section_map")
    if isinstance(section_map, dict):
        claim_ids = [
            str(claim.get("claim_id"))
            for claim in probe.get("claims", [])
            if isinstance(claim, dict) and claim.get("claim_id")
        ]
        probe["section_map"] = {
            field_name: claim_ids if index == 0 else []
            for index, field_name in enumerate(schema_fields(policy))
        }
    return as_dict(validate_response(probe, policy, evidence_ids))


def as_dict(value: Any) -> dict[str, Any]:
    return {
        "valid": bool(value.valid),
        "category": value.category,
        "errors": list(value.errors),
    }


def validate_claim_bindings(payload: dict[str, Any] | None, evidence: Any) -> dict[str, Any]:
    claims = payload.get("claims") if isinstance(payload, dict) else None
    allowed = {item.source_id for item in evidence.items}
    errors: list[str] = []
    if not isinstance(claims, list):
        return {"valid": False, "errors": ["claims is not an array"]}
    ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("claim is not object")
            continue
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id or claim_id in ids:
            errors.append(f"invalid or duplicate claim_id: {claim_id}")
        ids.add(claim_id)
        evidence_values = claim.get("evidence_ids")
        if not isinstance(evidence_values, list) or not evidence_values:
            errors.append(f"{claim_id} has no evidence_ids")
        elif any(str(value) not in allowed for value in evidence_values):
            errors.append(f"{claim_id} has invalid evidence_id")
    return {"valid": not errors, "errors": errors, "claim_ids": sorted(ids), "evidence_ids": sorted(allowed)}


def repair_section_map_only(
    provider: OpenAICompatibleProvider,
    question: str,
    policy: Any,
    payload: dict[str, Any],
    evidence: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    claims = payload.get("claims", [])
    allowed_claim_ids = [str(claim.get("claim_id")) for claim in claims if isinstance(claim, dict)]
    repair_system = (
        "你是受限 Section Map Repair 工具。只修复 section_map。"
        "不得新增、删除或修改 claims，不得修改 claim_text，不得修改 evidence_ids，不得增加事实。"
    )
    repair_user = "\n".join(
        [
            f"问题：{question}",
            "原始 JSON：",
            json.dumps(payload, ensure_ascii=False, indent=2),
            f"allowed_claim_ids：{json.dumps(allowed_claim_ids, ensure_ascii=False)}",
            f"section_map 字段：{json.dumps(schema_fields(policy), ensure_ascii=False)}",
            "section_map values MUST reference Claim IDs only. Example: C1, C2.",
            "Evidence IDs such as S1 or S2 must NEVER appear in section_map.",
            "只返回完整 JSON，但只允许改变 section_map；claims 和 evidence_insufficient 必须保持不变。",
        ]
    )
    try:
        result = provider.generate(repair_system, repair_user, temperature=0, max_tokens=4096)
    except Exception as error:
        return None, {"success": False, "error": f"{type(error).__name__}: {error}", "raw_response": None, "diagnostics": getattr(provider, "last_diagnostics", {})}
    repaired, parse_error = parse_json_payload(result.content)
    if repaired is None:
        return None, {"success": False, "error": parse_error, "raw_response": result.content, "diagnostics": asdict_generation(result)}
    unchanged = repaired.get("claims") == payload.get("claims") and repaired.get("evidence_insufficient") == payload.get("evidence_insufficient")
    section_result = validate_section_map(repaired, claims, {item.source_id for item in evidence.items})
    success = unchanged and section_result["valid"]
    return repaired if success else None, {
        "success": success,
        "error": None if success else "Repair changed claims/evidence or section_map remains invalid",
        "raw_response": result.content,
        "diagnostics": asdict_generation(result),
        "section_map_validation": section_result,
        "claims_unchanged": unchanged,
    }


def asdict_generation(result: Any) -> dict[str, Any]:
    return {
        "request_id": result.request_id,
        "elapsed_ms": result.elapsed_ms,
        "diagnostics": result.diagnostics,
    }


def classify_final_status(payload: dict[str, Any] | None, schema: dict[str, Any], section: dict[str, Any], citation: Any, claims: Any, provider_error: bool) -> tuple[str, dict[str, Any]]:
    if provider_error:
        return "LLM_ERROR", {"primary": "I PROVIDER_FAILURE", "secondary": []}
    if payload is None:
        return "STRUCTURE_INVALID", {"primary": "C PARSER_FAILURE", "secondary": []}
    if not schema["valid"]:
        return "STRUCTURE_INVALID", {"primary": "B LLM_SCHEMA_FAILURE", "secondary": []}
    if not section["valid"]:
        return "STRUCTURE_INVALID", {"primary": "D SECTION_MAPPING_FAILURE", "secondary": section["errors"]}
    if citation is not None and not citation.valid:
        return "STRUCTURE_INVALID", {"primary": "F CITATION_FAILURE", "secondary": citation.errors}
    if claims is not None and not claims.valid:
        return "STRUCTURE_INVALID", {"primary": "E CLAIM_VALIDATION_FAILURE", "secondary": claims.errors}
    if not payload.get("claims"):
        return "NO_EVIDENCE", {"primary": "J OTHER", "secondary": ["NO_CLAIM"]}
    return "GENERATED", {"primary": "NONE", "secondary": []}


def run_once(index: int, provider: OpenAICompatibleProvider, evidence: Any, trace: dict[str, Any]) -> dict[str, Any]:
    policy = policy_for_intent(trace["intent"])
    prompt = build_prompt(trace["question"], policy, evidence)
    prompt.user_prompt += "\nsection_map contains Claim IDs only. Example: C1, C2. Do not put Evidence IDs such as S1 or S2 in section_map."
    try:
        result = provider.generate(prompt.system_prompt, prompt.user_prompt, max_tokens=4096)
        provider_error = False
    except Exception as error:
        result = None
        provider_error = True
        provider_error_text = f"{type(error).__name__}: {error}"
    if result is None:
        return {
            "run_id": f"BA-007-run-{index:02d}",
            "question_id": "BA-007",
            "final_status": "LLM_ERROR",
            "provider_status": "PROVIDER_ERROR",
            "provider_error": provider_error_text,
            "raw_llm_response": None,
            "parsed_response": None,
            "final_parsed_response": None,
            "repair_response": None,
            "claims": [],
            "section_map": None,
            "schema_validation": {"valid": False, "category": "I", "errors": [provider_error_text]},
            "claim_binding_validation": {"valid": False, "errors": [provider_error_text]},
            "claim_validation": None,
            "citation_validation": None,
            "repair_triggered": False,
            "repair_success": False,
            "unsupported_claims": 0,
            "invalid_evidence_ids": [],
            "diagnostics": getattr(provider, "last_diagnostics", {}),
            "invalid_section_references": [],
            "failure_stage": {"primary": "I PROVIDER_FAILURE", "secondary": []},
            "evidence_ids": [item.source_id for item in evidence.items],
        }
    payload, parse_error = parse_json_payload(result.content)
    evidence_ids = {item.source_id for item in evidence.items}
    structural = structural_schema_validation(payload, policy, evidence_ids)
    claim_binding = validate_claim_bindings(payload, evidence)
    section = validate_section_map(payload, payload.get("claims", []) if payload else [], evidence_ids)
    initial_section = section
    repair_triggered = False
    repair_record: dict[str, Any] | None = None
    final_payload = payload
    if structural["valid"] and claim_binding["valid"] and not section["valid"]:
        repair_triggered = True
        final_payload, repair_record = repair_section_map_only(provider, trace["question"], policy, payload, evidence)
        if final_payload is not None:
            section = validate_section_map(final_payload, final_payload.get("claims", []), evidence_ids)
            structural = structural_schema_validation(final_payload, policy, evidence_ids)
            claim_binding = validate_claim_bindings(final_payload, evidence)
    final_citation = None
    final_claim_validation = None
    if final_payload is not None and structural["valid"] and section["valid"]:
        from app.answer_engine.llm.citation_renderer import render_claim_citations

        rendered = render_claim_citations(final_payload, policy, evidence)
        final_citation = rendered
        final_claim_validation = validate_claims(rendered.answer_text, final_payload.get("claims", []), evidence)
    final_status, stage = classify_final_status(final_payload, structural, section, final_citation, final_claim_validation, False)
    return {
        "run_id": f"BA-007-run-{index:02d}",
        "question_id": "BA-007",
        "evidence_ids": [item.source_id for item in evidence.items],
        "available_claim_ids": sorted({str(claim.get("claim_id")) for claim in (payload or {}).get("claims", [])}),
        "available_evidence_ids": sorted(evidence_ids),
        "invalid_section_references": initial_section["invalid_section_references"],
        "initial_section_map_validation": initial_section,
        "final_section_map_validation": section,
        "raw_llm_response": result.content,
        "parsed_response": payload,
        "repair_response": repair_record,
        "final_parsed_response": final_payload,
        "claims": (final_payload or {}).get("claims", []),
        "section_map": (final_payload or {}).get("section_map"),
        "schema_validation": structural,
        "claim_binding_validation": claim_binding,
        "claim_validation": asdict(final_claim_validation) if final_claim_validation else None,
        "citation_validation": asdict(final_citation) if final_citation else None,
        "repair_triggered": repair_triggered,
        "repair_success": bool(repair_record and repair_record.get("success")),
        "provider_status": "OK",
        "provider_error": None,
        "final_status": final_status,
        "failure_stage": stage,
        "unsupported_claims": final_claim_validation.unsupported_claims if final_claim_validation else 0,
        "invalid_evidence_ids": final_claim_validation.invalid_source_ids if final_claim_validation else [],
        "diagnostics": asdict_generation(result),
        "prompt_suffix": "section_map contains Claim IDs only. Example: C1, C2. Do not put Evidence IDs such as S1 or S2 in section_map.",
    }


def render_report(records: list[dict[str, Any]], baseline: dict[str, Any]) -> str:
    status = Counter(record["final_status"] for record in records)
    repair_count = sum(record["repair_triggered"] for record in records)
    repair_success = sum(record["repair_success"] for record in records)
    leak_count = sum(any(item["error"] == "EVIDENCE_ID_IN_SECTION_MAP" for item in record["invalid_section_references"]) for record in records)
    unknown_count = sum(any(item["error"] == "UNKNOWN_CLAIM_ID" for item in record["invalid_section_references"]) for record in records)
    claim_pass = sum(bool((record.get("claim_validation") or {}).get("valid")) for record in records)
    citation_pass = sum(bool((record.get("citation_validation") or {}).get("valid")) for record in records)
    unsupported = sum(record.get("unsupported_claims", 0) for record in records)
    invalid_ids = sum(len(record.get("invalid_evidence_ids", [])) for record in records)
    lines = [
        "# Section Mapping Stability Report",
        "",
        "> TASK-016E-3.1：Shadow Section Mapping Hardening 与 BA-007 30 次稳定性回归。",
        "> 未修改 Retriever、Evidence Selection、Embedding、RRF、Reranker、正式 Qdrant、8000 服务或 BA-010 Fact Answer Path。",
        "",
        "## 1. 基线复现",
        "",
        f"- 基线文件：`evaluation/answer_stability/BA-007/run_05.json`",
        f"- available_claim_ids：`{[claim.get('claim_id') for claim in baseline.get('parsed_response', {}).get('claims', [])]}`",
        f"- available_evidence_ids：`{baseline.get('evidence_ids') or []}`",
        f"- invalid_section_references：`{baseline.get('citation_validation')}`",
        "- 原始问题：section_map.evidence 使用 S1；S1 属于 Evidence namespace，不属于 Claim namespace。",
        "",
        "## 2. Namespace 规则",
        "",
        "- Claim ID namespace：`C1、C2、C3...`",
        "- Evidence ID namespace：`S1、S2、S3...`",
        "- `section_map`：只允许 Claim ID。",
        "- `claims[].evidence_ids`：只允许 Evidence ID。",
        "",
        "## 3. 30 次稳定性结果",
        "",
        f"- 状态分布：`{json.dumps(dict(status), ensure_ascii=False)}`",
        f"- SECTION_MAP_ONLY_REPAIR 触发：{repair_count}",
        f"- Repair 成功：{repair_success}",
        f"- EVIDENCE_ID_IN_SECTION_MAP：{leak_count}",
        f"- UNKNOWN_CLAIM_ID：{unknown_count}",
        f"- Claim Validator 通过：{claim_pass}/30",
        f"- Citation Validator 通过：{citation_pass}/30",
        f"- Unsupported Claim：{unsupported}",
        f"- Invalid Evidence ID：{invalid_ids}",
        f"- Provider Error：{status.get('LLM_ERROR', 0)}",
        f"- 验收结论：**{'30/30_GENERATED' if status.get('GENERATED', 0) == 30 and claim_pass == 30 and citation_pass == 30 and unsupported == 0 and invalid_ids == 0 else '未达到30/30，保留失败样本继续诊断'}**",
        "",
        "## 4. 失败样本",
        "",
    ]
    failures = [record for record in records if record["final_status"] != "GENERATED"]
    if failures:
        for record in failures:
            lines.append(
                f"- `{record['run_id']}`：status=`{record['final_status']}`；stage=`{record['failure_stage']}`；raw=`evaluation/section_mapping_stability/BA-007/{record['run_id']}.json`"
            )
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 5. Repair 安全检查",
        "",
        "- Repair 只允许改变 section_map；脚本验证 claims、claim_text、evidence_ids 和 evidence_insufficient 未改变。",
        "- 未执行 S1→C1 等位置替换；Repair 必须基于实际 Claim IDs 重新生成映射。",
        "- Repair 失败保持 STRUCTURE_INVALID，不强制改为 GENERATED。",
        "",
        "## 6. 路径结论",
        "",
        "- BA-007：仅对 Shadow Prompt 增加 Section Map namespace 约束，并增加 Section Map Validator 与受限 Repair；未修改正式 Answer Engine。",
        "- BA-010：未运行、未修改、未重新计算；Fact Answer Path 保持原有确定性结果。",
        "- 通过本次验收后，BA-007 才可继续作为 Shadow 普通知识问答路径；正式接入仍需单独审批。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow Section Mapping hardening stability runner")
    parser.add_argument("--report-only", action="store_true", help="根据已有 30 个 run JSON 生成报告，不调用 LLM")
    args = parser.parse_args()
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    evidence = build_bundle(trace)
    baseline = json.loads(BASELINE_FAILURE.read_text(encoding="utf-8"))
    if args.report_only:
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(OUTPUT_DIR.glob("run_*.json"))
        ]
        if len(records) != RUNS:
            raise ValueError(f"expected {RUNS} run records, found {len(records)}")
        REPORT.write_text(render_report(records, baseline), encoding="utf-8")
        print(json.dumps({"report": str(REPORT.resolve()), "runs": len(records), "status": dict(Counter(record['final_status'] for record in records))}, ensure_ascii=False, indent=2))
        return 0
    provider = OpenAICompatibleProvider(Settings.load())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for index in range(1, RUNS + 1):
        record = run_once(index, provider, evidence, trace)
        path = OUTPUT_DIR / f"run_{index:02d}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        records.append(record)
        print(f"section_mapping_progress={index}/{RUNS}", flush=True)
    REPORT.write_text(render_report(records, baseline), encoding="utf-8")
    print(json.dumps({"report": str(REPORT.resolve()), "runs": len(records), "status": dict(Counter(record['final_status'] for record in records)), "repairs": sum(record['repair_triggered'] for record in records)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
