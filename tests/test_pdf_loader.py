from pathlib import Path

from app.ingestion.loaders.pdf_loader import PDFLoader, extract_value_creation_rows, extract_value_creation_summary


FIXTURES = Path(__file__).parent / "fixtures" / "pdf"
LOADER = PDFLoader()


def test_normal_pdf_emits_page_source_block_and_quality_metrics() -> None:
    result = LOADER.load(FIXTURES / "normal.pdf", "normal")

    assert result.status == "parsed"
    assert result.quality is not None
    assert result.quality.total_pages == 1
    assert result.quality.text_pages == 1
    assert result.quality.image_page_ratio == 0
    assert len(result.blocks) == 1
    assert result.blocks[0].location == {"page": 1, "text_length": len(result.blocks[0].text)}
    assert "Table text:" in result.blocks[0].text
    assert "Field | Value" in result.blocks[0].text


def test_empty_pdf_returns_empty_status_without_ocr() -> None:
    result = LOADER.load(FIXTURES / "empty.pdf", "empty")

    assert result.status == "empty"
    assert result.quality is not None
    assert result.quality.total_pages == 1
    assert result.quality.text_chars == 0
    assert result.quality.image_pages == 0
    assert result.quality.suspected_scanned is False
    assert len(result.blocks) == 1
    assert result.blocks[0].text == ""


def test_scanned_feature_pdf_is_marked_needs_ocr_without_running_ocr() -> None:
    result = LOADER.load(FIXTURES / "scanned_feature.pdf", "scanned")

    assert result.status == "needs_ocr"
    assert result.quality is not None
    assert result.quality.total_pages == 2
    assert result.quality.image_pages == 2
    assert result.quality.image_page_ratio == 1
    assert result.quality.suspected_scanned is True
    assert len(result.blocks) == 2
    assert [block.location["page"] for block in result.blocks] == [1, 2]


def test_broken_pdf_returns_read_error_without_raising() -> None:
    result = LOADER.load(FIXTURES / "broken.pdf", "broken")

    assert result.status == "read_error"
    assert result.blocks == []
    assert result.quality is None
    assert result.error


def test_value_creation_summary_extracts_stage_counts() -> None:
    text = """设计价值创造点各专业、阶段数量统计
专业
阶段
方案设计
初步设计
施工图设计
备注
总图规划
9
0
2
电气
2
5
38
合计
88
72
578
"""
    assert extract_value_creation_summary(text)["合计"] == (88, 72, 578)


def test_value_creation_rows_extract_value_item_and_applicability() -> None:
    text = """序号
专业类别
部位或所属系统
图纸阶段
业态
价值项
价值点成效
适用条件说明
工期
施工
品质
收入
成本
效益
1
总图规划
场地整体控制
方案设计
学校
价值点内容
-
+
/
/
-
+
适用于山地或高差较大的项目。
"""
    assert extract_value_creation_rows(text)[0]["value_item"] == "价值点内容"
    assert extract_value_creation_rows(text)[0]["applicability"] == "适用于山地或高差较大的项目。"
