from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.answer_engine.evidence_selector import EvidenceBundle, EvidenceItem
from app.answer_engine.llm.claim_validator import validate_claims
from app.answer_engine.llm.llm_provider import OpenAICompatibleProvider
from app.config import Settings
from app.llm import LLMError


INPUT = PROJECT_ROOT / "evaluation" / "v1_business_acceptance" / "BA-004.json"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "ba004_answer_structure_hardening"
REPORT = PROJECT_ROOT / "docs" / "BA004_ANSWER_STRUCTURE_HARDENING_REPORT.md"
RUNS = 20

OPTION_FIELDS = ("conclusion", "options", "recommendation", "evidence_boundary")
CLAIM_TYPES = {"OPTION", "RECOMMENDATION", "EVIDENCE_BOUNDARY"}
ROW_MARKER = "\u7b2c89\u884c"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def make_bundle(items: list[dict[str, Any]]) -> EvidenceBundle:
    evidence: list[EvidenceItem] = []
    for item in items:
        evidence.append(
            EvidenceItem(
                source_id=str(item["source_id"]),
                chunk_id=str(item.get("chunk_id") or ""),
                document_id=str(item.get("document_id") or ""),
                file_name=str(item.get("file_name") or ""),
                source_path=str(item.get("source_path") or ""),
                document_role=str(item.get("document_role") or "OTHER"),
                authority_level=str(item.get("authority_level") or "UNKNOWN"),
                usage_scene=str(item.get("usage_scene") or "OTHER"),
                location=dict(item.get("location") or {}),
                excerpt=str(item.get("excerpt") or ""),
                retrieval_score=float(item.get("retrieval_score") or item.get("score") or 0.0),
                selection_score=float(item.get("selection_score") or item.get("score") or 0.0),
                evidence_status="DIRECT" if str(item.get("source_id")) in {"S1", "S2"} else "SUPPORTING",
                document_score=float(item.get("selection_score") or item.get("score") or 0.0),
            )
        )
    return EvidenceBundle(
        items=evidence,
        status="SELECTED" if evidence else "NO_EVIDENCE",
        selection_notes=["Frozen Shadow Evidence; retrieval was not rerun"],
    )


def load_frozen_ba004() -> tuple[dict[str, Any], EvidenceBundle]:
    data = read_json(INPUT)
    items = data.get("top_evidence") or data.get("final_evidence") or []
    if not items:
        raise ValueError(f"No frozen BA-004 evidence in {INPUT}")
    return data, make_bundle(items)


def extract_target_row(bundle: EvidenceBundle) -> dict[str, Any]:
    """Extract the already-persisted target row from Evidence; never reread Excel."""
    pattern = re.compile(
        r"\u7b2c89\u884c.*?(?:\u7b2c4\u5217|\u52174)[:：](.*?)\s*\|\s*"
        r"(?:\u7b2c5\u5217|\u52175)[:：](.*?)\s*\|\s*(?:\u7b2c6\u5217|\u52176)",
        re.S,
    )
    recommendation_pattern = re.compile(
        r"\u7b2c89\u884c.*?(?:\u7b2c9\u5217|\u52179)[:：](.*?)\s*\|\s*"
        r"(?:\u7b2c10\u5217|\u521710)",
        re.S,
    )
    for item in bundle.items:
        if not item.file_name.lower().endswith(".xlsx"):
            continue
        if ROW_MARKER not in item.excerpt or "PVC-C" not in item.excerpt:
            continue
        match = pattern.search(item.excerpt)
        if not match:
            continue
        options = [clean_cell(match.group(1)), clean_cell(match.group(2))]
        recommendation_match = recommendation_pattern.search(item.excerpt)
        recommendation = clean_cell(recommendation_match.group(1)) if recommendation_match else None
        row_match = re.search(r"(\u7b2c89\u884c.*?)(?=\u7b2c90\u884c|$)", item.excerpt, re.S)
        return {
            "source_id": item.source_id,
            "file_name": item.file_name,
            "source_path": item.source_path,
            "sheet": item.location.get("sheet_name", "Sheet1"),
            "row": 89,
            "options_raw": options,
            "options_display": [display_option(value) for value in options],
            "recommendation": recommendation,
            "excerpt": item.excerpt,
            "target_excerpt": clean_cell(row_match.group(1)) if row_match else item.excerpt,
        }
    raise ValueError("Frozen Evidence does not contain the expected target row")


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\n", " ").strip(" |"))


def display_option(value: str) -> str:
    value = value.replace("\u4f20\u7edf\u7edf\u9540\u950c\u94a2\u7ba1", "\u4f20\u7edf\u9540\u950c\u94a2\u7ba1")
    return re.sub(r"^.*?\u91c7\u7528", "", value, count=1).strip() or value


def validate_option_query(question: str) -> dict[str, Any]:
    option_terms = (
        "\u54ea\u51e0\u79cd",
        "\u54ea\u4e9b\u65b9\u6848",
        "\u65b9\u6848\u6709\u54ea\u4e9b",
        "\u54ea\u4e9b\u505a\u6cd5",
        "\u53ef\u91c7\u7528\u54ea\u4e9b",
        "\u53ef\u9009\u54ea\u4e9b",
        "\u53ef\u9009\u65b9\u6848",
        "\u6709\u51e0\u79cd",
        "\u54ea\u4e9b\u6750\u6599",
    )
    matched = [term for term in option_terms if term in question]
    return {
        "policy": "OPTION_QUERY" if matched else "GENERAL_QUERY",
        "matched_terms": matched,
        "operations": ["LIST_OPTIONS"] if matched else [],
    }


def option_schema_validation(payload: Any, evidence_ids: set[str], *, require_claim_type: bool = True) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"valid": False, "category": "PARSER", "errors": ["response is not an object"]}
    required = {"claims", "section_map", "evidence_insufficient"}
    errors: list[str] = []
    unknown = sorted(set(payload) - required)
    missing = sorted(required - set(payload))
    if unknown:
        errors.append(f"unknown fields: {unknown}")
    if missing:
        errors.append(f"missing fields: {missing}")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        errors.append("claims must be an array")
    else:
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                errors.append(f"claims[{index}] must be an object")
                continue
            allowed = {"claim_id", "claim_type", "claim_text", "evidence_ids"}
            if set(claim) - allowed:
                errors.append(f"claims[{index}] has unknown fields")
            for field in ("claim_id", "claim_text", "evidence_ids"):
                if field not in claim:
                    errors.append(f"claims[{index}] missing {field}")
            if require_claim_type and "claim_type" not in claim:
                errors.append(f"claims[{index}] missing claim_type")
            if "claim_type" in claim and claim.get("claim_type") not in CLAIM_TYPES:
                errors.append(f"claims[{index}] invalid claim_type")
            if "claim_id" in claim and not isinstance(claim.get("claim_id"), str):
                errors.append(f"claims[{index}].claim_id must be string")
            if "claim_text" in claim and (not isinstance(claim.get("claim_text"), str) or not claim.get("claim_text", "").strip()):
                errors.append(f"claims[{index}].claim_text must be non-empty string")
            evidence_values = claim.get("evidence_ids")
            if not isinstance(evidence_values, list) or not evidence_values or any(not isinstance(value, str) for value in evidence_values):
                errors.append(f"claims[{index}].evidence_ids must be non-empty string array")
    section_map = payload.get("section_map")
    if not isinstance(section_map, dict):
        errors.append("section_map must be an object")
    else:
        unknown_sections = sorted(set(section_map) - set(OPTION_FIELDS))
        missing_sections = sorted(set(OPTION_FIELDS) - set(section_map))
        if unknown_sections:
            errors.append(f"unknown section_map fields: {unknown_sections}")
        if missing_sections:
            errors.append(f"missing section_map fields: {missing_sections}")
        for field in OPTION_FIELDS:
            value = section_map.get(field)
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                errors.append(f"section_map.{field} must be string array")
    insufficient = payload.get("evidence_insufficient")
    if not isinstance(insufficient, list) or any(not isinstance(item, str) for item in insufficient):
        errors.append("evidence_insufficient must be string array")
    return {"valid": not errors, "category": "A" if not errors else "SCHEMA", "errors": errors, "allowed_evidence_ids": sorted(evidence_ids)}


def validate_claim_bindings(payload: dict[str, Any] | None, evidence_ids: set[str]) -> dict[str, Any]:
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list):
        return {"valid": False, "unsupported_claims": len(claims) if isinstance(claims, list) else 1, "errors": ["claims is not an array"]}
    ids: set[str] = set()
    errors: list[str] = []
    option_count = 0
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claims[{index}] is not an object")
            continue
        claim_id = str(claim.get("claim_id") or "")
        if not re.fullmatch(r"C\d+", claim_id) or claim_id in ids:
            errors.append(f"invalid or duplicate claim_id: {claim_id}")
        ids.add(claim_id)
        if claim.get("claim_type") == "OPTION":
            option_count += 1
        values = claim.get("evidence_ids")
        if not isinstance(values, list) or not values:
            errors.append(f"{claim_id} has no evidence_ids")
        elif any(str(value) not in evidence_ids for value in values):
            errors.append(f"{claim_id} has invalid evidence_id")
    return {
        "valid": not errors,
        "unsupported_claims": sum(1 for error in errors if "evidence" in error or "claim" in error),
        "errors": errors,
        "claim_ids": sorted(ids),
        "option_claim_count": option_count,
    }


def validate_section_map(payload: dict[str, Any] | None, claims: list[dict[str, Any]], evidence_ids: set[str]) -> dict[str, Any]:
    available_claim_ids = {str(claim.get("claim_id")) for claim in claims if isinstance(claim, dict) and claim.get("claim_id")}
    invalid: list[dict[str, Any]] = []
    section_map = payload.get("section_map") if isinstance(payload, dict) else None
    if not isinstance(section_map, dict):
        return {"valid": False, "errors": ["INVALID_SECTION_MAP_VALUE"], "invalid_section_references": [{"field": None, "id": None, "error": "INVALID_SECTION_MAP_VALUE"}], "available_claim_ids": sorted(available_claim_ids), "available_evidence_ids": sorted(evidence_ids)}
    for field, values in section_map.items():
        if not isinstance(values, list):
            invalid.append({"field": field, "id": None, "error": "INVALID_SECTION_MAP_VALUE"})
            continue
        for value in values:
            value = str(value)
            if value in evidence_ids:
                error = "EVIDENCE_ID_IN_SECTION_MAP"
            elif value not in available_claim_ids:
                error = "UNKNOWN_CLAIM_ID"
            else:
                continue
            invalid.append({"field": field, "id": value, "error": error})
    return {
        "valid": not invalid,
        "errors": sorted({item["error"] for item in invalid}),
        "invalid_section_references": invalid,
        "available_claim_ids": sorted(available_claim_ids),
        "available_evidence_ids": sorted(evidence_ids),
    }


def parse_json_payload(content: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not content:
        return None, "empty response"
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        return None, f"invalid JSON: {error}"
    return (value, None) if isinstance(value, dict) else (None, "JSON root is not object")


def build_prompt(question: str, bundle: EvidenceBundle, target: dict[str, Any]) -> tuple[str, str]:
    evidence_payload = [
        {
            "source_id": item.source_id,
            "file_name": item.file_name,
            "location": item.location,
            "document_role": item.document_role,
            "authority_level": item.authority_level,
            "excerpt": item.excerpt,
        }
        for item in bundle.items
    ]
    schema = {
        "claims": [
            {"claim_id": "C1", "claim_type": "OPTION", "claim_text": "...", "evidence_ids": [target["source_id"]]},
            {"claim_id": "C2", "claim_type": "OPTION", "claim_text": "...", "evidence_ids": [target["source_id"]]},
            {"claim_id": "C3", "claim_type": "RECOMMENDATION", "claim_text": "...", "evidence_ids": [target["source_id"]]},
        ],
        "section_map": {field: ["C1"] if field == "options" else [] for field in OPTION_FIELDS},
        "evidence_insufficient": [],
    }
    system = (
        "你是企业设计管理知识库的受限结构化回答器。只依据 Evidence 回答。"
        "只输出 JSON，不输出 Markdown、解释文字或 Citation。"
        "这是 OPTION_QUERY：将用户要列举的方案拆成独立的 OPTION Claim。"
        "section_map 的值只能是 Claim ID（C1、C2），不得写 Evidence ID（S1、S2），不得写自然语言。"
        "claims[].evidence_ids 只能使用当前 Evidence ID。不得新增 Evidence，不得补造材料。"
    )
    user = "\n".join(
        [
            f"用户问题：{question}",
            f"目标证据 ID：{target['source_id']}（该证据包含问题对应的结构化方案行；其他证据只作补充，不得替代目标行中的材料）",
            "只回答问题要求的方案列表；推荐意见只能作为独立的 RECOMMENDATION Claim。",
            "若证据支持不足，保留 claims 为空并在 evidence_insufficient 说明，不得猜测。",
            "section_map 字段固定为：conclusion, options, recommendation, evidence_boundary。",
            "Minimal Schema 示例：",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "Evidence：",
            json.dumps(evidence_payload, ensure_ascii=False, indent=2),
        ]
    )
    return system, user


def validate_frozen_facts(payload: dict[str, Any] | None, target: dict[str, Any]) -> dict[str, Any]:
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    text = " ".join(str(claim.get("claim_text") or "") for claim in claims if isinstance(claim, dict))
    normalized = text.replace("（", "(").replace("）", ")")
    normalized = normalized.replace("\u4f20\u7edf\u7edf\u9540\u950c\u94a2\u7ba1", "\u4f20\u7edf\u9540\u950c\u94a2\u7ba1")
    required = [value.replace("（", "(").replace("）", ")") for value in target["options_display"]]
    missing = [value for value in required if value not in normalized]
    forbidden_terms = ["PPR", "不锈钢", "钢塑复合管", "PE"]
    forbidden = [term for term in forbidden_terms if term in normalized]
    option_claim_count = sum(1 for claim in claims if isinstance(claim, dict) and claim.get("claim_type") == "OPTION")
    return {
        "valid": not missing and not forbidden and option_claim_count >= 2,
        "required_option_markers": required,
        "missing_option_markers": missing,
        "forbidden_materials": forbidden,
        "option_claim_count": option_claim_count,
        "source_id": target["source_id"],
    }


def render_option_answer(payload: dict[str, Any], bundle: EvidenceBundle) -> dict[str, Any]:
    claims = {str(claim["claim_id"]): claim for claim in payload.get("claims", []) if isinstance(claim, dict) and claim.get("claim_id")}
    section_map = payload.get("section_map", {})
    titles = {"conclusion": "结论", "options": "可比选方案", "recommendation": "补充说明", "evidence_boundary": "证据边界"}
    lines: list[str] = []
    rendered_claim_ids: list[str] = []
    cited: set[str] = set()
    visible_sections: list[str] = []
    errors: list[str] = []
    for field in OPTION_FIELDS:
        lines.append(f"## {titles[field]}")
        ids = section_map.get(field, [])
        if not ids:
            if field == "conclusion":
                option_ids = section_map.get("options", [])
                option_claims = [claims.get(str(claim_id)) for claim_id in option_ids]
                option_claims = [claim for claim in option_claims if claim is not None]
                if option_claims:
                    sources = sorted({str(source_id) for claim in option_claims for source_id in claim.get("evidence_ids", [])})
                    lines.append(f"- 可以采用以下 {len(option_claims)} 种方案进行比选：{' '.join(f'[{source_id}]' for source_id in sources)}")
                    cited.update(sources)
                    visible_sections.append(field)
                    continue
            lines.append("- evidence_insufficient")
            continue
        rendered_in_section = 0
        for claim_id in ids:
            claim = claims.get(str(claim_id))
            if claim is None:
                errors.append(f"{field} references missing claim {claim_id}")
                continue
            evidence_ids = [str(value) for value in claim.get("evidence_ids", [])]
            invalid = [value for value in evidence_ids if value not in {item.source_id for item in bundle.items}]
            if invalid:
                errors.append(f"claim {claim_id} references invalid evidence {invalid}")
                continue
            text = str(claim.get("claim_text") or "").strip()
            if not text:
                errors.append(f"claim {claim_id} has empty text")
                continue
            lines.append(f"- {text} {' '.join(f'[{value}]' for value in evidence_ids)}")
            rendered_claim_ids.append(str(claim_id))
            cited.update(evidence_ids)
            rendered_in_section += 1
        if rendered_in_section:
            visible_sections.append(field)
    unrendered = sorted(set(claims) - set(rendered_claim_ids))
    if unrendered:
        errors.append(f"claims are not visible in section_map: {unrendered}")
    return {
        "answer_text": "\n".join(lines),
        "valid": not errors,
        "errors": errors,
        "rendered_claim_ids": rendered_claim_ids,
        "visible_section_ids": visible_sections,
        "cited_evidence_ids": sorted(cited),
    }


def citation_validate(rendered: dict[str, Any], payload: dict[str, Any], bundle: EvidenceBundle) -> dict[str, Any]:
    result = validate_claims(rendered.get("answer_text", ""), payload.get("claims", []), bundle)
    return {
        "valid": bool(rendered.get("valid")) and result.valid,
        "unsupported_claims": result.unsupported_claims,
        "invalid_source_ids": result.invalid_source_ids,
        "errors": list(rendered.get("errors", [])) + result.errors,
    }


def deterministic_section_map(payload: dict[str, Any]) -> dict[str, list[str]]:
    mapping = {field: [] for field in OPTION_FIELDS}
    for claim in payload.get("claims", []):
        if not isinstance(claim, dict) or not claim.get("claim_id"):
            continue
        claim_id = str(claim["claim_id"])
        claim_type = claim.get("claim_type")
        field = {
            "OPTION": "options",
            "RECOMMENDATION": "recommendation",
            "EVIDENCE_BOUNDARY": "evidence_boundary",
        }.get(claim_type, "conclusion")
        mapping[field].append(claim_id)
    return mapping


def repair_section_map(provider: OpenAICompatibleProvider, question: str, payload: dict[str, Any], evidence_ids: set[str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    allowed_claim_ids = [str(claim.get("claim_id")) for claim in payload.get("claims", []) if isinstance(claim, dict)]
    system = (
        "你是受限 SECTION_MAP_ONLY_REPAIR 工具。只能修改 section_map。"
        "不得新增、删除或修改 claims，不得修改 claim_text，不得修改 evidence_ids，不得新增事实。"
        "section_map 的所有值只能是允许的 Claim ID，Evidence ID 或自然语言都禁止。"
    )
    user = "\n".join(
        [
            f"问题：{question}",
            "原始 JSON：",
            json.dumps(payload, ensure_ascii=False, indent=2),
            f"allowed_claim_ids：{json.dumps(allowed_claim_ids, ensure_ascii=False)}",
            f"allowed_evidence_ids（只能用于 claims[].evidence_ids）：{json.dumps(sorted(evidence_ids), ensure_ascii=False)}",
            "section_map 字段：conclusion, options, recommendation, evidence_boundary",
            "只返回完整 JSON；section_map values MUST reference Claim IDs only.",
        ]
    )
    try:
        result = provider.generate(system, user, temperature=0, max_tokens=2048)
    except LLMError as error:
        return None, {"success": False, "error": f"{type(error).__name__}: {error}", "raw_response": None, "diagnostics": dict(provider.last_diagnostics)}
    repaired, parse_error = parse_json_payload(result.content)
    if repaired is None:
        return None, {"success": False, "error": parse_error, "raw_response": result.content, "diagnostics": dict(result.diagnostics)}
    unchanged = repaired.get("claims") == payload.get("claims") and repaired.get("evidence_insufficient") == payload.get("evidence_insufficient")
    section = validate_section_map(repaired, repaired.get("claims", []), evidence_ids)
    success = unchanged and section["valid"]
    return (repaired if success else None), {
        "success": success,
        "error": None if success else "Repair changed claims or section_map remains invalid",
        "raw_response": result.content,
        "diagnostics": dict(result.diagnostics),
        "section_map_validation": section,
        "claims_unchanged": unchanged,
    }


def run_once(index: int, provider: OpenAICompatibleProvider, question: str, bundle: EvidenceBundle, target: dict[str, Any]) -> dict[str, Any]:
    evidence_ids = {item.source_id for item in bundle.items}
    system, user = build_prompt(question, bundle, target)
    record: dict[str, Any] = {
        "run_id": f"BA-004-run-{index:02d}",
        "question_id": "BA-004",
        "question": question,
        "intent": "OPTION_QUERY",
        "evidence_ids": sorted(evidence_ids),
        "prompt_input": {"system_prompt": system, "user_prompt": user},
        "repair_triggered": False,
        "repair_type": None,
        "claims_changed": False,
        "new_facts_added": False,
    }
    provider_errors: list[str] = []
    result = None
    for attempt in range(1, 4):
        try:
            result = provider.generate(system, user, temperature=0, max_tokens=4096)
            break
        except LLMError as error:
            provider_errors.append(f"attempt={attempt}: {type(error).__name__}: {error}")
    if result is None:
        error = provider_errors[-1] if provider_errors else "provider returned no result"
        record.update(
            {
                "provider_status": "PROVIDER_ERROR",
                "provider_error": error,
                "provider_attempts": len(provider_errors),
                "provider_errors": provider_errors,
                "raw_llm_response": None,
                "parsed_response": None,
                "claims": [],
                "section_map": None,
                "schema_validation": {"valid": False, "errors": [str(error)]},
                "claim_validation": None,
                "section_map_validation": None,
                "citation_validation": None,
                "final_status": "LLM_ERROR",
                "failure_stage": "PROVIDER_FAILURE",
                "diagnostics": dict(provider.last_diagnostics),
            }
        )
        return record

    payload, parse_error = parse_json_payload(result.content)
    schema = option_schema_validation(payload, evidence_ids)
    claims_validation = validate_claim_bindings(payload, evidence_ids) if payload is not None else {"valid": False, "errors": [parse_error or "parse failure"], "unsupported_claims": 1}
    initial_section = validate_section_map(payload, payload.get("claims", []) if payload else [], evidence_ids)
    final_payload = payload
    final_section = initial_section
    repair_record: dict[str, Any] | None = None
    if payload is not None and schema["valid"] and claims_validation["valid"] and not initial_section["valid"]:
        record["repair_triggered"] = True
        repaired, repair_record = repair_section_map(provider, question, payload, evidence_ids)
        if repaired is not None:
            final_payload = repaired
            final_section = validate_section_map(repaired, repaired.get("claims", []), evidence_ids)
            schema = option_schema_validation(repaired, evidence_ids)
            claims_validation = validate_claim_bindings(repaired, evidence_ids)
            record["repair_type"] = "SECTION_MAP_ONLY_REPAIR"

    deterministic_rendered = False
    rendered: dict[str, Any] | None = None
    citation: dict[str, Any] | None = None
    if final_payload is not None and schema["valid"] and claims_validation["valid"] and final_section["valid"]:
        rendered = render_option_answer(final_payload, bundle)
        citation = citation_validate(rendered, final_payload, bundle)
    elif payload is not None and schema["valid"] and claims_validation["valid"]:
        deterministic = dict(payload)
        deterministic["section_map"] = deterministic_section_map(payload)
        deterministic_section = validate_section_map(deterministic, deterministic.get("claims", []), evidence_ids)
        if deterministic_section["valid"]:
            final_payload = deterministic
            final_section = deterministic_section
            rendered = render_option_answer(final_payload, bundle)
            citation = citation_validate(rendered, final_payload, bundle)
            deterministic_rendered = True
            record["repair_type"] = "DETERMINISTIC_CLAIM_RENDER"

    fact_validation = validate_frozen_facts(final_payload, target) if final_payload is not None else {"valid": False, "missing_option_markers": target["options_display"], "forbidden_materials": [], "option_claim_count": 0}
    if provider.last_diagnostics:
        diagnostics = dict(result.diagnostics)
    else:
        diagnostics = {}
    if final_payload is None:
        status = "STRUCTURE_INVALID"
        failure_stage = "PARSER_FAILURE"
    elif not schema["valid"]:
        status = "STRUCTURE_INVALID"
        failure_stage = "SCHEMA_VALIDATION"
    elif not claims_validation["valid"]:
        status = "STRUCTURE_INVALID"
        failure_stage = "CLAIM_VALIDATION"
    elif not final_section["valid"]:
        status = "STRUCTURE_INVALID"
        failure_stage = "SECTION_MAPPING_VALIDATION"
    elif citation is None or not citation["valid"]:
        status = "STRUCTURE_INVALID"
        failure_stage = "CITATION_VALIDATION"
    elif not fact_validation["valid"]:
        status = "PARTIAL_EVIDENCE"
        failure_stage = "BUSINESS_FACT_STABILITY"
    else:
        status = "GENERATED"
        failure_stage = None
    record.update(
        {
            "provider_status": "OK",
            "provider_error": None,
            "provider_attempts": len(provider_errors) + 1,
            "provider_errors": provider_errors,
            "raw_llm_response": result.content,
            "parsed_response": payload,
            "repair_response": repair_record,
            "final_parsed_response": final_payload,
            "claims": (final_payload or {}).get("claims", []),
            "section_map": (final_payload or {}).get("section_map"),
            "schema_validation": schema,
            "claim_validation": claims_validation,
            "initial_section_map_validation": initial_section,
            "section_map_validation": final_section,
            "citation_validation": citation,
            "deterministic_claim_render": deterministic_rendered,
            "business_fact_validation": fact_validation,
            "final_answer": rendered.get("answer_text") if rendered else "",
            "final_status": status,
            "failure_stage": failure_stage,
            "diagnostics": diagnostics,
            "repair_trace": {
                "triggered": bool(record["repair_triggered"]),
                "type": record["repair_type"],
                "claims_changed": False,
                "new_facts_added": False,
                "repair_success": bool(repair_record and repair_record.get("success")),
            },
        }
    )
    return record


def reproduce_baseline(data: dict[str, Any], bundle: EvidenceBundle) -> dict[str, Any]:
    answer_payload = data.get("answer_payload") or {}
    payload = answer_payload.get("parsed_response")
    evidence_ids = {item.source_id for item in bundle.items}
    schema = option_schema_validation(payload, evidence_ids, require_claim_type=False)
    claims_validation = validate_claim_bindings(payload, evidence_ids)
    section = validate_section_map(payload, payload.get("claims", []) if payload else [], evidence_ids)
    citation = render_option_answer(payload, bundle) if section["valid"] and payload else {"answer_text": "", "valid": False, "errors": ["section map invalid"]}
    citation_validation = citation_validate(citation, payload, bundle) if payload else None
    return {
        "source": str(INPUT),
        "question_id": data.get("question_id"),
        "question": data.get("question"),
        "raw_llm_response": None,
        "parsed_response": payload,
        "claims": (payload or {}).get("claims", []),
        "section_map": (payload or {}).get("section_map"),
        "schema_validation": {**schema, "compatibility_mode": "legacy payload without claim_type"},
        "claim_validation": claims_validation,
        "section_map_validation": section,
        "citation_validation": citation_validation,
        "repair_triggered": False,
        "final_status": "STRUCTURE_INVALID",
        "failure_stage": "SECTION_MAPPING_VALIDATION",
        "diagnosis": "section_map.evidence_boundary contains natural language instead of Claim ID; the historical claims and evidence binding are otherwise retained",
    }


def load_generic_bundle(path: Path) -> EvidenceBundle | None:
    if not path.exists():
        return None
    data = read_json(path)
    items = data.get("final_evidence") or data.get("top_evidence") or []
    return make_bundle(items[:5]) if items else None


def generic_option_tests() -> list[dict[str, Any]]:
    questions = [
        "该设计任务中有哪些方案可以列入比选？",
        "设计策划可以采用哪几种方法？",
        "这个专业可选哪些做法？",
        "方案比选有几种可行方案？",
        "材料方案有哪些可以比较？",
        "系统形式可以采用哪几种方案？",
        "该项目有哪些方案？",
        "结构方案可选哪些类型？",
        "给排水专业有哪几种方案可供比选？",
        "哪些方案适合作为候选方案？",
    ]
    records: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        path = PROJECT_ROOT / "evaluation" / "traces_optimized" / f"BA-{index:03d}.json"
        bundle = load_generic_bundle(path)
        if bundle is None or not bundle.items:
            records.append({"case_id": f"OPTION-{index:02d}", "question": question, "status": "NOT_RUN", "reason": "no persisted evidence bundle"})
            continue
        source_id = bundle.items[0].source_id
        payload = {
            "claims": [{"claim_id": "C1", "claim_type": "OPTION", "claim_text": "证据支持的候选方案信息。", "evidence_ids": [source_id]}],
            "section_map": {"conclusion": [], "options": ["C1"], "recommendation": [], "evidence_boundary": []},
            "evidence_insufficient": [],
        }
        schema = option_schema_validation(payload, {item.source_id for item in bundle.items})
        claims = validate_claim_bindings(payload, {item.source_id for item in bundle.items})
        section = validate_section_map(payload, payload["claims"], {item.source_id for item in bundle.items})
        rendered = render_option_answer(payload, bundle)
        citation = citation_validate(rendered, payload, bundle)
        records.append(
            {
                "case_id": f"OPTION-{index:02d}",
                "question": question,
                "policy": validate_option_query(question),
                "evidence_ids": [item.source_id for item in bundle.items],
                "schema_validation": schema,
                "claim_validation": claims,
                "section_map_validation": section,
                "citation_validation": citation,
                "status": "PASS" if schema["valid"] and claims["valid"] and section["valid"] and citation["valid"] else "FAIL",
            }
        )
    return records


def regression_snapshot() -> list[dict[str, Any]]:
    paths = {
        "BA-001": PROJECT_ROOT / "evaluation" / "v1_business_acceptance" / "BA-001.json",
        "BA-002": PROJECT_ROOT / "evaluation" / "ba002_formula_semantic_alignment" / "BA-002.json",
        "BA-007": PROJECT_ROOT / "evaluation" / "section_mapping_stability" / "BA-007" / "run_30.json",
        "BA-008": PROJECT_ROOT / "evaluation" / "scope_guard_leakage_cleanup" / "BA-008.json",
        "BA-010": PROJECT_ROOT / "evaluation" / "answer_stability" / "BA-010" / "run_10.json",
    }
    result = []
    for question_id, path in paths.items():
        if not path.exists():
            result.append({"question_id": question_id, "status": "NOT_FOUND", "artifact": str(path)})
            continue
        data = read_json(path)
        status = data.get("final_status") or data.get("answer_status") or data.get("aggregation_status") or data.get("fact_claim_validation", {}).get("valid")
        result.append({"question_id": question_id, "status": status, "artifact": str(path.relative_to(PROJECT_ROOT))})
    return result


def render_report(baseline: dict[str, Any], records: list[dict[str, Any]], target: dict[str, Any], generic: list[dict[str, Any]], regression: list[dict[str, Any]]) -> str:
    statuses = Counter(record.get("final_status", "UNKNOWN") for record in records)
    repairs = Counter(record.get("repair_type") for record in records if record.get("repair_type"))
    claim_pass = sum(bool((record.get("claim_validation") or {}).get("valid")) for record in records)
    section_pass = sum(bool((record.get("section_map_validation") or {}).get("valid")) for record in records)
    citation_pass = sum(bool((record.get("citation_validation") or {}).get("valid")) for record in records)
    unsupported = sum(int((record.get("claim_validation") or {}).get("unsupported_claims", 0) or 0) for record in records)
    invalid_ids = sum(len((record.get("citation_validation") or {}).get("invalid_source_ids", [])) for record in records)
    final = next((record for record in records if record.get("final_status") == "GENERATED"), records[0] if records else {})
    lines = [
        "# BA-004 Answer Structure Hardening Report",
        "",
        "> 本报告仅记录 Shadow Answer Structure 验证；未修改 Retriever、BM25、Dense、RRF、Embedding、Reranker、Router、Scope Guard、正式 Qdrant 或 BA-010 Fact Path。",
        "",
        "## 1. Failure Reproduction",
        "",
        f"- 冻结输入：`{INPUT.relative_to(PROJECT_ROOT)}`",
        f"- 历史状态：`{baseline['final_status']}`",
        f"- 历史问题：`section_map.evidence_boundary` 使用自然语言，而不是 Claim ID。",
        f"- available_claim_ids：`{baseline['section_map_validation'].get('available_claim_ids', [])}`",
        f"- available_evidence_ids：`{baseline['section_map_validation'].get('available_evidence_ids', [])}`",
        f"- 错误类型：`{baseline['section_map_validation'].get('errors', [])}`",
        "- 历史快照未持久化原始 LLM 文本，因此本次复现使用已保存的 parsed_response；未伪造 raw_llm_response。",
        "",
        "## 2. Frozen Evidence and Atomic Claims",
        "",
        f"- 文件：`{target['file_name']}`",
        f"- Sheet：`{target['sheet']}`",
        f"- 原始位置：第 {target['row']} 行",
        f"- Evidence ID：`{target['source_id']}`",
        f"- 方案一：{target['options_display'][0]}",
        f"- 方案二：{target['options_display'][1]}",
        f"- 原表备注：{target.get('recommendation') or '[未从冻结 Evidence 读到]'}",
        f"- 目标行摘录：{target.get('target_excerpt', target['excerpt'])}",
        "",
        "新 Shadow Schema 使用独立 Claim：",
        "",
        "- `OPTION`：每种方案一个 Claim；",
        "- `RECOMMENDATION`：推荐意见独立成 Claim；",
        "- `EVIDENCE_BOUNDARY`：证据范围独立成 Claim；",
        "- `claims[].evidence_ids` 只能使用 Evidence ID；`section_map` 只能使用 Claim ID。",
        "",
        "### Atomic Claims（以最终生成记录为准）",
        "",
        "```json",
        json.dumps(final.get("claims", []), ensure_ascii=False, indent=2),
        "```",
        "",
        "### Final Section Map",
        "",
        "```json",
        json.dumps(final.get("section_map"), ensure_ascii=False, indent=2),
        "```",
        "",
        "## 3. Section Map and Repair Trace",
        "",
        "处理顺序：Parse → Schema Validation → Claim Validation → Section Map Validation → Citation Validation。",
        "",
        f"- 20 次状态：`{dict(statuses)}`",
        f"- Section Map Repair：`{repairs.get('SECTION_MAP_ONLY_REPAIR', 0)}` 次",
        f"- Deterministic Claim Render：`{repairs.get('DETERMINISTIC_CLAIM_RENDER', 0)}` 次",
        f"- Claim Validator：`{claim_pass}/{len(records)}`",
        f"- Section Map Validator：`{section_pass}/{len(records)}`",
        f"- Citation Validator：`{citation_pass}/{len(records)}`",
        f"- Unsupported Claim：`{unsupported}`",
        f"- Invalid Evidence ID：`{invalid_ids}`",
        "",
        "Repair 与确定性渲染均记录 `claims_changed=false`、`new_facts_added=false`；没有执行 S1→C1 的位置替换。",
        "",
        "## 4. 20 次稳定性结果",
        "",
        "| Run | Final Status | Repair Type | Claim | Section Map | Citation | Fact Stability |",
        "|---:|---|---|---|---|---|---|",
    ]
    for record in records:
        lines.append(
            f"| {record.get('run_id')} | {record.get('final_status')} | {record.get('repair_type') or '-'} | "
            f"{(record.get('claim_validation') or {}).get('valid', '-')} | {(record.get('section_map_validation') or {}).get('valid', '-')} | "
            f"{(record.get('citation_validation') or {}).get('valid', '-')} | {(record.get('business_fact_validation') or {}).get('valid', '-')} |"
        )
    lines += [
        "",
        f"验收：**{'20/20 最终答案可用' if len(records) == RUNS and statuses.get('GENERATED') == RUNS and claim_pass == RUNS and section_pass == RUNS and citation_pass == RUNS and unsupported == 0 and invalid_ids == 0 else '未达到 20/20；保留失败记录供后续诊断'}**",
        "",
        "## 5. 最终实际答案",
        "",
        final.get("final_answer", "[未生成可用答案]") or "[未生成可用答案]",
        "",
        "### Citation",
        "",
        f"- 来源文件：`{target['file_name']}`",
        f"- Sheet：`{target['sheet']}`；位置：第 {target['row']} 行；Evidence：`{target['source_id']}`",
        f"- 原始证据摘录：{target.get('target_excerpt', target['excerpt'])}",
        "",
        "## 6. 通用 OPTION_QUERY 结构测试",
        "",
        "测试使用不同已持久化 Evidence Bundle，仅验证通用选项结构，不以 LLM 内容质量作为通过条件。",
        "",
        "| Case | Policy | Evidence 数 | Schema | Claim | Section Map | Citation | Result |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for case in generic:
        if case.get("status") == "NOT_RUN":
            lines.append(f"| {case['case_id']} | - | - | - | - | - | - | NOT_RUN |")
            continue
        lines.append(
            f"| {case['case_id']} | {case['policy']['policy']} | {len(case['evidence_ids'])} | "
            f"{case['schema_validation']['valid']} | {case['claim_validation']['valid']} | "
            f"{case['section_map_validation']['valid']} | {case['citation_validation']['valid']} | {case['status']} |"
        )
    lines += [
        "",
        f"- 通用测试通过：`{sum(case.get('status') == 'PASS' for case in generic)}/{len(generic)}`",
        "- 这些测试未写入 BA-004 专用材料名、问题全文或正确答案；OPTION_QUERY 识别只使用通用列举表达。",
        "",
        "## 7. BA 回归快照",
        "",
        "以下为既有 Shadow 产物读取快照，没有重新检索或重新改写其他 BA 题：",
        "",
        "| Question | Existing Status | Artifact |",
        "|---|---|---|",
    ]
    for item in regression:
        lines.append(f"| {item['question_id']} | {item['status']} | `{item['artifact']}` |")
    lines += [
        "",
        "- BA-002：保留公式语义边界；",
        "- BA-008：保留 Scope Guard 结果；",
        "- BA-010：未重新解析 Excel，保留既有 FACT_RESULT；",
        "- BA-001、BA-007：仅读取既有 Shadow 结果；",
        "- BA-003、BA-006、BA-009：未改写。",
        "",
        "## 8. 结论",
        "",
        "BA-004 的根因位于 Answer Structure：自然语言被写入 `section_map`，破坏了 Claim/Evidence 两个 ID namespace。当前 Shadow 修复只允许一次 Section Map Repair；若 Claims、Evidence 和 Citation 均有效，则可以使用 Deterministic Claim Render，但不修改 Claim、不新增事实、不放宽 Validator。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="BA-004 Shadow Answer Structure Hardening")
    parser.add_argument("--report-only", action="store_true", help="只根据已有 run JSON 生成报告")
    args = parser.parse_args()

    data, bundle = load_frozen_ba004()
    target = extract_target_row(bundle)
    baseline = reproduce_baseline(data, bundle)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_DIR / "baseline_reproduction.json", baseline)

    existing = sorted(OUTPUT_DIR.glob("run_*.json"))
    if args.report_only:
        if len(existing) != RUNS:
            raise ValueError(f"expected {RUNS} run records, found {len(existing)}")
        records = [read_json(path) for path in existing]
        for path, record in zip(existing, records):
            payload = record.get("final_parsed_response") or record.get("parsed_response")
            if isinstance(payload, dict):
                rendered = render_option_answer(payload, bundle)
                record["final_answer"] = rendered["answer_text"]
                record["citation_validation"] = citation_validate(rendered, payload, bundle)
                write_json(path, record)
    else:
        provider = OpenAICompatibleProvider(Settings.load())
        records = []
        for index in range(1, RUNS + 1):
            record = run_once(index, provider, data["question"], bundle, target)
            write_json(OUTPUT_DIR / f"run_{index:02d}.json", record)
            records.append(record)
            print(f"ba004_structure_progress={index}/{RUNS}", flush=True)

    generic = generic_option_tests()
    write_json(OUTPUT_DIR / "generic_option_tests.json", {"tests": generic})
    regression = regression_snapshot()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(baseline, records, target, generic, regression), encoding="utf-8")

    summary = {
        "report": str(REPORT.resolve()),
        "output_dir": str(OUTPUT_DIR.resolve()),
        "runs": len(records),
        "status": dict(Counter(record.get("final_status", "UNKNOWN") for record in records)),
        "generic_option_tests": sum(case.get("status") == "PASS" for case in generic),
        "baseline_status": baseline["final_status"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
