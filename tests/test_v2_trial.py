import json

import app.trial.v2 as v2
from scripts.build_verified_evidence_bundle_v1 import _direct_candidate
from app.trial.v2 import _closure_status, _core_phrases, _display_location, _evaluate_feedback_regression, _feedback_profile, _friendly_status, _with_exact_atomic_rescue


def test_v2_status_is_user_friendly():
    assert _friendly_status("CONFLICTING_ANSWER") == "资料存在冲突"
    assert _friendly_status("SOURCE_SCOPE_MISSING") == "当前知识范围暂无可靠来源"


def test_v2_docx_table_citation_keeps_table_and_row_range():
    assert _display_location({"table": 11, "row_start": 4, "row_end": 37}) == "表11，第4-37行"


def test_exact_core_phrase_rescue_adds_existing_shadow_evidence_without_query_injection():
    question = "二级设计进度计划，包含哪些节点"
    wrong = {"evidence_id": "E1", "document_id": "D1", "section_id": "S1", "text": "设计关键节点计划需要考虑方案比选。", "source_path": "D:/wrong.docx", "file_name": "wrong.docx"}
    exact = {"evidence_id": "E2", "document_id": "D2", "section_id": "S2", "text": "二级设计进度计划：应包括初步设计完成等节点。", "source_path": "D:/manual.pdf", "file_name": "manual.pdf", "location": {"page": 19}, "granularity": "frozen_chunk", "lineage_status": "LINEAGE_NOT_APPLICABLE"}
    retrieval = {"atomic_candidates": [{"evidence_id": "E1", "rank": 1}]}
    rescued = _with_exact_atomic_rescue(retrieval, question, [wrong, exact])
    assert _core_phrases(question) == ["二级设计进度计划"]
    assert rescued["atomic_candidates"][0]["evidence_id"] == "E2"
    assert rescued["atomic_candidates"][0]["candidate_origin"] == "ATOMIC_EXACT_RESCUE"


def test_every_negative_feedback_type_creates_a_review_candidate():
    for feedback_type in ("回答不完整", "答案错误", "引用不对", "没有回答我的问题", "资料缺失", "答案冲突"):
        assert _feedback_profile(feedback_type)["creates_candidate"] is True
    assert _feedback_profile("回答正确")["creates_candidate"] is False


def test_feedback_regression_requires_source_and_terms_and_never_uses_owner_answer_as_runtime_input():
    case = {"candidate_id": "FG-1", "case_id": "RG-1", "question": "二级设计进度计划包含哪些节点？", "expected_source_path": "D:/manual.pdf", "expected_source_location": "第19页", "required_terms": ["初步设计完成"], "owner_asserted_answer": "不参与运行时", "ready": True}
    result = {"answer_status": "ANSWERED", "answer": "结论：二级设计进度计划应包括初步设计完成。", "citations": [{"citation_id": "S1", "source_path": "D:/manual.pdf", "display_location": "第19页"}], "provider_http_requests": 0}
    run = _evaluate_feedback_regression(case, result, "reviewer-001")
    assert run["regression_status"] == "PASSED"
    assert run["gold_runtime_injection"] == 0
    assert _closure_status({"decision": "APPROVE"}, case, run) == "CLOSED"


def test_feedback_to_review_to_shadow_regression_closes_without_formal_publish(tmp_path, monkeypatch):
    growth = tmp_path / "growth"
    trial = tmp_path / "trial"
    monkeypatch.setattr(v2, "GROWTH", growth)
    monkeypatch.setattr(v2, "TRIAL", trial)
    monkeypatch.setattr(v2, "FEEDBACK_CANDIDATES", growth / "feedback_growth_candidates.jsonl")
    monkeypatch.setattr(v2, "FEEDBACK_CASES", growth / "feedback_regression_cases.jsonl")
    monkeypatch.setattr(v2, "FEEDBACK_RUNS", growth / "feedback_regression_runs.jsonl")
    monkeypatch.setattr(v2, "_source_runtime_status", lambda _: "INDEXED_SHADOW")
    v2._append_jsonl(trial / "trial_audit.jsonl", {"query_id": "Q-1", "question": "二级设计进度计划包含哪些节点？", "answer_status": "ANSWERED", "document_ids": [], "evidence_ids": []})
    feedback = v2.feedback(v2.V2FeedbackRequest(query_id="Q-1", feedback_type="回答不完整", source_path="D:/manual.pdf", source_location="第19页", required_terms=["初步设计完成"], expected_answer="仅供审核"))
    candidate_id = feedback["feedback_event"]["growth_candidate_id"]
    review = v2.growth_review(v2.GrowthReviewRequest(candidate_id=candidate_id, decision="APPROVE", confirmed_source_path="D:/manual.pdf", confirmed_source_location="第19页", required_terms=["初步设计完成"]))
    assert review["regression_case"]["ready"] is True

    class Engine:
        def answer(self, question, *, detect_growth):
            assert question == "二级设计进度计划包含哪些节点？"
            assert detect_growth is False
            return {"answer_status": "ANSWERED", "answer": "结论：二级设计进度计划包括初步设计完成。", "citations": [{"citation_id": "S1", "source_path": "D:/manual.pdf", "display_location": "第19页"}], "provider_http_requests": 0}

    monkeypatch.setattr(v2, "_engine_instance", lambda: Engine())
    result = v2.growth_regression(v2.GrowthRegressionRequest(candidate_id=candidate_id))
    assert result["regression"]["regression_status"] == "PASSED"
    closure = v2.feedback_closures()["closures"][0]
    assert closure["closure_status"] == "CLOSED"
    assert result["automatic_knowledge_publish"] == 0


def test_source_closure_gate_normalizes_quotes_and_rejects_structural_terms(monkeypatch):
    monkeypatch.setattr(v2, "_source_runtime_status", lambda _: "SOURCE_IDENTIFIED")
    case = v2._case_with_readiness({"expected_source_path": '"D:/outside/cover.docx"', "required_terms": ["目录"], "requested_required_terms": ["目录"]})
    assert case["expected_source_path"] == "D:\\outside\\cover.docx"
    assert case["ready"] is False
    assert case["invalid_required_terms"] == ["目录"]
    assert v2._closure_status({"decision": "APPROVE"}, case, {"regression_status": "FAILED"}) == "SOURCE_CLOSURE_REQUIRED"


def test_same_file_name_at_a_different_path_does_not_inherit_shadow_approval(tmp_path, monkeypatch):
    register = tmp_path / "source_closure.jsonl"
    register.write_text('{"correct_source_path":"D:\\\\work\\\\second-company\\\\manual.pdf","correct_source_file_name":"manual.pdf","source_status":"VERIFIED_RUNTIME"}\n', encoding="utf-8")
    monkeypatch.setattr(v2, "SOURCE_CLOSURE_REGISTER", register)
    assert v2._declared_source_status("D:/work/design-support/manual.pdf") == "SOURCE_IDENTIFIED"


def test_role_fact_candidate_can_promote_complete_role_evidence_beyond_top_five():
    candidate = {"candidate_rank": 6, "lineage_status": "LINEAGE_NOT_APPLICABLE", "scope": {}, "text": "阶段性设计成果审查由设计支持机构牵头，项目部参与。"}
    plan = {"original_question": "阶段性设计成果审查是由谁组织，谁参与？", "organization": [], "project": [], "year": [], "specialty": [], "metric": []}
    assert _direct_candidate(candidate, plan) is True


def test_negative_feedback_is_registered_as_trial_question_without_becoming_gold(tmp_path, monkeypatch):
    registry = tmp_path / "trial_feedback_questions.jsonl"
    monkeypatch.setattr(v2, "TRIAL_FEEDBACK_QUESTIONS", registry)
    event = {"source_path": "", "source_location": "", "required_terms": [], "feedback_type": "资料缺失"}
    candidate = {"candidate_id": "FG-test", "question": "工业厂房设备基础与结构梁柱错位有什么风险？"}
    v2._register_trial_question(event, candidate)
    row = json.loads(registry.read_text(encoding="utf-8"))
    assert row["registry_set"] == "TRIAL_QUESTION"
    assert row["source_governance_status"] == "SOURCE_UNKNOWN"
    assert row["regression_enabled"] is False
    assert row["runtime_input"] is False
