from app.retrieval.failure_taxonomy import classify
from app.retrieval.retrieval_trace import build_trace


def test_runtime_scope_mismatch_is_not_claimed_as_false_reject_without_gold():
    result = classify(answer_status="SOURCE_SCOPE_MISSING", bundle_status="SOURCE_SCOPE_MISSING", candidate_count=2, verified_evidence_count=0, scope_mismatch_in_top=True)
    assert result["failure_code"] == "SCOPE_MISMATCH"
    assert "SCOPE_MISMATCH_FALSE_REJECT" not in result["candidate_codes"]


def test_trace_records_field_level_scope_and_reject_reason():
    result = {
        "answer_status": "INSUFFICIENT_EVIDENCE", "answer_mode": "SAFE_REFUSAL", "citations": [], "claims": [], "latency": {},
        "debug": {"query_plan": {"query_type": "AGGREGATION_QUERY", "project": [], "year": ["2025"], "scope_constraints": {"year": ["2025"]}}, "document_candidates": [], "section_candidates": [], "table_candidates": [], "evidence_bundle": {"bundle_status": "INSUFFICIENT_EVIDENCE", "failure_reason": "EVIDENCE_INSUFFICIENT", "verified_evidence": [], "candidate_evidence": [{"evidence_id": "E1", "candidate_rank": 1, "role": "CONTEXT_ONLY", "scope": {"year": "MATCH", "project": "MISMATCH"}, "scope_reason": "fixture", "why_context_only": "wrong project"}]}},
    }
    trace = build_trace(query_run_id="QR1", question="问题", resolved_question="问题", result=result)
    row = trace["stages"]["evidence_validation"][0]
    assert row["scope_result"] == "MISMATCH"
    assert row["scope_mismatched"] == ["project"]
    assert row["reject_reason"] == "wrong project"
