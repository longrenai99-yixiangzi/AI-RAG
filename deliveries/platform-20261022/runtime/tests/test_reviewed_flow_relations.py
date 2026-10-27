from copy import deepcopy
import json
from pathlib import Path
import pytest
from app.ingestion.pdf_flow_paths import direct_paths
from app.retrieval.reviewed_flow_relations import load_index,relation_bundle,relation_answer

def frame(name,box):return {'node_id':name,'bbox':box}
def path(seq,points,color=(0.,0.,0.),width=.18):return {'seqno':seq,'type':'s','width':width,'color':color,'items':[('l',a,b) for a,b in zip(points,points[1:])]}
def head(seq,tip,color=(0.,0.,0.)):
    x,y=tip;v=[(x-6,y-2),(x,y),(x-6,y+2)]
    return {'seqno':seq,'type':'f','fill':color,'items':[('l',v[a],v[b]) for a,b in [(0,1),(1,2),(2,0)]]}

def test_thin_native_path_and_duplicate_arrowheads():
    chart={'nodes':[frame('A',[0,0,20,20]),frame('B',[100,0,120,20])]}
    rows=direct_paths(chart,[path(1,[(20,10),(95,10)]),head(2,(100,10)),head(3,(100,10))])
    assert rows[0]['status']=='EXPLICIT_NATIVE_PATHS' and rows[0]['paths'][0]['source_node_id']=='A'
    assert rows[1]['status']=='DUPLICATE_NATIVE_HEAD' and rows[1]['duplicate_of']==2

def test_complete_multiple_inputs_share_one_arrowhead_without_inventing_role_order():
    chart={'nodes':[frame('A',[0,0,20,20]),frame('B',[0,40,20,60]),frame('C',[100,20,120,40])]}
    rows=direct_paths(chart,[path(1,[(20,10),(60,10),(60,30),(95,30)]),path(2,[(20,50),(60,50),(60,30),(95,30)]),head(3,(100,30))])
    assert {p['source_node_id'] for p in rows[0]['paths']}=={'A','B'}
    assert all(p['target_node_id']=='C' for p in rows[0]['paths'])

def test_color_mismatch_and_crossed_frame_are_not_admitted():
    chart={'nodes':[frame('A',[0,0,20,20]),frame('B',[100,0,120,20]),frame('X',[50,0,60,20])]}
    rows=direct_paths(chart,[path(1,[(20,10),(95,10)]),head(2,(100,10))])
    assert rows[0]['status']=='HELD' and rows[0]['blocked_paths']
    rows=direct_paths({'nodes':chart['nodes'][:2]},[path(1,[(20,10),(95,10)],color=(1.,0.,0.)),head(2,(100,10))])
    assert rows[0]['status']=='HELD'








@pytest.mark.parametrize('mode',['NATIVE_FLOW_RELATION_NO_MODEL','SOURCE_BOUND_SPAN_NO_MODEL'])
def test_direct_local_answers_do_not_spend_model_budget(tmp_path,mode):
    from tests.test_daily_answers import daily
    value=daily.__wrapped__(tmp_path)
    service,flow,store,existing,policy,Provider,calls,now,prices,run=value
    service.approve(service.policy_hash,'synthetic approval')
    prior=list(prices);result=service.apply(run({'generation_mode':mode}))
    assert result['result']['daily_model']['route']=='LOCAL_DIRECT'
    assert calls==[] and prices==prior and not store._read()['daily_answer_policy']['reservations']
