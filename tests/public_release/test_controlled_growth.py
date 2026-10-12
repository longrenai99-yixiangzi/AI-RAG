import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.knowledge_growth_v1 import candidate_for_trace, merge_candidate, save_candidate, trace_from_runtime
from app.verified_answer_engine_v2 import _explicit_list_item_count
from scripts.run_knowledge_growth_v1 import main


def trace(identifier='QR_DEMO_1'):
    evidence={'evidence_id':'E1','source_id':'S1','document_id':'D1','source_path':'synthetic/demo.md','source_version':'1'*64,'text':'演示成果尚待核对。'}
    return {'question_id':identifier,'question':'演示成果有多少项？','traffic_kind':'REAL','candidate_hash':'a'*64,
            'answer':{'answer_status':'INSUFFICIENT_EVIDENCE','claims':[]},
            'bundle':{'bundle_status':'INSUFFICIENT_EVIDENCE','query_plan':{'project':['演示项目'],'year':['2030']},
                      'candidate_evidence':[evidence],'verified_evidence':[],'coverage_map':[]}}


@pytest.mark.parametrize('kind',['TECHNICAL','UNCLASSIFIED',''])
def test_only_real_traffic_can_propose_growth(kind):
    value=trace();value['traffic_kind']=kind
    assert candidate_for_trace(value) is None


def test_success_is_not_automatically_approved_knowledge():
    value=trace();value['answer']['answer_status']='ANSWERED';value['bundle']['bundle_status']='VERIFIED'
    assert candidate_for_trace(value) is None


@pytest.mark.parametrize('topic',['科研成果总结','科技研发管理','结题验收'])
def test_excluded_business_topics_are_not_reintroduced_by_growth(topic):
    value=trace();value['question']=topic+'有哪些要求？'
    assert candidate_for_trace(value) is None


def test_insufficient_answer_is_a_triage_item_not_a_missing_source_fact():
    candidate=candidate_for_trace(trace())
    assert candidate['growth_type']=='EVIDENCE_REVIEW_CANDIDATE'
    assert candidate['review_status']=='PROPOSED' and candidate['automatic_knowledge_publish']==0 and not candidate['runtime_input']
    assert candidate['evidence_snapshot']['sources'][0]['source_version']=='1'*64
    assert candidate['evidence_snapshot']['query_scope']['project']==['演示项目']


@pytest.mark.parametrize(('code','kind'),[('RECALL_MISS','RETRIEVAL_GROWTH'),('PARSE_FAILED','RETRIEVAL_GROWTH'),('SOURCE_VERSION_ERROR','RETRIEVAL_GROWTH'),('ANSWER_SYNTHESIS_FAIL','QA_GROWTH'),('CITATION_VALIDATION_FAIL','QA_GROWTH')])
def test_system_failures_are_not_proposed_as_standard_answers(code,kind):
    value=trace();value['failure']={'failure_code':code}
    assert candidate_for_trace(value)['growth_type']==kind


@pytest.mark.parametrize('field',['project','year','version','candidate'])
def test_different_scope_or_source_versions_do_not_merge(field):
    first=trace();second=copy.deepcopy(first)
    if field in {'project','year'}:second['bundle']['query_plan'][field]=['different']
    elif field=='version':second['bundle']['candidate_evidence'][0]['source_version']='2'*64
    else:second['candidate_hash']='b'*64
    with pytest.raises(ValueError,match='VERSION_OR_SCOPE'):
        merge_candidate(candidate_for_trace(first),candidate_for_trace(second))


def test_repeated_processing_preserves_reviews_and_counts_distinct_runs(tmp_path):
    path=tmp_path/'growth_candidates.jsonl'
    first=candidate_for_trace(trace());first.update(review_status='APPROVED',reviewer='synthetic-reviewer')
    save_candidate(path,first);before=path.read_bytes()
    save_candidate(path,candidate_for_trace(trace()))
    assert path.read_bytes()==before
    merged=save_candidate(path,candidate_for_trace(trace('QR_DEMO_2')))
    assert merged['occurrence_count']==2 and merged['review_status']=='APPROVED'
    assert set(merged['regression_question_ids'])=={'QR_DEMO_1','QR_DEMO_2'}


def test_concurrent_query_links_are_not_lost(tmp_path):
    path=tmp_path/'growth_candidates.jsonl'
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i:save_candidate(path,candidate_for_trace(trace('QR_'+str(i)))),range(10)))
    assert json.loads(path.read_text(encoding='utf-8').splitlines()[-1])['occurrence_count']==10


def test_replay_does_not_erase_reviews_events_or_inflate_counts(tmp_path):
    source=tmp_path/'input.jsonl';source.write_text(json.dumps(trace())+'\n',encoding='utf-8')
    output=tmp_path/'output';output.mkdir();review=output/'review_records.jsonl'
    review.write_text('{"decision":"APPROVE","comment":"synthetic prior decision"}\n',encoding='utf-8')
    args=['--input',str(source),'--output',str(output)]
    assert main(args)==0
    before={p.name:p.read_bytes() for p in output.iterdir() if p.name!='generation_report.json'}
    assert main(args)==0
    assert before=={p.name:p.read_bytes() for p in output.iterdir() if p.name!='generation_report.json'}
    assert json.loads((output/'generation_report.json').read_text())['new_events']==0
    with pytest.raises(SystemExit):main(args+['--rebuild'])


def test_historical_trace_never_borrows_a_current_source_version():
    audit={'query_run_id':'QR_DEMO','question':'演示问题','traffic_kind':'REAL'}
    persisted={'query_run_id':'QR_DEMO','candidate_hash':'old','answer_status':'INSUFFICIENT_EVIDENCE','stages':{}}
    with pytest.raises(ValueError,match='CANDIDATE_VERSION'):
        trace_from_runtime(audit,persisted,{'candidate_hash':'new','sources':[]})


def test_runtime_replay_keeps_claims_separate_from_source_quotations():
    audit={'query_run_id':'QR_DEMO','question':'演示问题','traffic_kind':'REAL'}
    persisted={'query_run_id':'QR_DEMO','candidate_hash':'a','answer_status':'INSUFFICIENT_EVIDENCE','bundle_status':'INSUFFICIENT_EVIDENCE',
               'stages':{'evidence_validation':[{'chunk_id':'E1','source_id':'S1','role':'SUPPORTING'}],
                         'final_evidence':[{'claim_text':'模型说的不能变成原文'}]}}
    normalized=trace_from_runtime(audit,persisted,{'candidate_hash':'a','sources':[{'source_id':'S1','sha256':'1'*64,'source_path':'synthetic.md'}]})
    candidate=candidate_for_trace(normalized)
    assert candidate['evidence_snapshot']['sources'][0]['source_version']=='1'*64
    assert candidate['evidence_snapshot']['sources'][0]['excerpt']==''


def test_runtime_replay_retains_professional_and_period_scope():
    audit={'query_run_id':'QR_DEMO','question':'演示问题','traffic_kind':'REAL'}
    persisted={'query_run_id':'QR_DEMO','candidate_hash':'a','answer_status':'INSUFFICIENT_EVIDENCE','bundle_status':'INSUFFICIENT_EVIDENCE',
               'stages':{'query_understanding':{'project':['演示项目'],'professional':['结构']},'retrieval_plan':{'hard_filters':{'period':['H1']}}}}
    candidate=candidate_for_trace(trace_from_runtime(audit,persisted))
    assert candidate['evidence_snapshot']['query_scope']['specialty']==['结构']
    assert candidate['evidence_snapshot']['query_scope']['period']=='H1'


def test_duty_list_count_stops_before_another_topic():
    text='主要职责：\n- 接收输入\n- 核对成果\n其他主题：\n- 发布资料\n'
    assert _explicit_list_item_count(text,question='职责有哪两项？')==2


@pytest.fixture
def client(tmp_path,monkeypatch):
    from app.trial import v2
    from app.trial.knowledge_store import TrialKnowledgeStore
    from app.retrieval import retrieval_trace
    monkeypatch.setattr(v2,'CONFIG',{'V2_VERIFIED_RAG_ENABLED':True})
    monkeypatch.setattr(v2,'KNOWLEDGE_STORE',TrialKnowledgeStore(tmp_path/'state.json'))
    for name,value in {'GROWTH':tmp_path/'growth','TRIAL':tmp_path/'trial','FEEDBACK_CANDIDATES':tmp_path/'growth/feedback.jsonl','FEEDBACK_CASES':tmp_path/'growth/cases.jsonl','FEEDBACK_RUNS':tmp_path/'growth/runs.jsonl'}.items():monkeypatch.setattr(v2,name,value)
    monkeypatch.setattr(retrieval_trace,'TRACE_DIR',tmp_path/'traces');monkeypatch.setattr(retrieval_trace,'TRACE_FILE',tmp_path/'traces.jsonl')
    monkeypatch.setattr(v2,'_primary_mode',lambda:v2.V262_CANDIDATE_MODE)
    monkeypatch.setattr(v2,'_current_candidate_hash',lambda:'a'*64)
    value=trace()
    def answer(*_,**__):
        return {'query_id':'Q_DEMO','question':value['question'],'pipeline_version':'synthetic','answer_status':'INSUFFICIENT_EVIDENCE','answer':'待核对','claims':[],'citations':[],'growth_candidate_ids':[],
                'debug':{'runtime_pointer':{'candidate_hash':'a'*64},'evidence_bundle':copy.deepcopy(value['bundle']),'query_plan':value['bundle']['query_plan']},'latency':{},'provider_http_requests':0}
    monkeypatch.setattr(v2,'_answer_current_runtime',answer)
    app=FastAPI();app.include_router(v2.router)
    with TestClient(app) as session:yield session,v2


def test_frozen_primary_query_records_proposal_without_activating_knowledge(client):
    session,v2=client
    for _ in range(2):
        response=session.post('/api/v2/query',json={'question':'演示成果有多少项？','traffic_kind':'REAL'})
        assert response.status_code==200 and len(response.json()['growth_candidate_ids'])==1
    rows=session.get('/api/v2/growth-candidates').json()['candidates']
    assert len(rows)==1 and rows[0]['occurrence_count']==2
    assert v2.KNOWLEDGE_STORE.active_knowledge()==[]
    before=(v2.GROWTH/'growth_candidates.jsonl').read_bytes()
    session.post('/api/v2/query',json={'question':'演示成果有多少项？','traffic_kind':'TECHNICAL'})
    assert (v2.GROWTH/'growth_candidates.jsonl').read_bytes()==before


def test_unknown_review_and_mismatched_feedback_are_rejected(client):
    session,_=client
    assert session.post('/api/v2/growth-review',json={'candidate_id':'missing','decision':'APPROVE'}).status_code==404
    result=session.post('/api/v2/query',json={'question':'演示问题','traffic_kind':'TECHNICAL'}).json()
    assert session.post('/api/v2/feedback',json={'query_id':'other','query_run_id':result['query_run_id'],'feedback_type':'答案错误'}).status_code==409


def test_broken_candidate_file_is_not_silently_replaced(client):
    session,v2=client;path=v2.GROWTH/'growth_candidates.jsonl';path.parent.mkdir();path.write_text('{broken\n')
    result=session.post('/api/v2/query',json={'question':'演示问题','traffic_kind':'REAL'})
    assert result.status_code==200 and result.json()['growth_recording_status']=='FAILED'
    assert path.read_text()=='{broken\n'
