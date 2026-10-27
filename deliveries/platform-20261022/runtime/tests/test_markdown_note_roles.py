from pathlib import Path
import pytest
from app.ingestion.normalization.markdown_links import inline_links,primary_source_link
from app.ingestion.normalization.markdown_normalizer import is_navigation_only_note
from app.retrieval.reference_bindings import linked_path


@pytest.mark.parametrize('target',[r'file:///D:/资料/文件(1).docx',r'file:///D:/资料/文件 (终版).pdf',r'file:///D:%5C资料%5C文件(1).pptx'])
def test_balanced_local_source_link_keeps_the_complete_name(target):
    text=f'**来源**：[资料]({target})\n\n## 关联内容\n- [[wiki/导航|导航]]'
    link=primary_source_link(text)
    assert link['complete'] and link['target']==target
    assert linked_path(text).suffix.lower() in {'.docx','.pdf','.pptx'}


def test_truncated_source_link_is_not_completed_or_used_as_a_file_target():
    text='**来源**：[资料](file:///D:/资料/项目(1)\n\n## 关联内容\n- [[导航]]'
    assert not primary_source_link(text)['complete'] and linked_path(text) is None
    assert is_navigation_only_note(text)


def test_bare_source_link_and_repeated_navigation_heading_are_not_body_evidence():
    text='[项目机制](file:///D:/资料/机制.docx)\n\n## ## 关联内容\n- [[wiki/概念|相关方沟通机制]]'
    assert is_navigation_only_note(text) and linked_path(text)==Path('D:/资料/机制.docx')
    assert not is_navigation_only_note(text+'\n报审计划应包含封样日期。')


def test_short_fact_and_factual_heading_are_not_discarded_by_a_length_threshold():
    assert not is_navigation_only_note('# 要求\n报审前须确认。\n[[导航]]')
    assert not is_navigation_only_note('# 报审计划应包含封样日期\n[[导航]]')


def test_navigation_without_the_original_source_remains_navigation():
    assert is_navigation_only_note('## 关联内容\n- [[业务/项目]]\n- [[业务/职责]]')


def test_multiple_primary_links_do_not_implicitly_choose_a_source():
    text='[甲](file:///D:/甲.docx)\n[乙](file:///D:/乙.docx)'
    assert primary_source_link(text) is None and linked_path(text) is None


def test_angle_wrapped_paths_are_supported_and_network_paths_are_not_read():
    assert primary_source_link('[甲](<file:///D:/资料/文件 (1).pdf>)')['complete']
    assert linked_path('[甲](file:////server/share/甲.docx)') is None


def test_legacy_mixed_parenthesis_filename_preserves_the_exact_existing_reference():
    text='**来源**：[项目总结（能源站).docx](file:///D:/资料/项目总结（能源站).docx)\n## 关联内容\n[[导航]]'
    assert primary_source_link(text)['syntax_mode']=='LEGACY_FULL_FILENAME_LITERAL'
    assert linked_path(text)==Path('D:/资料/项目总结（能源站).docx')
    assert is_navigation_only_note(text)
    bare=text.replace('**来源**：','')
    assert is_navigation_only_note(bare)
