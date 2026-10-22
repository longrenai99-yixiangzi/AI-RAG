import hashlib
from app.retrieval.project_source_scope import route_project_question
from app.retrieval.named_source_scope import ranking_question


def document(root,project):
    p=root/f'EPC设计管理经验总结({project}项目).docx';p.write_bytes(b'source')
    return {'file_name':p.name,'source_path':str(p),'source_version':hashlib.sha256(p.read_bytes()).hexdigest()}


def test_project_identifier_is_a_versioned_scope_selector_not_ranking_text(tmp_path):
    d=document(tmp_path,'甲方医院');docs={'d':d};q='甲方医院项目由谁牵头设计管理，配置多少人？'
    r=route_project_question(q,docs)
    assert r['status']=='PROJECT_FILENAME_VERSION_MATCHED' and r['original_question']==q
    assert ranking_question(r['question'],docs)=='由谁牵头设计管理，配置多少人？'


def test_no_fuzzy_alias_or_overriding_an_explicit_file(tmp_path):
    d=document(tmp_path,'甲方医院');docs={'d':d}
    assert route_project_question('医院项目谁负责？',docs)['status']=='NO_VERIFIED_FILENAME_SELECTOR'
    q='《另一文件.docx》中甲方医院项目谁负责？'
    assert route_project_question(q,docs)['question']==q


def test_multiple_projects_and_changed_source_fail_closed(tmp_path):
    a=document(tmp_path,'甲方医院');b=document(tmp_path,'乙方学校');docs={'a':a,'b':b}
    assert route_project_question('比较甲方医院与乙方学校的职责',docs)['status']=='AMBIGUOUS_PROJECT_SELECTOR'
    from pathlib import Path
    Path(a['source_path']).write_bytes(b'changed')
    assert route_project_question('甲方医院项目谁负责？',docs)['status']=='SOURCE_SCOPE_MISSING'
