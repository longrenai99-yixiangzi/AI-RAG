from app.retrieval.section_scope import section_scope,mark_scope,SectionTitleIndex
from app.trial.assisted_chat import assemble


def test_explicit_phase_and_specialty_conflicts():
    assert section_scope('暖通施工图管控',{'heading_path':'暖通专业 > 初步设计'})['design_stage']=='MISMATCH'
    assert section_scope('暖通初设管控',{'heading_path':'电气专业 > 初步设计'})['specialty']=='MISMATCH'
    assert section_scope('暖通初设管控',{'heading_path':'暖通专业 > 初步设计'})=={'design_stage':'MATCH','specialty':'MATCH'}


def test_comparison_and_unstated_scope_are_not_silently_narrowed():
    assert section_scope('暖通初设与施工图的区别',{'heading_path':'暖通 > 初步设计'})['design_stage']=='UNKNOWN'
    assert section_scope('暖通方案比选有哪些内容',{'heading_path':'暖通 > 初步设计'})['design_stage']=='UNKNOWN'
    assert section_scope('暖通初设',{'heading_path':'Sheet1'})=={'design_stage':'UNKNOWN','specialty':'UNKNOWN'}


def test_new_scope_flags_do_not_erase_existing_constraints_and_block_assembly():
    c={'heading_path':'暖通 > 初步设计','scope':{'project':'MISMATCH'}}
    result=mark_scope('暖通施工图',[c])[0]
    assert result['scope']['project']=='MISMATCH' and result['scope']['design_stage']=='MISMATCH'
    assert not assemble({'candidate_evidence':[result]})[0].items
    assert mark_scope('暖通初设',[{**c,'scope':{'specialty':'MISMATCH'}}])[0]['scope']['specialty']=='MISMATCH'


def test_title_delta_can_find_subsection_without_a_retrieved_child(tmp_path):
    s={'section_id':'s','source_path':str(tmp_path/'x.md'),'source_version':'a'*64,'text':'施工图核查要求。','heading_path':'暖通 > 施工图阶段','location':{}}
    others=[{**s,'section_id':str(i),'heading_path':heading,'text':'无关事项。'} for i,heading in enumerate(['项目组织','材料采购'])]
    items=SectionTitleIndex([s,*others]).search('暖通施工图管控')
    assert items[0]['evidence_id']=='section-s' and items[0]['scope']['design_stage']=='MATCH'


def test_query_assembler_checks_scope_even_if_retriever_did_not_mark_it(tmp_path):
    import hashlib
    p=tmp_path/'x.md';p.write_text('初步设计的要求。',encoding='utf-8')
    item={'evidence_id':'e','document_id':'d','source_path':str(p),'source_version':hashlib.sha256(p.read_bytes()).hexdigest(),'role':'DIRECT','heading_path':'暖通专业 > 初步设计','text':p.read_text(encoding='utf-8')}
    assert assemble({'candidate_evidence':[item]})[0].items
    assert not assemble({'candidate_evidence':[item]},'暖通施工图要求是什么？')[0].items
