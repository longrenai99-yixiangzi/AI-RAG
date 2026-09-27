from types import SimpleNamespace

import app.trial.v2 as v2
import app.trial.batch as batch
from app.trial.knowledge_store import TrialKnowledgeStore, source_id_for_path


def test_candidate_source_preview_search_and_answer_share_frozen_runtime(tmp_path, monkeypatch):
    path = str(tmp_path / "2026-project.md")
    source_id = source_id_for_path(path)
    record = {"evidence_id": "E1", "source_id": source_id, "source_path": path, "source_version": "frozen-hash", "file_name": "2026-project.md", "raw_text": "2026 项目事实", "location": {"line_start": 1}}
    candidate = SimpleNamespace(atomic={"E1": record})
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2, "_candidate_primary_runtime", lambda: (candidate, None))
    monkeypatch.setattr(v2, "_engine_instance", lambda: (_ for _ in ()).throw(AssertionError("V1 must not be read")))
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", TrialKnowledgeStore(tmp_path / "state.json"))
    monkeypatch.setattr(v2, "_search_candidate_atomic_evidence", lambda _candidate, _query, _limit: [{"score": 1, "record": record}])
    monkeypatch.setattr(v2, "_candidate_primary_answer", lambda _question: {"debug": {"runtime_pointer": {"mode": v2.V262_CANDIDATE_MODE, "candidate_hash": "frozen-hash"}}})

    source = v2.knowledge_source_evidence(source_id)["source"]
    assert source["runtime_source_version"] == "frozen-hash"
    assert v2.knowledge_source_evidence(source_id)["items"][0]["source_version"] == "frozen-hash"
    assert v2.knowledge_search("2026 项目")["items"][0]["evidence"]["source_id"] == source_id
    assert v2._answer_current_runtime("2026 项目?")["debug"]["runtime_pointer"]["candidate_hash"] == "frozen-hash"
    assert v2._runtime_has_source(str(tmp_path / "2025-project.md")) is False


def test_cited_evidence_can_be_previewed_after_first_fifty_chunks(tmp_path, monkeypatch):
    path = str(tmp_path / "many-chunks.md")
    source_id = source_id_for_path(path)
    records = {f"E{index}": {"evidence_id": f"E{index}", "source_id": source_id, "source_path": path, "source_version": "source-sha", "raw_text": f"chunk {index}"} for index in range(60)}
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2, "_candidate_primary_runtime", lambda: (SimpleNamespace(atomic=records), None))
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", TrialKnowledgeStore(tmp_path / "state.json"))
    assert "E55" not in {item["evidence_id"] for item in v2.knowledge_source_evidence(source_id, limit=50)["items"]}
    exact = v2.knowledge_source_evidence(source_id, evidence_id="E55")["items"]
    assert [(item["evidence_id"], item["source_version"]) for item in exact] == [("E55", "source-sha")]


def test_pending_candidate_is_not_active_and_invalidates_on_source_change(tmp_path):
    path = tmp_path / "source.md"
    path.write_text("第一版", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(path)
    feedback, _ = store.record_feedback({"question": "问题", "expected_answer": "第一版答案", "source_id": source["source_id"]}, "review")
    reviewed, knowledge = store.review_feedback(feedback["feedback_id"], decision="APPROVE", source_id=source["source_id"], location="第1行", required_terms=["第一版"], reviewer="owner", activate=False)
    assert reviewed["status"] == knowledge["status"] == "PENDING_CANDIDATE"
    assert store.active_knowledge() == []
    assert all(item["type"] != "KNOWLEDGE" for item in store.search("第一版答案"))
    assert store.rollback_knowledge(knowledge["knowledge_id"], target_version=1, reviewer="owner", reason="恢复", activate=False)["status"] == "PENDING_CANDIDATE"
    path.write_text("第二版", encoding="utf-8")
    store.register_source(path)
    assert store.feedback(feedback["feedback_id"])["status"] == "REVIEW_REQUIRED"
    assert store.overview()["pending_candidate_knowledge"] == 0


def test_pending_candidate_withdrawal_requires_new_review(tmp_path):
    path = tmp_path / "source.md"
    path.write_text("原文", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(path)
    feedback, _ = store.record_feedback({"question": "问题", "expected_answer": "答案", "source_id": source["source_id"]}, "review")
    store.review_feedback(feedback["feedback_id"], decision="APPROVE", source_id=source["source_id"], location="", required_terms=[], reviewer="owner", activate=False)
    store.withdraw_source(source["source_id"], reviewer="owner")
    assert store.feedback(feedback["feedback_id"])["status"] == "REVIEW_REQUIRED"
    assert store.overview()["pending_candidate_knowledge"] == 0


def test_search_excludes_registered_source_outside_current_runtime(tmp_path, monkeypatch):
    path = tmp_path / "2025-project.md"
    path.write_text("2025 项目事实", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    store.register_source(path)
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", store)
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V1_PRIMARY_MODE)
    monkeypatch.setattr(v2, "_runtime_evidence_records", lambda: [])
    monkeypatch.setattr(v2, "_engine_instance", lambda: SimpleNamespace(atomic={}))
    assert v2.knowledge_search("2025-project")["items"] == []


def test_feedback_regression_uses_current_candidate_identity(tmp_path, monkeypatch):
    path = tmp_path / "2026-project.md"
    path.write_text("2026 项目事实", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(path)
    store.mark_indexed(source["source_id"], source_hash_value=source["current_hash"], parse_status="parsed", chunk_count=1)
    feedback, _ = store.record_feedback({"question": "2026 项目事实是什么？", "expected_answer": "2026 项目事实", "source_id": source["source_id"], "required_terms": ["项目事实"]}, "review")
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", store)
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2, "_runtime_evidence_records", lambda: [{"source_id": source["source_id"], "source_path": str(path), "source_version": source["current_hash"]}])
    citation = {"source_id": "V262-frozen-source", "source_path": str(path), "source_version": source["current_hash"]}
    monkeypatch.setattr(v2, "_candidate_primary_answer", lambda _question: {"answer_status": "ANSWERED", "answer": "2026 项目事实", "citations": [citation], "debug": {"runtime_pointer": {"mode": v2.V262_CANDIDATE_MODE, "candidate_hash": "frozen-hash"}}})
    monkeypatch.setattr(v2, "_engine_instance", lambda: (_ for _ in ()).throw(AssertionError("V1 must not answer")))
    run = v2.run_feedback_workflow_regression(feedback["feedback_id"], v2.ReviewedFeedbackRequest(decision="APPROVE"))["regression"]
    assert run["regression_status"] == "PASSED"
    assert run["runtime_pointer"]["candidate_hash"] == "frozen-hash"
    assert run["citation_source_id"] == "V262-frozen-source"
    citation["source_version"] = "other-version"
    assert v2.run_feedback_workflow_regression(feedback["feedback_id"], v2.ReviewedFeedbackRequest())["regression"]["regression_status"] == "FAILED"
    citation.update({"source_version": source["current_hash"], "source_path": str(tmp_path / "2025-project.md")})
    assert v2.run_feedback_workflow_regression(feedback["feedback_id"], v2.ReviewedFeedbackRequest())["regression"]["regression_status"] == "FAILED"


def test_batch_regression_uses_same_candidate_answer_entry(monkeypatch):
    case = {"case_id": "B1", "question": "2026 项目事实？", "expected_source_path": "synthetic/2026.md", "expected_source_location": "", "required_terms": ["事实"]}
    monkeypatch.setattr(v2, "_read_jsonl", lambda _path: [case])
    monkeypatch.setattr(v2, "_append_jsonl", lambda _path, _row: None)
    monkeypatch.setattr(v2, "_runtime_has_source", lambda _path: True)
    monkeypatch.setattr(v2, "_answer_current_runtime", lambda _question: {"answer_status": "ANSWERED", "answer": "事实", "citations": [{"source_path": "synthetic/2026.md"}], "debug": {"runtime_pointer": {"mode": v2.V262_CANDIDATE_MODE, "candidate_hash": "frozen-hash"}}})
    result = batch.run_batch_regressions(batch.BatchRunRequest(case_ids=["B1"]))
    assert result["runs"][0]["runtime_pointer"]["candidate_hash"] == "frozen-hash"
