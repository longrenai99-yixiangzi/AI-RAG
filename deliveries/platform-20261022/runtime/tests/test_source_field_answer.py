import hashlib
from copy import deepcopy

import pytest

from app.trial.platform_existing import source_extract


def source(tmp_path,text,name='讲稿.md'):
    path=tmp_path/name;path.write_text(text,encoding='utf-8')
    return {'answer_status':'SOURCES_ONLY','citations':[{'citation_id':'S1','evidence_id':'section-parent','source_id':'SRC_case',
            'source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),'file_name':path.name,
            'excerpt':text,'display_location':'讲稿 > 案例','location':{'section':'案例'},'answer_usage':'PRIMARY'}]}


def test_selects_only_requested_project_area_preserving_approximation_and_narrow_source(tmp_path):
    text='概念说明与设计理论。\n案例1\n甲城剧院项目，建筑面积约4万㎡，总投资1.6亿美元。\n设计说明。\n案例2\n乙城住房项目，总建筑面积34万㎡。'
    data=source(tmp_path,text);before=deepcopy(data)
    result=source_extract(data,'甲城剧院项目，建筑面积是多少？')
    assert result['answer']=='甲城剧院项目，建筑面积约4万平方米。 [S1]'
    assert all(t not in result['answer'] for t in ['乙城','34万','1.6亿','理论'])
    citation=result['citations'][0]
    assert citation['excerpt']=='甲城剧院项目，建筑面积约4万㎡，总投资1.6亿美元。'
    assert citation['location']['line_start']==3 and citation['parent_location']==before['citations'][0]['location']
    assert data==before


@pytest.mark.parametrize('unit,expected',[('平方米','约40000平方米'),('万平方米','约4万平方米')])
def test_area_unit_conversion_keeps_approximation(tmp_path,unit,expected):
    result=source_extract(source(tmp_path,'甲项目，建筑面积约4万㎡。'),'甲项目建筑面积是多少'+unit+'？')
    assert expected in result['answer']


@pytest.mark.parametrize('question',[
    '丙项目建筑面积是多少？','甲项目二期建筑面积是多少？','甲项目2025年建筑面积是多少？',
    '甲项目和乙项目建筑面积合计多少？','这个项目建筑面积是多少？','甲项目建筑面积不含地下是多少？',
    '甲项目建筑面积和用地面积分别多少？','甲项目建筑面积地下部分是多少？',
    '甲项目建筑面积增加多少？','甲项目建筑面积上限是多少？'])
def test_unknown_scope_or_arithmetic_never_borrows_another_case(tmp_path,question):
    result=source_extract(source(tmp_path,'案例1\n甲项目，建筑面积4万㎡。\n案例2\n乙项目，总建筑面积9万㎡。'),question)
    assert result['answer_status']=='EVIDENCE_INSUFFICIENT'
    assert not any(c['answer_usage']=='PRIMARY' for c in result['citations'])
    assert '4万' not in result['answer'] and '9万' not in result['answer']


def test_missing_units_and_conflicting_values_fail_closed(tmp_path):
    missing=source_extract(source(tmp_path,'甲项目，建筑面积40000。'),'甲项目建筑面积多少？')
    assert missing['answer_status']=='EVIDENCE_INSUFFICIENT'
    conflicting=source_extract(source(tmp_path,'甲项目，建筑面积4万㎡。\n甲项目，建筑面积5万㎡。'),'甲项目建筑面积多少？')
    assert conflicting['field_audit']['reason']=='CONFLICTING_PROJECT_FIELD_VALUES'


def test_site_area_is_not_building_area_and_parenthesis_condition_is_retained(tmp_path):
    text='甲项目，建筑面积约4万㎡（不含地下车库），用地面积8公顷。'
    result=source_extract(source(tmp_path,text),'甲项目建筑面积多少？')
    assert '约4万平方米（不含地下车库）' in result['answer'] and '8公顷' not in result['answer']
    site=source_extract(source(tmp_path,text),'甲项目用地面积多少？')
    assert site['answer_status']=='EVIDENCE_INSUFFICIENT' # Unbound exclusion cannot silently transfer across fields.


def test_explicit_phase_and_same_file_scope_are_not_invented(tmp_path):
    phase=source_extract(source(tmp_path,'甲项目，一期总建筑面积34万㎡。'),'甲项目一期建筑面积多少？')
    assert '一期总建筑面积34万平方米' in phase['answer']
    data=source(tmp_path,'建筑面积8万㎡。',name='EPC经验总结(甲项目).md')
    assert '建筑面积8万平方米' in source_extract(data,'甲项目建筑面积多少？')['answer']
    other=source(tmp_path,'乙项目建筑面积99万㎡。',name='EPC经验总结(甲项目).md')
    assert source_extract(other,'甲项目建筑面积多少？')['answer_status']=='EVIDENCE_INSUFFICIENT'


def test_stale_source_and_background_do_not_supply_a_field(tmp_path):
    data=source(tmp_path,'甲项目，建筑面积4万㎡。')
    from pathlib import Path
    Path(data['citations'][0]['source_path']).write_text('changed',encoding='utf-8')
    assert source_extract(data,'甲项目建筑面积多少？')['answer_status']=='EVIDENCE_INSUFFICIENT'
    data['citations'][0]['answer_usage']='BACKGROUND'
    assert source_extract(data,'甲项目建筑面积多少？')['answer_status']=='SOURCES_ONLY'


def test_local_phase_reference_is_not_a_different_project_and_its_scope_is_kept(tmp_path):
    text='甲住房项目，一期总建筑面积34万㎡，其中一期项目占地面积约100公顷。'
    data=source(tmp_path,text)
    assert '一期总建筑面积34万平方米' in source_extract(data,'甲住房项目建筑面积多少？')['answer']
    assert '一期占地面积约100公顷' in source_extract(data,'甲住房项目占地面积多少？')['answer']


def test_unhandled_project_numeric_field_is_not_presented_as_an_answer(tmp_path):
    result=source_extract(source(tmp_path,'甲项目，总投资2亿元。这里还有许多背景说明。'),'甲项目总投资是多少？')
    assert result['answer_status']=='FIELD_EXTRACTION_REQUIRED'
    assert '2亿元' not in result['answer'] and '这不表示原文没有该信息' in result['answer']
    assert all(c['answer_usage']=='BACKGROUND' for c in result['citations'])


def test_field_name_only_question_can_use_the_same_explicit_fact(tmp_path):
    result=source_extract(source(tmp_path,'甲项目，建筑面积约4万㎡。'),'甲项目建筑面积？')
    assert result['answer']=='甲项目，建筑面积约4万平方米。 [S1]'
