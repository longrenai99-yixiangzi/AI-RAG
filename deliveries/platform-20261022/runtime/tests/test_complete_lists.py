import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.retrieval.complete_lists import build_catalog,list_bundle,list_request,render_list,enforce_complete_list
from app.retrieval.unified_candidate import UnifiedCandidate,file_sha
from app.trial.assisted_chat import assemble,run_flow,AssistedQuery
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import UnavailableLLMProvider
from app.trial.platform_app import create_app
from test_focused_candidate import Reranker
from test_daily_answers import daily,approve
from test_platform_existing_content import ask

TEXT='本手册规定3项验收任务，分为二个类别。第一类为准备工作，包括范围确认、资料复核；第二类为执行工作，包括成果移交。'
QUESTION='项目3项验收任务有哪些？'

def records(tmp_path,text=TEXT):
    path=tmp_path/'工作手册.md';split=text.index('第二')+2
    parts=[text[:split],text[split:]]
    path.write_text('\n'.join(parts),encoding='utf-8');version=file_sha(path)
    return [{'document_id':'doc','source_id':'SRC_local_manual','source_path':str(path),'source_version':version,'file_name':path.name,
             'evidence_id':'row'+str(i),'text':part,'heading_path':'Page 1','location':{'section':'Page 1'},'role':'DIRECT'} for i,part in enumerate(parts)]

def result(rows,question=QUESTION):
    bundle=list_bundle(question,build_catalog(rows),{r['evidence_id'] for r in rows})
    _,cards=assemble(bundle,question,include_background=True)
    return bundle,cards

def test_cross_chunk_list_is_extracted_from_source_not_question_numbers(tmp_path):
    rows=records(tmp_path);bundle,cards=result(rows);audit=bundle['complete_list_audit']
    assert audit['status']=='COMPLETE' and audit['declared_count']==3 and len(audit['groups'])==2
    assert audit['child_evidence_ids']==['row0','row1']
    rendered=render_list(audit,cards,QUESTION)
    assert rendered['generation_mode']=='VERIFIED_COMPLETE_LIST_NO_MODEL'
    assert all(n in rendered['answer'] for n in ['范围确认','资料复核','成果移交'])
    assert '[S1]' in rendered['answer'] and rendered['citations'][0]['source_version']==rows[0]['source_version']

@pytest.mark.parametrize('question,count,kind',[
    ('项目十三个管理动作有哪些？',13,'ITEMS'),('项目13项管理动作有哪些',13,'ITEMS'),
    ('二类验收任务有哪些？',2,'GROUPS'),('项目零项验收任务有哪些？',0,'ITEMS'),
])
def test_request_count_without_business_answer_registry(question,count,kind):
    r=list_request(question);assert r['expected_count']==count and r['count_kind']==kind

@pytest.mark.parametrize('question,status',[
    ('项目4项验收任务有哪些？','REQUEST_COUNT_DIFFERS_FROM_SOURCE'),
    ('项目3类验收任务有哪些？','REQUEST_COUNT_DIFFERS_FROM_SOURCE'),
    ('项目3项验收任务有哪些，各项流程是什么？','ADDITIONAL_DETAILS_NOT_VERIFIED'),
    ('项目3项验收任务有哪些，谁牵头？','ADDITIONAL_DETAILS_NOT_VERIFIED'),
    ('2025年项目3项验收任务有哪些？','ADDITIONAL_DETAILS_NOT_VERIFIED'),
    ('全部模板章节和内容有哪些？','NO_VERIFIED_COMPLETE_LIST'),
])
def test_wrong_count_details_period_and_topics_do_not_prove_completeness(tmp_path,question,status):
    bundle,cards=result(records(tmp_path),question)
    assert bundle['complete_list_audit']['status']==status and not cards
    checked=enforce_complete_list(question,{'citations':cards,'complete_list_audit':bundle['complete_list_audit']})
    assert checked['answer_status']=='LIST_COVERAGE_REQUIRED' and checked['generation_mode']=='NO_GENERATION'

@pytest.mark.parametrize('change',['truncated','duplicate','declared_count','group_count','eligible_mask','version'])
def test_missing_duplicate_or_changed_source_never_proves_full_list(tmp_path,change):
    text=TEXT
    if change=='truncated':text=text[:-1]
    if change=='duplicate':text=text.replace('成果移交','范围确认')
    if change=='declared_count':text=text.replace('3项','4项')
    if change=='group_count':text=text.replace('二个类别','三个类别')
    rows=records(tmp_path,text);catalog=build_catalog(rows);eligible={r['evidence_id'] for r in rows}
    if change=='eligible_mask':eligible.remove('row1')
    if change=='version':Path(rows[0]['source_path']).write_text('changed',encoding='utf-8')
    bundle=list_bundle(QUESTION,catalog,eligible)
    assert bundle['complete_list_audit']['status']!='COMPLETE' and not bundle['candidate_evidence']

def test_render_rechecks_question_quote_and_primary_reference(tmp_path):
    bundle,cards=result(records(tmp_path));audit=bundle['complete_list_audit']
    assert render_list(audit,[],QUESTION) is None and render_list(audit,cards,'另一问题') is None
    changed=copy.deepcopy(cards);changed[0]['excerpt']='只有某个子节。'
    assert render_list(audit,changed,QUESTION) is None
    raw={'answer_status':'VERIFIED_LIST','complete_list_audit':audit,'citations':[],'answer':'旧答复'}
    assert enforce_complete_list(QUESTION,raw)['answer_status']=='LIST_COVERAGE_REQUIRED'

def test_old_complete_flag_cannot_hide_new_question_details(tmp_path):
    import hashlib
    bundle,cards=result(records(tmp_path));audit=bundle['complete_list_audit']
    q=QUESTION+'谁牵头？';old={**audit,'question_sha256':hashlib.sha256(q.encode()).hexdigest()}
    assert render_list(old,cards,q) is None
    checked=enforce_complete_list(q,{'complete_list_audit':old,'citations':cards})
    assert checked['answer_status']=='LIST_COVERAGE_REQUIRED' and checked['complete_list_audit']['status']=='ADDITIONAL_DETAILS_NOT_VERIFIED'

def test_complete_list_keeps_scope_and_bypasses_dense_and_model(tmp_path):
    rows=records(tmp_path);pack=tmp_path/'pack';pack.mkdir()
    doc={k:rows[0][k] for k in ['document_id','source_id','source_path','source_version','file_name']};doc['file_type']='.md'
    for name,data in [('documents',[doc]),('evidence',rows)]:
        (pack/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data),encoding='utf-8')
    vectors=np.zeros((2,1024),dtype=np.float32);vectors[:,0]=1;np.save(pack/'dense_embeddings.npy',vectors)
    (pack/'bm25.json').write_text(json.dumps({'chunk_ids':['row0','row1'],'corpus':[['验收任务'],['成果移交']]}),encoding='utf-8')
    (pack/'sections.json').write_text('[]');contract=tmp_path/'contract.json';contract.write_text('{}')
    manifest={'artifact_sha256':{p.name:file_sha(p) for p in pack.iterdir()},'contract_path':str(contract),'contract_sha256':file_sha(contract),'candidate_hash':'test-list'}
    (pack/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    def forbidden(_):raise AssertionError('complete enumeration needs no query/model inference')
    candidate=UnifiedCandidate(pack,SimpleNamespace(embed_query=forbidden),Reranker())
    assert candidate.retrieve(QUESTION)['complete_list_audit']['status']=='COMPLETE'
    events=list(run_flow(AssistedQuery(question=QUESTION),candidate.retrieve,ShadowAnswerGenerator(UnavailableLLMProvider('offline')),lambda *a:None))
    assert events[-2]['result']['answer_status']=='VERIFIED_LIST'
    assert candidate.retrieve('《未指定文件.md》中'+QUESTION)['bundle_status']=='SOURCE_SCOPE_MISSING'

def test_unapproved_manual_list_stays_local_without_narrowing_retrieval(daily,tmp_path,monkeypatch):
    service,_,_,existing,policy,_,calls,_,_,_=daily
    bundle,cards=result(records(tmp_path));native=render_list(bundle['complete_list_audit'],cards,QUESTION)
    def retrieve(question,request_id,*,source_versions=None):
        existing.last_source_versions=source_versions
        return copy.deepcopy(native)
    monkeypatch.setattr(existing,'retrieve',retrieve)
    from app.trial.daily_answers import DailyAnswers
    monkeypatch.setattr(DailyAnswers,'_price_page',staticmethod(lambda:b'approved-price-page'))
    app=create_app(tmp_path/'api.json',existing=existing,generation_execution_enabled=False,daily_policy=policy)
    with TestClient(app) as client:
        d=app.state.daily_answers;d.clock=service.clock;d.generation.clock=service.clock;d.approve(d.policy_hash,'synthetic-human')
        r=ask(client,QUESTION)['result']
        assert existing.last_source_versions is None and r['answer_status']=='VERIFIED_LIST'
        assert r['daily_model']['route']=='LOCAL_DIRECT' and not calls and d.status()['used_requests']==0

def test_incomplete_list_stops_daily_and_old_preview_before_spending(daily):
    service,flow,store,_,_,_,calls,_,prices,run=daily;approve(daily)
    key=run();preview=flow.prepare(key,'CONCISE_V1')
    def change(state):
        state['query_runs'][key]['question']=QUESTION
        state['generations'][preview['preview_id']]['question']=QUESTION
    store._mutate(change);before=len(prices)
    assert service.apply(key)['result']['daily_model']['route']=='LIST_COVERAGE_REQUIRED'
    with pytest.raises(ValueError,match='完整清单'):flow.run(preview['preview_id'],preview['packet_sha256'],'test')
    assert not calls and len(prices)==before and service.status()['used_requests']==0
