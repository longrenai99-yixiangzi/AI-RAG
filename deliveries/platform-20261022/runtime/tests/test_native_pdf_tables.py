import json
from pathlib import Path
from copy import deepcopy

import numpy as np
import pymupdf
import pytest

from app.ingestion.pdf_table_records import extract_table_records
from app.retrieval.native_pdf_tables import direct_bundle,overview_bundle,purpose_supported,scoped_indices
from app.retrieval.unified_candidate import UnifiedCandidate,file_sha
from app.trial.platform_existing import source_extract
from tests.test_unified_candidate import candidate
from tests.test_focused_candidate import Reranker


def source(tmp_path):
    path=tmp_path/'评分表.pdf';pdf=pymupdf.open();p=pdf.new_page()
    def put(x,y,t):p.insert_text((x,y),t,fontname='china-s',fontsize=10)
    put(55,65,'评分表')
    xs=[50,100,280,360,440];ys=[90,130,180,230,270]
    boxes=[[[xs[c],ys[r],xs[c+1],ys[r+1]] for c in range(4)] for r in range(4)]
    boxes[1][0]=[50,130,100,230];boxes[2][0]=None;boxes[3][0]=[50,230,280,270];boxes[3][1]=None
    for x in xs:p.draw_line((x,90),(x,270))
    for y in ys:p.draw_line((50,y),(440,y))
    for c,h in enumerate(['序号','评价事项','标准分值','实际得分']):put(xs[c]+5,115,h)
    put(60,160,'1');put(105,155,'制定设计标准化整体框架。');put(300,155,'5')
    put(105,205,'开展应用培训。');put(300,205,'5');put(55,255,'汇总得分');put(300,255,'10')
    pdf.save(path);pdf.close()
    spec={'source_path':str(path),'source_version':file_sha(path),'page':1,'table':1,'cell_boxes':boxes,
          'headers':['序号','评价事项','标准分值','实际得分'],'caption':'评分表','caption_page':1,'caption_bbox':[50,45,200,75],
          'group_pages':[1],'table_complete':True,'notes':[],'appendix_number':1}
    return path,spec,extract_table_records([spec])


def card(row):return {**row,'citation_id':'S1','source_id':'SRC_test','excerpt':row['text'],'answer_usage':'PRIMARY'}
def result(row):return {'answer_status':'SOURCES_ONLY','citations':[card(row)]}


def test_merged_owners_empty_scores_and_explicit_total_are_distinct(tmp_path):
    _,_,rows=source(tmp_path)
    assert len(rows)==3
    for row in rows[:2]:
        assert row['table_evidence']['values'][-1]==''
        assert row['native_pdf_table']['item_group_rows']==2
        assert not row['native_pdf_table']['shared_standard_score']
    assert rows[1]['native_pdf_table']['cells'][0]['merged_inheritance']
    assert rows[2]['native_pdf_table']['summary_row'] and rows[2]['table_evidence']['values']==['10','']
    native=source_extract(result(rows[0]),'设计标准化整体框架的标准分值是多少？')
    assert native['answer_status']=='SOURCE_EXTRACT' and '标准分值：5' in native['answer']
    blank=source_extract(result(rows[0]),'实际得分是多少？')
    assert blank['answer_status']=='EVIDENCE_INSUFFICIENT' and blank['native_table_field_audit']['reason']=='EMPTY_FIELD_NOT_ZERO'
    ambiguous=source_extract(result(rows[0]),'这个评价事项满分是多少？')
    assert ambiguous['answer_status']=='EVIDENCE_INSUFFICIENT'


def test_direct_header_and_summary_use_original_fields_without_example_values(tmp_path):
    path,_,rows=source(tmp_path)
    bundle=direct_bundle('《评分表.pdf》附件1满分是多少？',rows,[str(path.resolve()).casefold()])
    response=source_extract({'answer_status':'SOURCES_ONLY','citations':[card(bundle['candidate_evidence'][0])]},'《评分表.pdf》附件1满分是多少？')
    assert '标准分值：10' in response['answer']
    header=direct_bundle('《评分表.pdf》评分表有哪些字段？',rows,None)['candidate_evidence'][0]
    response=source_extract({'answer_status':'SOURCES_ONLY','citations':[card(header)]},'《评分表.pdf》评分表有哪些字段？')
    assert '实际得分' in response['answer'] and '制定' not in response['answer'] and '5' not in response['answer']
    assert 'table_evidence' not in header and header['location']['row']==1
    assert direct_bundle('《评分表.pdf》2026年附件1满分是多少？',rows,None) is None
    assert direct_bundle('《评分表.pdf》附件1设计标准化整体框架满分是多少？',rows,None) is None


def test_explicit_action_in_a_cell_is_not_replaced_by_similar_work(tmp_path):
    _,_,rows=source(tmp_path);r=deepcopy(rows[0])
    r['table_evidence']={'headers':['评价事项','评分标准'],'values':['参与设计分供方考察工作，形成报告。','未及时参与评估，每延迟一周扣1分。']}
    r['native_pdf_table']['original_headers']=['评价事项','评分标准']
    r['native_pdf_table']['field_term_conflicts']=[{'left_field':'评价事项','left_term':'考察','right_field':'评分标准','right_term':'评估'}]
    other=deepcopy(r);other['evidence_id']='unrelated';other['table_evidence']['values']=['完成送样及封样。','未按计划完成送样，扣1分。']
    bundle=direct_bundle('《评分表.pdf》考察工作未完成扣几分？',[other,r],None)
    selected=bundle['candidate_evidence'][0];assert selected['evidence_id']==r['evidence_id']
    assert selected['native_pdf_table']['literal_object_or_condition']=='考察工作'
    response=source_extract(result(selected),'《评分表.pdf》考察工作未完成扣几分？')
    assert response['native_table_field_audit']['reason']=='ORIGINAL_FIELD_TERM_CONFLICT'


def test_original_term_conflict_does_not_turn_inspection_into_evaluation(tmp_path):
    _,_,rows=source(tmp_path);r=deepcopy(rows[0])
    r['table_evidence']={'headers':['评价事项','评分标准'],'values':['参与设计分供方考察工作。','未及时参与评估，每延迟一周扣1分。']}
    r['native_pdf_table']['field_term_conflicts']=[{'left_field':'评价事项','left_term':'考察','right_field':'评分标准','right_term':'评估'}]
    value=source_extract(result(r),'考察工作未完成扣几分？')
    assert value['answer_status']=='EVIDENCE_INSUFFICIENT' and value['native_table_field_audit']['reason']=='ORIGINAL_FIELD_TERM_CONFLICT'


def test_business_type_and_construction_execution_scope_are_not_interchanged(tmp_path):
    _,_,rows=source(tmp_path)
    for row in rows:row['native_pdf_table'].update(caption='地产开发业务设计管理体系执行评价表',appendix_number=4)
    assert not purpose_supported('《体系建设评价指南.pdf》建造业务如何扣分？',rows[0])
    assert purpose_supported('《体系建设评价指南.pdf》地产开发业务附件4如何扣分？',rows[0])
    assert not purpose_supported('《体系建设评价指南.pdf》附件1如何扣分？',rows[0])
    assert direct_bundle('《体系建设评价指南.pdf》建造业务附件4满分多少？',rows,None)['bundle_status']=='CONFLICTING_EVIDENCE'
    assert scoped_indices('《体系建设评价指南.pdf》建造业务附件4如何扣分？',rows,[0,1,2])==[]


def test_scoring_tables_do_not_replace_general_role_evidence(tmp_path):
    _,_,rows=source(tmp_path)
    assert not purpose_supported('这个岗位承担什么职责？',rows[0])
    assert not purpose_supported('《评分表.pdf》这个岗位承担什么职责？',rows[0])
    assert purpose_supported('《评分表.pdf》附件1列明什么职责？',rows[0])
    assert not purpose_supported('未建立制度扣几分？',rows[0])


def test_only_full_small_tables_can_be_returned_as_a_complete_list(tmp_path):
    _,_,rows=source(tmp_path)
    for row in rows:row['native_pdf_table']['caption']='设计风险类别';row['native_pdf_table']['table_id']='same'
    bundle=overview_bundle('《评分表.pdf》设计风险有哪些类别？',rows,None)
    assert bundle['native_table_overview_audit']['complete_rows_included']
    for row in rows:row['native_pdf_table']['table_complete']=False
    assert overview_bundle('《评分表.pdf》设计风险有哪些类别？',rows,None)['bundle_status']=='SOURCE_SCOPE_MISSING'


def pack(tmp_path):
    path,spec,rows=source(tmp_path);_,base,encoder,_=candidate(tmp_path)
    docs=[json.loads(l) for l in (base/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    old=[json.loads(l) for l in (base/'evidence.jsonl').read_text(encoding='utf-8').splitlines()]
    docs[0].update(source_path=str(path),source_version=file_sha(path),file_name=path.name,file_type='.pdf')
    old[0].update(docs[0],location={'section':'Page 1'},text='原表待结构化文字。')
    for name,values in [('documents',docs),('evidence',old)]:
        (base/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values),encoding='utf-8')
    manifest=json.loads((base/'manifest.json').read_text());manifest['embedding_model_digest']='same-model'
    manifest['artifact_sha256'].update({n:file_sha(base/n) for n in ['documents.jsonl','evidence.jsonl']});(base/'manifest.json').write_text(json.dumps(manifest))
    out=tmp_path/'tables';out.mkdir()
    exclusions=[{k:old[0][k] for k in ['evidence_id','source_path','source_version']}];exclusions[0]['page']=1
    for n,data in [('specs',[spec]),('records',rows),('flat_exclusions',exclusions)]:
        (out/(n+'.json')).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    vectors=np.zeros((len(rows),1024),dtype=np.float32)
    for i in range(len(rows)):vectors[i,i+2]=1
    np.save(out/'vectors.npy',vectors)
    m={'base_candidate_hash':'isolated-test','embedding_model_digest':'same-model','paragraph_manifest_sha256':None,
       'artifact_sha256':{n:file_sha(out/n) for n in ['specs.json','records.json','flat_exclusions.json','vectors.npy']}}
    (out/'manifest.json').write_text(json.dumps(m))
    return base,encoder,out


def test_append_aligns_new_text_tokens_vectors_catalog_and_retires_flattened_rows(tmp_path):
    base,encoder,out=pack(tmp_path)
    c=UnifiedCandidate(base,encoder,Reranker(),native_table_folder=out)
    assert len(c.records)==len(c.vectors)==len(c.record_paths)==5 and c.sources(limit=10)['total']==2
    assert 'e0' in c.quality_exclusions and c.native_tables['table_rows']==2 and c.native_tables['summaries']==1
    for i in range(2,5):assert c.vectors[i,i]==1 and c.records[i].get('native_pdf_table')
    sid=c.records[2]['source_id'];assert c.source_evidence(sid)['items'][0]['evidence_id']==c.records[2]['evidence_id']
    assert c.retrieve('《评分表.pdf》附件1满分是多少？')['candidate_evidence'][0]['native_pdf_table']['summary_row']


@pytest.mark.parametrize('damage',['original','cell','vector','dependency'])
def test_changed_native_source_grid_or_vector_stops_activation(tmp_path,damage):
    base,encoder,out=pack(tmp_path);m=json.loads((out/'manifest.json').read_text())
    if damage=='original':
        rows=json.loads((out/'records.json').read_text());Path(rows[0]['source_path']).write_bytes(b'changed')
    elif damage=='cell':
        rows=json.loads((out/'records.json').read_text());rows[0]['table_evidence']['values'][2]='999'
        (out/'records.json').write_text(json.dumps(rows));m['artifact_sha256']['records.json']=file_sha(out/'records.json')
    elif damage=='vector':(out/'vectors.npy').write_bytes(b'changed')
    else:m['paragraph_manifest_sha256']='wrong'
    (out/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError):UnifiedCandidate(base,encoder,Reranker(),native_table_folder=out)
