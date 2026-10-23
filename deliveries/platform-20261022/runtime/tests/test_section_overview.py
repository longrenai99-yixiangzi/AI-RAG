import hashlib
import json

import pytest

from app.retrieval.section_overview import comparison_required, collect_overview
from app.retrieval.focused_candidate import FocusedCandidate
from app.trial.assisted_chat import assemble
from test_focused_candidate import Reranker, Titles
from test_grounded_concise import render, response


@pytest.mark.parametrize('question,blocked',[
    ('方案比选需要比较哪些方面，最优方案应兼顾什么？',False),
    ('设计方案的对比标准是什么？',False),
    ('甲乙方案应该如何比较？',True),
    ('甲方案与乙方案比较哪些方面？',True),
    ('方案比选和限额设计有什么区别？',True),
    ('比较哪些方面？甲乙项目有什么差异？',True),
    ('方案比选指标是什么，与去年的指标有何区别？',True),
])
def test_method_lookup_is_distinct_from_actual_comparison(question,blocked):
    assert comparison_required(question)==blocked


def chapter(tmp_path):
    path=tmp_path/'EPC设计管理经验总结(演示训练馆).docx';path.write_bytes(b'demo')
    base={'document_id':'D','source_id':'S','source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),'role':'DIRECT'}
    rows=[{**base,'evidence_id':str(i),'heading_path':'第三章 管理情况 > 3.8设计质量管理 > '+heading,'text':text,'location':{'section':heading}}
          for i,(heading,text) in enumerate([('3.8.1 接口提资','项目部梳理接口清单。'),('3.8.2 成果审查','项目部组织图纸审查。'),('3.8.3 认质认样','项目部提前开展认质认样。')])]
    return rows


def test_existing_siblings_are_collected_in_source_order_with_separate_citations(tmp_path):
    rows=chapter(tmp_path);rows.append({**rows[-1],'evidence_id':'T','table_id':'table','text':'样板 | 1'})
    other={**rows[0],'evidence_id':'old','source_version':'a'*64,'text':'旧版内容'}
    provider=FocusedCandidate([],Titles(),Reranker(),records=rows+[other])
    result=provider.rank('演示训练馆项目在设计质量管控方面采取了哪些措施？',[rows[2]])
    _,cards=assemble(result,include_background=True)
    assert [c['evidence_id'] for c in cards]==['0','1','2']
    assert all(c['answer_usage']=='PRIMARY' for c in cards)
    assert result['chapter_coverage']['table_rows_not_selected']==1
    assert len({c['display_location'] for c in cards})==3


@pytest.mark.parametrize('question',[
    '设计质量管控全部清单有哪些？','设计质量管控共多少人？',
    '2025年设计质量管理采取什么措施？',
])
def test_parent_aggregation_never_bypasses_count_exhaustiveness_or_year(tmp_path,question):
    rows=chapter(tmp_path)
    selected,audit=collect_overview(question,rows[2],rows)
    assert not selected and audit['status']=='PARENT_COVERAGE_UNVERIFIED'


def test_leaf_question_does_not_collect_siblings_and_missing_or_large_children_fail_closed(tmp_path):
    rows=chapter(tmp_path)
    assert collect_overview('认质认样采取哪些措施？',rows[2],rows)[1]['status']=='NOT_PARENT_OVERVIEW'
    for changed in [rows[:2]+[{**rows[2],'table_id':'only-table'}],rows[:2]+[{**rows[2],'text':'长'*6001}]]:
        selected,audit=collect_overview('设计质量管控采取哪些措施？',rows[2],changed)
        assert not selected and audit['status']=='PARENT_COVERAGE_UNVERIFIED'


def test_model_must_cover_each_aggregated_child_and_preserve_table_limit(tmp_path):
    rows=chapter(tmp_path)
    selected,_=collect_overview('设计质量管控采取哪些措施？',rows[2],rows)
    _,cards=assemble({'candidate_evidence':selected})
    for c in cards:c['chapter_coverage']['table_rows_not_selected']=2
    question='演示训练馆项目在设计质量管控方面采取了哪些措施？'
    claims=[{'text':c['excerpt'],'evidence_ids':[f'U{i}'],'support_quotes':[c['excerpt']]} for i,c in enumerate(cards,1)]
    with pytest.raises(ValueError,match='遗漏'):
        render({'status':'ANSWERED','claims':claims[:1],'gaps':[]},cards,question)
    result=render({'status':'ANSWERED','claims':claims,'gaps':[]},cards,question)
    assert len(result['claims'])==3 and '附表明细未逐行核对' in result['answer']
    foreign=[{**cards[0],'excerpt':'其他训练馆项目，项目部梳理接口清单。'}]
    with pytest.raises(ValueError,match='项目'):
        render(response(foreign[0]['excerpt']),foreign,question)
