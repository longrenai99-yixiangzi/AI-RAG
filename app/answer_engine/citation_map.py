from __future__ import annotations

from dataclasses import dataclass, field

from .evidence_selector import EvidenceBundle


@dataclass(slots=True)
class ClaimEvidence:
    claim_id: str
    claim_text: str
    evidence_ids: list[str]
    support_level: str


@dataclass(slots=True)
class CitationMap:
    claims: list[ClaimEvidence] = field(default_factory=list)
    valid: bool = True
    errors: list[str] = field(default_factory=list)


def build_citation_map(bundle: EvidenceBundle) -> CitationMap:
    claims = [
        ClaimEvidence(
            claim_id=f"C{index}",
            claim_text=f"证据摘录：{item.excerpt[:240]}",
            evidence_ids=[item.source_id],
            support_level=item.evidence_status,
        )
        for index, item in enumerate(bundle.items, start=1)
    ]
    result = CitationMap(claims=claims)
    return validate_citation_map(result, bundle)


def validate_citation_map(citation_map: CitationMap, bundle: EvidenceBundle) -> CitationMap:
    allowed = {item.source_id for item in bundle.items}
    errors: list[str] = []
    for claim in citation_map.claims:
        if not claim.evidence_ids:
            errors.append(f"{claim.claim_id} 没有关联 Evidence")
        for evidence_id in claim.evidence_ids:
            if evidence_id not in allowed:
                errors.append(f"{claim.claim_id} 引用了不存在的 {evidence_id}")
    citation_map.errors = errors
    citation_map.valid = not errors
    return citation_map
