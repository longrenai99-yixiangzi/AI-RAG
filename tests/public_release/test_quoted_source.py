from app.quoted_source_v1 import compact_excerpt, quoted_statement, quoted_source_records
from app.retrieval.query_planner_v1 import plan_query
from app.ingestion.atomic_search import answer_support_gap
from app.trial.live_shadow_v25 import _candidate_row
from scripts.run_verified_answer_engine_v2 import _runtime_bundle
from app.verified_answer_engine_v2 import render


def question(text):return text+'——这个数据出自哪份资料、具体是多少？'
def record(text, eid='E1', version='sha1', path='synthetic/report.pdf'):
    return {'evidence_id':eid,'document_id':eid,'source_path':path,'file_name':path.split('/')[-1],
            'source_version':version,'text':text,'raw_text':text,'location':{'page':3}}


def test_quote_years_projects_and_numbers_are_lookup_text_not_scope_or_statistics():
    p=plan_query(question('甲项目2021年其中7项引用示例协议'))
    assert p.query_type=='QUOTED_SOURCE_LOOKUP'
    assert not p.year and not p.project and not p.aggregation_plan
    assert p.scope_constraints=={'quoted_statement':['甲项目2021年其中7项引用示例协议']}
    assert len(p.subquestions)==1
    assert not quoted_statement('甲项目2021年引用了多少项协议？')
    assert not quoted_statement(question('甲项目共有7项协议')+'现在还有效吗？')


def test_full_excerpt_matches_formatting_but_same_number_is_not_evidence():
    a=record('优化建议：与主体混凝土强度一致 | 已落实 | 避免施工措施 70 万元')
    q=question('与主体混凝土强度一致 | 已落实 | 避免施工措施70万元')
    assert not answer_support_gap(q,a['text'],plan_query(q).to_dict())
    assert answer_support_gap(q,'70万元',plan_query(q).to_dict())
    assert compact_excerpt('**利润 12.5％**')=='利润12.5%'
    assert compact_excerpt('利润12.5%')!=compact_excerpt('利润125%')
    assert quoted_source_records({'E1':a},quoted_statement(q),set())==[]
    assert len(quoted_source_records({'E1':a},quoted_statement(q),None))==1


def test_query_pages_links_missing_versions_excluded_and_versions_preserved():
    phrase='原文载明示例成本节约70万元'
    a=record(phrase);b=record(phrase,'E2','sha2')
    fake=record(phrase,'E3','sha3','synthetic/wiki/queries/old.md')
    missing=record(phrase,'E4','')
    selected=quoted_source_records({'E1':a,'E2':b,'E3':fake,'E4':missing},phrase,None)
    assert {r['source_version'] for r in selected}=={'sha1','sha2'}
    assert not quoted_source_records({'E1':record('[原件](file:///synthetic/原文载明示例成本节约70万元.pdf)')},phrase,None)


def test_live_bundle_quotes_source_values_and_never_certifies_present_truth():
    phrase='合同暂定费用为620万元';q=question(phrase);a=record('历史合同记载：'+phrase+'，尚需按实际结算复核。')
    docs={'E1':{'file_name':'report.pdf'}}
    candidates=[_candidate_row(r,i,'QUOTED_SOURCE_LOOKUP') for i,r in enumerate(quoted_source_records({'E1':a},phrase,None),1)]
    bundle=_runtime_bundle(q,plan_query(q).to_dict(),{'atomic_candidates':candidates},docs,{'E1':a},[])
    result=render(bundle)
    assert result['answer_status']=='PARTIAL_ANSWER' and '620万元' in result['answer_text']
    assert '同版原文' in result['answer_text'] and '不自动成为' in result['answer_text']
    assert result['citations'][0]['source_version']=='sha1'
    docs['E1']['source_content_role']='REFERENCE_ONLY_ORIGINAL'
    bundle=_runtime_bundle(q,plan_query(q).to_dict(),{'atomic_candidates':candidates},docs,{'E1':a},[])
    assert render(bundle)['answer_status']=='INSUFFICIENT_EVIDENCE'


def test_absent_excerpt_refuses_and_long_context_keeps_the_entire_quote():
    phrase='示例设计优化成本节约620万元'
    assert quoted_source_records({'a':record('另外一个项目仅节约620万元')},phrase,None)==[]
    raw='背景说明。'*700+phrase+'仍为暂定，未确认结算。'+'其他事项。'*700
    selected=quoted_source_records({'a':record(raw)},phrase,None)
    assert len(selected)==1 and phrase in selected[0]['text_override']
    assert len(selected[0]['text_override'])<2400
    q=question(phrase);result=render(_runtime_bundle(q,plan_query(q).to_dict(),{'atomic_candidates':[]},{},{},[]))
    assert result['answer_status']=='INSUFFICIENT_EVIDENCE' and not result['citations']


def test_navigation_quote_can_identify_its_own_origin_without_becoming_business_evidence():
    phrase='创建新项目导航页面5个';q=question(phrase);r=record(phrase,path='synthetic/log.md')
    selected=quoted_source_records({'E1':r},phrase,None)
    candidates=[_candidate_row(v,i,'QUOTED_SOURCE_LOOKUP') for i,v in enumerate(selected,1)]
    answer=render(_runtime_bundle(q,plan_query(q).to_dict(),{'atomic_candidates':candidates},{'E1':{}},{'E1':r},[]))
    assert answer['answer_status']=='PARTIAL_ANSWER' and '不能当业务原件' in answer['answer_text']


def test_precise_original_row_beats_a_long_chunk_with_neighbouring_locations():
    phrase='该条合同约定追加费用700万元';short=record(phrase,'ROW');long=record('下一章节内容。'*80+phrase+'其它事项。'*80,'CHUNK')
    short['location']={'page':7,'row_start':5};long['location']={'page':8}
    selected=quoted_source_records({'CHUNK':long,'ROW':short},phrase,None)
    assert len(selected)==1 and selected[0]['evidence_id']=='ROW'
    assert selected[0]['location']=={'page':7,'row_start':5}


def test_parsed_notes_require_an_active_indexed_path_version_and_document_identity():
    from app.quoted_source_v1 import source_reading_records
    anchor={**record('索引正文'),'source_id':'S1'}
    note={**record('讲者备注：历史项目占比约21%','NOTE'),'document_id':'E1','sha256':'sha1'}
    note.pop('source_version')
    bad={**note,'sha256':'retired'};wrong_path={**note,'source_path':'synthetic/unapproved.pdf'};wrong_doc={**note,'document_id':'OTHER'}
    selected=source_reading_records({'NOTE':note,'BAD':bad,'PATH':wrong_path,'DOC':wrong_doc},{'E1':anchor})
    assert set(selected)=={'NOTE'} and selected['NOTE']['source_id']=='S1'
    assert selected['NOTE']['source_version']=='sha1'


def test_citation_reopens_a_source_reading_record_without_polluting_regular_retrieval():
    from app.trial.live_shadow_v25 import V25LiveShadow
    engine=object.__new__(V25LiveShadow);engine.atomic={};engine.source_reading_atomic={'NOTE':{**record('讲者备注'),'source_id':'S1'}}
    assert engine.evidence_record('NOTE','S1','sha1')['text']=='讲者备注'
    assert engine.evidence_record('NOTE','S1','wrong') is None
    assert engine.evidence_record('NOTE','other','sha1') is None
    assert not engine.atomic


def test_slide_number_keeps_original_position_and_supplies_the_shared_page_display():
    from app.quoted_source_v1 import source_reading_records
    anchor=record('索引正文');note={**anchor,'location':{'slide':8,'text_index':2}}
    actual=source_reading_records({'NOTE':note},{'INDEX':anchor})['NOTE']
    assert actual['location']=={'slide':8,'page':8,'text_index':2}
