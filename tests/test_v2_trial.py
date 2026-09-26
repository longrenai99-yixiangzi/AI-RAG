import json
from types import SimpleNamespace

import app.trial.v2 as v2
from openpyxl import Workbook
from rank_bm25 import BM25Okapi
from app.bm25 import tokenize
from app.retrieval.retrieval_trace import build_trace
from app.trial.knowledge_store import TrialKnowledgeStore
from scripts.build_verified_evidence_bundle_v1 import _direct_candidate, _scope
from app.trial.v2 import _closure_status, _core_phrases, _display_location, _evaluate_feedback_regression, _feedback_profile, _friendly_status, _should_emit_live_shadow, _with_exact_atomic_rescue
from app.trial.live_shadow_v25 import _approved_gold_source_rescue, _owner_answer_gold_source_rescue, _restore_source_origin
from app.retrieval.query_planner_v1 import plan_query
from scripts.run_verified_answer_engine_v2 import _answer_relevant, _runtime_bundle, _same_structured_source, _structured_rows_complete
from scripts.run_v2_6_2_answer_gold_replay import _current_manual_review, _run_fingerprints
from scripts.run_v2_6_2_compatibility_replay import _batch_size
from scripts.replay_v2_6_live_shadow_manual_review import _ensure_no_manual_decisions_to_overwrite
from app.verified_answer_engine_v2 import render


def test_v2_status_is_user_friendly():
    assert _friendly_status("CONFLICTING_ANSWER") == "资料存在冲突"
    assert _friendly_status("SOURCE_SCOPE_MISSING") == "当前知识范围暂无可靠来源"


def test_candidate_primary_shadows_when_primary_hash_differs_from_current_candidate():
    assert _should_emit_live_shadow("V2_6_2_CANDIDATE", "f1c49", "f972") is True
    assert _should_emit_live_shadow("V2_6_2_CANDIDATE", "f972", "f972") is False


def test_candidate_primary_trace_keeps_candidate_hash_claims_and_real_evidence(monkeypatch):
    query_plan = {"query_type": "AGGREGATION_QUERY", "normalized_question": "无锡山姆结构策划点数量", "project": ["无锡山姆"], "scope_constraints": {"project": ["无锡山姆"]}}
    citation = {"citation_id": "S1", "evidence_id": "E1", "source_id": "SRC1", "file_name": "无锡山姆.xlsx", "source_path": "[LOCAL_PATH_REDACTED]", "location": {"sheet_name": "无锡山姆", "row_start": 2}}
    trace_context = {
        "query_plan": query_plan,
        "evidence_bundle": {"bundle_status": "VERIFIED", "candidate_evidence": [{"evidence_id": "E1", "document_id": "DOC1", "source_id": "SRC1", "file_name": "无锡山姆.xlsx", "role": "DIRECT", "scope": {"project": "MATCH"}}], "verified_evidence": [{"evidence_id": "E1"}]},
        "claims": [{"claim_id": "C1", "claim_text": "结构专业共 7 条。", "claim_type": "DIRECT", "citation_ids": ["S1"]}],
        "claim_evidence_map": {"C1": ["E1"]},
        "validation_errors": [],
        "chunk_retrieval": {"method": "BM25_DENSE_RRF", "candidate_count": 1, "items": [{"chunk_id": "E1", "document_id": "DOC1", "rank": 1}]},
    }

    class FakeDense:
        def embed_query(self, _question):
            return [0.0]

    class FakeCandidate:
        candidate_hash = "candidate-sha"

        def run(self, _question, _primary, *, query_vector, include_trace):
            assert query_vector == [0.0]
            assert include_trace is True
            return {"v2_status": "ANSWERED", "v2_bundle_status": "VERIFIED", "v2_answer": "结构专业共 7 条。", "v2_citations": [citation], "candidate_hash": self.candidate_hash, "candidate_revision": "test", "validation": {"valid": True, "validation_errors": []}, "latency_ms": 12.0, "trace_context": trace_context}

    monkeypatch.setattr(v2, "_candidate_primary_runtime", lambda: (FakeCandidate(), FakeDense()))
    result = v2._candidate_primary_answer("无锡山姆结构专业有多少条策划点？")
    trace = build_trace(query_run_id="QR_TEST", question=result["question"], resolved_question=result["question"], result=result)

    assert trace["candidate_hash"] == "candidate-sha"
    assert trace["stages"]["query_understanding"]["project"] == ["无锡山姆"]
    assert trace["stages"]["evidence_validation"][0]["role"] == "DIRECT"
    assert trace["stages"]["chunk_retrieval"]["candidate_count"] == 1
    assert trace["counts"]["claims"] == 1
    assert trace["failure"]["failure_code"] == "NO_FAILURE"
    assert result["latency"]["query_embedding_ms"] >= 0
    assert result["latency"]["candidate_pipeline_ms"] == 12.0


def test_candidate_search_reuses_bm25_and_filters_zero_score():
    corpus = ["无锡山姆项目结构设计管理策划", "汉江实验室建筑面积合同额", "混凝土施工方案"]
    chunks = [{"chunk_id": "relevant"}, {"chunk_id": "unrelated"}, {"chunk_id": "other"}]
    candidate = SimpleNamespace(
        bm25=BM25Okapi([tokenize(text) for text in corpus]),
        chunks=chunks,
        atomic={
            "relevant": {"evidence_id": "E1", "file_name": "无锡山姆策划.docx"},
            "unrelated": {"evidence_id": "E2", "file_name": "汉江实验室.docx"},
            "other": {"evidence_id": "E3", "file_name": "混凝土方案.docx"},
        },
    )

    hits = v2._search_candidate_atomic_evidence(candidate, "无锡山姆设计管理策划", 10)
    no_hits = v2._search_candidate_atomic_evidence(candidate, "qzxvkm749183aqwp", 10)

    assert hits[0]["record"]["evidence_id"] == "E1"
    assert no_hits == []


def test_parenthesized_ledger_project_blocks_another_projects_row():
    question = "直属分公司EPC项目设计价值创造统计台账（无锡山姆）中，结构专业共列了多少条创效策划点？"
    path = "[LOCAL_PATH_REDACTED]��属分公司EPC项目/常熟项目/设计价值创造统计台账.xlsx"
    text = "工作表：常熟项目\n第41行：序号：39 | 专业类别：结构 | 创效策划点：电梯基础"
    row = {"evidence_id": "E1", "document_id": "D1", "source_path": path, "file_name": "常熟设计价值创造统计台账.xlsx", "heading_path": "项目台账", "text": text, "location": {"sheet_name": "项目台账", "row_start": 41, "row_end": 41, "table_id": "T1"}, "rank": 1, "candidate_origin": "FROZEN_V2_5_RRF", "lineage_status": "LINEAGE_CONFIRMED"}
    document = {"document_id": "D1", "source_path": path, "file_name": "常熟设计价值创造统计台账.xlsx", "project": ["常熟药机厂项目"]}
    bundle = _runtime_bundle(question, plan_query(question).to_dict(), {"atomic_candidates": [row]}, {"D1": document}, {"E1": row}, [])

    assert bundle["query_plan"]["project"] == ["无锡山姆"]
    assert bundle["bundle_status"] == "SOURCE_SCOPE_MISSING"
    assert bundle["verified_evidence"] == []


def test_structured_rows_require_the_candidate_source_version_and_complete_table():
    candidate = {"source_path": "[LOCAL_PATH_REDACTED]", "source_version": "sha-current", "table_id": "T1", "location": {"table_id": "T1"}}
    old_row = {"source_path": "[LOCAL_PATH_REDACTED]", "source_version": "sha-old", "table_id": "T1"}
    current_rows = [{"source_path": "[LOCAL_PATH_REDACTED]", "source_version": "sha-current", "table_id": "T1", "expected_table_row_count": 2, "row_id": "R1"}, {"source_path": "[LOCAL_PATH_REDACTED]", "source_version": "sha-current", "table_id": "T1", "expected_table_row_count": 2, "row_id": "R2"}]

    assert _same_structured_source(candidate, old_row) is False
    assert _structured_rows_complete(current_rows) is True
    assert _structured_rows_complete(current_rows[:1]) is False
    assert _structured_rows_complete(current_rows + current_rows[:1]) is False


def test_explicit_counted_list_retrieval_requires_a_full_list_chunk():
    question = "二公司设计管理部的主要职责有哪 6 项？"
    plan = plan_query(question).to_dict()
    base = {"source_path": "[LOCAL_PATH_REDACTED]�公司设计管理部.md", "file_name": "二公司设计管理部.md", "scope": {}}
    summary = {**base, "text": "中建三局第二建设公司设计管理部是公司设计管理工作的核心部门，负责体系建设和EPC项目设计全过程管理。"}
    list_chunk = {**base, "text": "- 设计管理体系建设和维护\n- EPC项目设计支持与策划\n- 设计评审与评估管理\n- 设计资源库建设\n- 设计人才培养与能力建设\n- 设计管理制度文件的编制与更新"}

    assert _answer_relevant(summary, question, plan) is False
    assert _answer_relevant(list_chunk, question, plan) is True

    course_question = "《EPC项目设计管理方法与实务》课程分为哪5个章节？"
    course_plan = plan_query(course_question).to_dict()
    course_text = "课程结构（5章）：背景介绍 / 设计管理基本动作与要素 / 关键动作实施要点 / 全专业设计技术管控要点 / 问题与建议"
    course_candidate = {**base, "file_name": "EPC项目设计管理方法与实务.pptx", "text": course_text}
    assert _answer_relevant(course_candidate, course_question, course_plan) is True


def test_task_book_link_chunk_is_context_only_for_count_and_coverage_question():
    question = "设计任务书汇编收录了多少个项目的任务书？覆盖哪些业态？"
    path = "[LOCAL_PATH_REDACTED]��设计管理流程.md"
    plan = plan_query(question)
    link_labels = (
        "[[raw/设计支持/设计任务书|设计任务书文件夹（26个项目）]]",
        "[设计任务书文件夹（26个项目）](raw/设计支持/设计任务书)",
    )
    for link in link_labels:
        text = f"编制明确的设计任务书，规定设计范围、技术标准、进度要求和交付成果，作为设计工作的依据。\n关键文件：{link}"
        row = {"evidence_id": "E1", "document_id": "D1", "source_path": path, "file_name": "EPC项目设计管理流程.md", "heading_path": "3. 设计任务书", "text": text, "location": {"section_path": "3. 设计任务书"}, "rank": 1, "candidate_origin": "FROZEN_V2_5_RRF", "lineage_status": "LINEAGE_CONFIRMED"}
        document = {"document_id": "D1", "source_path": path, "file_name": "EPC项目设计管理流程.md", "document_type": "TOPIC_PAGE"}
        bundle = _runtime_bundle(question, plan.to_dict(), {"atomic_candidates": [row]}, {"D1": document}, {"E1": row}, [])

        assert bundle["bundle_status"] == "INSUFFICIENT_EVIDENCE"
        assert bundle["verified_evidence"] == []
        answer = render(bundle)
        assert answer["answer_status"] == "PARTIAL_ANSWER"
        assert "26个项目" not in answer["answer_text"]


def test_registration_pointer_label_cannot_supply_inventory_count():
    question = "设计支持中心资料登记共登记多少份资料？"
    path = "[LOCAL_PATH_REDACTED]��中心资料登记.md"
    text = "目录入口：[共登记26份资料](raw/设计支持中心资料登记.md)"
    row = {"evidence_id": "E1", "document_id": "D1", "source_path": path, "file_name": "设计支持中心资料登记.md", "heading_path": "资料登记", "text": text, "location": {"line_start": 1}, "rank": 1, "candidate_origin": "FROZEN_V2_5_RRF", "lineage_status": "LINEAGE_CONFIRMED"}
    document = {"document_id": "D1", "source_path": path, "file_name": "设计支持中心资料登记.md", "document_type": "REGISTER_PAGE"}
    plan = plan_query(question)
    bundle = _runtime_bundle(question, plan.to_dict(), {"atomic_candidates": [row]}, {"D1": document}, {"E1": row}, [])

    assert bundle["verified_evidence"] == []
    answer = render(bundle)
    assert answer["answer_status"] != "ANSWERED"
    assert "26份资料" not in answer["answer_text"]


def test_period_scoped_source_body_supports_quantity_difference_rate():
    question = "2024 年上半年二公司钢筋量差率是多少？"
    path = "[LOCAL_PATH_REDACTED]��结/2024年半年总结.md"
    text = "2024年上半年开展钢筋管理，钢筋量差率达8.45%，同比提升0.25个百分点。"
    row = {"evidence_id": "E1", "document_id": "D1", "source_path": path, "file_name": "2024年半年总结.md", "heading_path": "2024年半年总结 > 正文", "text": text, "location": {"line_start": 7, "line_end": 7}, "rank": 1, "candidate_origin": "PERIOD_SCOPE_RESCUE", "lineage_status": "LINEAGE_CONFIRMED"}
    document = {"document_id": "D1", "source_path": path, "file_name": "2024年半年总结.md", "document_type": "REVIEW_RECORD"}
    plan = plan_query(question)
    bundle = _runtime_bundle(question, plan.to_dict(), {"atomic_candidates": [row]}, {"D1": document}, {"E1": row}, [])

    answer = render(bundle)

    assert "量差率" in plan.metric
    assert bundle["bundle_status"] == "VERIFIED"
    assert bundle["verified_evidence"][0]["evidence_id"] == "E1"
    assert answer["answer_status"] == "ANSWERED"
    assert "8.45%" in answer["answer_text"]


def test_manual_review_runner_refuses_to_overwrite_owner_decisions(tmp_path):
    for suffix in ("jsonl", "json"):
        path = tmp_path / f"review.{suffix}"
        record = {"review_id": "LSR-001", "manual_decision": "VERIFIED_NEW_HIT"}
        if suffix == "jsonl":
            path.write_text(json.dumps(record), encoding="utf-8")
        else:
            path.write_text(json.dumps({"records": [record]}), encoding="utf-8")
        try:
            _ensure_no_manual_decisions_to_overwrite((path,))
        except RuntimeError as error:
            assert "REFUSE_TO_OVERWRITE_OWNER_REVIEW" in str(error)
        else:
            raise AssertionError(f"{suffix} decisions were not protected")

        path.unlink()
        _ensure_no_manual_decisions_to_overwrite((path,))


def test_compatibility_replay_batch_size_can_be_limited_safely():
    assert _batch_size(False) == 32
    assert _batch_size(True) == 64
    assert _batch_size(False, "4") == 4
    try:
        _batch_size(False, "0")
    except ValueError as error:
        assert "positive integer" in str(error)
    else:
        raise AssertionError("nonpositive compatibility replay batch size was accepted")


def test_previous_owner_runtime_review_is_not_carried_to_a_changed_run():
    citations = [{"citation_id": "S1", "evidence_id": "E1", "source_version": "V1", "source_path": "[LOCAL_PATH_REDACTED]", "location": {"line_start": 4}}]
    current = _run_fingerprints(code_sha256="CODE2", candidate_hash="CAND2", candidate_revision="R2", question_id="Q1", question="問題", answer="新候選答案", citations=citations)
    prior = {"manual_decision": "ANSWER_GOLD_MATCH", "reviewer": "USER_CONFIRMED", "reviewed_at": "2026-09-15T00:00:00Z"}

    stale = _current_manual_review(prior, current["run_fingerprint"])
    same = _current_manual_review({**prior, "run_fingerprint": current["run_fingerprint"]}, current["run_fingerprint"])
    changed = _run_fingerprints(code_sha256="CODE2", candidate_hash="CAND2", candidate_revision="R2", question_id="Q1", question="問題", answer="答案变化", citations=citations)

    assert stale["manual_decision"] is None
    assert stale["review_status"] == "PENDING_OWNER_RUNTIME_REVIEW"
    assert stale["previous_review"]["manual_decision"] == "ANSWER_GOLD_MATCH"
    assert stale["previous_review"]["carry_status"] == "STALE_FINGERPRINT_MISSING"
    assert same["manual_decision"] == "ANSWER_GOLD_MATCH"
    assert same["review_status"] == "OWNER_REVIEWED"
    assert changed["run_fingerprint"] != current["run_fingerprint"]


def test_shared_source_role_rescue_prefers_body_evidence_for_dop_dimensions_and_rank():
    atomic = {
        "dop": {
            "evidence_id": "DOP-BODY",
            "source_id": "V262-dop",
            "file_name": "2025年设计管理总结.md",
            "source_path": "[LOCAL_PATH_REDACTED]��结.md",
            "heading_path": "正文",
            "text": "DOP设计管理模块适配及应用，共完成41个项目，DOP设计管理平台新开项目上线覆盖率100%。",
        },
        "dimensions": {
            "evidence_id": "DIM-BODY",
            "source_id": "V262-dim",
            "file_name": "光谷实验中学项目.md",
            "source_path": "[LOCAL_PATH_REDACTED]�中学项目.md",
            "heading_path": "光谷实验中学项目 > 设计管理工作中涉及的方面",
            "text": "设计管理工作中涉及的方面：报批报建、方案比选、相关方沟通、设计策划、设计任务书、限额设计。",
        },
        "rank": {
            "evidence_id": "RANK-BODY",
            "source_id": "V262-rank",
            "file_name": "2025年EPC项目设计管理四季度检查暨EPC设计管理示范项目验收的通报.docx",
            "source_path": "[LOCAL_PATH_REDACTED]",
            "heading_path": "Document Body",
            "text": "表名：EPC项目设计管理检查评价排名表 行：1 | 华中师范大学南湖训练馆项目 | 华中公司 | 97.1",
        },
        "huaibei": {
            "evidence_id": "HUAIBEI-BODY",
            "source_id": "V262-huaibei",
            "file_name": "淮北科创项目含超塔（安徽）.md",
            "source_path": "[LOCAL_PATH_REDACTED]��科创项目含超塔（安徽）.md",
            "heading_path": "第 3 页/段",
            "text": "总投资额12.2亿元；仍有超概4000万元风险；设计方案优化35项，设计优化率达到3.6%。",
        },
    }
    assert _owner_answer_gold_source_rescue("2025 年上半年二公司 DOP 设计管理模块应用情况如何？", atomic)[0]["evidence_id"] == "DOP-BODY"
    assert _owner_answer_gold_source_rescue("光谷实验中学项目设计管理共涉及几个维度的工作？分别是哪些？", atomic)[0]["evidence_id"] == "DIM-BODY"
    assert _owner_answer_gold_source_rescue("2025年EPC项目设计管理检查评价排名，第一名是哪个项目", atomic)[0]["evidence_id"] == "RANK-BODY"
    assert _owner_answer_gold_source_rescue("某科创基地项目投标期间的投资预算是多少？化解多少超概风险、效益提升到多少？", atomic)[0]["evidence_id"] == "HUAIBEI-BODY"


def test_v2_docx_table_citation_keeps_table_and_row_range():
    assert _display_location({"table": 11, "row_start": 4, "row_end": 37}) == "表11，第4-37行"


def test_v2_xlsx_citation_keeps_sheet_and_row_range():
    assert _display_location({"sheet_name": "施工图审核要点提示汇编正文", "row_start": 631, "row_end": 652}) == "施工图审核要点提示汇编正文，第631-652行"


def test_same_named_xlsx_sections_keep_distinct_evidence(tmp_path):
    path = tmp_path / "review.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "正文"
    sheet.append(["3.动力及照明配电系统", "3.1普通电气要点", "电气"])
    sheet.append([None, "3.2普通电气要点", "电气"])
    sheet.append(["4.防雷接地系统", "4.1普通电气要点", "电气"])
    sheet.append(["3.动力及照明配电系统", "3.1车库电气要点", "车库电气"])
    sheet.append([None, "3.2车库电气要点", "车库电气"])
    sheet.append(["4.防雷接地系统", "4.1车库电气要点", "车库电气"])
    workbook.save(path)

    engine = object.__new__(v2.V2TrialEngine)
    engine.atomic = {}
    engine._load_approved_xlsx_review_sections(path, "D1")
    sections = [
        item for item in engine.atomic.values()
        if item.get("granularity") == "xlsx_section" and item["location"].get("section") == "3.动力及照明配电系统"
    ]
    assert {item["location"]["row_start"] for item in sections} == {1, 4}
    assert {item["text"].split("专业：", 1)[1].split("\n", 1)[0] for item in sections} == {"电气", "车库电气"}


def test_exact_core_phrase_rescue_adds_existing_shadow_evidence_without_query_injection():
    question = "二级设计进度计划，包含哪些节点"
    wrong = {"evidence_id": "E1", "document_id": "D1", "section_id": "S1", "text": "设计关键节点计划需要考虑方案比选。", "source_path": "[LOCAL_PATH_REDACTED]", "file_name": "wrong.docx"}
    exact = {"evidence_id": "E2", "document_id": "D2", "section_id": "S2", "text": "二级设计进度计划：应包括初步设计完成等节点。", "source_path": "[LOCAL_PATH_REDACTED]", "file_name": "manual.pdf", "location": {"page": 19}, "granularity": "frozen_chunk", "lineage_status": "LINEAGE_NOT_APPLICABLE"}
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
    case = {"candidate_id": "FG-1", "case_id": "RG-1", "question": "二级设计进度计划包含哪些节点？", "expected_source_path": "[LOCAL_PATH_REDACTED]", "expected_source_location": "第19页", "required_terms": ["初步设计完成"], "owner_asserted_answer": "不参与运行时", "ready": True}
    result = {"answer_status": "ANSWERED", "answer": "结论：二级设计进度计划应包括初步设计完成。", "citations": [{"citation_id": "S1", "source_path": "[LOCAL_PATH_REDACTED]", "display_location": "第19页"}], "provider_http_requests": 0}
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
    monkeypatch.setattr(v2, "KNOWLEDGE_STORE", TrialKnowledgeStore(tmp_path / "knowledge-store.json"))
    monkeypatch.setattr(v2, "_source_runtime_status", lambda _: "INDEXED_SHADOW")
    v2._append_jsonl(trial / "trial_audit.jsonl", {"query_id": "Q-1", "question": "二级设计进度计划包含哪些节点？", "answer_status": "ANSWERED", "document_ids": [], "evidence_ids": []})
    feedback = v2.feedback(v2.V2FeedbackRequest(query_id="Q-1", feedback_type="回答不完整", source_path="[LOCAL_PATH_REDACTED]", source_location="第19页", required_terms=["初步设计完成"], expected_answer="仅供审核"))
    candidate_id = feedback["feedback_event"]["growth_candidate_id"]
    review = v2.growth_review(v2.GrowthReviewRequest(candidate_id=candidate_id, decision="APPROVE", confirmed_source_path="[LOCAL_PATH_REDACTED]", confirmed_source_location="第19页", required_terms=["初步设计完成"]))
    assert review["regression_case"]["ready"] is True

    class Engine:
        def answer(self, question, *, detect_growth):
            assert question == "二级设计进度计划包含哪些节点？"
            assert detect_growth is False
            return {"answer_status": "ANSWERED", "answer": "结论：二级设计进度计划包括初步设计完成。", "citations": [{"citation_id": "S1", "source_path": "[LOCAL_PATH_REDACTED]", "display_location": "第19页"}], "provider_http_requests": 0}

    monkeypatch.setattr(v2, "_engine_instance", lambda: Engine())
    result = v2.growth_regression(v2.GrowthRegressionRequest(candidate_id=candidate_id))
    assert result["regression"]["regression_status"] == "PASSED"
    closure = v2.feedback_closures()["closures"][0]
    assert closure["closure_status"] == "CLOSED"
    assert result["automatic_knowledge_publish"] == 0


def test_source_closure_gate_normalizes_quotes_and_rejects_structural_terms(monkeypatch):
    monkeypatch.setattr(v2, "_source_runtime_status", lambda _: "SOURCE_IDENTIFIED")
    case = v2._case_with_readiness({"expected_source_path": '"[LOCAL_PATH_REDACTED]"', "required_terms": ["目录"], "requested_required_terms": ["目录"]})
    assert case["expected_source_path"] == "[LOCAL_PATH_REDACTED]"
    assert case["ready"] is False
    assert case["invalid_required_terms"] == ["目录"]
    assert v2._closure_status({"decision": "APPROVE"}, case, {"regression_status": "FAILED"}) == "SOURCE_CLOSURE_REQUIRED"


def test_same_file_name_at_a_different_path_does_not_inherit_shadow_approval(tmp_path, monkeypatch):
    register = tmp_path / "source_closure.jsonl"
    register.write_text('{"correct_source_path":"D:\\\\work\\\\second-company\\\\manual.pdf","correct_source_file_name":"manual.pdf","source_status":"VERIFIED_RUNTIME"}\n', encoding="utf-8")
    monkeypatch.setattr(v2, "SOURCE_CLOSURE_REGISTER", register)
    assert v2._declared_source_status("[LOCAL_PATH_REDACTED]") == "SOURCE_IDENTIFIED"


def test_role_fact_candidate_can_promote_complete_role_evidence_beyond_top_five():
    candidate = {"candidate_rank": 6, "lineage_status": "LINEAGE_NOT_APPLICABLE", "scope": {}, "text": "阶段性设计成果审查由设计支持机构牵头，项目部参与。"}
    plan = {"original_question": "阶段性设计成果审查是由谁组织，谁参与？", "organization": [], "project": [], "year": [], "specialty": [], "metric": []}
    assert _direct_candidate(candidate, plan) is True


def test_specialty_scope_can_match_explicit_evidence_text():
    plan = {"organization": [], "project": ["工业厂房项目"], "year": [], "specialty": ["结构"], "metric": []}
    row = {"source_path": "[LOCAL_PATH_REDACTED]", "file_name": "risk.docx", "text": "设备基础与结构梁柱错位"}
    scope, _ = _scope(plan, {}, {}, row)
    assert scope["specialty"] == "MATCH"


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


def test_approved_gold_course_rescue_fetches_all_five_chapter_headings():
    question = "《EPC项目设计管理方法与实务》课程分为哪5个章节？"
    texts = (
        "课程的整体框架共分为五个章节。",
        "一 背景介绍",
        "二 设计管理基本动作与要素",
        "三 设计管理关键动作实施要点",
        "四 全专业设计技术管控要点",
        "五 存在的问题与建议",
    )
    atomic = {
        f"E{index}": {
            "evidence_id": f"E{index}",
            "source_id": "V262-COURSE",
            "file_name": "EPC项目设计管理方法与实务.md",
            "text": text,
        }
        for index, text in enumerate(texts)
    }

    rescued = _approved_gold_source_rescue(question, atomic)

    assert {row["evidence_id"] for row in rescued} == set(atomic)


def test_owner_gold_review_closure_rescues_the_exact_duty_list_source():
    question = "扬州大运河“十里外滩”项目设计策划评审后形成了几项督办事项？要求何时完成？"
    fact_text = "督办清单（7项修改事宜，限6.1–6.15完成）"
    atomic = {
        "RIGHT": {
            "evidence_id": "RIGHT",
            "file_name": "设计策划评审.md",
            "source_path": r"[LOCAL_PATH_REDACTED]��\设计策划评审.md",
            "text": fact_text,
        },
        "QUERY_PAGE": {
            "evidence_id": "QUERY_PAGE",
            "file_name": "设计策划评审.md",
            "source_path": r"[LOCAL_PATH_REDACTED]",
            "text": fact_text,
        },
        "OTHER": {
            "evidence_id": "OTHER",
            "file_name": "other.md",
            "source_path": r"[LOCAL_PATH_REDACTED]��\other.md",
            "text": fact_text,
        },
    }

    rescued = _owner_answer_gold_source_rescue(question, atomic)

    assert [row["evidence_id"] for row in rescued] == ["RIGHT"]


def test_structured_source_origin_uses_the_confirmed_original_path():
    parsed = {"file_name": "丽水医院项目 .docx", "source_path": r"[LOCAL_PATH_REDACTED]��院项目 .docx"}

    restored = _restore_source_origin(parsed)

    assert restored["source_path"] == r"[LOCAL_PATH_REDACTED]�公司技术部\法人管项目\体系建设\5、检查督导\评价表\丽水医院项目 .docx"


def test_evaluation_table_rescue_is_scoped_to_its_exact_named_table():
    question = "《公司EPC项目设计管理评价表》采用多少分制？9个评价维度分别是什么？"
    title = "公司EPC项目设计管理评价表"
    labels = (
        "设计管理架构", "设计策划管理", "设计计划管理", "限额设计管理", "设计优化管理",
        "设计质量管理", "材料设备选型报审", "设计报批报建", "设计复盘总结",
    )
    atomic = {
        f"E{index}": {
            "evidence_id": f"E{index}",
            "source_id": "V262-EVALUATION",
            "file_name": "丽水医院项目.docx",
            "heading_path": title,
            "text": label,
        }
        for index, label in enumerate(labels, start=1)
    }
    atomic["OTHER"] = {
        "evidence_id": "OTHER",
        "source_id": "V262-OTHER",
        "file_name": "常熟台账.xlsx",
        "heading_path": "直属分公司设计价值创造统计表",
        "text": "设计优化管理|设计创效率",
    }

    rescued = _approved_gold_source_rescue(question, atomic)

    assert {row["evidence_id"] for row in rescued} == {f"E{index}" for index in range(1, 10)}


def test_huawei_optimization_rescue_stays_in_the_approved_baicaoyuan_source():
    question = "华为百草园项目通过设计优化完成多少项优化、创效多少？"
    atomic = {
        "RIGHT": {
            "evidence_id": "RIGHT",
            "source_id": "V262-BAICAOYUAN",
            "file_name": "百草园超高层产品线观摩材料.md",
            "source_path": r"[LOCAL_PATH_REDACTED]�优秀管理经验\4-为百草园超高层产品线观摩材料0528(1).pdf",
            "text": "桩基支护优化22项，主体结构优化38项，累计技术创效2473万元",
        },
        "OTHER": {
            "evidence_id": "OTHER",
            "source_id": "V262-OTHER",
            "file_name": "其他百草园材料.md",
            "source_path": r"[LOCAL_PATH_REDACTED]��\百草园.md",
            "text": "桩基支护优化22项，主体结构优化38项，累计技术创效2473万元",
        },
    }

    rescued = _approved_gold_source_rescue(question, atomic)

    assert [row["evidence_id"] for row in rescued] == ["RIGHT"]
