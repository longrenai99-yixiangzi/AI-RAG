from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from app.answer_engine.answer_policy import AnswerPolicy


SCHEMA_FIELDS = {
    "POLICY_QUERY": ("conclusion", "management_requirements", "evidence", "scope_or_exceptions"),
    "CASE_QUERY": ("background", "measures", "outcomes", "lessons"),
    "METHOD_QUERY": ("process", "steps", "precautions", "inputs_outputs", "checkpoints"),
    "TEMPLATE_QUERY": ("purpose", "fields", "usage", "precautions", "version_or_basis"),
    "DISCIPLINE_QUERY": (
        "professional_conclusion",
        "applicable_conditions",
        "checkpoints",
        "related_cases_or_methods",
        "evidence_boundary",
    ),
    "GENERAL_QUERY": ("evidence_summary", "evidence_boundary"),
}


@dataclass(slots=True)
class SchemaValidationResult:
    valid: bool
    category: str
    errors: list[str] = field(default_factory=list)


def schema_fields(policy: AnswerPolicy) -> tuple[str, ...]:
    return SCHEMA_FIELDS.get(policy.intent, SCHEMA_FIELDS["GENERAL_QUERY"])


def response_schema(policy: AnswerPolicy) -> dict[str, Any]:
    fields = schema_fields(policy)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["claims", "section_map", "evidence_insufficient"],
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["claim_id", "claim_text", "evidence_ids"],
                    "properties": {
                        "claim_id": {"type": "string"},
                        "claim_text": {"type": "string"},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                    },
                },
            },
            "section_map": {
                "type": "object",
                "additionalProperties": False,
                "required": list(fields),
                "properties": {
                    field_name: {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                    for field_name in fields
                },
            },
            "evidence_insufficient": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }


def response_schema_v2(policy: AnswerPolicy) -> dict[str, Any]:
    """Unsent candidate contract: scope remarks are separate from missing evidence."""
    schema=response_schema(policy)
    schema['title']='MINIMAL_ANSWER_V2_DRAFT'
    schema['required'].append('scope_notes')
    schema['properties']['scope_notes']={'type':'array','items':{'type':'string','minLength':1},'description':'范围、效力或背景备注；不是事实主张，也不自动表示本题未答完。'}
    schema['properties']['evidence_insufficient']['description']='只列原问题确实要求但证据未覆盖的对象及内容；不把未被问到的背景强行列为必要缺口。'
    schema['properties']['claims']['items']['properties']['claim_id']['pattern']=r'^C[1-9]\d*$'
    for field in schema['properties']['section_map']['properties'].values():
        field['items']['pattern']=r'^C[1-9]\d*$'
        field['description']='只放当前claims中已存在的事实编号；无对应事实时用空数组，备注放scope_notes。'
    return schema


def validate_response(
    payload: Any,
    policy: AnswerPolicy,
    allowed_source_ids: set[str],
) -> SchemaValidationResult:
    if not isinstance(payload, dict):
        return SchemaValidationResult(False, "E", ["response is not an object"])

    required = {"claims", "section_map", "evidence_insufficient"}
    unknown = set(payload) - required
    if unknown:
        return SchemaValidationResult(False, "C", [f"unknown fields: {sorted(unknown)}"])
    missing = sorted(required - set(payload))
    if missing:
        return SchemaValidationResult(False, "C", [f"missing fields: {missing}"])

    errors: list[str] = []
    claims = payload["claims"]
    if not isinstance(claims, list):
        errors.append("claims must be array")
        return SchemaValidationResult(False, "D", errors)

    section_map = payload["section_map"]
    if not isinstance(section_map, dict):
        errors.append("section_map must be object")
        return SchemaValidationResult(False, "E", errors)
    fields = set(schema_fields(policy))
    unknown_sections = set(section_map) - fields
    missing_sections = sorted(fields - set(section_map))
    if unknown_sections:
        errors.append(f"unknown section_map fields: {sorted(unknown_sections)}")
    if missing_sections:
        errors.append(f"missing section_map fields: {missing_sections}")
    for field_name in fields:
        value = section_map.get(field_name)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            errors.append(f"section_map.{field_name} must be string array")

    seen_claim_ids: set[str] = set()
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            errors.append(f"claims[{index - 1}] must be object")
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            errors.append(f"claims[{index - 1}].claim_id is missing")
        elif claim_id in seen_claim_ids:
            errors.append(f"duplicate claim_id: {claim_id}")
        else:
            seen_claim_ids.add(claim_id)
        if not isinstance(claim.get("claim_text"), str) or not claim.get("claim_text", "").strip():
            errors.append(f"claims[{index - 1}].claim_text is missing")
        evidence_ids = claim.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            errors.append(f"claims[{index - 1}].evidence_ids must be non-empty array")
        elif any(not isinstance(item, str) for item in evidence_ids):
            errors.append(f"claims[{index - 1}].evidence_ids must contain strings")
        elif any(item not in allowed_source_ids for item in evidence_ids):
            errors.append(f"claims[{index - 1}] references unknown evidence_id")

    mapped_claim_ids = {
        str(claim_id)
        for values in section_map.values()
        if isinstance(values, list)
        for claim_id in values
    }
    if any(claim_id not in seen_claim_ids for claim_id in mapped_claim_ids):
        errors.append("section_map references unknown claim_id")
    insufficient = payload.get("evidence_insufficient")
    all_sections_empty = all(
        isinstance(values, list) and not values
        for values in section_map.values()
    )
    if any(claim_id not in mapped_claim_ids for claim_id in seen_claim_ids) and not (
        all_sections_empty and isinstance(insufficient, list) and bool(insufficient)
    ):
        errors.append("claims contains unmapped claim_id")

    if not isinstance(insufficient, list) or any(not isinstance(item, str) for item in insufficient):
        errors.append("evidence_insufficient must be string array")

    if errors:
        category = "F" if any("evidence_id" in error for error in errors) else "E"
        if any("claims" in error and "array" in error for error in errors):
            category = "D"
        return SchemaValidationResult(False, category, errors)
    return SchemaValidationResult(True, "A", [])


def validate_response_v2(payload: Any, policy: AnswerPolicy, allowed_source_ids: set[str]) -> SchemaValidationResult:
    if not isinstance(payload,dict) or set(payload)!={'claims','section_map','evidence_insufficient','scope_notes'}:
        return SchemaValidationResult(False,'E',['V2 requires exact facts, mapping, gaps and scope_notes fields'])
    if not isinstance(payload['scope_notes'],list) or any(not isinstance(n,str) or not n.strip() for n in payload['scope_notes']):
        return SchemaValidationResult(False,'E',['scope_notes must be an array of nonblank strings'])
    checked=validate_response({k:v for k,v in payload.items() if k!='scope_notes'},policy,allowed_source_ids)
    if not checked.valid:return checked
    if any(not gap.strip() for gap in payload['evidence_insufficient']) or not payload['claims'] and not payload['evidence_insufficient']:
        return SchemaValidationResult(False,'E',['V2 requires nonblank gaps and an explicit gap when no claims are provided'])
    if any(set(c)!={'claim_id','claim_text','evidence_ids'} or not re.fullmatch(r'C[1-9]\d*',c['claim_id']) for c in payload['claims']):
        return SchemaValidationResult(False,'E',['V2 claims require exact fields and C-number identifiers'])
    return checked


def render_answer_text(payload: dict[str, Any], policy: AnswerPolicy) -> str:
    """Compatibility helper; final rendering uses citation_renderer with Evidence."""
    lines: list[str] = []
    section_map = payload.get("section_map", {})
    claims = {
        str(claim.get("claim_id")): claim
        for claim in payload.get("claims", [])
        if isinstance(claim, dict) and claim.get("claim_id")
    }
    for field_name in schema_fields(policy):
        lines.append(f"## {field_name}")
        ids = section_map.get(field_name, []) if isinstance(section_map, dict) else []
        if not ids:
            lines.append("- evidence_insufficient")
        for claim_id in ids:
            claim = claims.get(str(claim_id))
            if claim:
                lines.append(f"- {claim.get('claim_text', '')}")
    return "\n".join(lines)
