from app.ingestion.normalization.markdown_normalizer import (
    is_markdown_heading,
    normalize_markdown_block,
    normalize_markdown_text,
)


def test_normalizer_removes_bom_normalizes_newlines_and_trailing_spaces() -> None:
    text = "\ufeff# 标题  \r\n\r\n正文\t\r"

    assert normalize_markdown_text(text) == "# 标题\n\n正文"


def test_block_normalization_preserves_internal_blank_lines() -> None:
    assert normalize_markdown_block("# 标题\n\n正文\n") == "# 标题\n\n正文"


def test_heading_detection_requires_heading_spacing() -> None:
    assert is_markdown_heading("## 二级标题") is True
    assert is_markdown_heading("##无空格标题") is False
