from scripts.close_business_gold_020a22 import _compact_locations, _lineage_status


def test_lineage_requires_row_evidence_and_file_relation_for_confirmation():
    assert _lineage_status(
        same_project=True,
        common_headers=["专业类别"],
        exact_matches=[],
        docx_count=34,
        xlsx_count=80,
        docx_professions={"建筑"},
        xlsx_professions={"建筑", "消防"},
        file_reference_found=False,
    ) == "LINEAGE_PARTIAL"


def test_compact_locations_keeps_position_not_raw_excerpt():
    value = _compact_locations(
        [{"paragraph": 1, "text": "不要进入审核表的长正文"}, {"table": 11, "row": 3, "values": ["长表头"]}]
    )
    assert value == [{"paragraph": 1}, {"table": 11, "row": 3}]
