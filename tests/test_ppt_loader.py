from pathlib import Path

from app.ingestion.loaders.ppt_loader import PPTLoader


FIXTURES = Path(__file__).parent / "fixtures" / "ppt"
LOADER = PPTLoader()


def test_normal_pptx_extracts_text_title_notes_and_slide_location() -> None:
    result = LOADER.load(FIXTURES / "normal.pptx", "normal")

    assert result.status == "parsed"
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block.heading_path == "普通 PPTX"
    assert block.location == {"slide": 1, "title": "普通 PPTX"}
    assert block.source_path.endswith("normal.pptx")
    assert "这是一个普通文本框内容。" in block.text
    assert "讲者备注：普通幻灯片备注。" in block.text


def test_multi_page_pptx_emits_one_block_per_content_slide() -> None:
    result = LOADER.load(FIXTURES / "multi_page.pptx", "multi")

    assert result.status == "parsed"
    assert len(result.blocks) == 3
    assert [block.location["slide"] for block in result.blocks] == [1, 2, 3]
    assert [block.heading_path for block in result.blocks] == [
        "第 1 页",
        "第 2 页",
        "第 3 页",
    ]


def test_table_pptx_preserves_table_rows_and_notes() -> None:
    result = LOADER.load(FIXTURES / "table.pptx", "table")

    assert result.status == "parsed"
    assert len(result.blocks) == 1
    assert "表格：" in result.blocks[0].text
    assert "字段 | 内容" in result.blocks[0].text
    assert "类型 | PPTX" in result.blocks[0].text
    assert "讲者备注：表格备注。" in result.blocks[0].text
    assert result.blocks[0].location["slide"] == 1


def test_empty_pptx_has_empty_status() -> None:
    result = LOADER.load(FIXTURES / "empty.pptx", "empty")

    assert result.status == "empty"
    assert result.blocks == []


def test_legacy_ppt_is_not_converted(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.ppt"
    legacy_path.write_bytes(b"legacy presentation placeholder")

    result = LOADER.load(legacy_path, "legacy")

    assert result.status == "unsupported_legacy_format"
    assert result.blocks == []


def test_malformed_pptx_returns_read_error_without_raising(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.pptx"
    broken_path.write_bytes(b"not a pptx")

    result = LOADER.load(broken_path, "broken")

    assert result.status == "read_error"
    assert result.blocks == []
    assert result.error


def test_large_pptx_is_isolated_as_read_error() -> None:
    result = PPTLoader(max_file_size_mb=0).load(FIXTURES / "normal.pptx", "large")

    assert result.status == "read_error"
    assert result.blocks == []
    assert result.error and "解析上限" in result.error
