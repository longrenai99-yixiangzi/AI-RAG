from __future__ import annotations

from openpyxl import Workbook

from app.ingestion.atomic_evidence import build_markdown_records, build_xlsx_records
from app.ingestion.atomic_search import query_facets, search_atomic_evidence


def test_markdown_records_have_line_location_and_heading_path(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# 制度\n\n## 要求\n必须留痕。\n```text\n# 不是标题\n```\n", encoding="utf-8")

    result = build_markdown_records(path, tmp_path)

    assert result["status"] == "parsed"
    fact = next(record for record in result["records"] if record["text"] == "必须留痕。")
    assert fact["location"] == {"line_start": 4, "line_end": 4}
    assert fact["heading_path"] == "制度 > 要求"
    assert all(record["location"]["line_start"] == record["location"]["line_end"] for record in result["records"])


def test_xlsx_records_keep_sheet_header_and_exact_row(tmp_path):
    path = tmp_path / "sample.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "医疗"
    sheet.append(["项目名称", "施工图设计总工期"])
    sheet.append(["潜江市中心医院", 332])
    workbook.save(path)
    workbook.close()

    result = build_xlsx_records(path, tmp_path)

    assert result["status"] == "parsed"
    record = next(record for record in result["records"] if "潜江市中心医院" in record["text"])
    assert record["location"]["sheet_name"] == "医疗"
    assert record["location"]["row_start"] == record["location"]["row_end"] == 2
    assert {cell["header"] for cell in record["cells"]} == {"项目名称", "施工图设计总工期"}


def test_atomic_search_prefers_matching_row():
    records = [
        {"evidence_id": "a", "text": "项目名称：其他项目 | 施工图设计总工期：100", "file_name": "a.xlsx", "source_path": "a.xlsx"},
        {"evidence_id": "b", "text": "项目名称：潜江市中心医院 | 施工图设计总工期：332", "file_name": "b.xlsx", "source_path": "b.xlsx"},
    ]

    hits = search_atomic_evidence("潜江市中心医院施工图设计总工期是多少天", records)

    assert hits[0]["record"]["evidence_id"] == "b"


def test_atomic_query_facets_keep_year_metric_and_entity():
    facets = query_facets("2026年潜江市中心医院施工图设计总工期是多少天")

    assert facets["years"] == ["2026"]
    assert "工期" in facets["metrics"]
    assert "潜江市中心医院" in facets["entities"]
    assert "2026年潜江市中心医院" not in facets["entities"]


def test_atomic_search_combines_year_project_metric_and_field_constraints():
    records = [
        {
            "evidence_id": "wrong",
            "text": "项目名称：潜江市中心医院 | 施工图设计总工期：300",
            "file_name": "设计工期库2025.xlsx",
            "source_path": "2025/设计工期库2025.xlsx",
        },
        {
            "evidence_id": "right",
            "text": "项目名称：潜江市中心医院 | 施工图设计总工期：332",
            "file_name": "设计工期库2026.xlsx",
            "source_path": "2026/设计工期库2026.xlsx",
        },
    ]

    hits = search_atomic_evidence("2026年潜江市中心医院施工图设计总工期是多少天", records)

    assert hits[0]["record"]["evidence_id"] == "right"
    assert hits[0]["year_matches"] == ["2026"]
    assert "潜江市中心医院" in hits[0]["text_entity_matches"]
    assert "总工期" in hits[0]["field_matches"]
