from copy import deepcopy
import hashlib,json
import pytest
from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.llm.boundary_note_recovery import project_partial_body,recover_body
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import GenerationResult
from app.answer_engine.llm.prompt_builder import build_prompt,build_prompt_v2
from app.answer_engine.llm.response_schema import response_schema,validate_response_v2
from app.answer_engine.question_scope import question_scope
from app.llm import LLMError
from app.trial.assisted_chat import assemble,AssistedQuery,run_flow


def fixture(tmp_path):
    path=tmp_path/'原文.md';path.write_text('本项目配置设计总监1人，负责统筹管理项目设计工作。',encoding='utf-8')
    bundle={'candidate_evidence':[{'evidence_id':'e','document_id':'d','source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),'role':'DIRECT','text':path.read_text(encoding='utf-8')}]}
    payload={'claims':[{'claim_id':'C1','claim_text':'本项目配置设计总监1人，负责统筹管理项目设计工作。','evidence_ids':['S1']}],
             'section_map':{'evidence_summary':['C1'],'evidence_boundary':['本段未列出全团队人数。']},'evidence_insufficient':['未取得团队总人数。']}
    return bundle,payload


def test_partial_projection_preserves_original_claims_gaps_and_rejection(tmp_path):
    b,p=fixture(tmp_path);before=deepcopy(p);e,_=assemble(b);policy=policy_for_intent('GENERAL_QUERY')
    assert recover_body(json.dumps(p,ensure_ascii=False),policy,e) is None
    r=project_partial_body(json.dumps(p,ensure_ascii=False),policy,e)
    assert p==before and r['payload']['claims']==p['claims']
    assert r['payload']['evidence_insufficient']==p['evidence_insufficient']
    assert r['unverified_notes']==p['section_map']['evidence_boundary'] and not r['original_protocol_passed']
    p['section_map']['evidence_boundary']=[]
    assert project_partial_body(json.dumps(p),policy,e)['original_protocol_passed']


@pytest.mark.parametrize('change',['wrong_source','wrong_claim_id','wrong_number','negation','team_total','unmapped','unknown_field','no_claims','reordered_clauses'])
def test_partial_projection_rejects_unsafe_or_unbound_facts(tmp_path,change):
    b,p=fixture(tmp_path);e,_=assemble(b)
    if change=='wrong_source':p['claims'][0]['evidence_ids']=['S999']
    if change=='wrong_claim_id':p['section_map']['evidence_boundary']=['C999']
    if change=='wrong_number':p['claims'][0]['claim_text']='本项目配置设计总监9人，负责统筹管理项目设计工作。'
    if change=='negation':p['claims'][0]['claim_text']='本项目不配置设计总监1人。'
    if change=='team_total':p['claims'][0]['claim_text']='本项目团队总人数为1人。'
    if change=='unmapped':p['section_map']['evidence_summary']=[]
    if change=='unknown_field':p['claims'][0]['extra']='unverified'
    if change=='no_claims':p['claims']=[]
    if change=='reordered_clauses':p['claims'][0]['claim_text']='负责统筹管理项目设计工作，本项目配置设计总监1人。'
    assert project_partial_body(json.dumps(p,ensure_ascii=False),policy_for_intent('GENERAL_QUERY'),e) is None


def test_partial_flow_never_becomes_complete_and_keeps_source_and_missing_aspects(tmp_path):
    b,p=fixture(tmp_path)
    class Recorded:
        available=True;last_error=None;last_diagnostics={}
        def __init__(self):self.calls=0
        def generate(self,*a,**kw):
            self.calls+=1
            if self.calls>1:raise LLMError('Local repair refused; no HTTP')
            return GenerationResult(json.dumps(p,ensure_ascii=False),'recorded',0)
    events=list(run_flow(AssistedQuery(question='谁牵头设计管理，配置多少人？'),lambda _:b,ShadowAnswerGenerator(Recorded()),lambda *_:None))
    r=events[-2]['result']
    assert r['answer_status']=='MODEL_PARTIAL_DRAFT' and r['answer_completeness']=='PARTIAL'
    assert r['unresolved_aspects']==p['evidence_insufficient'] and r['original_schema_errors']
    assert '模型提出的证据缺口' in r['answer'] and r['citations'][0]['evidence_id']=='e'
    assert r['question_scope']['kind']=='LEAD_ROLE_COUNT'


def test_role_team_scope_hints_and_v2_prompt_do_not_rewrite_the_question(tmp_path):
    assert question_scope('负责人配置多少人？')['kind']=='LEAD_ROLE_COUNT'
    assert question_scope('整个团队总人数是多少？')['kind']=='TEAM_COUNT'
    assert question_scope('谁牵头，以及团队总人数是多少？')['kind']=='ROLE_AND_TEAM_COUNTS'
    assert question_scope('配置多少人？')['kind']=='UNSPECIFIED_COUNT'
    assert question_scope('设计评估有什么作用？') is None
    b,_=fixture(tmp_path);e,_=assemble(b);q='谁牵头，配置多少人？';policy=policy_for_intent('GENERAL_QUERY')
    old=build_prompt(q,policy,e);draft=build_prompt_v2(q,policy,e)
    assert build_prompt(q,policy,e)==old and draft.user_prompt!=old.user_prompt
    assert 'MINIMAL_ANSWER_V2_DRAFT' in draft.user_prompt and '问题：'+q in draft.user_prompt
    assert 'scope_notes' in draft.response_schema['required'] and 'scope_notes' not in old.response_schema['properties']


def test_v2_contract_separates_notes_and_gaps_and_keeps_old_schema_unchanged(tmp_path):
    _,p=fixture(tmp_path);policy=policy_for_intent('GENERAL_QUERY');old_schema=response_schema(policy)
    notes=p['section_map']['evidence_boundary'];p['section_map']['evidence_boundary']=[];p['scope_notes']=notes
    before=deepcopy(p)
    assert validate_response_v2(p,policy,{'S1'}).valid and p==before
    assert response_schema(policy)==old_schema
    p['section_map']['evidence_boundary']=['范围不是事实编号']
    assert not validate_response_v2(p,policy,{'S1'}).valid
    p=before;p['claims'][0]['evidence_ids']=['S999']
    assert not validate_response_v2(p,policy,{'S1'}).valid
