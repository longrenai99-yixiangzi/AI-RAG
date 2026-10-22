import json
from copy import deepcopy
import pytest
from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import GenerationResult
from app.answer_engine.llm.claim_validator import check_source_units
from app.trial.assisted_chat import AssistedQuery,run_flow,assemble
from app.llm import LLMError
from tests.test_unified_grounding import evidence


class Synthetic:
    available=True;last_error=None;last_diagnostics={}
    def __init__(self,payload):self.payload=payload;self.calls=[]
    def generate(self,system,user,**kwargs):
        self.calls.append((system,user))
        if isinstance(self.payload,Exception):raise self.payload
        return GenerationResult(json.dumps(self.payload,ensure_ascii=False),'synthetic-offline',0)


def payload(gaps=False,empty=False):
    return {'claims':[] if empty else [{'claim_id':'C1','claim_text':'本项目配置设计总监1人。','evidence_ids':['S1']}],
            'section_map':{'evidence_summary':[] if empty else ['C1'],'evidence_boundary':[]},
            'evidence_insufficient':['未取得团队总人数。'] if gaps else [],'scope_notes':['这只是负责人岗位人数。']}


@pytest.mark.parametrize('gaps,empty,status',[(False,False,'MODEL_DRAFT'),(True,False,'MODEL_PARTIAL_DRAFT'),(True,True,'MODEL_EVIDENCE_GAP')])
def test_v2_keeps_facts_scope_notes_and_question_gaps_separate(tmp_path,gaps,empty,status):
    b,_=evidence(tmp_path,'本项目配置设计总监1人。团队人数未披露。');p=payload(gaps,empty);before=deepcopy(p);provider=Synthetic(p)
    question='团队总人数是多少？' if empty else '负责人是谁及团队总人数是多少？' if gaps else '谁牵头设计管理，配置多少人？'
    events=list(run_flow(AssistedQuery(question=question),lambda _:b,ShadowAnswerGenerator(provider,protocol_version='V2'),lambda *_:None))
    r=events[-2]['result']
    assert r['answer_status']==status and len(provider.calls)==1 and p==before
    assert 'MINIMAL_ANSWER_V2_DRAFT' in provider.calls[0][1]
    assert r['unverified_model_notes']==p['scope_notes'] and r['unresolved_aspects']==p['evidence_insufficient']
    assert r['answer_contract_version']=='MINIMAL_ANSWER_V2_DRAFT'
    if not gaps:assert '部分回答项尚未形成内容' not in r['answer']
    if empty:assert not r['claims'] and r['answer_completeness']=='UNANSWERED'
    else:assert r['claims'][0]['claim_text']==p['claims'][0]['claim_text']


@pytest.mark.parametrize('change',['claim_id','unknown_field','notes_in_mapping','unsupported_number','bad_json_shape','blank_gap','empty_answer'])
def test_v2_never_rewrites_bad_ids_or_issues_a_repair_call(tmp_path,change):
    b,_=evidence(tmp_path,'本项目配置设计总监1人。');p=payload()
    if change=='claim_id':p['claims'][0]['claim_id']='natural-id';p['section_map']['evidence_summary']=['natural-id']
    if change=='unknown_field':p['extra']='unreviewed'
    if change=='notes_in_mapping':p['section_map']['evidence_boundary']=['not a claim']
    if change=='unsupported_number':p['claims'][0]['claim_text']='本项目配置设计总监9人。'
    if change=='bad_json_shape':p=[]
    if change=='blank_gap':p['evidence_insufficient']=[' ']
    if change=='empty_answer':p['claims']=[];p['section_map']['evidence_summary']=[]
    provider=Synthetic(p)
    r=list(run_flow(AssistedQuery(question='负责人多少人？'),lambda _:b,ShadowAnswerGenerator(provider,protocol_version='V2'),lambda *_:None))[-2]['result']
    assert r['answer_status'] in {'MODEL_OUTPUT_REJECTED','MODEL_GROUNDING_UNVERIFIED'} and not r['claims']
    assert len(provider.calls)==1


def test_v2_transport_failure_is_one_attempt_and_never_runs_repair(tmp_path):
    _,e=evidence(tmp_path,'本项目配置设计总监1人。');provider=Synthetic(LLMError('offline simulated failure'))
    r=ShadowAnswerGenerator(provider,protocol_version='V2').generate('负责人多少人？',policy_for_intent('GENERAL_QUERY'),e)
    assert r.status=='LLM_ERROR' and len(provider.calls)==1 and not r.repair_triggered


@pytest.mark.parametrize('source',[
    '适用前提：审批通过。可采用A方案。',
    '适用条件：审批通过。\n可采用A方案。',
    '可采用A方案。\n但须经审批。',
    '可采用A方案。必须进行复核。',
])
def test_adjacent_explicit_condition_cannot_be_omitted(tmp_path,source):
    _,e=evidence(tmp_path,source)
    r=check_source_units([{'claim_id':'C1','claim_text':'可采用A方案。','evidence_ids':['S1']}],e,allow_connector_omission=True)
    assert not r['valid'] and r['checks'][0]['status']=='CONDITION_CONTEXT_OMITTED'
