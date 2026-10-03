from types import SimpleNamespace

import numpy as np

import app.trial.v2 as v2
import app.trial.batch as batch
from app.trial.knowledge_store import TrialKnowledgeStore, source_id_for_path
from app.trial.live_shadow_v25 import _referenced_knowledge_card_candidates, _filter_retired_source_versions, _chunk_source_location, V25LiveShadow


def test_chunk_preserves_parsed_row_only_for_same_document_and_version():
    chunk = {"atomic_evidence_ids": ["A"], "document_id": "D", "source_version": "sha", "section_path": "Sheet1"}
    parsed = {"A": {"document_id": "D", "sha256": "sha", "location": {"row_start": 7, "row_end": 7}}}
    assert _chunk_source_location(chunk, parsed)["row_start"] == 7
    parsed["A"]["sha256"] = "other-version"
    assert "row_start" not in _chunk_source_location(chunk, parsed)


def test_retirement_excludes_only_exact_old_version_and_preserves_vector_order(tmp_path):
    path = str(tmp_path / "source.md")
    rows = [{"source_path": path, "source_version": "old"}, {"source_path": str(tmp_path / "other.md"), "source_version": "old"}, {"source_path": path, "source_version": "new"}]
    vectors = np.asarray([[1, 0], [2, 0], [3, 0]])
    kept, aligned = _filter_retired_source_versions(rows, vectors, [{"source_path": path.upper(), "source_version": "old"}])
    assert kept == rows[1:]
    assert aligned.tolist() == [[2, 0], [3, 0]]


def test_structured_citation_projects_exact_rows_and_reconstructs_after_cache_reset(tmp_path):
    candidate = V25LiveShadow.__new__(V25LiveShadow)
    candidate.atomic = {}
    row = {"row_id": "R5", "row_number": 5, "table_id": "T1", "source_id": "S1", "source_path": str(tmp_path / "standard.docx"), "source_version": "sha1", "file_name": "standard.docx", "source_location": {"table": 2}, "header_text": "设备 | 等级 | 品牌", "values": ["合成设备甲", "等级乙", "品牌甲、品牌乙"]}
    candidate._structured_tables = {"T1": [row, {**row, "row_id": "R6", "row_number": 6, "values": ["另一设备", "A级", "其他品牌"]}]}
    candidate.evidence_record("V25-STRUCTURED-T1")
    record = candidate.cited_evidence_record({"evidence_id": "V25-STRUCTURED-T1", "location": {"source_row_ids": ["R5", "FOREIGN_ROW"]}})
    assert record["evidence_id"] == "V25-STRUCTURED-T1@rows=5"
    assert record["source_version"] == "sha1" and record["location"]["table"] == 2
    assert "品牌甲、品牌乙" in record["raw_text"] and "其他品牌" not in record["raw_text"]
    candidate.atomic = {}
    assert candidate.evidence_record(record["evidence_id"])["raw_text"] == record["raw_text"]
    assert candidate.evidence_record("V25-STRUCTURED-T1@rows=99") is None


def test_preview_never_substitutes_a_new_version_for_an_old_citation(tmp_path, monkeypatch):
    path = str(tmp_path / "source.md")
    record = {"evidence_id": "E1", "source_id": "S1", "source_path": path, "source_version": "new-version", "raw_text": "新版正文"}
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2, "_candidate_primary_runtime", lambda: (SimpleNamespace(atomic={"E1": record}), None))
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", TrialKnowledgeStore(tmp_path / "state.json"))
    assert v2.knowledge_source_evidence("S1", evidence_id="E1", source_version="old-version")["items"] == []
    assert v2.knowledge_source_evidence("S1", evidence_id="E1", source_version="new-version")["items"][0]["raw_text"] == "新版正文"


def test_candidate_table_answer_citation_and_claim_map_resolve_same_row_version(tmp_path, monkeypatch):
    candidate = V25LiveShadow.__new__(V25LiveShadow)
    candidate.atomic = {}
    row = {"row_id": "R1", "row_number": 7, "source_id": "S1", "source_path": str(tmp_path / "assessment.xlsx"), "source_version": "sha-assessment", "file_name": "assessment.xlsx", "source_location": {"sheet_name": "Sheet1"}, "header_text": "评分规则", "values": ["未完成合成测试事项扣7分"]}
    candidate._structured_tables = {"T1": [row]}
    candidate.run = lambda *a, **k: {"v2_status": "ANSWERED", "v2_answer": "未完成合成测试事项扣7分", "v2_citations": [{"citation_id": "S1", "evidence_id": "V25-STRUCTURED-T1", "location": {"source_row_ids": ["R1"]}}], "trace_context": {"claims": [{"evidence_ids": ["V25-STRUCTURED-T1"]}], "claim_evidence_map": {"evidence_ids": ["V25-STRUCTURED-T1"]}}, "candidate_hash": "current"}
    monkeypatch.setattr(v2, "_candidate_primary_runtime", lambda: (candidate, SimpleNamespace(embed_query=lambda q: [0])))
    result = v2._candidate_primary_answer("合成测试事项扣几分")
    citation = result["citations"][0]
    assert citation["source_version"] == "sha-assessment"
    assert citation["evidence_id"] == result["claims"][0]["evidence_ids"][0] == result["claim_evidence_map"]["evidence_ids"][0]
    assert citation["display_location"] == "Sheet1，第7行"
    assert citation["excerpt"] == candidate.evidence_record(citation["evidence_id"])["raw_text"]


def test_explicit_card_identifier_limits_evidence_without_question_specific_answers():
    record = {"evidence_id": "E1", "source_id": "S1", "source_version": "v1", "raw_text": "方法和范围", "document_id": "D1"}
    chunk = {**record, "chunk_id": "E1", "knowledge_card": {"id": "CARD-1", "approval_status": "OWNER_CONFIRMED"}}
    assert _referenced_knowledge_card_candidates("CARD-1的方法及范围", [chunk], {"E1": record})[0]["evidence_id"] == "E1"
    assert _referenced_knowledge_card_candidates("CARD-10的方法", [chunk], {"E1": record}) == []
    assert _referenced_knowledge_card_candidates("普通方法问题", [chunk], {"E1": record}) == []
    assert _referenced_knowledge_card_candidates("CARD-1的方法", [{**chunk, "source_version": "old"}], {"E1": record}) == []
    assert _referenced_knowledge_card_candidates("CARD-1的方法", [{**chunk, "knowledge_card": {"id": "CARD-1", "approval_status": "PENDING"}}], {"E1": record}) == []


def test_node_cards_only_expose_owner_confirmed_current_candidate_evidence(monkeypatch):
    record = {"evidence_id": "E-card", "source_id": "S-card", "source_version": "sha-current", "raw_text": "已审核的方法及适用边界"}
    chunk = {"chunk_id": "E-card", **record, "knowledge_card": {"id": "C1", "node_id": "node-1", "approval_status": "OWNER_CONFIRMED"}}
    unapproved = {**chunk, "knowledge_card": {**chunk["knowledge_card"], "id": "C2", "approval_status": "PENDING"}}
    wrong_version = {**chunk, "source_version": "sha-old", "knowledge_card": {**chunk["knowledge_card"], "id": "C3"}}
    wrong_text = {**chunk, "raw_text": "未纳入的本地修改", "knowledge_card": {**chunk["knowledge_card"], "id": "C4"}}
    candidate = SimpleNamespace(chunks=[chunk, unapproved, wrong_version, wrong_text], atomic={"E-card": record}, candidate_hash="candidate-current")
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2, "_candidate_primary_runtime", lambda: (candidate, None))
    items = v2.knowledge_items()["items"]
    assert len(items) == 1
    assert (items[0]["knowledge_id"], items[0]["source_version"], items[0]["evidence_id"], items[0]["content"], items[0]["candidate_hash"]) == ("C1", "sha-current", "E-card", record["raw_text"], "candidate-current")


def test_candidate_answer_inline_citation_contains_the_same_preview_text(monkeypatch):
    record = {"evidence_id": "E1", "source_id": "S1", "source_version": "sha-current", "source_path": "source.md", "file_name": "source.md", "location": {"section_path": "知识卡CARD-1"}, "raw_text": "已确认的方法和适用条件"}
    candidate = SimpleNamespace(atomic={"E1": record}, run=lambda *args, **kwargs: {"v2_status": "PARTIAL_ANSWER", "v2_answer": record["raw_text"], "v2_citations": [{"citation_id": "S1", "evidence_id": "E1", "display_location": "位置未定位"}], "candidate_hash": "current"})
    monkeypatch.setattr(v2, "_candidate_primary_runtime", lambda: (candidate, SimpleNamespace(embed_query=lambda _q: [0])))
    citation = v2._candidate_primary_answer("方法是什么")["citations"][0]
    assert (citation["source_version"], citation["source_path"], citation["excerpt"]) == ("sha-current", "source.md", record["raw_text"])
    assert citation["display_location"] == "知识卡CARD-1"
    assert v2._display_location({"page": 3, "section_path": "附表"}) == "第3页"


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


def test_candidate_review_and_refresh_never_load_v1_and_keep_new_source_pending(tmp_path, monkeypatch):
    path = tmp_path / "2026-method.md"
    path.write_text("# 方法\n\n该合成方法具有明确的输入、输出和适用条件，仅用于运行范围验收。", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    feedback, _ = store.record_feedback({"question": "合成方法的范围？", "expected_answer": "只用于验收"}, "candidate-review")
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", store)
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2, "_runtime_evidence_records", lambda: [])
    monkeypatch.setattr(v2, "_engine_instance", lambda: (_ for _ in ()).throw(AssertionError("V1 is outside the candidate review scope")))
    monkeypatch.setattr(v2, "reset_trial_engine", lambda: (_ for _ in ()).throw(AssertionError("Local pending review must not invalidate the frozen candidate")))
    result = v2.review_feedback_workflow(feedback["feedback_id"], v2.ReviewedFeedbackRequest(decision="APPROVE", source_path=str(path)))
    assert result["knowledge"]["status"] == "PENDING_CANDIDATE"
    assert store.active_knowledge() == []
    assert result["source"]["body_status"] == "PARSED" and result["source"]["index_status"] == "INDEXED"
    path.write_text("# 第二版\n\n资料内容和版本已经更新，需要重新复核，仍不加入当前冻结候选。", encoding="utf-8")
    v2.refresh_knowledge_source(result["source"]["source_id"], v2.WithdrawKnowledgeRequest())
    assert store.feedback(feedback["feedback_id"])["status"] == "REVIEW_REQUIRED"


def test_candidate_review_reuses_current_source_even_when_registration_id_differs(tmp_path, monkeypatch):
    path = tmp_path / "source.md"
    path.write_text("已纳入的来源原文", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(path)
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", store)
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2, "_runtime_evidence_records", lambda: [{"source_id": "V262-current", "source_path": str(path), "source_version": source["current_hash"]}])
    monkeypatch.setattr(v2, "build_atomic_evidence", lambda *_args: (_ for _ in ()).throw(AssertionError("Current evidence must be reused")))
    v2._prepare_reviewed_source(path, source)
    assert store.source(source["source_id"])["index_generation"] == source["current_hash"][:12]


def test_registered_alias_reports_current_candidate_and_previews_actual_runtime_id(tmp_path, monkeypatch):
    path = tmp_path / "2026-project.md"
    path.write_text("当前候选已有该版本的正文", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(path)
    record = {"evidence_id": "E1", "source_id": "V262-current", "source_path": str(path), "source_version": source["current_hash"], "raw_text": "当前候选已有该版本的正文"}
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", store)
    monkeypatch.setattr(v2, "_primary_mode", lambda: v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2, "_candidate_primary_runtime", lambda: (SimpleNamespace(atomic={"E1": record}), None))
    catalog = v2.knowledge_source(source["source_id"])["source"]
    assert catalog["runtime_included"] is True
    assert catalog["runtime_source_id"] == "V262-current"
    assert v2.knowledge_source_evidence(source["source_id"], evidence_id="E1")["items"][0]["source_id"] == "V262-current"
    path.write_text("2027版本已经变化，不能冒充当前候选的旧正文", encoding="utf-8")
    store.register_source(path)
    assert v2.knowledge_source(source["source_id"])["source"]["runtime_included"] is False
    assert v2.knowledge_source_evidence(source["source_id"], evidence_id="E1")["items"] == []


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
