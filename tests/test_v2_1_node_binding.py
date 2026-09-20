from scripts.build_v2_1_node_binding import classify


def test_node_binding_keeps_root_and_adds_detail_rule():
    rows = classify("EPC设计任务书与接口管理")
    ids = {row["knowledge_node_id"] for row in rows}
    assert "design-management" in ids
    assert "design-management/epc-design-process" in ids
    assert "design-management/design-support/设计任务书" in ids
    assert all(row["status"] in {"VERIFIED", "RULE_BASED"} for row in rows)
