from copy import deepcopy

import pytest

from app.trial.platform_existing import source_extract
from test_source_field_answer import source


def test_project_money_is_extracted_from_recalled_case_without_admission_whitelist(tmp_path):
    text=('概念说明。\n案例1\n甲剧院项目，总投资2.7亿美元。\n案例2\n'
          '乙园区项目，包含住宅地块和商业地块，总建筑面积约22.7万平方米，工程费12.34亿元。\n后续职责说明。')
    data=source(tmp_path,text);before=deepcopy(data)
    result=source_extract(data,'乙园区项目，工程费用多少')
    assert result['answer']=='乙园区项目，工程费12.34亿元。 [S1]'
    assert result['field_audit']['metric']=='工程费'
    assert '约' not in result['answer'] and '22.7' not in result['answer']
    citation=result['citations'][0]
    assert '甲剧院' not in citation['excerpt'] and '概念说明' not in citation['excerpt']
    assert citation['location']['line_start']==5 and citation['location']['line_end']==5
    assert result['generation_mode']=='LOCAL_PROJECT_MONEY_FIELD_NO_MODEL' and data==before


@pytest.mark.parametrize('label,query,canonical',[
    ('工程费','工程费用','工程费'),('工程费用','工程费','工程费'),
    ('合同金额','合同金额','合同金额'),('合同总价','合同额','合同金额'),
    ('工程造价','工程造价','工程造价'),('总造价','工程造价','工程造价'),
    ('总投资','总投资','总投资'),('建安工程费用','建安工程费','建安工程费'),
    ('工程建设其他费用','工程建设其他费用','工程建设其他费用'),
    ('预备费','预备费','预备费'),('初步设计概算费用','初设概算费用','初设概算费用')])
def test_shared_metric_aliases_do_not_need_project_specific_rules(tmp_path,label,query,canonical):
    result=source_extract(source(tmp_path,f'甲项目，{label}12.34万元。'),f'甲项目{query}多少？')
    assert result['answer_status']=='SOURCE_EXTRACT'
    assert result['field_audit']['metric']==canonical and '12.34万元' in result['answer']


@pytest.mark.parametrize('question',['请问甲项目的工程费用是多少钱？','甲项目工程费大概多少呢？','查询甲项目工程费用总共多少钱？'])
def test_common_amount_question_wording_does_not_change_scope(tmp_path,question):
    result=source_extract(source(tmp_path,'甲项目，工程费12.34亿元。'),question)
    assert result['answer']=='甲项目，工程费12.34亿元。 [S1]'


@pytest.mark.parametrize('project',['目的地园区项目','总投资研究园项目'])
def test_project_name_words_are_not_mistaken_for_question_intent_or_another_metric(tmp_path,project):
    result=source_extract(source(tmp_path,f'{project}，工程费2亿元。'),f'请问{project}的工程费是多少？')
    assert result['answer']==f'{project}，工程费2亿元。 [S1]'


def test_explanations_and_foreign_currency_questions_are_not_rmb_field_requests(tmp_path):
    from app.trial.source_field_answer import money_answer
    data=source(tmp_path,'甲项目，工程费12.34亿元。')
    for query in ['甲项目如何控制工程费用？','甲项目工程费由谁负责？','甲项目总投资多少美元？']:
        assert money_answer(data,query) is None


def test_similar_amount_fields_are_not_interchangeable(tmp_path):
    data=source(tmp_path,'甲项目，总投资20亿元，建安工程费8亿元，工程费12.34亿元，合同金额9亿元。')
    result=source_extract(data,'甲项目工程费多少？')
    assert result['answer']=='甲项目，工程费12.34亿元。 [S1]'
    only=source(tmp_path,'甲项目，工程费12.34亿元。')
    assert source_extract(only,'甲项目合同金额多少？')['answer_status']=='EVIDENCE_INSUFFICIENT'


@pytest.mark.parametrize('unit,expected',[('亿元','约12.34亿元'),('万元','约123400万元'),('元','约1234000000元')])
def test_decimal_conversion_keeps_the_original_qualifier_and_parenthesis(tmp_path,unit,expected):
    result=source_extract(source(tmp_path,'甲项目，工程费约12.34亿元（含税）。'),f'甲项目工程费换算多少{unit}？')
    assert expected+'（含税）' in result['answer']


@pytest.mark.parametrize('text',[
    '甲项目，工程费12.34。','甲项目，工程费12.34亿。',
    '甲项目，总投资2.7亿美元。','甲项目，工程费10万元/平方米。',
    '甲项目，商业地块工程费12.34亿元。',
    '甲项目，工程费12.34亿元，不含设计费。',
    '甲项目，工程费12.34亿元。\n备注：以上费用不含设计费。'])
def test_missing_units_foreign_currency_subscope_and_unbound_conditions_are_rejected(tmp_path,text):
    query='甲项目总投资多少？' if '总投资' in text else '甲项目工程费用多少？'
    result=source_extract(source(tmp_path,text),query)
    assert result['answer_status']=='EVIDENCE_INSUFFICIENT'
    assert not any(c['answer_usage']=='PRIMARY' for c in result['citations'])
    assert '12.34' not in result['answer'] and '2.7' not in result['answer']


@pytest.mark.parametrize('query',[
    '丙项目工程费多少？','甲项目商业地块工程费多少？','甲项目工程费2025年多少？',
    '甲项目工程费最终结算多少？','甲项目工程费和总投资分别多少？',
    '甲项目和乙项目工程费合计多少？','甲项目工程费扣除税费多少？'])
def test_other_project_scope_year_and_unverified_arithmetic_never_borrow_money(tmp_path,query):
    result=source_extract(source(tmp_path,'案例1\n甲项目，工程费2亿元。\n案例2\n乙项目，工程费9亿元。'),query)
    assert result['answer_status']=='EVIDENCE_INSUFFICIENT'
    assert '2亿元' not in result['answer'] and '9亿元' not in result['answer']


def test_phase_is_verified_and_not_used_as_whole_project_total(tmp_path):
    data=source(tmp_path,'甲项目，一期工程费2亿元，二期工程费3亿元。')
    assert '一期工程费2亿元' in source_extract(data,'甲项目一期工程费多少？')['answer']
    assert '二期工程费3亿元' in source_extract(data,'甲项目二期工程费多少？')['answer']
    assert source_extract(data,'甲项目工程费多少？')['answer_status']=='EVIDENCE_INSUFFICIENT'


def test_conflicts_stale_source_and_background_are_not_answers(tmp_path):
    data=source(tmp_path,'甲项目，工程费2亿元。\n甲项目，工程费3亿元。')
    assert source_extract(data,'甲项目工程费多少？')['field_audit']['reason']=='CONFLICTING_PROJECT_MONEY_VALUES'
    data=source(tmp_path,'甲项目，工程费2亿元。');data['citations'][0]['answer_usage']='BACKGROUND'
    assert source_extract(data,'甲项目工程费多少？')['answer_status']=='SOURCES_ONLY'
    data['citations'][0]['answer_usage']='PRIMARY';data['citations'][0]['source_version']='0'*64
    assert source_extract(data,'甲项目工程费多少？')['answer_status']=='EVIDENCE_INSUFFICIENT'


def test_equivalent_units_are_not_a_conflict_and_anchors_stay_readable(tmp_path):
    data=source(tmp_path,'[/body/p[@paraId=AB12]] 甲项目，工程费2亿元。\n[/body/p[@paraId=CD34]] 甲项目，工程费20000万元。')
    result=source_extract(data,'甲项目工程费多少？')
    assert result['answer']=='甲项目，工程费2亿元。 [S1]'
    assert result['citations'][0]['location']['paragraph_anchor']=='AB12'


def test_failed_model_does_not_discard_an_already_bound_money_answer(tmp_path):
    from pathlib import Path
    from app.answer_engine.llm.reviewed_packet_provider import sha
    from app.trial.platform_generation import GenerationWorkflow
    from app.trial.platform_store import PlatformStore
    data=source(tmp_path,'甲项目，工程费12.34亿元。')
    question='甲项目工程费用多少？';local=source_extract(data,question)
    store=PlatformStore(tmp_path/'generation/state.json');row,_=store.begin_run('a'*32,question,'synthetic')
    store.finish_run(row['query_run_id'],local);calls=[]
    class FailedProvider:
        def generate(self,*args,**kwargs):
            calls.append(True);raise RuntimeError('synthetic transport failure')
    flow=GenerationWorkflow(store,lambda c:sha(c['source_path'])==c['source_version'],
                            provider_factory=lambda *args,**kwargs:FailedProvider())
    preview=flow.prepare(row['query_run_id'],'CONCISE_V1')
    result=flow.run(preview['preview_id'],preview['packet_sha256'],'synthetic')
    assert result['status']=='ERROR' and result['result']['answer']==local['answer']
    assert result['result']['answer_status']=='MODEL_FAILED_LOCAL_FALLBACK' and len(calls)==1
    with pytest.raises(ValueError):flow.run(preview['preview_id'],preview['packet_sha256'],'again')
    assert len(calls)==1
