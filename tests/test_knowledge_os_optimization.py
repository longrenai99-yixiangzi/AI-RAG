from app.ingestion.atomic_search import search_atomic_evidence
from app.trial.v2 import CONFIG, _asks_organization_alias_relationship, _failure_message, _matches_reviewed_question, _rank_atomic_candidates, _resolve_followup, _review_candidates, _synthesis_trace
from scripts.build_verified_evidence_bundle_v1 import _coverage, _link_only, _same_scope_conflicts
from scripts.run_verified_answer_engine_v2 import _answer_relevant


def test_search_context_improves_retrieval_without_changing_raw_text():
    record = {"evidence_id": "E1", "text": "原始正文只说明中心设置。", "raw_text": "原始正文只说明中心设置。", "search_context": "二公司 总部中心隶属哪个部门", "file_name": "source.pdf"}
    result = search_atomic_evidence("总部中心隶属哪个部门", [record])
    assert result[0]["record"]["raw_text"] == "原始正文只说明中心设置。"
    assert "隶属" not in result[0]["record"]["raw_text"]


def test_parent_evidence_is_added_once_and_question_variants_do_not_duplicate_it():
    child = {"evidence_id": "C1", "parent_evidence_id": "P1", "source_id": "S1", "source_version": "V1", "text": "岗位设置", "search_context": "岗位设置 相似问", "file_name": "source.pdf", "rank": 1}
    parent = {"evidence_id": "P1", "source_id": "S1", "source_version": "V1", "text": "主体为区域分公司中心，岗位属于选择设置。", "file_name": "source.pdf"}
    ranked = _rank_atomic_candidates("区域分公司中心岗位设置", [child, {**child, "rank": 2}], {"C1": child, "P1": parent})
    assert {item["evidence_id"] for item in ranked} == {"C1", "P1"}


def test_parent_evidence_from_another_version_is_not_added():
    child = {"evidence_id": "C1", "parent_evidence_id": "P1", "source_id": "S1", "source_version": "V2", "text": "岗位设置", "file_name": "source.pdf"}
    parent = {"evidence_id": "P1", "source_id": "S1", "source_version": "V1", "text": "旧版父条款", "file_name": "source.pdf"}
    ranked = _rank_atomic_candidates("岗位设置", [child], {"C1": child, "P1": parent})
    assert [item["evidence_id"] for item in ranked] == ["C1"]


def test_alias_relationship_uses_system_config_evidence_first():
    question = "中建三局第二建设公司设计与技术支持中心与二公司设计与技术支持中心是什么关系？"
    alias = {"evidence_id": "A1", "source_id": "SYS_ORGANIZATION_ALIASES", "text": "中建三局第二建设公司：二公司", "file_name": "组织别名配置（系统）"}
    other = {"evidence_id": "E1", "text": "中建三局第二建设公司设计与技术支持中心运行方案", "file_name": "运行方案.pdf"}
    ranked = _rank_atomic_candidates(question, [other, alias], {"A1": alias, "E1": other})
    assert _asks_organization_alias_relationship(question) is True
    assert ranked[0]["source_id"] == "SYS_ORGANIZATION_ALIASES"


def test_exact_reviewed_question_is_ranked_first_without_duplicate_answer_text():
    question = "区域公司中心可以额外设什么岗位？"
    reviewed = {"evidence_id": "K1", "approved_trial_knowledge": True, "standard_question": "区域公司中心可选哪些岗位？", "similar_questions": [question], "text": "区域分公司中心选择设置技术投标岗、钢筋翻样岗。", "file_name": "policy.pdf"}
    other = {"evidence_id": "E1", "text": question * 3, "file_name": "other.pdf"}
    ranked = _rank_atomic_candidates(question, [other, reviewed, reviewed], {"K1": reviewed, "E1": other})
    assert _matches_reviewed_question(reviewed, question) is True
    assert ranked[0]["evidence_id"] == "K1"
    assert [item["evidence_id"] for item in ranked].count("K1") == 1


def test_body_with_link_is_not_link_only_but_registration_stub_is():
    assert _link_only("来源：[[制度原文]]") is True
    assert _link_only("区域分公司中心选择设置技术投标岗。") is False
    assert _link_only("本条款明确公司总部中心的职责、工作边界和运行要求，详见[[制度原文]]。后续执行应保留审核记录。") is False


def test_subquestion_coverage_is_checked_per_fact():
    candidates = [{"evidence_id": "E1", "role": "DIRECT", "text": "公司总部中心作为二级部室。"}]
    coverage = _coverage(["组织定位和隶属关系", "各层级的岗位或机构设置"], {}, candidates)
    assert [item["coverage_status"] for item in coverage] == ["COVERED", "EVIDENCE_INSUFFICIENT"]


def test_page_numbers_do_not_create_metric_conflict():
    scope = {"organization": "MATCH", "year": "MATCH", "metric": "MATCH"}
    candidates = [
        {"evidence_id": "E1", "scope": scope, "text": "第1页。2025年公司设计创效金额100万元。"},
        {"evidence_id": "E2", "scope": scope, "text": "第2页。2025年公司设计创效金额100万元。"},
    ]
    assert _same_scope_conflicts(candidates, {"organization": ["公司"], "year": ["2025"], "metric": ["创效金额"]}) == {}


def test_followup_uses_previous_question_not_previous_answer():
    previous = {"question": "中建三局二公司设计与技术支持中心的组织架构是什么样的", "resolved_question": "中建三局二公司设计与技术支持中心的组织架构是什么样的", "answer": "错误答案不应进入补全"}
    resolved = _resolve_followup("那分公司呢？", previous)
    assert "中建三局第二建设公司" in resolved
    assert "错误答案" not in resolved


def test_v2_synthesis_contract_exposes_provider_posture_and_deterministic_fallback():
    """The contract must mirror whatever posture is configured.

    The internal trial now runs with the provider-dependent claim enabled under a
    hard request budget, so the status flipped from BLOCKED_PROVIDER_CLAIM_DISABLED
    to READY. Assert against the configured posture instead of a frozen string so this
    test keeps guarding the contract when the switch is toggled either way.
    """
    bundle = {"question": "制度要求是什么？", "verified_evidence": [{"evidence_id": "E1", "source_id": "S1", "source_version": "V1"}]}
    trace = _synthesis_trace(bundle, "EVIDENCE_SYNTHESIS")
    expected = "READY" if CONFIG.get("provider_claim_answer_enabled") else "BLOCKED_PROVIDER_CLAIM_DISABLED"
    assert trace["integration_status"] == expected
    # The dry-run trace stays a deterministic render with no outbound calls regardless of posture.
    assert trace["generation_mode"] == "DETERMINISTIC_EVIDENCE_RENDER"
    assert trace["provider_http_requests"] == 0
    assert trace["input_contract"]["evidence"] == [{"evidence_id": "E1", "source_id": "S1", "source_version": "V1"}]


def test_failed_answer_exposes_actionable_reason_and_review_candidates():
    bundle = {"failure_reason": "EVIDENCE_INSUFFICIENT", "candidate_evidence": [{"evidence_id": "E1", "source_id": "S1", "source_version": "V1", "file_name": "2025年总结.md", "source_path": "[LOCAL_PATH_REDACTED]��结.md", "location": {"line_start": 7, "line_end": 7}, "raw_text": "候选正文", "role": "SUPPORTING", "scope": {"year": "MATCH", "project": "NOT_APPLICABLE"}}]}
    assert "候选来源" in _failure_message(bundle)
    candidates = _review_candidates(bundle)
    assert candidates[0]["file_name"] == "2025年总结.md"
    assert candidates[0]["display_location"] == "第7-7行"


def test_organization_relation_is_verified_from_raw_text_not_search_context_alone():
    plan = {"project": [], "query_type": "SOURCE_LOOKUP"}
    supported = {"text": "公司总部设置设计与技术支持中心，作为公司设计与技术管理部二级部室。", "file_name": "source.pdf", "source_path": "[LOCAL_PATH_REDACTED]", "heading_path": "", "scope": {}}
    unsupported = {**supported, "text": "公司总部设置设计与技术支持中心。", "search_context": "隶属设计与技术管理部"}
    assert _answer_relevant(supported, "二公司总部中心隶属哪个部门？", plan) is True
    assert _answer_relevant(unsupported, "二公司总部中心隶属哪个部门？", plan) is False


def test_generic_project_count_relevance_uses_the_query_plan_not_a_second_regex():
    candidate = {"text": "2025年度最终4个项目成功打造为设计管理示范项目。", "file_name": "2025年述职.md", "source_path": "[LOCAL_PATH_REDACTED]��.md", "heading_path": "", "scope": {"project": "NOT_APPLICABLE"}}
    question = "2025年度多少个项目成功打造为设计管理示范项目？"
    assert _answer_relevant(candidate, question, {"project": [], "query_type": "AGGREGATION_QUERY"}) is True
    assert _answer_relevant(candidate, "星谷科创中心项目有哪些信息？", {"project": ["星谷科创中心项目"], "query_type": "SOURCE_LOOKUP"}) is False
