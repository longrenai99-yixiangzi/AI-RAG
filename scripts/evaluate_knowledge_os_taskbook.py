from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ingestion.atomic_search import search_atomic_evidence
from app.trial.knowledge_store import TrialKnowledgeStore
from app.trial.v2 import _rank_atomic_candidates
from scripts.build_verified_evidence_bundle_v1 import _coverage, _link_only, _same_scope_conflicts


OUTPUT = ROOT / "evaluation" / "knowledge_os_optimization" / "taskbook_acceptance_matrix.json"
PUBLIC = ROOT / "evaluation" / "knowledge_os_optimization" / "public_acceptance.json"
FEEDBACK = ROOT / "evaluation" / "knowledge_os_optimization" / "feedback_learning_acceptance.json"
BROWSER = Path(r"[LOCAL_PATH_REDACTED]")
API = "http://127.0.0.1:8010/api/v2"


def main() -> int:
    public = json.loads(PUBLIC.read_text(encoding="utf-8"))
    feedback = json.loads(FEEDBACK.read_text(encoding="utf-8"))
    browser = json.loads(BROWSER.read_text(encoding="utf-8"))
    rows = [
        {"id": row["id"], "passed": row["passed"], "evidence": "普通全库问答", "detail": _public_detail(row)}
        for row in public["rows"]
    ]
    checks: list[tuple[str, str, Callable[[], str]]] = [
        ("E01", "最小逻辑夹具", _e01),
        ("E02", "最小逻辑夹具", _e02),
        ("E03", "最小逻辑夹具", _e03),
        ("F01", "隔离持久库", _f01),
        ("F02", "隔离持久库", _f02),
        ("C01", "8010 普通入口", _c01),
        ("U01", "8010 搜索接口", _u01),
        ("U02", "8010 来源与证据接口", _u02),
        ("U03", "真实浏览器", lambda: _u03(browser)),
        ("B01", "最小逻辑夹具", _b01),
        ("B02", "最小逻辑夹具", _b02),
        ("B03", "最小逻辑夹具", _b03),
        ("B04", "普通全库问答", lambda: _b04(public)),
        ("B05", "隔离持久库", _b05),
        ("B06", "隔离持久库", _b06),
        ("B07", "隔离持久库", _b07),
        ("B08", "隔离持久库", _b08),
    ]
    for case_id, evidence, check in checks:
        try:
            detail = check()
            rows.append({"id": case_id, "passed": True, "evidence": evidence, "detail": detail})
        except Exception as error:
            rows.append({"id": case_id, "passed": False, "evidence": evidence, "detail": f"{type(error).__name__}: {error}"})

    feedback_before_wrong = "二级部室" not in feedback["before"]["answer"]
    feedback_after_right = (
        feedback["after_restart"].get("answer_mode") == "STANDARD_ANSWER"
        and "二级部室" in feedback["after_restart"]["answer"]
        and feedback.get("regression", {}).get("regression_status") == "PASSED"
    )
    feedback_similar_right = feedback["similar_after_restart"].get("answer_mode") == "STANDARD_ANSWER" and "二级部室" in feedback["similar_after_restart"]["answer"]
    validity = next(row for row in public["rows"] if row["id"] == "O09")
    metrics = {
        "correct_body_retrieval": public["retrieval_source_hit"],
        "final_evidence_hit": public["final_evidence_hit"],
        "conclusion_correct": public["conclusion_correct"],
        "necessary_fact_coverage": public["answer_required_fact_coverage"],
        "itemized_citation_support": public["citation_fact_support"],
        "answerable_erroneous_refusal": public["erroneous_refusals"],
        "unanswerable_overreach": {"numerator": int(not (validity["status"] == "PARTIAL_ANSWER" and "没有证明它是现行有效版本" in validity["answer"])), "denominator": 1},
        "feedback_original_improvement": {"numerator": int(feedback_before_wrong and feedback_after_right), "denominator": 1},
        "feedback_derived_improvement": {"numerator": int(feedback_similar_right), "denominator": 1},
    }
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "KnowledgeOS_Codex优化执行任务书 T08 全矩阵；O/G 为普通全库入口，E/F/B 为隔离夹具，C/U 为 8010/浏览器实测",
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "blocked": 0,
        "metrics": metrics,
        "rows": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("cases", "passed", "failed", "blocked", "metrics")}, ensure_ascii=False))
    return 0 if payload["failed"] == 0 else 1


def _public_detail(row: dict[str, Any]) -> str:
    return f"status={row['status']}; source_hit={row['source_hit']}; location_hit={row['location_hit']}; conclusion_correct={row['conclusion_correct']}"


def _e01() -> str:
    assert _link_only("来源：[[制度原文]]")
    assert not _link_only("本条款明确公司总部中心的职责、工作边界和运行要求，详见[[制度原文]]。后续执行应保留审核记录。")
    return "纯链接登记页退出直接证据；带链接的完整正文保留"


def _e02() -> str:
    scope = {"organization": "MATCH", "year": "MATCH", "metric": "MATCH"}
    candidates = [{"evidence_id": "E1", "scope": scope, "text": "第1页。2025年金额100万元。"}, {"evidence_id": "E2", "scope": scope, "text": "第2页。2025年金额100万元。"}]
    assert _same_scope_conflicts(candidates, {"organization": ["二公司"], "year": ["2025"], "metric": ["金额"]}) == {}
    return "相同事实的不同页码未形成冲突"


def _e03() -> str:
    result = _coverage(["组织定位和隶属关系", "各层级的岗位或机构设置"], {}, [{"evidence_id": "E1", "role": "DIRECT", "text": "公司总部中心作为二级部室。"}])
    assert [item["coverage_status"] for item in result] == ["COVERED", "EVIDENCE_INSUFFICIENT"]
    return "两项事实仅一项有证据时返回部分覆盖"


def _f01() -> str:
    with tempfile.TemporaryDirectory() as directory:
        store = TrialKnowledgeStore(Path(directory) / "state.json")
        first, created = store.record_feedback({"expected_answer": "第一版"}, "same-attempt")
        retry, retry_created = store.record_feedback({"expected_answer": "忽略"}, "same-attempt")
        second, second_created = store.record_feedback({"expected_answer": "第二版"}, "edited-attempt")
        assert created and not retry_created and second_created
        assert first["feedback_id"] == retry["feedback_id"] != second["feedback_id"]
    return "同一次重试去重；修改后的第二次反馈形成新记录"


def _f02() -> str:
    store, path, source, knowledge = _active_fixture()
    restarted = TrialKnowledgeStore(store.path)
    assert restarted.active_knowledge()[0]["knowledge_id"] == knowledge["knowledge_id"]
    path.write_text("第二版。", encoding="utf-8")
    updated = restarted.register_source(path)
    assert updated["current_hash"] != source["current_hash"] and restarted.active_knowledge() == []
    withdrawn = restarted.withdraw_source(source["source_id"], reviewer="reviewer-001")
    assert withdrawn and withdrawn["withdrawn"]
    return "生效知识跨实例保留；源文更新触发复核；撤回后不可用"


def _c01() -> str:
    with httpx.Client(timeout=180, trust_env=False) as client:
        conversation = "taskbook-context-check"
        first = client.post(f"{API}/query", json={"question": "中建三局二公司设计与技术支持中心的组织架构是什么样的？", "trial_user": "reviewer-001", "conversation_id": conversation}).json()
        follow = client.post(f"{API}/query", json={"question": "那分公司呢？", "trial_user": "reviewer-001", "conversation_id": conversation}).json()
        fresh = client.post(f"{API}/query", json={"question": "那分公司呢？", "trial_user": "reviewer-001", "conversation_id": "taskbook-context-fresh"}).json()
    assert first["answer_status"] == "ANSWERED"
    assert "中建三局第二建设公司" in follow["resolved_question"] and follow["resolved_question"] != follow["question"]
    assert fresh["resolved_question"] == fresh["question"] and "中建三局第二建设公司" not in fresh["resolved_question"]
    return "同会话继承组织主体；新会话不继承"


def _u01() -> str:
    with httpx.Client(timeout=180, trust_env=False) as client:
        found = client.get(f"{API}/knowledge/search", params={"q": "设计与技术支持中心"}).json()
        missing = client.get(f"{API}/knowledge/search", params={"q": "zzzxxyy987654notfound"}).json()
        empty = client.get(f"{API}/knowledge/search", params={"q": ""}).json()
    assert found["items"] and missing["items"] == [] and empty["items"] == []
    assert "请输入" in empty["message"]
    return "相关词有结果；不存在词和空文本均明确返回空结果"


def _u02() -> str:
    with httpx.Client(timeout=180, trust_env=False) as client:
        answer = client.post(f"{API}/query", json={"question": "二公司总部中心隶属哪个部门？", "trial_user": "reviewer-001", "conversation_id": "taskbook-citation"}).json()
        citation = answer["citations"][0]
        preview = client.get(f"{API}/knowledge/sources/{citation['source_id']}/evidence").json()
    evidence = next(item for item in preview["items"] if item["evidence_id"] == citation["evidence_id"])
    assert evidence["source_version"] == citation["source_version"] and evidence["raw_text"]
    assert citation["display_location"] == "第1页"
    return f"引用、来源预览和版本一致：{citation['source_id']}@{citation['source_version'][:12]}"


def _u03(browser: dict[str, Any]) -> str:
    assert browser["feedback"]["regression"] == "PASSED"
    assert browser["feedback"]["final_state"] == "WITHDRAWN_AFTER_ROLLBACK"
    assert browser["page_errors"] == [] and browser["failed_requests"] == []
    return "浏览器同链完成反馈、发布、回归、回滚和撤回"


def _b01() -> str:
    child = {"evidence_id": "C1", "source_id": "S1", "source_version": "V1", "parent_evidence_id": "P1", "text": "岗位设置", "search_context": "相似问法", "file_name": "a.pdf"}
    parent = {"evidence_id": "P1", "source_id": "S1", "source_version": "V1", "text": "区域分公司中心选择设置岗位", "file_name": "a.pdf"}
    ranked = _rank_atomic_candidates("区域分公司岗位", [child, child], {"C1": child, "P1": parent})
    assert len({item["evidence_id"] for item in ranked}) == len(ranked) == 2
    return "多入口命中同一证据后去重，未重复占位"


def _b02() -> str:
    record = {"evidence_id": "E1", "raw_text": "原文只说明中心设置。", "text": "原文只说明中心设置。", "search_context": "总部中心隶属哪个部门", "file_name": "a.pdf"}
    result = search_atomic_evidence("总部中心隶属哪个部门", [record])
    assert result and result[0]["record"]["raw_text"] == "原文只说明中心设置。"
    return "检索上下文改善召回，引用原文保持不变"


def _b03() -> str:
    child = {"evidence_id": "C1", "source_id": "S1", "source_version": "V2", "parent_evidence_id": "P2", "text": "技术投标岗", "file_name": "a.pdf"}
    current = {"evidence_id": "P2", "source_id": "S1", "source_version": "V2", "text": "区域分公司中心选择设置技术投标岗", "file_name": "a.pdf"}
    old = {"evidence_id": "P1", "source_id": "S1", "source_version": "V1", "text": "旧版父条款", "file_name": "a.pdf"}
    ranked = _rank_atomic_candidates("区域分公司技术投标岗", [child], {"C1": child, "P2": current, "P1": old})
    assert {item["evidence_id"] for item in ranked} == {"C1", "P2"}
    return "补入同源同版本父条款，旧版父条款未进入"


def _b04(public: dict[str, Any]) -> str:
    rows = {row["id"]: row for row in public["rows"]}
    assert all(rows[case]["passed"] for case in ("O04", "O05", "O06"))
    return "相似问可回答；未登记反例仍由范围及必设/选设规则纠正"


def _b05() -> str:
    store, path, source, _ = _active_fixture()
    path.write_text("第二版但解析失败。", encoding="utf-8")
    updated = store.register_source(path)
    failed = store.mark_indexed(updated["source_id"], source_hash_value=updated["current_hash"], parse_status="read_error", chunk_count=0, error="fixture failure")
    assert failed and failed["index_status"] == "FAILED" and failed["index_generation"] == ""
    assert len(failed["versions"]) == 2 and failed["versions"][0]["sha256"] == source["current_hash"]
    return "新附件解析失败保持 FAILED；旧新版本分离且新代次未生效"


def _b06() -> str:
    store, path, source, knowledge = _active_fixture()
    path.write_text("第二版。", encoding="utf-8")
    store.register_source(path)
    candidate = store.list_change_candidates()[0]
    current = next(row for row in store._read()["knowledge"].values() if row["knowledge_id"] == knowledge["knowledge_id"])
    assert candidate["status"] == "PROPOSED" and candidate["existing_content"] == "人工答案"
    assert current["content"] == "人工答案" and current["status"] == "REVIEW_REQUIRED"
    return "自动刷新只形成变更候选，人工内容未被覆盖"


def _b07() -> str:
    store, _, source, knowledge = _active_fixture()
    store.withdraw_knowledge(knowledge["knowledge_id"], reviewer="reviewer-001")
    store.withdraw_source(source["source_id"], reviewer="reviewer-001")
    restored = store.rollback_knowledge(knowledge["knowledge_id"], target_version=1, reviewer="reviewer-001", reason="验收回滚")
    assert restored and restored["status"] == "REVIEW_REQUIRED" and store.active_knowledge() == []
    return "回滚到已撤回来源的历史版本后保持待复核"


def _b08() -> str:
    store, _, source, knowledge = _active_fixture()
    store.withdraw_knowledge(knowledge["knowledge_id"], reviewer="reviewer-001")
    assert store.active_variants() == [] and store.source(source["source_id"])["withdrawn"] is False
    assert store.source(source["source_id"])["index_status"] == "INDEXED"
    return "标准答复退出，原始来源仍保持已索引"


def _active_fixture() -> tuple[TrialKnowledgeStore, Path, dict[str, Any], dict[str, Any]]:
    directory = Path(tempfile.mkdtemp(prefix="knowledge-os-acceptance-"))
    path = directory / "policy.md"
    path.write_text("第一版。", encoding="utf-8")
    store = TrialKnowledgeStore(directory / "state.json")
    source = store.register_source(path)
    store.mark_indexed(source["source_id"], source_hash_value=source["current_hash"], parse_status="parsed", chunk_count=1)
    feedback, _ = store.record_feedback({"question": "标准问题", "expected_answer": "人工答案", "source_id": source["source_id"]}, "feedback")
    _, knowledge = store.review_feedback(feedback["feedback_id"], decision="APPROVE", source_id=source["source_id"], location="第1行", required_terms=["人工答案"], reviewer="reviewer-001", standard_question="标准问题", similar_questions=["相似问题"], negative_questions=["反例问题"])
    assert knowledge is not None
    return store, path, source, knowledge


if __name__ == "__main__":
    raise SystemExit(main())
