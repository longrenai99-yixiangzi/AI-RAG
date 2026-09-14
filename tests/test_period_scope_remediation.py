from scripts.build_verified_evidence_bundle_v1 import _direct_candidate, _period_status, _same_scope_conflicts, _scope
from app.retrieval.query_planner_v1 import plan_query


def _scope_for(plan: dict, file_name: str, text: str) -> dict[str, str]:
    scope, _ = _scope(
        plan,
        {"file_name": file_name, "source_path": f"[LOCAL_PATH_REDACTED]"},
        {},
        {"file_name": file_name, "source_path": f"[LOCAL_PATH_REDACTED]", "text": text},
    )
    return scope


def _candidate(evidence_id: str, scope: dict[str, str], text: str) -> dict:
    return {
        "evidence_id": evidence_id,
        "scope": scope,
        "text": text,
        "lineage_status": "LINEAGE_CONFIRMED",
        "link_only": False,
        "negative_questions": [],
        "candidate_rank": 1,
        "document_role": "",
    }


def test_period_scope_separates_h1_and_full_year_facts() -> None:
    h1_plan = plan_query("2025 \u5e74\u4e0a\u534a\u5e74\u4e8c\u516c\u53f8\u4e09\u4f18\u4e00\u521b\u603b\u4f53\u521b\u6548\u7387\u662f\u591a\u5c11\uff1f").to_dict()
    h1_scope = _scope_for(h1_plan, "2025\u5e74\u534a\u5e74\u603b\u7ed3.md", "\u4e0a\u534a\u5e74\u4e09\u4f18\u4e00\u521b\u603b\u4f53\u521b\u6548\u73873.31%")
    annual_scope = _scope_for(h1_plan, "2025\u5e74\u5e74\u5ea6\u603b\u7ed3.md", "2025\u5e74\u4e09\u4f18\u4e00\u521b\u6574\u4f53\u521b\u6548\u73873.33%")
    assert h1_plan["period"] == "H1"
    assert h1_scope["period"] == "MATCH"
    assert annual_scope["period"] == "MISMATCH"
    h1 = _candidate("h1", {"organization": "MATCH", "year": "MATCH", "metric": "MATCH", "period": "MATCH"}, "\u4e0a\u534a\u5e74\u603b\u4f53\u521b\u6548\u73873.31%")
    annual = _candidate("annual", {"organization": "MATCH", "year": "MATCH", "metric": "MATCH", "period": "MISMATCH"}, "\u5168\u5e74\u603b\u4f53\u521b\u6548\u73873.33%")
    assert _same_scope_conflicts([h1, annual], h1_plan) == {}
    assert _direct_candidate(h1, h1_plan)
    assert not _direct_candidate(annual, h1_plan)


def test_period_unspecified_query_keeps_conflict_guard() -> None:
    plan = plan_query("2025 \u5e74\u4e8c\u516c\u53f8\u4e09\u4f18\u4e00\u521b\u603b\u4f53\u521b\u6548\u7387\u662f\u591a\u5c11\uff1f").to_dict()
    first = _candidate("first", {"organization": "MATCH", "year": "MATCH", "metric": "MATCH", "period": "NOT_APPLICABLE"}, "\u603b\u4f53\u521b\u6548\u73873.31%")
    second = _candidate("second", {"organization": "MATCH", "year": "MATCH", "metric": "MATCH", "period": "NOT_APPLICABLE"}, "\u603b\u4f53\u521b\u6548\u73873.33%")
    assert plan["period"] == ""
    assert set(_same_scope_conflicts([first, second], plan)) == {"first", "second"}
