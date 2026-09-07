import app.trial.batch as batch
from types import SimpleNamespace
from pathlib import Path


def test_project_names_extracts_numbered_table_rows():
    text = "表格：\n序号 | 工程名称\n1 | 项目一\n2 | 项目二"
    assert batch._project_names(text) == ["项目一", "项目二"]


def test_batch_case_requires_source_location_and_terms():
    case = {
        "case_id": "BQ-1",
        "expected_source_path": "D:/source.docx",
        "expected_source_location": "表11",
        "required_terms": ["建筑：2条"],
    }
    result = {
        "answer_status": "ANSWERED",
        "answer": "结论：建筑：2条。",
        "citations": [{"source_path": "D:\\source.docx", "display_location": "表11，第4-5行", "citation_id": "S1"}],
        "provider_http_requests": 0,
    }
    run = batch._evaluate_case(case, result, "reviewer-001")
    assert run["regression_status"] == "PASSED"
    assert run["citation_source_hit"] is True
    assert run["citation_location_hit"] is True


def test_batch_cases_are_scoped_to_current_sources():
    cases = [
        {"expected_source_path": "D:/current.pdf", "case_id": "current"},
        {"expected_source_path": "D:/history.docx", "case_id": "history"},
    ]
    assert [case["case_id"] for case in batch._filter_cases(cases, ["d:\\CURRENT.PDF"])] == ["current"]


def test_pdf_generates_summary_acceptance_case(monkeypatch):
    block = SimpleNamespace(text="""设计价值创造点各专业、阶段数量统计
方案设计
初步设计
施工图设计
备注
合计
88
72
578
""", location={"page": 3})
    monkeypatch.setattr(batch, "load_pdf", lambda path, document_id: SimpleNamespace(status="parsed", blocks=[block]))
    cases = batch._generate_pdf_cases(Path("D:/value-creation.pdf"))
    assert {case["generation_mode"] for case in cases} == {
        "PDF_VALUE_CREATION_STAGE_SUMMARY",
        "PDF_VALUE_CREATION_PROFESSION_COUNTS",
        "PDF_VALUE_CREATION_PROFESSION_COUNT",
    }
    assert "合计：738条" in next(case for case in cases if case["generation_mode"] == "PDF_VALUE_CREATION_STAGE_SUMMARY")["required_terms"]
