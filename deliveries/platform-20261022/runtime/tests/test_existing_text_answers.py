import hashlib
from copy import deepcopy
import pytest

from app.trial.existing_text_answers import render_existing
from app.retrieval.query_planner_v1 import plan_query
from app.verified_answer_engine_v2 import validate


def bundle(tmp_path,question,text):
    source=tmp_path/'甲学校项目.md';source.write_text(text,encoding='utf-8')
    original=tmp_path/'original.pptx';original.write_bytes(b'fixed-original')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    candidate={'evidence_id':'retrieved','document_id':'doc','source_id':'source','source_path':str(source),'source_version':digest,
               'file_name':source.name,'heading_path':'甲学校项目 > 合同概况','text':text,'raw_text':text,'location':{},'role':'CONTEXT_ONLY'}
    data={'query_id':'q','question':question,'query_plan':plan_query(question).to_dict(),'bundle_status':'VERIFIED',
          'candidate_evidence':[candidate],'verified_evidence':[]}
    links={str(source):{'markdown_sha256':digest,'original_path':str(original),'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
                       'scope':{'project':'甲学校项目','aliases':['甲学校项目'],'phases':['一期'],'packages':[]}}}
    return data,links,source,original


@pytest.mark.parametrize('unit,number',[('万元','12345.678912'),('亿元','1.2345678912')])
def test_label_binding_condition_and_conversion_ignore_unrelated_money(tmp_path,unit,number):
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额是多少'+unit+'？','合同总价 123456789.12 元（暂定，根据施工图预算核对确定）\n最低起付金额500万元')
    answer,grounded=render_existing(data,links)
    assert answer['answer_status']=='ANSWERED' and number+unit in answer['answer_text']
    assert '暂定，根据施工图预算核对确定' in answer['answer_text'] and '500万元' not in answer['answer_text']
    assert answer['citations'][0]['location']['markdown_line']==1 and validate(answer,grounded)['valid']


def test_wrong_phase_or_stale_or_unretrieved_text_cannot_supply_amount(tmp_path):
    data,links,source,original=bundle(tmp_path,'甲学校项目二期合同金额多少万元？','合同总价731万元')
    answer,_=render_existing(data,links);assert answer['answer_status']=='SOURCE_SCOPE_MISSING' and '731万元' not in answer['answer_text']
    empty=deepcopy(data);empty['candidate_evidence']=[];assert render_existing(empty,links) is None
    original.write_bytes(b'changed');assert render_existing(data,links) is None
    source.write_text('合同总价999万元',encoding='utf-8');assert render_existing(data,links) is None


def test_scope_mismatch_and_unvalidated_arithmetic_do_not_borrow_a_number(tmp_path):
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额相差多少万元？','合同总价731万元')
    assert render_existing(data,links) is None
    data['question']='甲学校项目合同金额多少万元？'
    data['candidate_evidence'][0]['scope']={'project':'MISMATCH'}
    assert render_existing(data,links) is None


def test_total_contract_is_distinct_from_self_performed_contract_and_short_money_units(tmp_path):
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额多少万元？','合同造价43210.56万元。自施合同额8765.43万元。自营合同额8765.43万。')
    answer,grounded=render_existing(data,links)
    assert answer['answer_status']=='ANSWERED' and '43210.56万元' in answer['answer_text'] and '8765.43' not in answer['answer_text']
    assert validate(answer,grounded)['valid']
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额多少万元？','合同额12.34亿。土方12.34万方。')
    assert '123400万元' in render_existing(data,links)[0]['answer_text']


def test_bid_award_and_control_price_do_not_become_contract_total(tmp_path):
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额多少万元？','合同价格 招标控制价8.76亿元，中标金额543210987.65元（包含设计费）。')
    answer,grounded=render_existing(data,links)
    assert answer['answer_status']=='PARTIAL_ANSWER' and not any(c['claim_type']=='DIRECT' for c in answer['claims'])
    assert validate(answer,grounded)['valid']


def test_existing_original_format_chunk_uses_versioned_index_text_without_reparsing(tmp_path):
    data,links,source,original=bundle(tmp_path,'甲学校项目工程造价多少万元？','表头：工程造价 | 56789万\n行：合同形式 | 固定总价')
    c=data['candidate_evidence'][0];c.update(source_path=str(original),source_version=hashlib.sha256(original.read_bytes()).hexdigest(),file_name=original.name,heading_path='Slide 12')
    answer,grounded=render_existing(data,links)
    assert answer['answer_status']=='ANSWERED' and '56789万元' in answer['answer_text']
    assert answer['citations'][0]['location']['slide']==12 and 'markdown_line' not in answer['citations'][0]['location']
    original.write_bytes(b'changed');assert render_existing(data,links) is None


def test_component_cost_and_per_area_price_do_not_conflict_with_project_totals(tmp_path):
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额多少万元？','合同造价43210.56万元。实际合同造价为4567.89元/㎡。桩基工程造价：3210万元。工程造价43210.56万元。')
    answer,_=render_existing(data,links)
    assert answer['answer_status']=='ANSWERED' and '43210.56万元' in answer['answer_text']
    data['question']='甲学校项目工程造价多少万元？'
    answer,_=render_existing(data,links)
    assert answer['answer_status']=='ANSWERED' and '43210.56万元' in answer['answer_text'] and '3210万元' not in answer['answer_text']


def test_equivalent_money_units_are_compared_after_normalization(tmp_path):
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额多少万元？','合同总价23456万元。合同造价2.3456亿。')
    answer,_=render_existing(data,links)
    assert answer['answer_status']=='ANSWERED' and '23456万元' in answer['answer_text']


def test_standalone_total_requires_contract_context_and_ignores_rounded_summary(tmp_path):
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额多少万元？','合同价格形式：总价合同；总价987654321.09元。摘要固定总价9.88亿元。')
    answer,_=render_existing(data,links)
    assert answer['answer_status']=='ANSWERED' and '98765.432109万元' in answer['answer_text']
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额多少万元？','投资估算：总价9.88亿元。')
    assert render_existing(data,links) is None


def test_estimated_total_cost_keeps_qualifier_and_does_not_become_contract_amount(tmp_path):
    data,links,_,_=bundle(tmp_path,'甲学校项目工程造价多少万元？','工程造价 总造价暂估12.34亿元，其中建安费12亿元。')
    answer,_=render_existing(data,links)
    assert answer['answer_status']=='ANSWERED' and '123400万元' in answer['answer_text'] and '暂估' in answer['answer_text']
    data['question']='甲学校项目合同金额多少万元？'
    answer,_=render_existing(data,links)
    assert answer['answer_status']=='PARTIAL_ANSWER' and not any(c['claim_type']=='DIRECT' for c in answer['claims'])


def test_project_fact_in_recalled_window_is_used_without_scanning_other_sources(tmp_path):
    data,links,_,_=bundle(tmp_path,'甲学校项目合同金额多少万元？','合同总价987654321.09元')
    parent=deepcopy(data['candidate_evidence'][0]);data['candidate_evidence']=[]
    answer,_=render_existing(data,links,recalled_parents=[parent])
    assert answer['answer_status']=='ANSWERED' and '98765.432109万元' in answer['answer_text']
    data['query_plan']['year']=['2030']
    assert render_existing(data,links,recalled_parents=[parent]) is None


@pytest.mark.parametrize('question,expected,excluded',[('给排水专业特点分析，管控要点有哪些？','系统规模','室内给排水'),('给排水设计四大模块有哪些？','室内给排水','系统规模')])
def test_explicit_text_lists_bypass_irrelevant_table_and_keep_distinct_labels(tmp_path,question,expected,excluded):
    text='给排水专业特点分析\n本专业包括四大板块：室内给排水、室外给排水、水消防以及专项配合。\n其管控要点一是系统规模，避免过大。二是设备选择。三是接口提资。四是利旧。'
    data,_,_,_=bundle(tmp_path,question,text)
    data['query_plan']['aggregation_plan']=['LIST_DISTINCT'];data['structured_evidence_complete']=False
    answer,grounded=render_existing(data,{})
    assert answer['answer_status']=='ANSWERED' and expected in answer['answer_text'] and excluded not in answer['answer_text']
    assert validate(answer,grounded)['valid']


def test_parent_expansion_requires_same_source_version_and_page(tmp_path):
    from tests.test_layout_evidence import sample
    data,_,source,_=bundle(tmp_path,'暖通初步设计阶段管控有哪六个方面？','无可用列表')
    child=sample('控制要点',['甲','乙','丙','丁','戊'],'暖通专业 初步设计阶段管控要点')
    child.update(source_path=str(source),source_version=hashlib.sha256(source.read_bytes()).hexdigest(),location={'slide':7})
    parent={'source_path':str(source),'source_version':child['source_version'],'location':{'page':7}}
    answer,grounded=render_existing(data,{},recalled_parents=[parent],indexed_layouts=[child])
    assert answer['answer_status']=='PARTIAL_ANSWER' and '不能补造' in answer['answer_text'] and validate(answer,grounded)['valid']
    parent['location']['page']=8;assert render_existing(data,{},recalled_parents=[parent],indexed_layouts=[child]) is None
    parent.update(source_path=str(source.with_suffix('.pptx')),heading_path='Slide 7',location={})
    source.with_suffix('.pptx').write_bytes(source.read_bytes());child['source_path']=parent['source_path']
    assert render_existing(data,{},recalled_parents=[parent],indexed_layouts=[child])[0]['answer_status']=='PARTIAL_ANSWER'
