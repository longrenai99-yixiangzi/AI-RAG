import json
import hashlib
from copy import deepcopy

import numpy as np
import pymupdf
import pytest

from app.bm25 import tokenize
from app.ingestion.pdf_paragraph_context import native_lines,paragraph_text,complete_rows,compact,prose_before_tables
from app.retrieval.unified_candidate import UnifiedCandidate,file_sha
from app.trial.candidate_platform import CandidateKnowledge
from tests.test_unified_candidate import candidate
from tests.test_focused_candidate import Reranker


def fixture(tmp_path):
    path=tmp_path/'原件.pdf';pdf=pymupdf.open();page=pdf.new_page()
    page.insert_text((80,90),'4）采购管理部',fontname='china-s',fontsize=12)
    page.insert_text((80,120),'负责统筹资源，若存在设计变更，\n应在报批前核对完整接口。',fontname='china-s',fontsize=12)
    page.insert_text((80,190),'2）不得省略审核。',fontname='china-s',fontsize=12)
    pdf.save(path);pdf.close();version=file_sha(path)
    with pymupdf.open(path) as doc:lines=native_lines(doc[0])
    ids=[i for i,l in enumerate(lines) if l['text'].startswith(('负责统筹','应在报批'))]
    spec={'source_path':str(path),'source_version':version,'page':1,'line_ids':ids,'context_line_ids':[ids[0]-1],
          'left_id':'e0','right_id':'e1','clue_id':'TEST'}
    body,header=paragraph_text(lines,spec);cut=compact(body).index('变')+1;spec['cut_in_paragraph']=cut
    offset=[i for i,c in enumerate(body) if not c.isspace()][cut]
    base={'source_path':str(path),'source_version':version,'location':{'section':'Page 1'}}
    rows=[{**base,'evidence_id':'e0','text':header+'\n'+body[:offset]},
          {**base,'evidence_id':'e1','text':body[offset:]+'\n2）不得省略审核。'}]
    return path,rows,spec,body


def test_native_paragraph_completion_keeps_conditions_actor_and_other_clauses(tmp_path):
    path,rows,spec,body=fixture(tmp_path);old=deepcopy(rows);changed=complete_rows(rows,[spec])
    for r in changed.values():assert compact(body) in compact(r['text']) and '若存在设计变更' in compact(r['text'])
    assert changed['e1']['text'].startswith('4）采购管理部')
    assert '不得省略审核' in changed['e1']['text']
    assert rows==old and file_sha(path)==spec['source_version']


@pytest.mark.parametrize('damage',['source','page','tail','lines','actor'])
def test_changed_original_missing_tail_or_wrong_context_cannot_be_completed(tmp_path,damage):
    path,rows,spec,_=fixture(tmp_path)
    if damage=='source':path.write_bytes(b'changed')
    elif damage=='page':rows[1]['location']['section']='Page 2'
    elif damage=='tail':rows[1]['text']='别的业务内容。'
    elif damage=='lines':spec['line_ids']=[-1,0,1]
    else:spec['context_line_ids']=[spec['line_ids'][-1]+1]
    with pytest.raises(ValueError):complete_rows(rows,[spec])


def test_mixed_page_keeps_qualified_prose_and_drops_only_the_later_layout_tail(tmp_path):
    path,rows,spec,body=fixture(tmp_path)
    text='4）采购管理部\n'+body+'\n2）不得省略审核。'
    row={**rows[0],'evidence_id':'safe','text':text}
    safe={k:spec[k] for k in ('source_path','source_version','page')}
    safe.update(evidence_id='safe',line_ids=[0,1,2],table_bbox=[70,175,350,250])
    result=prose_before_tables([row],[safe])['safe']
    assert compact(body) in compact(result['text']) and '若存在设计变更' in compact(result['text'])
    assert '2）不得省略审核' not in result['text'] and row['text']==text
    safe['table_bbox'][1]=100
    with pytest.raises(ValueError,match='Table cells'):prose_before_tables([row],[safe])


def prepared(tmp_path):
    path,rows,spec,body=fixture(tmp_path)
    _,pack,encoder,_=candidate(tmp_path)
    docs=[json.loads(l) for l in (pack/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    records=[json.loads(l) for l in (pack/'evidence.jsonl').read_text(encoding='utf-8').splitlines()]
    for d,r,native in zip(docs,records,rows):
        d.update(source_path=str(path),source_version=file_sha(path),file_name=path.name,file_type='.pdf')
        r.update(d);r.update(native)
    for name,values in [('documents',docs),('evidence',records)]:
        (pack/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values),encoding='utf-8')
    manifest=json.loads((pack/'manifest.json').read_text());manifest['embedding_model_digest']='same-model'
    manifest['artifact_sha256'].update({n:file_sha(pack/n) for n in ('documents.jsonl','evidence.jsonl')})
    (pack/'manifest.json').write_text(json.dumps(manifest))
    layer=tmp_path/'repair';layer.mkdir();changed=complete_rows(records,[spec]);revisions=[]
    for i,r in enumerate(records):revisions.append({'evidence_id':r['evidence_id'],'text':changed[r['evidence_id']]['text'],
        'original_effective_text_sha256':hashlib.sha256(r['text'].encode()).hexdigest(),'vector_row':i})
    for name,value in [('paragraphs',[spec]),('safe_prose',[]),('exclusions',[]),('rows',revisions)]:
        (layer/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    v=np.zeros((2,1024),dtype=np.float32);v[0,2]=v[1,3]=1;np.save(layer/'vectors.npy',v)
    specfile={'base_candidate_hash':'isolated-test','embedding_model_digest':'same-model','text_cleanup_manifest_sha256':None,
              'artifact_sha256':{n:file_sha(layer/n) for n in ['paragraphs.json','safe_prose.json','rows.json','vectors.npy','exclusions.json']}}
    (layer/'manifest.json').write_text(json.dumps(specfile))
    return pack,encoder,layer,body


def test_complete_context_vectors_keyword_index_preview_and_snapshot_agree(tmp_path):
    pack,encoder,layer,body=prepared(tmp_path)
    c=UnifiedCandidate(pack,encoder,Reranker(),paragraph_repair_folder=layer)
    assert c.paragraph_repair['completed_boundaries']==1 and c.paragraph_repair['reencoded_rows']==2
    for r in c.records:assert compact(body) in compact(r['text'])
    assert c.vectors[0,2]==1 and np.load(pack/'dense_embeddings.npy')[0,0]==1
    sid=c.records[0]['source_id'];items=c.source_evidence(sid)['items']
    assert all(i.get('paragraph_completion') for i in items)
    snapshot=CandidateKnowledge(c).source_snapshot(sid)
    assert snapshot['vectors'][0][2]==1 and compact(body) in compact(snapshot['records'][0]['text'])
    assert all(term in c.bm25.doc_freqs[0] for term in tokenize('设计变更'))


def test_tampered_completed_text_or_wrong_cleanup_dependency_stops_startup(tmp_path):
    pack,encoder,layer,_=prepared(tmp_path)
    spec=json.loads((layer/'manifest.json').read_text());spec['text_cleanup_manifest_sha256']='wrong'
    (layer/'manifest.json').write_text(json.dumps(spec))
    with pytest.raises(ValueError,match='cleanup differs'):UnifiedCandidate(pack,encoder,Reranker(),paragraph_repair_folder=layer)
    spec['text_cleanup_manifest_sha256']=None
    rows=json.loads((layer/'rows.json').read_text());rows[0]['text']='虚构的业务结论。'
    (layer/'rows.json').write_text(json.dumps(rows));spec['artifact_sha256']['rows.json']=file_sha(layer/'rows.json')
    (layer/'manifest.json').write_text(json.dumps(spec))
    with pytest.raises(ValueError,match='differs from native'):UnifiedCandidate(pack,encoder,Reranker(),paragraph_repair_folder=layer)


def test_additional_batch_reuses_source_vector_and_snapshot_contract(tmp_path,monkeypatch):
    from app.retrieval import native_flowcharts
    pack,encoder,layer,body=prepared(tmp_path)
    m=json.loads((layer/'manifest.json').read_text());m['required_runtime_flow_manifest_sha256']='reviewed-flow'
    (layer/'manifest.json').write_text(json.dumps(m))
    monkeypatch.setattr(native_flowcharts,'append_flowcharts',lambda *args:(args[-1],{'manifest_sha256':'reviewed-flow'}))
    c=UnifiedCandidate(pack,encoder,Reranker(),flowchart_folder=tmp_path,additional_paragraph_folder=layer)
    assert c.additional_paragraph_repair['completed_boundaries']==1
    assert c.vectors[0,2]==1 and all(compact(body) in compact(r['text']) for r in c.records)
    snap=CandidateKnowledge(c).source_snapshot(c.records[0]['source_id'])
    assert snap['vectors'][0][2]==1 and compact(body) in compact(snap['records'][0]['text'])


def test_additional_batch_requires_exact_preceding_layer(tmp_path):
    pack,encoder,layer,_=prepared(tmp_path)
    m=json.loads((layer/'manifest.json').read_text());m['required_runtime_flow_manifest_sha256']='other-flow'
    (layer/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError,match='flow dependency'):
        UnifiedCandidate(pack,encoder,Reranker(),additional_paragraph_folder=layer)
