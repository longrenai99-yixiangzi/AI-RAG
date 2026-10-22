from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.answer_engine.answer_policy import AnswerPolicy
from app.answer_engine.evidence_selector import EvidenceBundle

from .response_schema import schema_fields


@dataclass(slots=True)
class CitationRenderResult:
    answer_text: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    rendered_claim_ids: list[str] = field(default_factory=list)
    visible_section_ids: list[str] = field(default_factory=list)


def render_claim_citations(
    payload: dict[str, Any],
    policy: AnswerPolicy,
    evidence: EvidenceBundle,
) -> CitationRenderResult:
    """Render only verified claim_text and evidence_ids; never summarize facts."""
    allowed = {item.source_id for item in evidence.items}
    claims = payload.get("claims")
    section_map = payload.get("section_map")
    if not isinstance(claims, list) or not isinstance(section_map, dict):
        return CitationRenderResult("", False, ["minimal answer schema is incomplete"])

    claim_map = {
        str(claim.get("claim_id")): claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("claim_id")
    }
    errors: list[str] = []
    lines: list[str] = []
    rendered: list[str] = []
    visible_sections: list[str] = []
    for field_name in schema_fields(policy):
        lines.append(f"## {field_name}")
        claim_ids = section_map.get(field_name)
        if not isinstance(claim_ids, list):
            errors.append(f"section_map.{field_name} is not an array")
            continue
        if not claim_ids:
            lines.append("- evidence_insufficient")
            continue
        section_rendered = 0
        for claim_id in claim_ids:
            claim_key = str(claim_id)
            claim = claim_map.get(claim_key)
            if claim is None:
                errors.append(f"{field_name} references missing claim {claim_key}")
                continue
            evidence_ids = claim.get("evidence_ids")
            if not isinstance(evidence_ids, list) or not evidence_ids:
                errors.append(f"claim {claim_key} has no evidence")
                continue
            invalid = [str(item) for item in evidence_ids if str(item) not in allowed]
            if invalid:
                errors.append(f"claim {claim_key} references invalid evidence {invalid}")
                continue
            text = claim.get("claim_text")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"claim {claim_key} has empty claim_text")
                continue
            citations = " ".join(f"[{source_id}]" for source_id in evidence_ids)
            lines.append(f"- {text.strip()} {citations}")
            rendered.append(claim_key)
            section_rendered += 1
        if section_rendered:
            visible_sections.append(field_name)

    unrendered = sorted(set(claim_map) - set(rendered))
    if unrendered:
        errors.append(f"claims are not visible in section_map: {unrendered}")
    return CitationRenderResult(
        answer_text="\n".join(lines),
        valid=not errors,
        errors=errors,
        rendered_claim_ids=rendered,
        visible_section_ids=visible_sections,
    )
