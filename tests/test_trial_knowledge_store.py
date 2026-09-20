from pathlib import Path

import pytest

from app.trial.knowledge_store import TrialKnowledgeStore


def test_reviewed_knowledge_is_versioned_searchable_and_withdrawable(tmp_path: Path) -> None:
    source_path = tmp_path / "policy.md"
    source_path.write_text("原文。", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(source_path)
    store.mark_indexed(source["source_id"], source_hash_value=source["current_hash"], parse_status="parsed", chunk_count=1)
    feedback, created = store.record_feedback({
        "question": "区域公司中心可选哪些岗位？",
        "expected_answer": "区域分公司中心选择设置技术投标岗、钢筋翻样岗。",
        "source_id": source["source_id"],
        "source_location": "第1页",
        "required_terms": ["选择设置", "技术投标岗", "钢筋翻样岗"],
    }, "one-submit")
    same, duplicated = store.record_feedback({"question": "ignored"}, "one-submit")
    assert created is True and duplicated is False
    assert same["feedback_id"] == feedback["feedback_id"]

    reviewed, knowledge = store.review_feedback(
        feedback["feedback_id"],
        decision="APPROVE",
        source_id=source["source_id"],
        location="第1页",
        required_terms=["选择设置", "技术投标岗", "钢筋翻样岗"],
        reviewer="reviewer-001",
        standard_question="区域公司中心可选哪些岗位？",
        similar_questions=["区域公司中心可以额外设什么岗位？"],
        negative_questions=["所有分公司都必须设钢筋翻样岗吗？"],
        applicability="区域分公司中心；选设，不是必设",
    )
    assert reviewed["status"] == "ACTIVE"
    assert knowledge is not None and knowledge["source_version"] == source["current_hash"]
    assert len([row for row in store.search("区域公司中心可以额外设什么岗位") if row["type"] == "KNOWLEDGE"]) == 1

    withdrawn = store.withdraw_knowledge(knowledge["knowledge_id"], reviewer="reviewer-001")
    assert withdrawn and withdrawn["status"] == "WITHDRAWN"
    assert store.active_knowledge() == []
    restored = store.rollback_knowledge(knowledge["knowledge_id"], target_version=1, reviewer="reviewer-001", reason="恢复已核实版本")
    assert restored and restored["status"] == "ACTIVE"


def test_source_change_marks_reviewed_knowledge_for_review(tmp_path: Path) -> None:
    source_path = tmp_path / "policy.md"
    source_path.write_text("第一版。", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(source_path)
    feedback, _ = store.record_feedback({"question": "问题", "expected_answer": "答案", "source_id": source["source_id"]}, "feedback")
    store.review_feedback(feedback["feedback_id"], decision="APPROVE", source_id=source["source_id"], location="第1行", required_terms=["答案"], reviewer="reviewer-001")
    source_path.write_text("第二版。", encoding="utf-8")
    updated = store.register_source(source_path)
    assert updated["current_hash"] != source["current_hash"]
    assert store.active_knowledge() == []
    assert store.overview()["active_knowledge"] == 0
    candidate = store.list_change_candidates()[0]
    assert candidate["status"] == "PROPOSED"
    assert candidate["existing_content"] == "答案"
    assert candidate["previous_source_version"] == source["current_hash"]
    assert candidate["proposed_source_version"] == updated["current_hash"]


def test_modified_feedback_is_new_but_network_retry_is_idempotent(tmp_path: Path) -> None:
    store = TrialKnowledgeStore(tmp_path / "state.json")
    first, created = store.record_feedback({"expected_answer": "第一版"}, "attempt-1")
    retry, retry_created = store.record_feedback({"expected_answer": "被忽略"}, "attempt-1")
    second, second_created = store.record_feedback({"expected_answer": "第二版"}, "attempt-2")
    assert created is True and retry_created is False and second_created is True
    assert retry["feedback_id"] == first["feedback_id"]
    assert second["feedback_id"] != first["feedback_id"]


def test_system_defect_cannot_be_published_as_standard_answer(tmp_path: Path) -> None:
    store = TrialKnowledgeStore(tmp_path / "state.json")
    feedback, _ = store.record_feedback({
        "question": "资料存在但没有召回",
        "expected_answer": "不能用固定答案掩盖召回失败",
        "system_fix_required": True,
        "failure_stage": "RECALL",
        "failure_code": "RECALL_MISS",
    }, "system-defect")

    with pytest.raises(ValueError, match="SYSTEM_DEFECT_CANNOT_PUBLISH_AS_STANDARD_ANSWER"):
        store.review_feedback(feedback["feedback_id"], decision="APPROVE", source_id="SRC_x", location="第1页", required_terms=[], reviewer="reviewer-001")
    assert store.feedback(feedback["feedback_id"])["status"] == "RECORDED"


def test_failed_source_refresh_keeps_new_version_unavailable(tmp_path: Path) -> None:
    source_path = tmp_path / "policy.md"
    source_path.write_text("第一版。", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(source_path)
    store.mark_indexed(source["source_id"], source_hash_value=source["current_hash"], parse_status="parsed", chunk_count=1)
    feedback, _ = store.record_feedback({"question": "问题", "expected_answer": "人工答案", "source_id": source["source_id"]}, "feedback")
    _, knowledge = store.review_feedback(feedback["feedback_id"], decision="APPROVE", source_id=source["source_id"], location="第1行", required_terms=["人工答案"], reviewer="reviewer-001")
    source_path.write_text("第二版但解析失败。", encoding="utf-8")
    updated = store.register_source(source_path)
    failed = store.mark_indexed(updated["source_id"], source_hash_value=updated["current_hash"], parse_status="read_error", chunk_count=0, error="fixture failure")
    assert failed and failed["index_status"] == "FAILED" and failed["index_generation"] == ""
    assert store.active_knowledge() == []
    assert store.list_change_candidates()[0]["knowledge_id"] == knowledge["knowledge_id"]


def test_rollback_to_withdrawn_source_stays_under_review(tmp_path: Path) -> None:
    source_path = tmp_path / "policy.md"
    source_path.write_text("原文。", encoding="utf-8")
    store = TrialKnowledgeStore(tmp_path / "state.json")
    source = store.register_source(source_path)
    store.mark_indexed(source["source_id"], source_hash_value=source["current_hash"], parse_status="parsed", chunk_count=1)
    feedback, _ = store.record_feedback({"question": "问题", "expected_answer": "答案", "source_id": source["source_id"]}, "feedback")
    _, knowledge = store.review_feedback(feedback["feedback_id"], decision="APPROVE", source_id=source["source_id"], location="第1行", required_terms=["答案"], reviewer="reviewer-001")
    store.withdraw_knowledge(knowledge["knowledge_id"], reviewer="reviewer-001")
    store.withdraw_source(source["source_id"], reviewer="reviewer-001")
    restored = store.rollback_knowledge(knowledge["knowledge_id"], target_version=1, reviewer="reviewer-001", reason="验收回滚")
    assert restored and restored["status"] == "REVIEW_REQUIRED"
    assert store.active_knowledge() == [] and store.active_variants() == []
