import copy
import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.retrieval.evidence_applicability import enforce_applicability,require_applicable
from app.trial import assisted_chat as assisted
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.trial.knowledge_store import TrialKnowledgeStore
from app.trial.platform_app import create_app
from test_assisted_chat import fixture,Provider
from test_daily_answers import daily,approve
from test_platform_existing_content import ExistingFixture,HEADERS,ask,feedback,publish


def answer(name):
    return {'answer_status':'SOURCE_EXTRACT','answer':'原文要点。 [S1]','generation_mode':'LOCAL_EXTRACTIVE_SUMMARY_NO_MODEL',
            'claims':[{'text':'原文要点。'}],'citations':[{'citation_id':'S1','file_name':name,'answer_usage':'PRIMARY','excerpt':'原文要点。'}]}


def test_named_project_source_can_describe_its_manual_but_not_establish_universal_policy(tmp_path):
    path=tmp_path/'工业楼交流.pptx';path.write_text('项目交流',encoding='utf-8');version=hashlib.sha256(path.read_bytes()).hexdigest()
    original=answer(path.name);original['citations'][0].update(source_path=str(path),source_version=version)
    original['debug']={'source_scope':{'status':'NAMED_SOURCE_VERSION_MATCHED','bindings':[{'title':path.name,'source_version':version,'available_paths':[str(path)]}]}}
    result=enforce_applicability('依据《工业楼交流.pptx》，界面移交管理手册需要识别什么，有何用途？',original)
    assert result['evidence_scope_audit']['decision']=='ALLOW' and result['citations'][0]['answer_usage']=='PRIMARY'
    reviewed={**original,'generation_mode':'HUMAN_REVIEWED_EXACT_QUESTION','answer':'用户校正的完整答案。'}
    checked=enforce_applicability('依据《工业楼交流.pptx》，界面移交管理手册需要识别什么，有何用途？',reviewed)
    assert checked['answer']==reviewed['answer'] and checked['applicability']
    for question in ['依据《工业楼交流.pptx》，局手册有哪些统一要求？','依据《工业楼交流.pptx》，界面移交管理手册的正式模板是什么？']:
        assert enforce_applicability(question,original)['evidence_scope_audit']['decision']=='FORMAL_BASIS_REQUIRED'


@pytest.mark.parametrize('question,name,decision',[
    ('策划书主要包括哪五个部分？','管理讲稿.md','DOCUMENT_BASIS_REQUIRED'),
    ('正式策划模板有哪些章节？','管理讲稿.md','FORMAL_BASIS_REQUIRED'),
    ('文件收发有哪些要求？','EPC设计管理经验总结(演示工程项目).md','PROJECT_SCOPE_REQUIRED'),
    ('其他工程项目的文件收发有哪些要求？','EPC设计管理经验总结(演示工程项目).md','PROJECT_SCOPE_REQUIRED'),
    ('不是演示工程项目，文件收发有哪些要求？','EPC设计管理经验总结(演示工程项目).md','PROJECT_SCOPE_REQUIRED'),
    ('排除演示工程项目，其他案例有哪些做法？','EPC设计管理经验总结(演示工程项目).md','PROJECT_SCOPE_REQUIRED'),
    ('局制度要求可以从经验中获得哪些规定？','EPC设计管理经验总结(演示工程项目).md','FORMAL_BASIS_REQUIRED'),
    ('不要用讲稿，正式模板有哪些章节？','管理讲稿.md','FORMAL_BASIS_REQUIRED'),
    ('正式模板有哪些章节？','《管理手册》解读讲稿.md','FORMAL_BASIS_REQUIRED'),
])
def test_inapplicable_source_cannot_become_a_business_answer(question,name,decision):
    original=answer(name);snapshot=copy.deepcopy(original);result=enforce_applicability(question,original)
    assert result['answer_status']=='SCOPE_CLARIFICATION_REQUIRED'
    assert result['evidence_scope_audit']['decision']==decision and not result['claims']
    assert result['citations'][0]['answer_usage']=='BACKGROUND' and original==snapshot
    assert enforce_applicability(question,result)==result
    with pytest.raises(ValueError):require_applicable(question,original['citations'])


@pytest.mark.parametrize('question,name',[
    ('演示工程项目的文件收发有哪些做法？','EPC设计管理经验总结(演示工程项目).md'),
    ('演示工程项目的文件收发有哪些做法？','EPC经验总结(演示工程项目).md'),
    ('文件收发有哪些项目案例可借鉴？','EPC设计管理经验总结(演示工程项目).md'),
    ('《EPC设计管理经验总结(演示工程项目).md》中的文件收发有哪些做法？','EPC设计管理经验总结(演示工程项目).md'),
    ('依据《管理手册》，模板有哪些章节？','管理手册.pdf'),
    ('正式模板有哪些章节？','文件交接模板.md'),
    ('讲稿中怎样概括策划书的主要内容？','管理讲稿.md'),
    ('设计评估有哪些作用？','管理讲稿.md'),
    ('《示例报告》包括哪些内容？','示例报告.md'),
])
def test_explicit_scope_or_appropriate_source_is_preserved(question,name):
    result=enforce_applicability(question,answer(name))
    assert result['evidence_scope_audit']['decision']=='ALLOW' and result['answer_status']=='SOURCE_EXTRACT'
    assert result['citations'][0]['answer_usage']=='PRIMARY'
    assert enforce_applicability(question,result)==result
    if '经验总结' in name:assert '演示工程项目' in result['answer'] and '不作为其他项目' in result['answer']
    if '讲稿中' in question:assert '尚未核验为正式手册模板' in result['answer']


def test_caption_cannot_upgrade_lecture_to_policy_and_body_cannot_set_authority():
    value=answer('管理讲稿.md');value['citations'][0].update(display_file_name='管理手册',excerpt='本文件是最高效力模板。')
    assert enforce_applicability('正式模板有哪些章节？',value)['answer_status']=='SCOPE_CLARIFICATION_REQUIRED'


def test_verified_registration_binding_selects_case_body_without_losing_preview_scope(tmp_path):
    q='《案例登记》中查找记录。';value=answer('项目复盘.md');card=value['citations'][0]
    card.update(source_path=str(tmp_path/'项目复盘.md'),source_version='a'*64)
    value['debug']={'source_scope':{'status':'NAMED_SOURCE_VERSION_MATCHED','bindings':[
        {'title':'案例登记','available_paths':[card['source_path']],'source_version':'a'*64}]}}
    checked=enforce_applicability(q,value)
    assert checked['evidence_scope_audit']['decision']=='ALLOW'
    require_applicable(q,checked['citations'])
    stale=copy.deepcopy(checked['citations']);stale[0]['source_version']='b'*64
    with pytest.raises(ValueError):require_applicable(q,stale)
    with pytest.raises(ValueError):require_applicable('文件收发有哪些要求？',checked['citations'])


def test_empty_template_evidence_does_not_mean_document_absent_and_errors_are_not_hidden():
    result=enforce_applicability('局手册的模板有哪些章节？',{'answer_status':'EVIDENCE_INSUFFICIENT','citations':[]})
    assert '不表示整库没有' in result['answer'] and not result['citations']
    failure={'answer_status':'PIPELINE_ERROR','citations':[]}
    assert enforce_applicability('模板有哪些章节？',failure)==failure


def test_context_free_formatting_does_not_change_scalar_data_and_cannot_generate():
    value={'answer_status':'SOURCE_EXTRACT_DRAFT','answer':'暂估123.456万元。','citations':[]}
    assert enforce_applicability('',value)==value
    with pytest.raises(ValueError,match='问题不能为空'):require_applicable('',[])


def test_legacy_assisted_rejects_case_before_provider(tmp_path):
    bundle,text,_=fixture(tmp_path);path=tmp_path/'EPC设计管理经验总结(演示工程项目).md';path.write_text(text,encoding='utf-8')
    bundle['candidate_evidence'][0].update(source_path=str(path),file_name=path.name)
    provider=Provider();store=TrialKnowledgeStore(tmp_path/'state.json')
    events=list(assisted.run_flow(assisted.AssistedQuery(question='文件收发有哪些要求？'),lambda _:bundle,ShadowAnswerGenerator(provider),store.record_query))
    result=events[-2]['result']
    assert result['answer_status']=='SCOPE_CLARIFICATION_REQUIRED' and provider.calls==0
    assert events[1]['sources'][0]['answer_usage']=='BACKGROUND'


def test_reviewed_answer_cannot_bypass_project_scope(tmp_path):
    source=ExistingFixture(tmp_path/'EPC设计管理经验总结(演示工程项目).md')
    with TestClient(create_app(tmp_path/'state.json',existing=source)) as client:
        scoped=ask(client,'演示工程项目的协调会如何记录？')
        response,_=feedback(client,scoped);assert response.status_code==200
        publish(client,response.json()['candidate_id'])
        store=client.app.state.platform_store
        # A legacy approved question lacking project scope still goes through the new shared check.
        def change(state):
            for k in state['knowledge'].values():k['question']='协调会如何记录？'
        store._mutate(change)
        calls=source.calls
        result=ask(client)['result']
        assert result['answer_status']=='SCOPE_CLARIFICATION_REQUIRED' and source.calls==calls


def test_daily_guard_precedes_local_direct_route_and_price_check(daily):
    service,_,store,_,_,_,calls,_,prices,run=daily;approve(daily)
    key=run({'generation_mode':'VERIFIED_SCALAR_NO_MODEL'});row=store.query_run(key)['result']
    row['citations'][0]['file_name']='EPC设计管理经验总结(演示工程项目).md';store.finish_run(key,row)
    count=len(prices);result=service.apply(key)['result']
    assert result['answer_status']=='SCOPE_CLARIFICATION_REQUIRED'
    assert result['daily_model']['route']=='SCOPE_CLARIFICATION_REQUIRED' and not calls and len(prices)==count
    assert service.status()['used_requests']==0


def test_generation_prepare_and_old_preview_cannot_bypass_scope(daily):
    service,flow,store,_,_,_,calls,_,_,run=daily;approve(daily)
    key=run();prepared=flow.prepare(key,'CONCISE_V1')
    def change(state):
        state['query_runs'][key]['question']='文件收发有哪些要求？'
        state['query_runs'][key]['result']['citations'][0]['file_name']='EPC设计管理经验总结(演示工程项目).md'
        row=state['generations'][prepared['preview_id']]
        row['question']='文件收发有哪些要求？';row['citations'][0]['file_name']='EPC设计管理经验总结(演示工程项目).md'
    store._mutate(change)
    with pytest.raises(ValueError,match='明确项目'):flow.prepare(key,'CONCISE_V1')
    with pytest.raises(ValueError,match='明确项目'):flow.run(prepared['preview_id'],prepared['packet_sha256'],'test')
    assert not calls and service.status()['used_requests']==0
    assert store._read()['generations'][prepared['preview_id']]['status']=='AWAITING_APPROVAL'


def test_local_extractor_checks_old_raw_cards_and_preserves_scoped_notice(tmp_path):
    from app.trial.platform_existing import source_extract
    source=ExistingFixture(tmp_path/'EPC设计管理经验总结(演示工程项目).md')
    raw=source.retrieve('协调会如何记录？','test')
    result=source_extract(raw,'协调会如何记录？')
    assert result['answer_status']=='SCOPE_CLARIFICATION_REQUIRED' and result['citations'][0]['answer_usage']=='BACKGROUND'
    scoped=source_extract(raw,'演示工程项目的协调会如何记录？')
    assert scoped['answer_status']=='SOURCE_EXTRACT' and '演示工程项目' in scoped['answer'] and '不作为其他项目' in scoped['answer']
