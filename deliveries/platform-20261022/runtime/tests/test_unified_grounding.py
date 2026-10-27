import hashlib,json
import pytest
from app.trial.assisted_chat import assemble,run_flow,AssistedQuery
from app.answer_engine.llm.claim_validator import check_source_units
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import GenerationResult


def evidence(tmp_path,text):
    p=tmp_path/'source.md';p.write_text(text,encoding='utf-8')
    bundle={'answer_grounding_policy':'STRICT_SOURCE_UNITS','candidate_evidence':[{'document_id':'d','evidence_id':'e','source_path':str(p),'source_version':hashlib.sha256(p.read_bytes()).hexdigest(),'role':'DIRECT','text':text}]}
    return bundle,assemble(bundle)[0]


@pytest.mark.parametrize('source,claim,status',[
    ('甲项目配置设计总监1人。','甲项目配置设计总监9人。','NUMBER_NOT_IN_CITED_SOURCE'),
    ('甲项目配置设计总监1人。','乙项目配置设计总监1人。','TEXT_NOT_MATCHED'),
    ('不得采用A方案。','应采用A方案。','TEXT_NOT_MATCHED'),
    ('如果审批通过，可采用A方案。','可采用A方案。','CONDITION_CONTEXT_OMITTED'),
    ('可采用A方案，但须经审批。','可采用A方案。','CONDITION_CONTEXT_OMITTED'),
    ('如果审批通过，可采用A方案。','如果审批通过，可采用A方案。','SOURCE_UNITS_MATCHED'),
    ('甲项目配置负责人1人。','甲项目团队总人数为1人。','TEXT_NOT_MATCHED'),
])
def test_source_unit_check_preserves_subject_numbers_polarity_and_conditions(tmp_path,source,claim,status):
    _,e=evidence(tmp_path,source)
    r=check_source_units([{'claim_id':'C1','claim_text':claim,'evidence_ids':['S1']}],e)
    assert r['checks'][0]['status']==status


def test_complete_answer_cannot_pass_on_a_valid_citation_with_an_unsupported_number(tmp_path):
    bundle,_=evidence(tmp_path,'甲项目配置设计总监1人。')
    class Local:
        available=True;last_error=None;last_diagnostics={}
        def generate(self,*args,**kwargs):
            return GenerationResult(json.dumps({'claims':[{'claim_id':'C1','claim_text':'甲项目配置设计总监9人。','evidence_ids':['S1']}],'section_map':{'evidence_summary':['C1'],'evidence_boundary':[]},'evidence_insufficient':[]},ensure_ascii=False),'offline',0)
    events=list(run_flow(AssistedQuery(question='甲项目配置多少人？'),lambda _:bundle,ShadowAnswerGenerator(Local()),lambda *_:None))
    r=events[-2]['result']
    assert r['answer_status']=='MODEL_GROUNDING_UNVERIFIED' and not r['claims']
    assert '9人' not in r['answer'] and r['citations'][0]['evidence_id']=='e'


@pytest.mark.parametrize('heading',['3. 会后落实（24 小时内完成）','办理期限（3个工作日内）','审核期限（两日内完成）'])
def test_adjacent_timed_heading_is_a_required_source_condition(tmp_path,heading):
    source=heading+'\n设计管理部编制会议纪要，经参会方确认后分发。'
    _,e=evidence(tmp_path,source)
    claim={'claim_id':'C1','claim_text':'设计管理部编制会议纪要，经参会方确认后分发。','evidence_ids':['S1']}
    checked=check_source_units([claim],e,allow_connector_omission=True,allow_sentence_span=True)
    assert not checked['valid'] and checked['checks'][0]['status']=='CONDITION_CONTEXT_OMITTED'
    claim['claim_text']=source
    assert check_source_units([claim],e,allow_connector_omission=True,allow_sentence_span=True)['valid']


def test_unrelated_duration_is_not_a_timed_heading(tmp_path):
    _,e=evidence(tmp_path,'会议持续24小时。\n设计管理部编制会议纪要。')
    assert check_source_units([{'claim_id':'C1','claim_text':'设计管理部编制会议纪要。','evidence_ids':['S1']}],e)['valid']


@pytest.mark.parametrize('source,claim,valid',[
    ('机电为内部单位，因此由技术总监牵头。','机电为内部单位，由技术总监牵头。',True),
    ('机电为内部单位，所以由技术总监牵头。','机电为内部单位，由技术总监牵头。',True),
    ('机电为内部单位，因而由技术总监牵头。','机电为内部单位，由技术总监牵头。',True),
    ('甲项目配置1人，因此由技术总监牵头。','甲项目配置9人，由技术总监牵头。',False),
    ('甲项目配置1人，因此由技术总监牵头。','乙项目配置1人，由技术总监牵头。',False),
    ('因此不得采用A方案。','可采用A方案。',False),
    ('如果审批通过，因此可采用A方案。','可采用A方案。',False),
    ('可采用A方案，因此必须复核。','可采用A方案。',False),
    ('机电为内部单位，因此只有审批通过才能实施。','机电为内部单位。',False),
    ('机电为内部单位，由技术总监牵头。','机电为内部单位，因此由技术总监牵头。',False),
    ('机电为内部单位，因为由技术总监牵头。','机电为内部单位，由技术总监牵头。',False),
])
def test_only_source_connector_omission_is_allowed_without_weakening_other_facts(tmp_path,source,claim,valid):
    _,e=evidence(tmp_path,source);claims=[{'claim_id':'C1','claim_text':claim,'evidence_ids':['S1']}]
    assert check_source_units(claims,e,allow_connector_omission=True)['valid']==valid
    assert not check_source_units(claims,e)['valid']


def test_scope_stop_reports_coverage_reason_without_calling_generation(tmp_path):
    bundle,_=evidence(tmp_path,'项目四大核心。')
    bundle.update(bundle_status='SOURCE_SCOPE_MISSING',coverage_audit={'status':'COMPOUND_COVERAGE_UNVERIFIED'},selection_notes=['第二个问题缺少金额主题证据。'])
    class Never:
        available=True
        def generate(self,*a,**kw):raise AssertionError('generation must not run')
    result=list(run_flow(AssistedQuery(question='核心是什么？金额是多少？'),lambda _:bundle,ShadowAnswerGenerator(Never()),lambda *_:None))[-2]['result']
    assert result['answer_status']=='EVIDENCE_INSUFFICIENT'
    assert result['failure_message']=='第二个问题缺少金额主题证据。'
    assert result['debug']['coverage_audit']['status']=='COMPOUND_COVERAGE_UNVERIFIED'
