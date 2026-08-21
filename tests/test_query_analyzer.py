from pathlib import Path

from app.query_analyzer import analyze_question


RULES = Path(__file__).parents[1] / "config" / "metadata_rules.yaml"


def test_query_analyzer_extracts_soft_metadata_filters() -> None:
    analysis = analyze_question("医院项目施工图设计策划有哪些管理要求？", RULES)

    assert analysis.intent == "POLICY_QUERY"
    assert analysis.filters["building_type"] == "医院"
    assert analysis.filters["project_stage"] == "施工图设计"
    assert analysis.filters["topic"] == ["设计策划"]


def test_query_analyzer_does_not_force_unknown_filters() -> None:
    analysis = analyze_question("一个资料库没有覆盖的开放问题", RULES)

    assert analysis.filters == {}
    assert analysis.intent == "GENERAL_RAG"
