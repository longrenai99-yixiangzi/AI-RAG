import hashlib,json,uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.trial import assisted_chat as flow
from app.trial.knowledge_store import TrialKnowledgeStore
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import GenerationResult,UnavailableLLMProvider


def fixture(tmp_path):
    text='原文'+('长段落。'*350)+'最后的要求：设计任务书应明确成果交付要求。'
    path=tmp_path/'资料.md';path.write_text(text,encoding='utf-8')
    record={'evidence_id':'e1','document_id':'d1','source_id':'original','source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),
            'text':text,'heading_path':'任务书','location':{'paragraph':1},'role':'DIRECT','scope':{'project':'MATCH'}}
    return {'bundle_status':'VERIFIED','candidate_evidence':[record]},text,path


class Provider:
    available=True;name='synthetic-offline-test';last_error=None;last_diagnostics={}
    def __init__(self,invalid=False):self.calls=0;self.invalid=invalid;self.prompts=[]
    def generate(self,system,user,**kwargs):
        self.calls+=1;self.prompts.append(user)
        if '必须严格符合以下 Minimal Answer Schema，不得改名、加字段或返回 Markdown 代码块：\n' in user:
            schema=json.loads(user.split('必须严格符合以下 Minimal Answer Schema，不得改名、加字段或返回 Markdown 代码块：\n')[1].split('\nclaims 只保存')[0])
            self.fields=schema['properties']['section_map']['required']
        fields=self.fields
        value={'claims':[{'claim_id':'C1','claim_text':'设计任务书应明确成果交付要求。','evidence_ids':['NOT_PROVIDED' if self.invalid else 'S1']}],
               'section_map':{key:['C1'] if i==0 else [] for i,key in enumerate(fields)},'evidence_insufficient':[]}
        return GenerationResult(json.dumps(value,ensure_ascii=False),'synthetic',1)


def test_reuses_generator_full_evidence_and_persists_before_retrieval(tmp_path):
    bundle,text,_=fixture(tmp_path);provider=Provider();store=TrialKnowledgeStore(tmp_path/'state.json');data=flow.AssistedQuery(question='设计任务书如何明确成果交付？',conversation_id='c')
    def retrieve(q):
        assert store.query_run('QR_'+data.request_id)['status']=='RUNNING';return bundle
    events=list(flow.run_flow(data,retrieve,ShadowAnswerGenerator(provider),store.record_query))
    assert [e['type'] for e in events]==['status','sources','status','status','result','done']
    result=events[-2]['result'];assert result['answer_status']=='MODEL_DRAFT' and result['citations'][0]['evidence_id']=='e1'
    assert 'evidence_insufficient' not in result['answer'] and '## process' not in result['answer'] and '部分回答项' in result['answer']
    assert text in provider.prompts[0] and provider.calls==1
    assert store.query_run(result['query_run_id'])['result']==result


def test_sources_and_disabled_model_never_call_provider(tmp_path):
    bundle,_,_=fixture(tmp_path);provider=Provider();store=TrialKnowledgeStore(tmp_path/'state.json')
    sources=list(flow.run_flow(flow.AssistedQuery(question='查任务书',mode='sources'),lambda _:bundle,ShadowAnswerGenerator(provider),store.record_query))
    assert sources[-2]['result']['answer_status']=='SOURCES_ONLY' and provider.calls==0
    disabled=list(flow.run_flow(flow.AssistedQuery(question='查任务书'),lambda _:bundle,ShadowAnswerGenerator(UnavailableLLMProvider('disabled')),store.record_query))
    assert disabled[-2]['result']['answer_status']=='MODEL_UNAVAILABLE'


def test_stale_source_and_unbound_model_citation_cannot_be_validated_answers(tmp_path):
    bundle,_,path=fixture(tmp_path);store=TrialKnowledgeStore(tmp_path/'state.json');provider=Provider(invalid=True)
    events=list(flow.run_flow(flow.AssistedQuery(question='如何交付？'),lambda _:bundle,ShadowAnswerGenerator(provider),store.record_query))
    assert events[-2]['result']['answer_status']=='MODEL_OUTPUT_REJECTED'
    path.write_text('new version',encoding='utf-8');provider=Provider()
    events=list(flow.run_flow(flow.AssistedQuery(question='如何交付？'),lambda _:bundle,ShadowAnswerGenerator(provider),store.record_query))
    assert events[-2]['result']['answer_status']=='EVIDENCE_INSUFFICIENT' and provider.calls==0


def test_api_reuses_record_for_duplicate_request_and_exposes_no_credentials(tmp_path):
    bundle,_,_=fixture(tmp_path);app=FastAPI();app.include_router(flow.router);store=TrialKnowledgeStore(tmp_path/'state.json');provider=Provider()
    app.state.assisted_store=store;app.state.assisted_retrieve=lambda _:bundle;app.state.assisted_generator=ShadowAnswerGenerator(provider)
    body={'question':'如何编制任务书？','request_id':uuid.uuid4().hex,'conversation_id':'c'}
    with TestClient(app,base_url='http://127.0.0.1:8891') as client:
        info=client.get('/api/v2/assisted/capabilities');assert 'api_key' not in info.text and info.json()['generation_enabled']
        assert client.post('/api/v2/assisted/query',json=body).status_code==403
        headers={'Origin':'http://127.0.0.1:8891'}
        first=client.post('/api/v2/assisted/query',headers=headers,json=body);assert first.status_code==200 and 'MODEL_DRAFT' in first.text
        assert client.post('/api/v2/assisted/query',headers=headers,json=body).status_code==200 and provider.calls==1
        assert client.post('/api/v2/assisted/query',headers=headers,json={**body,'question':'different'}).status_code==409
        assert client.get('/api/v2/assisted/runs/QR_'+body['request_id']+'?conversation_id=c').json()['result']['answer_status']=='MODEL_DRAFT'
        assert client.get('/api/v2/assisted/runs/QR_'+body['request_id']+'?conversation_id=other').status_code==404


def test_pipeline_failure_is_preserved_and_not_reported_as_missing_material(tmp_path):
    store=TrialKnowledgeStore(tmp_path/'state.json')
    def fail(_):raise RuntimeError('private backend detail')
    events=list(flow.run_flow(flow.AssistedQuery(question='如何编制？'),fail,ShadowAnswerGenerator(Provider()),store.record_query))
    assert events[-2]['result']['answer_status']=='PIPELINE_ERROR' and 'private backend detail' not in str(events)


def test_disconnect_before_retrieval_preserves_question_without_calling_model(tmp_path):
    bundle,_,_=fixture(tmp_path);provider=Provider();store=TrialKnowledgeStore(tmp_path/'state.json');data=flow.AssistedQuery(question='如何编制？')
    events=flow.run_flow(data,lambda _:bundle,ShadowAnswerGenerator(provider),store.record_query)
    assert next(events)['type']=='status';events.close()
    assert provider.calls==0 and store.query_run('QR_'+data.request_id)['status']=='INTERRUPTED'


def test_existing_v2_exposes_retrieval_before_rule_rendering():
    import inspect
    from app.trial.v2 import V2TrialEngine
    source=inspect.getsource(V2TrialEngine.answer)
    assert source.index('if retrieve_only:')<source.index('answer = render(bundle)')
