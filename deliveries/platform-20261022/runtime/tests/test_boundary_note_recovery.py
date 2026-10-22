from copy import deepcopy
import hashlib,json
from pathlib import Path
import pytest
from app.answer_engine.answer_policy import policy_for_intent
from app.answer_engine.llm.boundary_note_recovery import recover_body
from app.answer_engine.llm.response_schema import validate_response
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import GenerationResult
from app.llm import LLMError
from app.trial.assisted_chat import assemble,AssistedQuery,run_flow


def fixture(tmp_path):
    path=tmp_path/'原文.md';path.write_text('设计标准文件应体现项目需求。',encoding='utf-8')
    bundle={'candidate_evidence':[{'evidence_id':'e','document_id':'d','source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),'role':'DIRECT','text':path.read_text(encoding='utf-8')}]}
    payload={'claims':[{'claim_id':'C1','claim_text':'设计标准文件应体现项目需求。','evidence_ids':['S1']}],
             'section_map':{'evidence_summary':['C1'],'evidence_boundary':['来源效力未在本次材料中核实。']},'evidence_insufficient':[]}
    return bundle,payload


def test_boundary_notes_quarantined_without_changing_claims_or_original_schema_status(tmp_path):
    bundle,payload=fixture(tmp_path);before=deepcopy(payload);policy=policy_for_intent('GENERAL_QUERY');evidence,_=assemble(bundle)
    assert not validate_response(payload,policy,{'S1'}).valid
    recovered=recover_body(json.dumps(payload,ensure_ascii=False),policy,evidence)
    assert payload==before and recovered['payload']['claims']==payload['claims']
    assert recovered['payload']['section_map']['evidence_boundary']==[]
    assert recovered['unverified_notes']==payload['section_map']['evidence_boundary']
    assert recovered['original_protocol_passed'] is False


@pytest.mark.parametrize('change',['unknown_source','unknown_claim','broken_summary','unmapped','extra_field','insufficient'])
def test_other_errors_are_not_bypassed(tmp_path,change):
    bundle,p=fixture(tmp_path);e,_=assemble(bundle)
    if change=='unknown_source':p['claims'][0]['evidence_ids']=['S999']
    if change=='unknown_claim':p['section_map']['evidence_boundary']=['C999']
    if change=='broken_summary':p['section_map']['evidence_summary']=['这不是事实编号']
    if change=='unmapped':p['section_map']['evidence_summary']=[]
    if change=='extra_field':p['extra']='unapproved'
    if change=='insufficient':p['evidence_insufficient']=['缺少适用条件']
    assert recover_body(json.dumps(p,ensure_ascii=False),policy_for_intent('GENERAL_QUERY'),e) is None


def test_existing_flow_shows_valid_body_with_explicit_warning_and_keeps_notes_unverified(tmp_path):
    bundle,payload=fixture(tmp_path)
    class Offline:
        available=True;last_error=None;last_diagnostics={};name='offline-replay'
        def __init__(self):self.calls=0
        def generate(self,*a,**kw):
            self.calls+=1
            if self.calls>1:raise LLMError('No repair response or external call')
            return GenerationResult(json.dumps(payload,ensure_ascii=False),'offline',1)
    events=list(run_flow(AssistedQuery(question='设计标准文件有什么要求？'),lambda _:bundle,ShadowAnswerGenerator(Offline()),lambda *_:None))
    r=next(e['result'] for e in events if e['type']=='result')
    assert r['answer_status']=='MODEL_DRAFT_PROTOCOL_WARNING' and '格式警告' in r['answer']
    assert r['claims'][0]['claim_text']==payload['claims'][0]['claim_text'] and r['citations'][0]['citation_id']=='S1'
    assert r['unverified_model_notes']==payload['section_map']['evidence_boundary']
