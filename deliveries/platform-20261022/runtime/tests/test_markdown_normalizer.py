from app.ingestion.normalization.markdown_normalizer import (
    is_markdown_heading,
    normalize_markdown_block,
    normalize_markdown_text,
    is_source_reference_note,
)


def test_normalizer_removes_bom_normalizes_newlines_and_trailing_spaces() -> None:
    text = "\ufeff# 标题  \r\n\r\n正文\t\r"

    assert normalize_markdown_text(text) == "# 标题\n\n正文"


def test_block_normalization_preserves_internal_blank_lines() -> None:
    assert normalize_markdown_block("# 标题\n\n正文\n") == "# 标题\n\n正文"


def test_heading_detection_requires_heading_spacing() -> None:
    assert is_markdown_heading("## 二级标题") is True
    assert is_markdown_heading("##无空格标题") is False


def test_reference_registration_handles_nested_filename_parentheses():
    note='# 手册\n\n**来源**：[带分工](file:///D:/文件(1).docx)\n\n## 关联内容\n- [[知识/入口|入口]]\n'
    assert is_source_reference_note(note)
    assert is_source_reference_note('\ufeff---\ntype: original\n---\n'+note)
    assert not is_source_reference_note(note+'报审计划应包含封样日期。')
    assert not is_source_reference_note(note+'\n## 报审计划应包含封样日期\n')
    assert not is_source_reference_note('# 管控要求\n报审计划应包含封样日期。')
    assert not is_source_reference_note(note.replace('**来源**：','原文说：'))
