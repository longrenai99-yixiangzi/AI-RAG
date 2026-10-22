import hashlib
from types import SimpleNamespace
import pytest
from app.retrieval.focused_candidate import FocusedCandidate
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
    def search(self,q):return []


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
