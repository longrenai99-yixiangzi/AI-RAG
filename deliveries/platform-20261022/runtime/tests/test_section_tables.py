import copy
import hashlib
import json

import pytest

from app.retrieval.section_tables import associate_section,parallel_facets,table_row,facet_gaps
from app.retrieval.focused_candidate import FocusedCandidate
from app.trial.assisted_chat import assemble
from app.trial.platform_existing import source_extract
from app.trial.platform_generation import selection_packet
from app.answer_engine.llm.grounded_concise import render_concise
from tests.test_focused_candidate import Reranker,Titles


def rows(tmp_path):
    path=tmp_path/'EPC设计管理经验总结(演示项目).docx';path.write_bytes(b'synthetic')
    base={'source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),'source_id':'SRC_demo','document_id':'D',
          'file_name':path.name,'heading_path':'第三章 > 3.3沟通机制','role':'DIRECT','location':{'section':'第三章 > 3.3沟通机制'}}
    intro={**base,'evidence_id':'intro','text':'已建立文件收发等制度，具体情况如下：\n具体图纸流程如下：'}
    row={**base,'evidence_id':'row','table_id':'T','text':'表名：原件第2表\n表头：序号 | 沟通形式 | 具体内容 | 处理要求\n行：1 | 文件收发 | 纸质文件登记，紧急情况可先发送电子件 | 电子件不得作为验收依据，须补交纸件。'}
    header={**row,'evidence_id':'header','text':'表名：原件第2表\n表头：序号 | 沟通形式 | 具体内容 | 处理要求\n行：序号 | 沟通形式 | 具体内容 | 处理要求'}
    unrelated={**row,'evidence_id':'other','text':'表头：序号 | 沟通形式 | 具体内容\n行：2 | 设计例会 | 记录会议事项。'}
    return intro,row,header,unrelated


def rank(tmp_path,question='文档的收发及版本管理有哪些要求？',extra=()):
    intro,row,header,other=rows(tmp_path)
    provider=FocusedCandidate([],Titles(),Reranker(),records=[intro,row,header,other,*extra])
    result=provider.rank(question,[intro]);_,cards=assemble(result,question,include_background=True)
    return result,cards,row


def test_intro_links_real_row_with_readable_locator_preserves_columns_and_marks_missing_aspect(tmp_path):
    question='演示项目的文档的收发及版本管理有哪些要求？';result,cards,row=rank(tmp_path,question)
    assert cards[0]['evidence_id']=='row' and cards[0]['answer_usage']=='PRIMARY'
    assert cards[1]['evidence_id']=='intro' and cards[1]['answer_usage']=='BACKGROUND'
    assert '原件第2表' in cards[0]['display_location'] and '沟通形式=文件收发' in cards[0]['display_location']
    assert cards[0]['table_evidence']['values'][2].startswith('纸质文件登记')
    assert result['table_association_audit']['linked_rows']==1
    assert result['table_association_audit']['rejected_header_or_invalid_rows']==1
    assert [p['status'] for p in result['facet_coverage']['facets']]==['TOPIC_LOCATED','NOT_LOCATED']
    extracted=source_extract({'answer_status':'SOURCES_ONLY','citations':cards},question)
    assert extracted['answer_completeness']=='PARTIAL' and '版本管理' in extracted['coverage_gaps'][0]
    assert '演示项目' in extracted['answer'] and '不作为其他项目' in extracted['answer'] and '电子件不得作为验收依据' in extracted['answer']


@pytest.mark.parametrize('change',['path','version','section','stage'])
def test_never_links_foreign_source_old_version_other_section_or_conflicting_scope(tmp_path,change):
    intro,row,_,_=rows(tmp_path)
    if change=='path':row['source_path']=str(tmp_path/'foreign.docx')
    if change=='version':row['source_version']='a'*64
    if change=='section':row['heading_path']='第四章 > 4.1其他内容'
    if change=='stage':row['scope']={'design_stage':'MISMATCH'}
    selected,audit,_=associate_section('文件收发有哪些要求？',intro,[intro],[row])
    assert selected==[] and audit['linked_rows']==0


def test_header_only_intro_only_and_oversized_rows_do_not_become_an_answer(tmp_path):
    intro,row,header,_=rows(tmp_path)
    for candidates in [[header],[],[{**row,'text':row['text']+'长'*801}]]:
        selected,_,_=associate_section('文件收发有哪些要求？',intro,[intro],candidates)
        assert selected==[]
    assert table_row(header['text']) is None
    selected,_,_=associate_section('沟通要求有哪些内容？',header,[header],[header])
    assert selected==[]


@pytest.mark.parametrize('q',[
    '装饰事业部和安装事业部共多少专职人员？','材料金额和设备金额合计是多少？',
    '甲方案与乙方案有什么区别？','文件收发是什么？为什么要版本管理？',
])
def test_parallel_lookup_does_not_relax_count_comparison_or_reasoning(q):
    assert parallel_facets(q)==[]


def model_answer(cards,question,quotes=None):
    _,units=selection_packet(question,cards)
    claims=[{'text':'文件收发可按原表执行。','evidence_ids':[u['unit_id']],
             'support_quotes':[(quotes or {}).get(u['unit_id'],u['text'])]} for u in units]
    return render_concise(json.dumps({'status':'ANSWERED','claims':claims,'gaps':[]},ensure_ascii=False),units,cards,question)


def test_model_cannot_claim_complete_or_hide_row_conditions_when_one_aspect_is_missing(tmp_path):
    q='文档的收发及版本管理有哪些要求？';_,cards,_=rank(tmp_path,q)
    result=model_answer(cards,q)
    assert result['answer_completeness']=='PARTIAL' and result['model_gaps']==[] and result['coverage_gaps']
    assert result['claims'][0]['check']=='TABLE_ROW_FIELDS_RESTORED'
    assert '须补交纸件' in result['answer'] and '项目复盘' in result['answer']
    with pytest.raises(ValueError,match='完整业务行'):
        model_answer(cards,q,{'U1':'电子件不得作为验收依据，须补交纸件。'})
    wrong=copy.deepcopy(cards);wrong[0]['table_evidence']['values'][-1]='不需补纸件'
    with pytest.raises(ValueError,match='绑定表头'):
        model_answer(wrong,q)


def test_all_located_aspects_still_check_which_evidence_the_model_used(tmp_path):
    intro,row,_,_=rows(tmp_path)
    version={**row,'evidence_id':'version','text':'表头：序号 | 管理事项 | 具体要求\n行：2 | 版本管理 | 新版发放时登记，旧版标注失效。'}
    q='文档的收发及版本管理有哪些要求？'
    result=FocusedCandidate([],Titles(),Reranker(),records=[intro,row,version]).rank(q,[intro])
    _,cards=assemble(result,q)
    assert len(cards)==2 and result['facet_coverage']['status']=='TOPICS_LOCATED_NOT_SEMANTICALLY_VERIFIED'
    full=model_answer(cards,q);assert full['coverage_gaps']==[]
    _,units=selection_packet(q,cards)
    response={'status':'ANSWERED','claims':[{'text':'按原表收发。','evidence_ids':['U1'],'support_quotes':[units[0]['text']]}],'gaps':[]}
    partial=render_concise(json.dumps(response,ensure_ascii=False),units,cards,q)
    assert partial['answer_completeness']=='PARTIAL' and '版本管理' in partial['coverage_gaps'][0]


def test_coverage_metadata_must_belong_to_current_question(tmp_path):
    q='文档的收发及版本管理有哪些要求？';_,cards,_=rank(tmp_path,q)
    cards[0]['facet_coverage']['question_sha256']='a'*64
    with pytest.raises(ValueError,match='与本题不一致'):model_answer(cards,q)


def test_recalled_duplicate_header_and_unknown_cells_do_not_cover_missing_topic(tmp_path):
    intro,row,header,_=rows(tmp_path)
    fake={**header,'text':'表头：序号 | 版本管理\n行：序号 | 版本管理'}
    missing={**row,'text':'表头：序号 | 管理事项 | 要求\n行：2 | 版本管理 | 待补充'}
    provider=FocusedCandidate([],Titles(),Reranker(),records=[intro,row,fake,missing])
    result=provider.rank('文档的收发及版本管理需要明确哪些内容？',[intro,fake,missing])
    assert result['facet_coverage']['status']=='PARTIAL'
    assert result['facet_coverage']['facets'][1]['status']=='NOT_LOCATED'
    assert [r['evidence_id'] for r in result['candidate_evidence'] if r['answer_usage']=='PRIMARY']==['row']


def test_explicit_two_questions_and_excessive_facets_are_not_silently_collapsed(tmp_path):
    intro,row,_,_=rows(tmp_path)
    provider=FocusedCandidate([],Titles(),Reranker(),records=[intro,row])
    result=provider.rank('文件收发有哪些要求？版本管理有哪些要求？',[intro])
    assert result['facet_coverage']['status']=='PARTIAL'
    result=provider.rank('文件收发、版本管理、图纸会审、设计交底、材料报审、设计策划、方案比选、设计评估、质量审查有哪些要求？',[intro])
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING' and result['table_association_audit']['status']=='TOO_MANY_FACETS'


@pytest.mark.parametrize('question',[
    '管理平台承担什么职责，重点把控哪些方面？',
    '资料审查有哪些步骤，需要保留哪些记录？',
])
def test_predicate_only_ellipsis_is_not_an_independent_topic(question):
    assert parallel_facets(question)==[]


def test_subject_with_elliptical_predicate_keeps_matching_section(tmp_path):
    intro,_,_,_=rows(tmp_path)
    candidate={**intro,'text':'管理平台负责资源支持，重点保障质量、进度和风险控制。','heading_path':'平台管理职责'}
    provider=FocusedCandidate([],Titles(),Reranker(),records=[candidate])
    result=provider.rank('管理平台承担什么职责，重点把控哪些方面？',[candidate])
    assert result['candidate_evidence'][0]['answer_usage']=='PRIMARY' and not result['facet_coverage']
