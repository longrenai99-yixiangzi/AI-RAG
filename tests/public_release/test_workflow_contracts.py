import copy
import io
import base64
import zipfile
import pytest
from app.assessment_handoff import apply_gap_policy,build_handoff,render_handoff,gap_type
from app.scheme_comparison import comparison_topics,build_comparison,render_comparison


def compare(c,common=None,options=None):
    topic=comparison_topics(c)['topics'][0]
    return build_comparison(c,c['source']['source_version'],topic['topic_id'],common or {},options or [{},{}])

def common():return {'scope':'合成对象','cost_scope':'相同费用范围','cost_basis':'同数量、价格时点和税费','duration_scope':'相同前置与施工范围'}
def options():return [{'cost':'2','cost_unit':'万元','cost_evidence':'合成金额A','duration_days':'7','duration_evidence':'合成用时A'},
                      {'cost':'15000','cost_unit':'元','cost_evidence':'合成金额B','duration_days':'5','duration_evidence':'合成用时B'}]

def test_empty_inputs_export_as_gaps_without_automatic_selection(sample_case):
    d=compare(sample_case);assert d['gaps'] and d['recommended_option'] is None
    assert d['cost_comparison']['status']==d['time_comparison']['status']=='MISSING_INPUT'
    assert len(render_comparison(d))==4 and not d['owner_approved'] and not d['knowledge_published']

def test_exact_conversion_and_known_zero_distinct_from_unknown(sample_case):
    d=compare(sample_case,common(),options());assert d['cost_comparison']['B_minus_A_yuan']=='-5000'
    assert d['time_comparison']['B_minus_A_days']=='-2'
    o=options();o[0].update(cost='0',duration_days='0');assert compare(sample_case,common(),o)['time_comparison']['B_minus_A_days']=='5'
    o[0]['cost']='';assert compare(sample_case,common(),o)['cost_comparison']['status']=='MISSING_INPUT'

def test_decimal_arithmetic_has_no_binary_float_error(sample_case):
    o=options();o[0].update(cost='0.7',cost_unit='元');o[1].update(cost='0.2',cost_unit='元')
    assert compare(sample_case,common(),o)['cost_comparison']['B_minus_A_yuan']=='-0.5'

@pytest.mark.parametrize('field',['scope','cost_scope','cost_basis'])
def test_different_or_missing_cost_basis_does_not_produce_savings(sample_case,field):
    shared=common();shared.pop(field);assert compare(sample_case,shared,options())['cost_comparison']['status']=='MISSING_INPUT'

def test_constraint_failure_is_not_a_cheap_winner(sample_case):
    o=options();o[1]['constraint_status']='不满足';d=compare(sample_case,common(),o)
    assert '不进入推荐范围' in d['eligibility'][1] and d['recommended_option'] is None

@pytest.mark.parametrize('value',['-1','NaN','Infinity','1e9999999','1,000','6元','123456789012345'])
def test_ambiguous_nonfinite_negative_or_excessive_values_rejected(sample_case,value):
    o=options();o[0]['cost']=value
    with pytest.raises(ValueError):compare(sample_case,common(),o)

def test_private_source_mappings_are_required_and_not_baked_into_code(sample_case):
    c=copy.deepcopy(sample_case);c.pop('comparison_topic_specs')
    with pytest.raises(ValueError):comparison_topics(c)
    assert comparison_topics(sample_case)['topics'][0]['subject']=='演示对象'

def test_user_notes_and_gap_policy_do_not_change_original_source(sample_case):
    original=copy.deepcopy(sample_case);c=apply_gap_policy(sample_case,sample_case['gap_policy'])
    d=build_handoff(c,c['source']['source_version'],['ITEM-BETA'],{})
    assert sample_case==original and d['items'][0]['current_inputs']=={}
    assert not d['owner_approved'] and '不要求先考证' in render_handoff(d)['评估问题任务准备.md']

@pytest.mark.parametrize('quote,kind',[('', 'REPORT_CONTENT_GAP'),('缺合成成果','SOURCE_REPORTED_GAP'),('未评估','ASSESSMENT_GAP'),('如需调整，可选演示方案','TECHNICAL_REVIEW')])
def test_missing_report_content_does_not_assert_real_design_defect(quote,kind):assert gap_type(quote)[0]==kind

@pytest.mark.parametrize('kind',['date','version','duplicate','quote','other_item'])
def test_task_preparation_validates_date_version_selection_and_source_text(sample_case,kind):
    version=sample_case['source']['source_version'];selected=['ITEM-BETA'];updates={}
    if kind=='date':updates={'ITEM-BETA':{'start_date':'2030-03-04','due_date':'2030-03-03'}}
    if kind=='version':version='0'*64
    if kind=='duplicate':selected*=2
    if kind=='quote':updates={'ITEM-BETA':{'quote':'改变来源'}}
    if kind=='other_item':selected=['OTHER_CASE']
    with pytest.raises(ValueError):build_handoff(sample_case,version,selected,updates)

def test_synthetic_endpoints_export_and_reject_unsafe_inputs(adapter_client):
    client,c,original=adapter_client
    response=client.get('/api/v2/scheme-comparison/projects/demo-project');assert response.status_code==200
    payload={'project_id':'demo-project','source_version':c['source']['source_version'],'topic_id':response.json()['topics'][0]['topic_id']}
    response=client.post('/api/v2/scheme-comparison/draft',json=payload);assert response.status_code==200
    p=response.json();assert p['recommended_option'] is None and p['draft']['gaps']
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(p['download_base64']))) as z:assert z.testzip() is None and len(z.namelist())==5
    assert client.post('/api/v2/scheme-comparison/draft',json={**payload,'recommended_option':'B'}).status_code==422
    assert client.post('/api/v2/scheme-comparison/draft',json={**payload,'project_id':'other'}).status_code==404
    assert client.post('/api/v2/scheme-comparison/draft',json={**payload,'source_version':'0'*64}).status_code==409
    assert client.post('/api/v2/knowledge/sources/overwrite',json={}).status_code==403
    original.write_bytes(b'tampered synthetic source')
    assert client.post('/api/v2/scheme-comparison/draft',json=payload).status_code==409
