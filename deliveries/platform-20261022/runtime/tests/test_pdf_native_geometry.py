import pytest
from app.ingestion.pdf_native_geometry import character_layer,cell_text,reconstruct_table,join_continuation,outline_anchors


def raw_span(text,alpha=255,direction=(1,0)):
    chars=[{'c':c,'bbox':[i,0,i+1,2],'origin':[i,1]} for i,c in enumerate(text)]
    return {'blocks':[{'type':0,'lines':[{'dir':direction,'spans':[{'font':'F','size':16,'alpha':alpha,'bbox':[0,0,len(text),2],'chars':chars}]}]}]}


def test_version_bound_exclusion_does_not_remove_opaque_business_text():
    profile={'source_version':'V','font':'F','size':16,'alpha':51,'direction':[.7071,-.7071]}
    kept,excluded=character_layer(raw_span('水印',51,(.7071,-.7071)),'V',profile)
    assert not kept and excluded[0]['text']=='水印'
    kept,excluded=character_layer(raw_span('原文',255),'V',profile)
    assert ''.join(c['text'] for c in kept)=='原文' and not excluded
    with pytest.raises(ValueError):character_layer(raw_span('原文'),'OTHER',profile)


def test_unprofiled_rotated_text_is_preserved_and_requires_review():
    chars,_=character_layer(raw_span('竖表',255,(0,1)),'V')
    assert len(chars)==2
    with pytest.raises(ValueError):cell_text(chars,[0,0,3,3])


def test_blank_cells_are_not_filled_but_native_merged_owners_are_linked():
    chars,_=character_layer(raw_span('甲'),'V')
    table=reconstruct_table(chars,[[[0,0,1,4],[1,0,2,2]],[None,[1,2,2,4]]],1,1,'V')
    assert table['matrix']==[['甲',''],['甲','']]
    assert table['cells'][2]['merged_inheritance'] and table['cells'][2]['owner_row']==1


def test_continuation_preserves_exception_and_rejects_wrong_version_or_columns():
    left={'page':5,'table':2,'source_version':'V','matrix':[['序号','范围'],['4','施工配合，']],'column_boundaries':[0,1,2],'cells':[]}
    right={'page':6,'table':1,'source_version':'V','matrix':[['','不包括实验室。'],['5','景观设计']],'column_boundaries':[0,1,2],'cells':[]}
    profile={'source_version':'V','tables':[5,2,6,1],'continuation_column':2}
    joined=join_continuation(left,right,profile)
    assert '不包括实验室' in joined['matrix'][1][1] and len(joined['matrix'])==3
    with pytest.raises(ValueError):join_continuation(left,{**right,'source_version':'OLD'},profile)
    with pytest.raises(ValueError):join_continuation(left,{**right,'column_boundaries':[0,1,8]},profile)
    with pytest.raises(ValueError):join_continuation(left,{**right,'matrix':[['99','不包括实验室。'],['5','景观设计']]},profile)


def test_outline_destination_requires_actual_heading_text_on_that_page():
    line={'direction':[1,0],'bbox':[0,0,10,10],'spans':[{'text':'1 总则'}]}
    result=outline_anchors([[1,'1总则',1],[2,'附件19流程图',1],[1,'不存在',2]],[{'lines':[line]}])
    assert [r['status'] for r in result]==['TITLE_FOUND_AT_NATIVE_DESTINATION','DESTINATION_TITLE_NOT_VERIFIED','DESTINATION_OUT_OF_RANGE']


def test_bookmark_without_an_internal_destination_is_not_a_page_anchor():
    assert outline_anchors([[2,'转换软件分组',-1]],[{'lines':[]}])[0]['status']=='NO_IN_DOCUMENT_DESTINATION'


def test_blank_lines_do_not_create_multiple_heading_matches():
    line={'direction':[1,0],'bbox':[0,10,100,20],'spans':[{'text':'附件14：设计报批报建工作清单'}]}
    blank={'direction':[1,0],'bbox':[0,20,100,30],'spans':[{'text':' '}]}
    assert outline_anchors([[3,'附件14：设计报批报建工作清单',1]],[{'lines':[line,blank]}])[0]['status']=='TITLE_FOUND_AT_NATIVE_DESTINATION'
