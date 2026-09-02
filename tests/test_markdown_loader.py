from pathlib import Path

from app.ingestion.loaders.markdown_loader import MarkdownLoader


FIXTURES = Path(__file__).parent / "fixtures" / "markdown"
LOADER = MarkdownLoader()


def test_normal_markdown_parses_front_matter_and_locations() -> None:
    result = LOADER.load(FIXTURES / "normal.md", "normal")

    assert result.status == "parsed"
    assert result.front_matter["title"] == "正常 Markdown"
    assert result.front_matter["tags"] == ["设计管理", "文档处理"]
    assert len(result.blocks) == 2
    assert result.blocks[0].heading_path == "设计管理"
    assert result.blocks[0].location == {"line_start": 8, "line_end": 10}
    assert result.blocks[1].heading_path == "设计管理 > 解析目标"
    assert result.blocks[1].location == {"line_start": 12, "line_end": 14}


def test_bom_markdown_is_read_without_bom_in_source_block() -> None:
    result = LOADER.load(FIXTURES / "bom.md", "bom")

    assert result.status == "parsed"
    assert result.blocks[0].text.startswith("# BOM Markdown")
    assert "\ufeff" not in result.blocks[0].text


def test_markdown_extension_is_supported(tmp_path: Path) -> None:
    markdown_path = tmp_path / "sample.markdown"
    markdown_path.write_text("# 扩展名测试\n\n内容。", encoding="utf-8")

    result = LOADER.load(markdown_path, "markdown-extension")

    assert result.status == "parsed"
    assert result.blocks[0].heading_path == "扩展名测试"


def test_invalid_utf8_has_explicit_encoding_status(tmp_path: Path) -> None:
    invalid_path = tmp_path / "encoding-error.md"
    invalid_path.write_bytes((FIXTURES / "encoding_error.md").read_bytes() + b"\xff")

    result = LOADER.load(invalid_path, "invalid")

    assert result.status == "encoding_error"
    assert result.blocks == []
    assert result.error and "invalid UTF-8" in result.error


def test_nested_headings_keep_the_current_heading_path() -> None:
    result = LOADER.load(FIXTURES / "nested_headings.md", "headings")

    assert result.status == "parsed"
    assert [block.heading_path for block in result.blocks] == [
        "一级标题",
        "一级标题 > 二级标题",
        "一级标题 > 二级标题 > 三级标题",
        "一级标题 > 另一个二级标题",
    ]


def test_table_text_is_preserved() -> None:
    result = LOADER.load(FIXTURES / "table.md", "table")

    assert result.status == "parsed"
    assert "| 字段 | 内容 |" in result.blocks[0].text
    assert result.blocks[0].location == {"line_start": 1, "line_end": 6}


def test_code_block_text_is_preserved() -> None:
    result = LOADER.load(FIXTURES / "code_block.md", "code")

    assert result.status == "parsed"
    assert 'return "hello"' in result.blocks[0].text
    assert "```python" in result.blocks[0].text


def test_empty_markdown_has_explicit_empty_status(tmp_path: Path) -> None:
    empty_path = tmp_path / "empty.md"
    empty_path.write_bytes(b"\xef\xbb\xbf\n\n")

    result = LOADER.load(empty_path, "empty")

    assert result.status == "empty"
    assert result.blocks == []
