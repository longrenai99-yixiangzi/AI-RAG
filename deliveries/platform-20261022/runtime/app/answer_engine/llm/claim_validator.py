from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.answer_engine.evidence_selector import EvidenceBundle


SOURCE_PATTERN = re.compile(r"\[(S\d+)\]")


def check_source_units(claims, evidence, *, allow_connector_omission=False, allow_sentence_span=False):
    """Conservative textual support, not general entailment or business verification."""
    def parts(text):return [re.sub(r'\s+','',p) for p in re.split(r'[，,。；;！？!?\n]+',text) if p.strip()]
    def without_connector(clause):return re.sub(r'^(?:因此|因而|所以)(?!说)', '', clause)
    sources={item.source_id:item.excerpt for item in evidence.items};checks=[]
    for claim in claims:
        ids=claim.get('evidence_ids') or [];text=claim.get('claim_text','');status='TEXT_NOT_MATCHED'
        if len(ids)!=1 or ids[0] not in sources:status='SOURCE_BINDING_UNVERIFIED'
        else:
            wanted=parts(text);source=sources[ids[0]];matched=False;context_missing=False;normalized_match=False
            sentences=[s for s in re.split(r'[。；;！？!?\n]+',source) if s.strip()]
            span=max(1,len([s for s in re.split(r'[。；;！？!?\n]+',text) if s.strip()])) if allow_sentence_span else 1
            for index in range(max(0,len(sentences)-span+1)):
                sentence='。'.join(sentences[index:index+span])
                clauses=parts(sentence)
                for start in range(len(clauses)):
                    actual=clauses[start:start+len(wanted)]
                    exact=actual==wanted
                    normalized=allow_connector_omission and [without_connector(p) for p in actual]==wanted
                    if not wanted or not (exact or normalized):continue
                    before=clauses[:start];after=clauses[start+len(wanted):]
                    # shortcut: adjacent explicit scope labels only; implicit cross-sentence scope needs review.
                    if index and re.match(r'\s*(?:适用前提|适用条件|前提条件|仅当|只有|除非|仅在)',sentences[index-1]):before=parts(sentences[index-1])+before
                    if index+span<len(sentences) and re.match(r'\s*(?:但|不过|除外|仅限|不适用|否则|前提|须经|需经|必须)',sentences[index+span]):after+=parts(sentences[index+span])
                    omitted=any(re.search(r'^(?:适用前提|适用条件|前提条件|如果|若|当|仅在|仅当|只有|除非)|(?:条件下|前提下|审批通过后|批准后|验收后)',without_connector(p)) for p in before)
                    omitted|=any(re.search(r'^(?:但|不过|除外|仅限|不适用|不得|严禁|需经|须经|应经|必须|须|需|应当|否则|前提|如果|若|当|仅当|只有|除非)',without_connector(p)) for p in after)
                    context_missing|=omitted
                    if not omitted:
                        matched=True
                        normalized_match|=not exact
            if matched:status='SOURCE_UNITS_CONNECTOR_OMITTED' if normalized_match else 'SOURCE_UNITS_MATCHED'
            elif context_missing:status='CONDITION_CONTEXT_OMITTED'
            elif set(re.findall(r'\d+(?:[.,]\d+)?',text))-set(re.findall(r'\d+(?:[.,]\d+)?',source)):status='NUMBER_NOT_IN_CITED_SOURCE'
        checks.append({'claim_id':claim.get('claim_id'),'status':status,'evidence_ids':ids})
    return {'valid':bool(claims) and all(r['status'] in {'SOURCE_UNITS_MATCHED','SOURCE_UNITS_CONNECTOR_OMITTED'} for r in checks),'checks':checks,'scope':'SOURCE_TEXT_UNITS_NOT_SEMANTIC_VERIFICATION'}


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
