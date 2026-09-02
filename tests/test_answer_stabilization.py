from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.evidence_selector import EvidenceBundle, EvidenceItem
from app.answer_engine.llm.answer_generator import _answer_status
from app.answer_engine.llm.citation_renderer import render_claim_citations
from app.answer_engine.llm.response_schema import validate_response


def _evidence() -> EvidenceBundle:
    return EvidenceBundle(
        status="SELECTED",
        items=[
            EvidenceItem(
                source_id="S1",
                chunk_id="chunk-1",
                document_id="doc-1",
                file_name="制度.md",
                source_path="D:/设计管理/制度.md",
                document_role="正式制度",
                authority_level="L1",
                usage_scene="制度执行",
                location={"line_start": 1, "line_end": 8},
                excerpt="组织评审并形成闭环。",
                retrieval_score=1.0,
                selection_score=1.0,
                evidence_status="DIRECT",
            ),
            EvidenceItem(
                source_id="S2",
                chunk_id="chunk-2",
                document_id="doc-2",
                file_name="指南.md",
                source_path="D:/设计管理/指南.md",
                document_role="管理指南",
                authority_level="L2",
                usage_scene="管理指导",
                location={"line_start": 9, "line_end": 16},
                excerpt="明确责任人与完成时限。",
                retrieval_score=0.8,
                selection_score=0.8,
                evidence_status="DIRECT",
            ),
        ],
    )


def test_deterministic_renderer_uses_claim_evidence_ids_only() -> None:
    policy = policy_for_intent("POLICY_QUERY")
    payload = {
        "claims": [
            {"claim_id": "C1", "claim_text": "先组织评审。", "evidence_ids": ["S1"]},
            {"claim_id": "C2", "claim_text": "再明确时限。", "evidence_ids": ["S2"]},
        ],
        "section_map": {
            "conclusion": ["C1"],
            "management_requirements": ["C2"],
            "evidence": [],
            "scope_or_exceptions": [],
        },
        "evidence_insufficient": [],
    }

    schema = validate_response(payload, policy, {"S1", "S2"})
    rendered = render_claim_citations(payload, policy, _evidence())

    assert schema.valid
    assert rendered.valid
    assert "先组织评审。 [S1]" in rendered.answer_text
    assert "再明确时限。 [S2]" in rendered.answer_text


def test_claim_with_unknown_evidence_is_rejected() -> None:
    policy = policy_for_intent("POLICY_QUERY")
    payload = {
        "claims": [
            {"claim_id": "C1", "claim_text": "未经证实。", "evidence_ids": ["S9"]},
        ],
        "section_map": {
            "conclusion": ["C1"],
            "management_requirements": [],
            "evidence": [],
            "scope_or_exceptions": [],
        },
        "evidence_insufficient": [],
    }

    result = validate_response(payload, policy, {"S1", "S2"})

    assert not result.valid
    assert result.category == "F"


def test_unassigned_claim_is_rejected_without_inventing_a_section() -> None:
    policy = policy_for_intent("POLICY_QUERY")
    payload = {
        "claims": [
            {"claim_id": "C1", "claim_text": "可核查事实。", "evidence_ids": ["S1"]},
        ],
        "section_map": {
            "conclusion": [],
            "management_requirements": [],
            "evidence": [],
            "scope_or_exceptions": [],
        },
        "evidence_insufficient": [],
    }

    rendered = render_claim_citations(payload, policy, _evidence())

    assert not rendered.valid
    assert "not visible in section_map" in rendered.errors[0]


def test_empty_sections_are_no_evidence_not_generated() -> None:
    policy = policy_for_intent("POLICY_QUERY")
    payload = {
        "claims": [
            {"claim_id": "C1", "claim_text": "仅作为未使用证据。", "evidence_ids": ["S1"]},
        ],
        "section_map": {
            "conclusion": [],
            "management_requirements": [],
            "evidence": [],
            "scope_or_exceptions": [],
        },
        "evidence_insufficient": ["当前证据不足以回答。"],
    }
    schema = validate_response(payload, policy, {"S1", "S2"})
    rendered = render_claim_citations(payload, policy, _evidence())
    validation = type("Validation", (), {"valid": True})()

    assert schema.valid
    assert _answer_status(schema, rendered, validation, payload) == "NO_EVIDENCE"
