from app.knowledge_growth_v1 import candidate_for_trace, merge_candidate


def test_verified_answer_does_not_create_growth_candidate():
    trace = _trace("ANSWERED", "VERIFIED")
    assert candidate_for_trace(trace) is None


def test_source_scope_missing_is_governance_candidate():
    candidate = candidate_for_trace(_trace("SOURCE_SCOPE_MISSING", "SOURCE_SCOPE_MISSING"))
    assert candidate["growth_type"] == "KNOWLEDGE_GROWTH"
    assert candidate["governance_status"] == "REQUIRES_SOURCE_GOVERNANCE_REVIEW"
    assert candidate["review_status"] == "PROPOSED"


def test_conflict_is_not_mislabeled_as_missing_knowledge():
    candidate = candidate_for_trace(_trace("CONFLICTING_ANSWER", "CONFLICTING_EVIDENCE"))
    assert candidate["growth_type"] == "CONFLICT_REVIEW_CANDIDATE"
    assert candidate["priority"] == "P0"


def test_partial_candidate_retains_only_insufficient_subquestion_gap():
    trace = _trace("PARTIAL_ANSWER", "VERIFIED_PARTIAL")
    trace["bundle"]["coverage_map"] = [{"subquestion": "条件统计", "coverage_status": "EVIDENCE_INSUFFICIENT"}]
    candidate = candidate_for_trace(trace)
    assert candidate["failure_type"] == "INSUFFICIENT_EVIDENCE"
    assert candidate["knowledge_gap"] == "条件统计"


def test_duplicate_candidate_merges_occurrence_count():
    candidate = candidate_for_trace(_trace("SOURCE_SCOPE_MISSING", "SOURCE_SCOPE_MISSING"))
    merged = merge_candidate(candidate, candidate)
    assert merged["occurrence_count"] == 2


def _trace(answer_status, bundle_status):
    return {"question_id": "Q-1", "question": "测试问题", "answer": {"answer_status": answer_status}, "bundle": {"bundle_status": bundle_status, "coverage_map": [], "candidate_evidence": [], "verified_evidence": [], "conflicting_evidence": []}}
