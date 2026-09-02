import numpy as np

from app.retrieval.hierarchical_v1 import HierarchicalIndex, _merge_section_candidates, _merge_table_parent_sections
from app.retrieval.query_planner_v1 import plan_query
from scripts.run_hierarchical_retrieval_v1 import _evaluate


def test_rule_planner_covers_single_policy_aggregation_comparison_and_multifact():
    policy = plan_query("2026年公司责任状要求DOP上传数量是多少？")
    aggregation = plan_query("某项目价值创造清单有哪些专业，每个专业多少条，其中利润>0多少条？")
    comparison = plan_query("自动喷淋系统管材方案比选有哪些方案？")
    multi = plan_query("土木公司有哪些督办事项？")
    assert policy.year == ["2026"]
    assert policy.document_type_hint == ["RESPONSIBILITY_CONTRACT"]
    assert {"LIST_DISTINCT", "GROUP_BY", "COUNT", "FILTER"} <= set(aggregation.aggregation_plan)
    assert len(aggregation.subquestions) >= 3
    assert comparison.query_type in {"OPTION_QUERY", "COMPARISON_QUERY"}
    assert multi.subquestions


def test_hierarchical_document_section_table_and_registration_penalty():
    documents = [
        _document("body", "年度述职.md", "年度述职 公司 2025 创效金额 4.45亿元", "RETROSPECTIVE"),
        _document("register", "资料登记.md", "资料登记 公司 2025 创效金额", "REGISTER_PAGE"),
        _document("rescue", "项目案例.md", "项目案例", "PROJECT_CASE"),
    ]
    sections = [
        _section("s-body", "body", "年度总结", "公司年度创效金额"),
        _section("s-register", "register", "登记", "外部资料入口"),
        _section("s-rescue", "rescue", "价值创造", "公司 创效金额"),
    ]
    tables = [_table("t-body", "body", "s-body", "自动喷淋 管材 传统镀锌钢管 PVC-C")]
    atomic = [{"evidence_id": "e1", "document_id": "body", "section_id": "s-body", "source_path": "D:/body.md", "file_name": "年度述职.md", "location": {"line_start": 1, "line_end": 1}, "granularity": "line", "text": "2025年公司设计创效金额约4.45亿元。", "lineage_status": "LINEAGE_NOT_APPLICABLE"}]
    index = HierarchicalIndex(documents, sections, tables, atomic, np.asarray([[1, 0], [1, 0], [0, 1]], dtype=np.float32), np.asarray([[1, 0], [1, 0], [1, 0]], dtype=np.float32))
    plan = plan_query("2025年公司设计创效金额是多少？")
    result = index.retrieve(plan, [1, 0])
    assert result["document_candidates"][0]["document_id"] == "body"
    assert result["section_candidates"]
    table_result = index.retrieve(plan_query("自动喷淋管材方案比选有哪些方案？"), [1, 0])
    assert table_result["table_candidates"][0]["table_id"] == "t-body"
    merged = _merge_section_candidates(
        [{"section_id": "s-body", "rank": 1, "candidate_origin": "HIERARCHICAL"}],
        [{"section_id": "s-rescue", "rank": 1, "candidate_origin": "GLOBAL_RESCUE"}],
    )
    assert any(item["candidate_origin"] == "GLOBAL_RESCUE" for item in merged)
    table_parent = _merge_table_parent_sections([], [{"table_id": "t-body", "rank": 1, "record": {"section_id": "s-body"}}], {"s-body": sections[0]})
    assert table_parent[0]["section_id"] == "s-body"


def test_scope_unavailable_and_lineage_partial_are_evaluation_boundaries():
    gold = {"question_id": "X", "gold_type": "SOURCE_SCOPE_GOLD", "gold_primary_source": "D:/outside.docx", "gold_location": {"page": 1}}
    result = {"document_candidates": [], "section_candidates": [], "table_candidates": [], "atomic_candidates": []}
    evaluation = _evaluate(gold, {}, {"runtime_source_available": False}, result)
    assert evaluation["failure"] == "SOURCE_SCOPE_MISSING"


def test_document_stage_keeps_the_best_section_as_a_document_representation():
    documents = [
        _document("target", "guide.pdf", "general guide", "MANAGEMENT_GUIDE"),
        _document("other", "other.md", "unrelated annual material", "OTHER"),
    ]
    sections = [
        _section("target-section", "target", "task book", "task book required contents"),
        _section("other-section", "other", "other", "unrelated text"),
    ]
    index = HierarchicalIndex(
        documents,
        sections,
        [],
        [],
        np.asarray([[0, 1], [1, 0]], dtype=np.float32),
        np.asarray([[1, 0], [0, 1]], dtype=np.float32),
    )
    result = index.retrieve(plan_query("task book required contents"), [1, 0])
    target = next(item for item in result["document_candidates"] if item["document_id"] == "target")
    assert target["representation_trace"]["best_section_dense_rank"] == 1


def test_table_miss_is_not_hidden_by_global_rescue_evidence():
    source = "D:/target.xlsx"
    gold = {"question_id": "X", "gold_type": "OFFICIAL_GOLD", "gold_primary_source": source, "gold_location": {"sheet_name": "Sheet1", "row_start": 10}}
    document = {"rank": 2, "source_path": source}
    section = {"rank": 12, "source_path": source, "location": {"sheet_name": "Sheet1"}, "candidate_origin": "HIERARCHICAL"}
    table = {"rank": 12, "source_path": source, "location": {"sheet_name": "Sheet1", "row_start": 10, "row_end": 12}}
    evidence = {"rank": 1, "source_path": source, "location": {"sheet_name": "Sheet1", "row_start": 10}, "candidate_origin": "GLOBAL_RESCUE"}
    result = {"document_candidates": [document], "local_section_candidates": [section], "section_candidates": [section], "table_candidates": [table], "atomic_candidates": [evidence]}
    evaluation = _evaluate(gold, {}, {"runtime_source_available": True}, result)
    assert evaluation["failure"] == "TABLE_MISSED"
    assert evaluation["rescue_status"] == "GLOBAL_RESCUE_RECOVERED"


def _document(document_id, file_name, text, document_type):
    return {"document_id": document_id, "knowledge_root_id": "Root-001", "source_path": f"D:/{document_id}.md", "file_name": file_name, "document_search_text": text, "document_type": document_type, "document_role": "汇报材料", "authority_level": "L6", "scope": {"organization": ["公司"]}, "organization": ["公司"], "project": [], "year": ["2025"], "specialty": [], "metric": ["创效金额"], "lineage_status": "LINEAGE_NOT_APPLICABLE"}


def _section(section_id, document_id, heading, text):
    return {"section_id": section_id, "document_id": document_id, "knowledge_root_id": "Root-001", "source_path": f"D:/{document_id}.md", "file_name": f"{document_id}.md", "heading": heading, "heading_path": heading, "parent_heading": "", "location": {"start": {"line_start": 1}, "end": {"line_end": 3}}, "section_search_text": text, "document_type": "OTHER", "document_role": "汇报材料", "authority_level": "L6", "scope": {}, "lineage_status": "LINEAGE_NOT_APPLICABLE"}


def _table(table_id, document_id, section_id, text):
    return {"table_id": table_id, "document_id": document_id, "section_id": section_id, "knowledge_root_id": "Root-001", "source_path": f"D:/{document_id}.md", "file_name": f"{document_id}.md", "sheet_name": "Sheet1", "header": ["方案"], "source_location": {"sheet_name": "Sheet1", "row_start": 1, "row_end": 3}, "table_search_text": text, "document_type": "TABLE_LEDGER", "document_role": "标准模板", "authority_level": "L3", "scope": {}, "lineage_status": "LINEAGE_PARTIAL"}
