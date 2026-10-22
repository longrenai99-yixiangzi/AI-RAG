import hashlib
from pathlib import Path
from app.retrieval.named_source_scope import resolve_named_scope,named_document_ids,ranking_question


def document(tmp_path,name='质量工作指引.md',text='原文'):
    p=tmp_path/name;p.write_text(text,encoding='utf-8')
    return {'file_name':name,'source_path':str(p),'source_version':hashlib.sha256(p.read_bytes()).hexdigest()}


def test_exact_title_and_explicit_extension(tmp_path):
    d=document(tmp_path)
    assert named_document_ids({'a':d},'质量工作指引')=={'a'}
    assert not named_document_ids({'a':d},'质量工作指引.docx')
    assert resolve_named_scope('《质量工作指引》要求什么？',{'a':d})['status']=='NAMED_SOURCE_VERSION_MATCHED'


def test_missing_title_never_borrows_similar_source(tmp_path):
    d=document(tmp_path,'质量工作指引补充.md')
    r=resolve_named_scope('《质量工作指引》要求什么？',{'a':d})
    assert r['status']=='SOURCE_SCOPE_MISSING' and not r['allowed_paths']


def test_different_versions_with_same_display_name_are_blocked(tmp_path):
    a=document(tmp_path);other=tmp_path/'other';other.mkdir();b=document(other,text='另一版本')
    assert resolve_named_scope('《质量工作指引》要求什么？',{'a':a,'b':b})['status']=='CONFLICTING_EVIDENCE'


def test_identical_verified_copies_are_not_false_version_conflicts(tmp_path):
    a=document(tmp_path);other=tmp_path/'other';other.mkdir();b=document(other)
    r=resolve_named_scope('《质量工作指引》要求什么？',{'a':a,'b':b})
    assert r['status']=='NAMED_SOURCE_VERSION_MATCHED' and len(r['allowed_paths'])==2


def test_source_change_is_not_inherited_by_title(tmp_path):
    d=document(tmp_path);Path(d['source_path']).write_text('已修改',encoding='utf-8')
    assert resolve_named_scope('《质量工作指引》要求什么？',{'a':d})['status']=='SOURCE_SCOPE_MISSING'


def test_no_catalog_and_multi_title_partial_coverage_fail_closed(tmp_path):
    d=document(tmp_path)
    assert resolve_named_scope('《质量工作指引》要求什么？',None)['status']=='SOURCE_SCOPE_MISSING'
    assert not resolve_named_scope('比较《质量工作指引》和《尚未入库的标准》',{'a':d})['allowed_paths']
    assert resolve_named_scope('有哪些质量要求？',None)['allowed_paths'] is None


def test_verified_title_is_only_a_scope_selector_not_ranking_text(tmp_path):
    d=document(tmp_path)
    q='《质量工作指引.md》中，哪个岗位负责检查？'
    assert ranking_question(q,{'a':d})=='哪个岗位负责检查？'
    assert resolve_named_scope(q,{'a':d})['status']=='NAMED_SOURCE_VERSION_MATCHED'
    assert ranking_question('《未登记制度》中谁检查？',{'a':d})=='《未登记制度》中谁检查？'


def test_numbered_filenames_are_distinct_scope_selectors(tmp_path):
    a=document(tmp_path,'0.md');b=document(tmp_path,'1.md',text='另一份原文')
    assert named_document_ids({'a':a,'b':b},'1.md')=={'b'}
    assert named_document_ids({'a':a,'b':b},'0')=={'a'}


def test_nested_book_title_filename_and_incomplete_selector(tmp_path):
    d=document(tmp_path,'《项目设计管理手册》.md')
    assert resolve_named_scope('《《项目设计管理手册》.md》中有哪些要求？',{'a':d})['status']=='NAMED_SOURCE_VERSION_MATCHED'
    assert ranking_question('《《项目设计管理手册》.md》中，查阅要求',{'a':d})=='查阅要求'
    assert resolve_named_scope('《项目设计管理手册》有哪些要求？',{'a':d})['status']=='NAMED_SOURCE_VERSION_MATCHED'
    for q in ['《项目设计管理手册','项目设计管理手册》','《》']:
        assert resolve_named_scope(q,{'a':d})['status']=='SOURCE_SCOPE_MISSING'
