import pytest

from app.document_overview_v1 import file_key, named_document_ids, overview_records, overview_title
from app.retrieval.query_planner_v1 import plan_query
from app.verified_answer_engine_v2 import render
from scripts.run_verified_answer_engine_v2 import _runtime_bundle


@pytest.mark.parametrize('title',['203007演示专业培训','02演示学院项目','公司季度EPC项目检查通报','报名表（演示公司66人）'])
def test_title_is_a_file_constraint_not_a_year_project_or_count(title):
    q=f'《{title}》这份资料主要讲了什么？请给出其中的关键内容。'
    p=plan_query(q)
    assert p.query_type=='DOCUMENT_OVERVIEW' and not p.aggregation_plan
    assert not p.year and not p.project and not p.specialty
    assert p.scope_constraints['source_reference']==[title] and p.subquestions==[q]


def test_among_is_not_by_itself_a_filter_and_real_statistics_still_are():
    assert 'FILTER' not in plan_query('请解释其中的风险。').aggregation_plan
    assert 'FILTER' in plan_query('台账里其中利润大于0的记录有多少条？').aggregation_plan
    assert not overview_title('《演示报告》主要讲了什么？其中投资额是多少？')


def record(eid='E1',did='D1',version='v1',name='演示通知.pdf',text=None,page=1):
    raw=text or ('培训内容为演示输入核对、成果复核与问题登记。'*6)
    return {'evidence_id':eid,'document_id':did,'source_version':version,'file_name':name,
            'source_path':'synthetic/'+name,'text':raw,'raw_text':raw,'location':{'page':page},'heading_path':f'Page {page}'}


def test_exact_names_preserve_extensions_and_do_not_match_other_files():
    docs={'a':{'file_name':'09.演示资料.pdf'},'b':{'file_name':'演示资料.pptx'},'c':{'file_name':'关于演示资料的通知.pdf'}}
    assert named_document_ids(docs,'演示资料')=={'a','b'}
    assert named_document_ids(docs,'演示资料.pdf')=={'a'}
    assert file_key('203007演示')=='203007演示'
    assert file_key('2.5演示')!='5演示'
    docs={'a':{'file_name':'演示.pdf','source_path':'synthetic/A/演示.pdf'},'b':{'file_name':'演示.pdf','source_path':'synthetic/B/演示.pdf'}}
    assert named_document_ids(docs,'synthetic\\B\\演示.pdf')=={'b'}
    assert not named_document_ids(docs,'synthetic/C/演示.pdf')


def test_overview_respects_allowed_sources_and_excludes_link_registrations():
    atomic={'a':record('a'),'b':record('b','D2'), 'c':record('c',text='[原件](file:///synthetic/source.pdf)')}
    selected=overview_records(atomic,{'D1'},{'a','c'})
    assert [r['evidence_id'] for r in selected]==['a']
    assert overview_records(atomic,{'D1'},set())==[]
    atomic['a']['source_path']='synthetic/wiki/queries/演示通知.md'
    assert overview_records(atomic,{'D1'},{'a','c'})==[]


def test_distinct_versions_require_selection_but_same_sha_copies_do_not():
    atomic={'a':record('a'),'b':record('b','D2','v2')}
    assert all(r['overview_context']['ambiguous'] for r in overview_records(atomic,{'D1','D2'},None))
    atomic['b']['source_version']='v1'
    assert len(overview_records(atomic,{'D1','D2'},None))==1


def test_form_overview_quotes_fields_without_personal_row_values():
    raw='表名：演示报名\n表头：姓名 | 手机 | 职务\n行：示例人 | DEMO_PHONE | 示例岗位'
    selected=overview_records({'a':record(name='演示报名表.docx',text=raw)}, {'D1'},None)
    assert selected[0]['text_override']=='表头：姓名 | 手机 | 职务'
    assert 'DEMO_PHONE' not in selected[0]['raw_text_override']


def make_answer(atomic, docs):
    from app.trial.live_shadow_v25 import _candidate_row
    q='《演示通知》这份资料主要讲了什么？请给出其中的关键内容。'
    chosen=overview_records(atomic,set(docs),None)
    candidates=[_candidate_row(r,i,'DOCUMENT_OVERVIEW') for i,r in enumerate(chosen,1)]
    data=_runtime_bundle(q,plan_query(q).to_dict(),{'atomic_candidates':candidates},docs,atomic,[])
    return render(data)


def test_real_bundle_and_renderer_keep_excerpts_cited_and_partial():
    answer=make_answer({'E1':record()}, {'D1':{'file_name':'演示通知.pdf'}})
    assert answer['answer_status']=='PARTIAL_ANSWER'
    assert '输入核对' in answer['answer_text'] and '原文选读' in answer['answer_text']
    assert answer['citations'][0]['source_version']=='v1'


def test_ambiguous_and_absent_documents_never_borrow_another_source():
    answer=make_answer({'a':record('a'),'b':record('b','D2','v2')},{'D1':{},'D2':{}})
    assert answer['answer_status']=='SOURCE_SCOPE_MISSING'
    answer=make_answer({}, {})
    assert answer['answer_status']=='INSUFFICIENT_EVIDENCE' and '不代表原件不存在' in answer['answer_text']
    answer=make_answer({'E1':record()}, {'D1':{'document_type':'REGISTER_PAGE'}})
    assert answer['answer_status']=='INSUFFICIENT_EVIDENCE'


def test_reference_only_originals_cannot_answer_general_or_current_project_facts():
    from scripts.build_verified_evidence_bundle_v1 import _deliverable_source_in_scope
    c={'source_content_role':'REFERENCE_ONLY_ORIGINAL'}
    assert _deliverable_source_in_scope(c,{'query_type':'DOCUMENT_OVERVIEW'})
    assert not _deliverable_source_in_scope(c,{'query_type':'SINGLE_FACT','project':['演示项目']})
    assert not _deliverable_source_in_scope(c,{'query_type':'POLICY_QUERY'})
    from app.trial.live_shadow_v25 import _candidate_row
    q='演示项目目前是否已经完成全部整改？'
    evidence=record(text='演示项目目前已经完成全部整改。'*6)
    docs={'D1':{'source_content_role':'REFERENCE_ONLY_ORIGINAL','scope':{'project':['演示项目']}}}
    data=_runtime_bundle(q,plan_query(q).to_dict(),{'atomic_candidates':[_candidate_row(evidence,1,'PROJECT_SCOPE_SOURCE_RESCUE')]},docs,{'E1':evidence},[])
    assert not data['verified_evidence']
    assert render(data)['answer_status']=='INSUFFICIENT_EVIDENCE'
