import json
from pathlib import Path
import pytest
from app.retrieval.reviewed_flow_relations import direction_intent,load_index,relation_bundle,relation_answer
from app.retrieval.contract_context import paragraph_bundle,paragraph_answer,requested_subitems

ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))

@pytest.mark.parametrize('text,direction',[
 ('它的箭头来自哪些图框？','INCOMING'),('哪些角色的箭头连过来？','INCOMING'),('箭头是从哪里来的？','INCOMING'),
 ('箭头直接指向哪些图框？','OUTGOING'),('连线直接连到哪里？','OUTGOING'),('箭头接到哪儿？','OUTGOING'),
 ('哪些图框的箭头直接指向它？','INCOMING'),('有哪些图框连入，又连到哪些图框？','BOTH'),
 ('它接收哪些图框的箭头，并且箭头还指向哪些图框？','BOTH'),('有哪些箭头？','BOTH'),('这条连线怎么理解？','UNKNOWN'),
 ('从初步设计阶段开始，施工图阶段的图框箭头指向谁？','OUTGOING'),
])
def test_arrow_direction_is_not_default_outgoing_or_chart_start(text,direction):
    assert direction_intent(text)==direction






@pytest.mark.parametrize('q,expected',[
 ('第（1）项',[1]),('第一项',[1]),('第十五项',[15]),('第1项和第2项',[1,2]),
])
def test_chinese_and_arabic_subitem_numbers_are_consistent(q,expected):assert requested_subitems(q)==expected


def test_exact_raw_subitem_does_not_invoke_billable_model(tmp_path):
    from tests.test_daily_answers import daily
    service,flow,store,existing,policy,Provider,calls,now,prices,run=daily.__wrapped__(tmp_path)
    service.approve(service.policy_hash,'synthetic approval');old=list(prices)
    result=service.apply(run({'generation_mode':'REVIEWED_NATIVE_CLAUSE_NO_MODEL'}))
    assert result['result']['daily_model']['route']=='LOCAL_DIRECT' and calls==[] and prices==old




def test_runtime_reports_the_loaded_revision_not_a_later_edited_spec():
    from types import SimpleNamespace
    from app.trial.candidate_platform import CandidateKnowledge
    spec={'revision':'loaded-R14','fingerprint':'1'*64}
    candidate=SimpleNamespace(candidate_hash='0'*64,records=[],sources=lambda **_: {'total':0},
                              content_revision=spec['revision'],runtime_spec_sha256=spec['fingerprint'])
    existing=CandidateKnowledge(candidate)
    spec.update(revision='edited-but-not-loaded',fingerprint='2'*64)
    assert existing.status()['content_revision']=='loaded-R14'
    assert existing.status()['runtime_spec_sha256']=='1'*64
