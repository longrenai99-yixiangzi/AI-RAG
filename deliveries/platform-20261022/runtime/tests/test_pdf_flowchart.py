from app.ingestion.pdf_flowchart import confirmed_arrows
from app.ingestion.flowchart_records import flowchart_records


def node(name,box):
    return {'node_id':name,'bbox':box}


def path(a=(10,5),b=(38,5),seq=1):
    return {'seqno':seq,'type':'s','width':1,'color':[0,0,0],'items':[('l',a,b)]}


def head():
    return {'seqno':2,'type':'f','fill':[0,0,0],
            'items':[('l',(38,4),(40,5)),('l',(40,5),(38,6)),('l',(38,6),(38,4))]}


NODES=[node('source',[0,0,10,10]),node('target',[40,0,50,10])]


def test_unique_arrow_accepts_line_ending_at_arrow_base():
    edges,held=confirmed_arrows(NODES,[path(),head()])
    assert not held and len(edges)==1
    assert (edges[0]['source_node_id'],edges[0]['target_node_id'])==('source','target')
    assert edges[0]['meaning']=='DRAWN_DIRECTION_ONLY_NOT_APPROVAL_OR_TIME_RULE'


def test_unique_arrow_accepts_line_ending_at_tip():
    edges,held=confirmed_arrows(NODES,[path(b=(40,5)),head()])
    assert len(edges)==1 and not held


def test_arrowhead_direction_must_agree_with_connector():
    edges,held=confirmed_arrows([node('source',[50,0,60,10]),NODES[1]],[path(a=(50,5)),head()])
    assert not edges and held[0]['reason']=='ENDPOINTS_NOT_UNIQUE'


def test_shared_bus_is_held_even_when_two_endpoints_are_unique():
    edges,held=confirmed_arrows(NODES,[path(),head(),path(a=(25,5),b=(25,20),seq=3)])
    assert not edges and held[0]['reason']=='POSSIBLE_SHARED_BUS_OR_JUNCTION'


def test_connector_cannot_cross_another_frame():
    edges,held=confirmed_arrows(NODES+[node('middle',[20,0,30,10])],[path(),head()])
    assert not edges and held[0]['reason']=='CONNECTOR_PASSES_OTHER_FRAME'


def test_multiple_frame_owners_are_not_resolved_by_guessing():
    edges,held=confirmed_arrows(NODES+[node('overlap',[40,0,50,10])],[path(),head()])
    assert not edges and held[0]['reason']=='ENDPOINTS_NOT_UNIQUE'


def test_disconnected_cycle_in_one_drawing_does_not_become_one_connector():
    draw=path();draw['items'] += [('l',(20,20),(25,20)),('l',(25,20),(22,25)),('l',(22,25),(20,20))]
    edges,held=confirmed_arrows(NODES,[draw,head()])
    assert not edges and held[0]['reason']=='ENDPOINTS_NOT_UNIQUE'


def test_colors_do_not_match_different_connectors():
    arrow=head();arrow['fill']=[1,0,0]
    edges,held=confirmed_arrows(NODES,[path(),arrow])
    assert not edges and held


def test_chart_origin_node_phase_and_output_column_remain_distinct():
    spec={'source_path':'manual.pdf','source_version':'V','page':69,'appendix':17,'caption':'附件17流程图',
          'chart_start':'方案设计阶段','phase_labels':['方案设计阶段','施工图设计阶段'],
          'lane_names':['项目设计管理负责人','输出成果'],'business_labels':['设计管理成果总结'],'caption_bbox':[0,0,100,20]}
    frame={'node_id':'A','bbox':[40,100,80,120],'kind':'OUTPUT','lane':'输出成果',
           'phase':'施工图设计阶段','business':'设计管理成果总结','text':'总结成果'}
    rows=flowchart_records([{'spec':spec,'nodes':[frame]}])
    assert len(rows)==2 and rows[1]['native_flow_node']['relations_complete'] is False
    assert '图的起点：方案设计阶段' in rows[1]['text'] and '节点所在阶段：施工图设计阶段' in rows[1]['text']
    assert '输出成果列：输出成果' in rows[1]['text'] and '角色泳道' not in rows[1]['text']
