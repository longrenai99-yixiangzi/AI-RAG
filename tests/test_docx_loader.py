from pathlib import Path

from app.ingestion.loaders.docx_loader import DOCXLoader


FIXTURES = Path(__file__).parent / "fixtures" / "docx"
LOADER = DOCXLoader()


def test_normal_docx_extracts_paragraph_source_block() -> None:
    result = LOADER.load(FIXTURES / "normal.docx", "normal")

    assert result.status == "parsed"
    assert len(result.blocks) == 1
    assert "普通 DOCX 段落文本。" in result.blocks[0].text
    assert result.blocks[0].source_path.endswith("normal.docx")
    assert result.blocks[0].location == {"paragraph_start": 1, "paragraph_end": 1}


def test_heading_docx_preserves_nested_heading_paths() -> None:
    result = LOADER.load(FIXTURES / "headings.docx", "headings")

    assert result.status == "parsed"
    assert [block.heading_path for block in result.blocks] == [
        "一级标题",
        "一级标题 > 二级标题",
    ]
    assert result.blocks[0].location == {"paragraph_start": 1, "paragraph_end": 2}
    assert result.blocks[1].location == {"paragraph_start": 3, "paragraph_end": 4}


def test_table_docx_preserves_rows_and_columns() -> None:
    result = LOADER.load(FIXTURES / "table.docx", "table")

    assert result.status == "parsed"
    table_blocks = [block for block in result.blocks if block.location.get("table") == 1]
    assert len(table_blocks) == 1
    block = table_blocks[0]
    assert block.heading_path == "表格章节"
    assert "字段 | 内容" in block.text
    assert "类型 | DOCX" in block.text
    assert block.location == {"table": 1, "rows": 3, "columns": 2}


def test_empty_docx_returns_empty_status() -> None:
    result = LOADER.load(FIXTURES / "empty.docx", "empty")

    assert result.status == "empty"
    assert result.blocks == []


def test_broken_docx_returns_read_error_without_raising() -> None:
    result = LOADER.load(FIXTURES / "broken.docx", "broken")

    assert result.status == "read_error"
    assert result.blocks == []
    assert result.error


def test_legacy_doc_is_not_converted(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.doc"
    legacy_path.write_bytes(b"legacy document placeholder")

    result = LOADER.load(legacy_path, "legacy")

    assert result.status == "read_error"
    assert result.blocks == []
    assert result.error and "不自动转换" in result.error
