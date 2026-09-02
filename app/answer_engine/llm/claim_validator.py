from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.answer_engine.evidence_selector import EvidenceBundle


SOURCE_PATTERN = re.compile(r"\[(S\d+)\]")


@dataclass(slots=True)
class ClaimValidationResult:
    valid: bool
    unsupported_claims: int
    invalid_source_ids: list[str]
    missing_evidence_claims: int
    errors: list[str]


def validate_claims(
    answer_text: str,
    claims: Iterable[dict[str, Any]],
    evidence: EvidenceBundle,
) -> ClaimValidationResult:
    allowed = {item.source_id for item in evidence.items}
    invalid_source_ids: set[str] = set()
    unsupported = 0
    missing = 0
    errors: list[str] = []
    for claim in claims:
        evidence_ids = claim.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            missing += 1
            unsupported += 1
            errors.append("claim has no evidence_ids")
            continue
        invalid = [str(item) for item in evidence_ids if str(item) not in allowed]
        if invalid:
            invalid_source_ids.update(invalid)
            unsupported += 1
            errors.append(f"claim references invalid sources: {invalid}")
    cited = set(SOURCE_PATTERN.findall(answer_text))
    invalid_answer_sources = sorted(cited - allowed)
    if invalid_answer_sources:
        invalid_source_ids.update(invalid_answer_sources)
        errors.append(f"answer references invalid sources: {invalid_answer_sources}")
    if claims and not cited:
        errors.append("answer contains no inline citation markers")
    claim_sources = {
        str(source_id)
        for claim in claims
        for source_id in (claim.get("evidence_ids") or [])
    }
    missing_inline_citations = sorted(claim_sources - cited)
    if missing_inline_citations:
        errors.append(
            f"claim citations are not present in answer text: {missing_inline_citations}"
        )
    return ClaimValidationResult(
        valid=not errors,
        unsupported_claims=unsupported,
        invalid_source_ids=sorted(invalid_source_ids),
        missing_evidence_claims=missing,
        errors=errors,
    )
