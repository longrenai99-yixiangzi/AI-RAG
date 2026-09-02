from __future__ import annotations

from dataclasses import dataclass, field
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
