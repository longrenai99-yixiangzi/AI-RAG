import hashlib
from copy import deepcopy

import pytest

from app.trial.concise_extract import concise_text, readable_citations
from app.trial.platform_existing import source_extract


def test_parallel_items_keep_every_item_and_protected_qualifications():
    text='本规则仅适用于试点项目。\n第一，是明确边界。这里是详细解释。第二，是控制成本。暂估费用50万元，最终以审核为准。第三，是风险控制。一般说明。'
    summary,method=concise_text(text,'管理目的是什么？')
    assert method=='COMPLETE_PARALLEL_ITEMS'
    assert all(s in summary for s in ['第一','第二','第三','仅适用于试点项目','暂估费用50万元，最终以审核为准'])
    assert '这里是详细解释' not in summary


def test_actor_selection_excludes_other_duties_but_keeps_trailing_exception():
    text='一线层级：负责日常施工。\n中台层级：负责提供支持。\n但特殊设备不适用本条，须另行核实。'
    summary,method=concise_text(text,'中台层级承担什么职责？')
    assert method=='EXPLICIT_ACTOR_BLOCK'
    assert '一线层级' not in summary and '负责提供支持' in summary and '不适用' in summary


def test_overview_can_drop_examples_but_not_a_child_restriction():
    text='提资包括主体、专项、施工三个界面。\n（1）主体\n举例说明。\n（2）专项\n举例说明。\n（3）施工\n举例说明。'
    summary,method=concise_text(text,'提资包括哪些界面？')
    assert method=='COMPLETE_LIST_OVERVIEW' and summary=='提资包括主体、专项、施工三个界面。'
    # Use an explicit supported qualifier; ambiguous structures retain their full source.
    restricted=text+'\n仅改造项目适用第三类界面。'
    assert concise_text(restricted,'包括哪些界面？')==(restricted,'FULL_SOURCE_FALLBACK')
    with_example=text+'\n这个示例节约工期40天。'
    assert concise_text(with_example,'包括哪些界面？')[1]=='COMPLETE_LIST_OVERVIEW'
    assert concise_text(with_example,'初设阶段包括哪些界面？')==(with_example,'FULL_SOURCE_FALLBACK')


@pytest.mark.parametrize('target,expected',[
    ('DESIGN_STAGE_POSITION','阶段：专项阶段；岗位：检测部门；人员配置数量：4；专职/兼职：兼职。'),
    ('','表头：序号 | 阶段 | 岗位 | 人员配置数量 | 专职/兼职\n行：2 | 专项阶段 | 检测部门 | 4 | 兼职')])
def test_table_formatting_never_invents_zero_or_sums(target,expected):
    text='表头：序号 | 阶段 | 岗位 | 人员配置数量 | 专职/兼职\n行：2 | 专项阶段 | 检测部门 | 4 | 兼职'
    assert concise_text(text,'检测部门配置多少人？',target)[0]==expected
    multiple=text+'\n行：3 | 专项阶段 | 另一部门 | 5 | 专职'
    assert concise_text(multiple,'两部门合计多少人？',target)[0]==multiple


def test_role_count_keeps_duty_and_does_not_drop_an_exception():
    text='本项目配置协调经理2人，负责统筹设计接口，各专业分别落实。'
    assert concise_text(text,'协调经理几人？','LEAD_ROLE')[0]=='本项目配置协调经理2人，负责统筹设计接口。'
    qualified='本项目配置协调经理2人，但仅1人常驻现场。'
    assert concise_text(qualified,'协调经理几人？','LEAD_ROLE')[0]==qualified


def test_unknown_or_incomplete_structure_has_no_hard_character_cutoff():
    text='条文说明：'+('完整段落。'*300)+'仅2025年度试用，其他年度不适用。'
    assert concise_text(text,'有哪些要求？')[0]==text


def test_unique_letter_labelled_block_keeps_its_conditions_and_full_citation():
    first='（c) 专家评审\n在施工前由总承包单位组织专家，审查通过后才能实施。'
    selected='（d） 专题协调会\n根据实际情况，专题会议可由任意一方组织，但紧急事项须在3天内核实。'
    text=first+'\n'+selected
    excerpt,method=concise_text(text,'专题会议针对什么情况，可由哪些单位组织？')
    assert (excerpt,method)==(selected,'EXPLICIT_SIBLING_BLOCK')
    card={'citation_id':'S1','answer_usage':'PRIMARY','excerpt':text}
    result=source_extract({'answer_status':'SOURCES_ONLY','citations':[card]},'专题会议针对什么情况，可由哪些单位组织？')
    assert '专家评审' not in result['answer'] and '3天内' in result['answer'] and result['citations'][0]['excerpt']==text


@pytest.mark.parametrize('question,prefix,suffix',[
    ('专家评审和专题会议有哪些要求？','',''),
    ('会议有哪些要求？','',''),
    ('专题会议需要多少人？','',''),
    ('2025年专题会议有哪些要求？','',''),
    ('专题会议有哪些要求？','本规定仅适用于改造项目。\n',''),
    ('专题会议有哪些要求？','','\n但上述条款仅适用于改造项目。'),
])
def test_sibling_selection_does_not_drop_global_scope_or_choose_ambiguous_topic(question,prefix,suffix):
    text=prefix+'（c） 专家评审\n组织专家评审。\n（d） 专题会议\n安排专题会议。'+suffix
    assert concise_text(text,question)==(text,'FULL_SOURCE_FALLBACK')


def test_numbered_peer_item_is_complete_and_mixed_or_skipped_labels_stay_unmodified():
    first='1、选择设计院时，不应只看设计费，还需考察团队和概算编制能力；'
    second='2、限额设计指标需结合实际情况，不是一定要达到，可能增加后期维修费用；'
    text=first+'\n'+second
    assert concise_text(text,'依据《演示资料09.pptx》，选择设计院时考察哪些因素？')==(first,'EXPLICIT_SIBLING_BLOCK')
    assert concise_text(text,'限额设计指标是否一定要达到？')==(second,'EXPLICIT_SIBLING_BLOCK')
    for malformed in [text.replace('2、','3、'),text.replace('2、','（b） ')]:
        assert concise_text(malformed,'选择设计院时考察哪些因素？')==(malformed,'FULL_SOURCE_FALLBACK')


def test_shared_generic_words_do_not_replace_the_requested_subject():
    text='（a） 质量管理\n质量部门的主要工作是质量复核。\n（b） 专题会议\n专题会议按需召开。'
    assert concise_text(text,'成本部门的主要工作是什么？')==(text,'FULL_SOURCE_FALLBACK')


def test_source_extract_keeps_full_citations_and_never_summarizes_background():
    primary={'citation_id':'S1','excerpt':'第一，是建立边界。详细解释。第二，是控制风险。详细解释。','answer_usage':'PRIMARY'}
    background={'citation_id':'S2','excerpt':'背景金额100万元。','answer_usage':'BACKGROUND'}
    value={'answer_status':'SOURCES_ONLY','citations':[primary,background]};before=deepcopy(value)
    result=source_extract(value,'作用有哪些？')
    assert '背景金额' not in result['answer'] and result['citations']==value['citations'] and value==before
    assert result['generation_mode']=='LOCAL_EXTRACTIVE_SUMMARY_NO_MODEL'
    refused=source_extract({'answer_status':'EVIDENCE_INSUFFICIENT','answer':'证据不足','citations':[background]})
    assert refused['answer_status']=='EVIDENCE_INSUFFICIENT' and refused['answer']=='证据不足'


def test_scalar_answer_and_qualifier_are_never_rewritten():
    value={'answer_status':'SOURCE_EXTRACT_DRAFT','answer':'工程造价暂估123456.789万元。[S1]','generation_mode':'VERIFIED_SCALAR_NO_MODEL','citations':[]}
    assert source_extract(value)==value


@pytest.mark.parametrize('prefix,suffix',[('source_path: D:/原讲稿.docx\n','（转换稿）'),('','（Markdown）')])
def test_display_title_is_version_checked_and_leaves_source_identity_unchanged(tmp_path,prefix,suffix):
    path=tmp_path/'abcdefabcdefabcd.md';path.write_text(prefix+'# 可识别讲稿名称\n原文。',encoding='utf-8')
    card={'file_name':path.name,'source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest()}
    result=readable_citations([card])[0]
    assert result['display_file_name']=='可识别讲稿名称'+suffix and result['file_name']==path.name
    path.write_text('# 已改变来源',encoding='utf-8')
    assert 'display_file_name' not in readable_citations([card])[0]
