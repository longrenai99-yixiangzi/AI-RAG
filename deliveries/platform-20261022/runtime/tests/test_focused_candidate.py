import hashlib
from types import SimpleNamespace
import pytest
from app.retrieval.focused_candidate import FocusedCandidate,explicit_topic_coverage
from app.trial.assisted_chat import assemble


class Tokenizer:
    def __call__(self,text,**_):return {'offset_mapping':[(i,i+1) for i in range(len(text))]}
    def encode(self,text,**_):return list(text)
    def num_special_tokens_to_add(self,**_):return 4


class Reranker:
    max_length=1024
    def __init__(self):self.model=SimpleNamespace(tokenizer=Tokenizer());self.calls=[]
    def load(self):pass
    def score(self,q,parts):self.calls.append((q,parts));return [5 if '查找标记' in p else 1 for p in parts]


class Titles:
    def search(self,q,*,allowed_versions=None):return []


def records(tmp_path):
    rows=[]
    for i,text in enumerate(['无关背景。','正文。'*450+'查找标记：完整要求。']):
        p=tmp_path/f'{i}.md';p.write_text(text,encoding='utf-8')
        rows.append({'evidence_id':str(i),'document_id':str(i),'source_path':str(p),'source_version':hashlib.sha256(p.read_bytes()).hexdigest(),'heading_path':'管理要求','text':text,'role':'DIRECT'})
    return rows


def test_bounded_probe_retains_full_primary_and_excludes_background_from_generation(tmp_path):
    rows=records(tmp_path);provider=Reranker();candidate=FocusedCandidate([],Titles(),provider)
    result=candidate.rank('查找标记是什么？',rows)
    primary=result['candidate_evidence'][0]
    assert primary['evidence_id']=='1' and primary['text']==rows[1]['text']
    assert '查找标记' in primary['ranking_probe']['text']
    assert primary['ranking_probe']['probe_pair_tokens']<=1024 and primary['ranking_probe']['not_complete_coverage']
    model,cards=assemble(result,'查找标记是什么？')
    assert len(model.items)==1 and rows[1]['text']==model.items[0].excerpt and len(cards)==1
    _,all_cards=assemble(result,'查找标记是什么？',include_background=True)
    assert len(all_cards)==2 and {c['answer_usage'] for c in all_cards}=={'PRIMARY','BACKGROUND'}


def test_cache_requires_exact_question_text_source_version_and_full_evidence(tmp_path):
    rows=records(tmp_path);p=Reranker();candidate=FocusedCandidate([],Titles(),p)
    candidate.rank('查找标记是什么？',rows);candidate.rank('查找标记是什么？',rows)
    assert len(p.calls)==1 and candidate.stats['cache_hits']==2
    changed=[dict(r) for r in rows];changed[1]['source_version']='b'*64
    candidate.rank('查找标记是什么？',changed)
    assert len(p.calls)==2 and len(p.calls[-1][1])==1
    candidate.rank('查找标记是否适用于今年？',changed)
    assert len(p.calls)==3


def test_broad_coverage_does_not_become_an_approved_single_unit_answer(tmp_path):
    result=FocusedCandidate([],Titles(),Reranker()).rank('请综合汇总全部资料的全流程要求',records(tmp_path))
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert not assemble(result)[0].items


def test_invalid_local_scores_fail_explicitly(tmp_path):
    provider=Reranker();provider.score=lambda q,p:[float('nan')]*len(p)
    with pytest.raises(ValueError,match='Invalid reranker'):FocusedCandidate([],Titles(),provider).rank('查找标记是什么？',records(tmp_path))


@pytest.mark.parametrize('question',[
    '2025年查找标记的完整要求是什么？',
    '今年查找标记的完整要求是什么？',
    '去年查找标记的完整要求是什么？',
    '查找标记与其他制度有什么区别？',
    '查找标记的完整要求发生了哪些变化？',
])
def test_unverified_time_and_comparison_do_not_become_single_primary(tmp_path,question):
    result=FocusedCandidate([],Titles(),Reranker()).rank(question,records(tmp_path))
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert not assemble(result)[0].items and result['selection_notes']


def test_simple_enumeration_and_phase_names_do_not_imply_global_aggregation(tmp_path):
    candidate=FocusedCandidate([],Titles(),Reranker())
    for question in ['设计评估有几个方面？','设计提资包括哪些内容？','方案阶段管控什么？']:
        assert candidate.rank(question,records(tmp_path))['bundle_status']=='PRIMARY_SECTION_CANDIDATE'


def test_named_scope_filters_before_reranking_and_strips_selector_only_for_scoring(tmp_path):
    rows=records(tmp_path);docs={r['document_id']:{**r,'file_name':f'{i}.md'} for i,r in enumerate(rows)}
    provider=Reranker();candidate=FocusedCandidate([],Titles(),provider,documents=docs)
    assert not candidate.rank('《0.md》中，查找标记是什么？',[rows[1]])['candidate_evidence']
    assert provider.calls==[]
    result=candidate.rank('《1.md》中，查找标记是什么？',rows+[dict(rows[1],evidence_id='duplicate')])
    assert len(result['candidate_evidence'])==1
    assert provider.calls[0][0]=='查找标记是什么？'
    assert result['candidate_evidence'][0]['source_path']==rows[1]['source_path']


def test_multiple_named_files_never_collapse_into_one_primary_answer(tmp_path):
    rows=records(tmp_path);docs={r['document_id']:{**r,'file_name':f'{i}.md'} for i,r in enumerate(rows)}
    result=FocusedCandidate([],Titles(),Reranker(),documents=docs).rank('《0.md》和《1.md》的要求有什么区别？',rows)
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert len(result['candidate_evidence'])==2
    assert not assemble(result)[0].items


@pytest.mark.parametrize('question,ready',[
    ('查找标记是什么？完整要求是什么？',True),
    ('查找标记是什么？？完整要求是什么？',True),
    ('查找标记是什么？合同金额多少万元？',False),
    ('查找标记是什么？为什么有完整要求？',False),
    ('查找标记是什么？什么？',False),
])
def test_compound_lookup_requires_each_topic_in_the_same_primary_unit(tmp_path,question,ready):
    result=FocusedCandidate([],Titles(),Reranker()).rank(question,records(tmp_path))
    assert bool(assemble(result)[0].items)==ready
    assert result['coverage_audit']['status']==('SINGLE_UNIT_ANCHORS_MATCHED' if ready else 'COMPOUND_COVERAGE_UNVERIFIED')
    assert all(c['matched'] for c in result['coverage_audit']['units'])==ready


@pytest.mark.parametrize('question,text,heading,status',[
    ('幕墙接口应关注哪些内容？','室内接口需要复核。','精装接口','TOPIC_NOT_FOUND'),
    ('幕墙接口应关注哪些内容？','玻璃幕墙、接口转接分别列项。','构件清单','TOPIC_NOT_FOUND'),
    ('幕墙接口应关注哪些内容？','核对锚固条件。','幕墙接口','TOPIC_PRESENT'),
    ('设计管理成果复核应关注哪些内容？','成果复核包括图纸完整性。','质量管理','TOPIC_PRESENT'),
    ('设计供方评价应重点关注哪些方面？','合同中约定对设计方的评价机制。','资源管理','TOPIC_PRESENT'),
    ('平衡阀是什么？','调节流量。','阀门','NOT_EXPLICIT_TOPIC'),
    ('管理应该如何开展？','记录责任分工。','通用工作','NOT_EXPLICIT_TOPIC'),
])
def test_explicit_topic_is_a_necessary_check_not_a_question_answer_registry(question,text,heading,status):
    assert explicit_topic_coverage(question,{'text':text,'heading_path':heading})['status']==status


def test_irrelevant_top_score_cannot_hide_a_matching_lower_candidate_or_become_primary(tmp_path):
    rows=records(tmp_path)
    rows[0].update(text='幕墙接口应核对锚固条件。',heading_path='幕墙接口')
    rows[1].update(text='查找标记：室内接口要求。',heading_path='室内接口')
    provider=FocusedCandidate([],Titles(),Reranker())
    result=provider.rank('幕墙接口应关注哪些内容？',rows)
    assert result['candidate_evidence'][0]['evidence_id']=='0'
    assert result['candidate_evidence'][0]['answer_usage']=='PRIMARY'
    missing=provider.rank('外墙防水实施前应完成哪些确认？',rows)
    assert missing['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert all(c['answer_usage']=='BACKGROUND' for c in missing['candidate_evidence'])
    assert missing['topic_coverage']['status']=='TOPIC_NOT_FOUND'


@pytest.mark.parametrize('heading,text,ready',[
    ('综合策划','综合策划包括采购界面策划、交付节点。',False),
    ('资料提交','先做好采购界面策划，划分各方工作范围。随后编制提交计划。',False),
    ('采购界面策划','按专业划分工作范围并明确责任。',True),
    ('通用说明','采购界面策划包括专业范围、责任分工和节点。',True),
    ('通用说明','采购界面策划的主要内容：专业范围、责任分工和节点。',True),
])
def test_content_list_requires_topic_section_or_explicit_statement(tmp_path,heading,text,ready):
    rows=records(tmp_path)[:1];rows[0].update(heading_path=heading,text=text)
    result=FocusedCandidate([],Titles(),Reranker()).rank('采购界面策划需要明确哪些内容？',rows)
    assert any(r['answer_usage']=='PRIMARY' for r in result['candidate_evidence'])==ready
    if not ready:assert result['topic_coverage']['status']=='RELATED_MENTION_ONLY'
