import hashlib
from pathlib import Path

from app.retrieval.focused_candidate import FocusedCandidate
from app.retrieval.responsibility_scope import responsibility_action,responsibility_quotes
from app.trial.concise_extract import concise_text
from app.trial.assisted_chat import assemble
from test_focused_candidate import Titles,Reranker


def rows(tmp_path):
    path=tmp_path/'测试指南.pdf';path.write_bytes(b'fixture')
    base={'source_path':str(path),'source_version':hashlib.sha256(path.read_bytes()).hexdigest(),
          'document_id':'doc','file_name':path.name,'source_id':'SRC_test','heading_path':'Page 2','role':'DIRECT'}
    return [{**base,'evidence_id':'wrong','text':'查找标记：负责总结成果。'},
            {**base,'evidence_id':'right','text':'本指南由甲管理部组织编制，由乙管理部负责具体内容的解释。'}]


def test_named_source_can_recover_missing_literal_predicate_despite_higher_irrelevant_score(tmp_path):
    data=rows(tmp_path);data[1].pop('role');docs={'doc':data[0]}
    ranker=FocusedCandidate([],Titles(),Reranker(),documents=docs,records=data)
    result=ranker.rank('根据《测试指南.pdf》，由哪个部门负责解释？',[data[0]])
    assert result['candidate_evidence'][0]['evidence_id']=='right'
    assert result['candidate_evidence'][0]['answer_usage']=='PRIMARY'
    assert result['intent_audit']['responsibility_action']=='解释'
    assert result['intent_audit']['matching_statements']==1
    assert assemble(result)[0].items[0].chunk_id=='right'


def test_missing_or_conflicting_duties_cannot_become_a_direct_answer(tmp_path):
    data=rows(tmp_path);ranker=FocusedCandidate([],Titles(),Reranker(),documents={'doc':data[0]},records=data)
    result=ranker.rank('《测试指南.pdf》由哪个部门负责批准？',[data[0]])
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING'
    data.append({**data[1],'evidence_id':'conflict','text':'本指南由丙管理部负责具体内容的解释。'})
    ranker=FocusedCandidate([],Titles(),Reranker(),documents={'doc':data[0]},records=data)
    assert ranker.rank('《测试指南.pdf》由哪个部门负责解释？',[data[0]])['bundle_status']=='SOURCE_SCOPE_MISSING'


def test_repeated_unqualified_same_actor_is_consistent_but_conditions_stay_distinct(tmp_path):
    data=rows(tmp_path);data.append({**data[1],'evidence_id':'appendix','text':'6\n附则\n本指南由乙管理部负责解释。'})
    ranker=FocusedCandidate([],Titles(),Reranker(),documents={'doc':data[0]},records=data)
    result=ranker.rank('《测试指南.pdf》由哪个部门负责解释？',[data[0]])
    assert result['bundle_status']=='PRIMARY_SECTION_CANDIDATE' and result['intent_audit']['matching_statements']==1
    data[-1]['text']='仅试点阶段，本指南由乙管理部负责解释。'
    ranker=FocusedCandidate([],Titles(),Reranker(),documents={'doc':data[0]},records=data)
    assert ranker.rank('《测试指南.pdf》由哪个部门负责解释？',[data[0]])['bundle_status']=='SOURCE_SCOPE_MISSING'


def test_recovery_obeys_explicit_source_versions_and_other_sources(tmp_path):
    data=rows(tmp_path);ranker=FocusedCandidate([],Titles(),Reranker(),documents={'doc':data[0]},records=data)
    result=ranker.rank('《测试指南.pdf》由哪个部门负责解释？',[data[0]],allowed_versions=set())
    assert not result['candidate_evidence']
    other=Path(tmp_path/'另一指南.pdf');other.write_bytes(b'other')
    foreign={**data[1],'source_path':str(other),'source_version':hashlib.sha256(other.read_bytes()).hexdigest()}
    ranker=FocusedCandidate([],Titles(),Reranker(),documents={'doc':data[0]},records=[data[0],foreign])
    assert ranker.rank('《测试指南.pdf》由哪个部门负责解释？',[data[0]])['bundle_status']=='SOURCE_SCOPE_MISSING'


def test_literal_sentence_preserves_complete_duty_and_unverified_conditions():
    text='管理概述。\n本指南由甲管理部组织编制，由乙管理部负责具体内容的解释。'
    assert concise_text(text,'谁负责解释？')==(text.split('\n')[1],'EXPLICIT_RESPONSIBILITY_SENTENCE')
    dated='2024年编制本指南。\n'+text
    assert concise_text(dated,'谁负责解释？')==(text.split('\n')[1],'EXPLICIT_RESPONSIBILITY_SENTENCE')
    limited='本条仅适用于试点。\n'+text
    assert concise_text(limited,'谁负责解释？')[0]==limited
    assert not responsibility_quotes('解释','甲部门不负责具体内容的解释。')
    assert responsibility_action('设计评估有哪些作用？') is None
