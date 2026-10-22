import hashlib,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from app.retrieval.unified_candidate import UnifiedCandidate,file_sha
from app.trial.assisted_chat import assemble
from tests.test_focused_candidate import Reranker


def candidate(tmp_path):
    records=[];docs=[]
    for i,name in enumerate(['甲校医院','乙方工厂']):
        p=tmp_path/f'EPC设计管理经验总结({name}项目).docx';p.write_text('查找标记：负责人1人。',encoding='utf-8')
        d={'document_id':str(i),'source_id':'SRC'+str(i),'source_path':str(p),'file_name':p.name,'file_type':'.docx','source_version':file_sha(p)}
        docs.append(d);records.append({**d,'evidence_id':'e'+str(i),'text':p.read_text(encoding='utf-8'),'heading_path':'组织','location':{'section':'组织'}})
    pack=tmp_path/'pack';pack.mkdir();contract=tmp_path/'contract.json';contract.write_text('{}')
    for name,data in [('documents',docs),('evidence',records)]:
        (pack/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data),encoding='utf-8')
    v=np.zeros((2,1024),dtype=np.float32);v[0,0]=v[1,1]=1;np.save(pack/'dense_embeddings.npy',v)
    (pack/'bm25.json').write_text(json.dumps({'chunk_ids':['e0','e1'],'corpus':[['甲校医院','负责人'],['乙方工厂','负责人']]},ensure_ascii=False),encoding='utf-8')
    (pack/'sections.json').write_text('[]')
    manifest={'artifact_sha256':{p.name:file_sha(p) for p in pack.iterdir()},'contract_path':str(contract),'contract_sha256':file_sha(contract),'candidate_hash':'isolated-test'}
    (pack/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    encoder=SimpleNamespace(calls=[])
    def embed(q):encoder.calls.append(q);return v[0]
    encoder.embed_query=embed
    return UnifiedCandidate(pack,encoder,Reranker()),pack,encoder,docs


def test_sources_and_retrieval_use_the_same_versioned_records(tmp_path):
    c,_,encoder,docs=candidate(tmp_path)
    rows=c.sources(query='甲校医院');assert rows['total']==1
    sid=rows['items'][0]['source_id'];body=c.source_evidence(sid)['items']
    bundle=c.retrieve('甲校医院项目哪个岗位负责，配置多少人？')
    assert [r['evidence_id'] for r in bundle['candidate_evidence']]==[body[0]['evidence_id']]
    assert bundle['answer_grounding_policy']=='STRICT_SOURCE_UNITS'
    assert assemble(bundle)[1][0]['source_version']==docs[0]['source_version']
    assert len(encoder.calls)==1 and '甲校医院' not in encoder.calls[0]


def test_missing_ambiguous_and_changed_sources_stop_before_query_encoding(tmp_path):
    c,_,encoder,docs=candidate(tmp_path)
    assert c.retrieve('《未登记.docx》要求什么？')['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert c.retrieve('比较甲校医院项目与乙方工厂项目的配置')['bundle_status']=='SOURCE_SCOPE_MISSING'
    Path(docs[0]['source_path']).write_text('changed')
    assert c.retrieve('甲校医院项目谁牵头？')['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert not encoder.calls


def test_scalar_scope_can_reuse_admitted_original_when_derived_duplicate_is_excluded(tmp_path):
    c,pack,encoder,docs=candidate(tmp_path)
    link={'original_path':docs[0]['source_path'],'original_sha256':docs[0]['source_version'],
          'markdown_sha256':'b'*64,'scope':{'project':'甲校医院项目','aliases':['甲校医院项目'],'phases':[],'packages':[]}}
    links={str(tmp_path/'excluded-derived.md'):link}
    revised=UnifiedCandidate(pack,encoder,Reranker(),scalar_links=links)
    result=revised.retrieve('甲校医院项目合同金额多少万元？')
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert all(r['answer_usage']=='BACKGROUND' for r in result['candidate_evidence'])
    link['original_sha256']='a'*64
    with pytest.raises(ValueError,match='outside the admitted candidate'):
        UnifiedCandidate(pack,encoder,Reranker(),scalar_links=links)


def test_reference_note_stays_browsable_but_cannot_supply_answer_text(tmp_path):
    c,pack,encoder,docs=candidate(tmp_path)
    p=Path(docs[0]['source_path']);note=p.with_suffix('.md')
    note.write_text('# 原件登记\n**来源**：[原件](file:///D:/原件.pdf)\n## 关联内容\n- [[关联笔记]]',encoding='utf-8')
    docfile=pack/'documents.jsonl';recfile=pack/'evidence.jsonl'
    for file in (docfile,recfile):
        rows=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
        rows[0].update(source_path=str(note),file_name=note.name,source_version=file_sha(note),file_type='.md')
        if file==recfile:rows[0]['text']=note.read_text(encoding='utf-8')
        file.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    manifest=json.loads((pack/'manifest.json').read_text());manifest['artifact_sha256'].update({file.name:file_sha(file) for file in (docfile,recfile)});(pack/'manifest.json').write_text(json.dumps(manifest))
    revised=UnifiedCandidate(pack,encoder,Reranker());result=revised.retrieve('《'+note.name+'》规定哪些管理要求？')
    assert not encoder.calls and result['bundle_status']=='SOURCE_SCOPE_MISSING'
    assert result['candidate_evidence'] and all(row['answer_usage']=='BACKGROUND' for row in result['candidate_evidence'])
    assert not assemble(result)[0].items and assemble(result,include_background=True)[1]
    source=next(row for row in revised.sources()['items'] if row['source_path']==str(note))
    assert source['body_status']=='仅原件链接' and revised.source_evidence(source['source_id'])['items']


def test_tampered_vector_artifact_and_changed_contract_fail_closed(tmp_path):
    c,pack,encoder,_=candidate(tmp_path)
    contract=Path(c.manifest['contract_path']);contract.write_text('changed')
    with pytest.raises(ValueError,match='contract changed'):UnifiedCandidate(pack,encoder,Reranker())
    contract.write_text('{}');del c
    import gc
    gc.collect()
    (pack/'dense_embeddings.npy').write_bytes(b'changed')
    with pytest.raises(ValueError,match='artifact changed'):UnifiedCandidate(pack,encoder,Reranker())


def test_evidence_quality_exclusion_is_version_bound_and_keeps_source_trace(tmp_path):
    c,pack,encoder,_=candidate(tmp_path);quality=tmp_path/'quality';quality.mkdir();proof=quality/'proof.json';proof.write_text('{}')
    record=c.records[0];entry={k:record[k] for k in ('evidence_id','source_path','source_version')};entry['reason']='原件版面核对尚未通过'
    manifest={'base_candidate_hash':c.candidate_hash,'proof_sha256':{str(proof):file_sha(proof)},'exclusions':[entry]};path=quality/'manifest.json';path.write_text(json.dumps(manifest))
    revised=UnifiedCandidate(pack,encoder,Reranker(),quality_folder=quality)
    result=revised.retrieve('甲校医院项目查找标记是什么？')
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING' and not encoder.calls
    assert not assemble(result)[0].items
    sid=record['source_id'];body=revised.source_evidence(sid)['items'][0]
    assert body['raw_text']==record['text'] and body['answer_exclusion_reason']==entry['reason']
    manifest['exclusions'][0]['source_version']='b'*64;path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='source binding'):UnifiedCandidate(pack,encoder,Reranker(),quality_folder=quality)
    manifest['exclusions'][0]['source_version']=record['source_version'];path.write_text(json.dumps(manifest));proof.write_text('changed')
    with pytest.raises(ValueError,match='proof changed'):UnifiedCandidate(pack,encoder,Reranker(),quality_folder=quality)


def test_opt_in_personnel_rows_are_browsable_and_skip_query_encoding(tmp_path):
    c,pack,encoder,_=candidate(tmp_path);layer=tmp_path/'personnel';layer.mkdir()
    native={**c.records[0],'evidence_id':'native-personnel','personnel':{'kind':'LEAD_ROLE','position':'负责人'}}
    (layer/'records.json').write_text(json.dumps([native],ensure_ascii=False),encoding='utf-8')
    (layer/'manifest.json').write_text(json.dumps({'base_candidate_hash':'isolated-test','records_sha256':file_sha(layer/'records.json')}),encoding='utf-8')
    revised=UnifiedCandidate(pack,encoder,Reranker(),personnel_folder=layer)
    result=revised.retrieve('甲校医院项目谁负责，配置多少人？');assert not encoder.calls
    assert result['candidate_evidence'][0]['evidence_id']=='native-personnel'
    sid=result['candidate_evidence'][0]['source_id'];body=revised.source_evidence(sid)['items']
    assert body[0]['evidence_id']=='native-personnel' and revised.sources(query='甲校医院')['items'][0]['chunk_count']==2
    assert revised.retrieve('甲校医院项目查找标记是什么？')['candidate_evidence'] and len(encoder.calls)==1
    uncovered=revised.retrieve('乙方工厂项目谁负责，配置多少人？')
    assert uncovered['bundle_status']=='SOURCE_SCOPE_MISSING' and uncovered['candidate_evidence']
    assert all(r['answer_usage']=='BACKGROUND' for r in uncovered['candidate_evidence'])
    assert not assemble(uncovered)[0].items and assemble(uncovered,include_background=True)[0].items


def reference_candidate(tmp_path):
    c,pack,encoder,docs=candidate(tmp_path);body=Path(docs[1]['source_path']);linked=tmp_path/'原件副本.docx';linked.write_bytes(body.read_bytes())
    note=tmp_path/'《制度登记》.md';note.write_text('# 制度登记\n**来源**：[原件]('+linked.as_uri()+')\n## 关联内容\n- [[制度导航]]',encoding='utf-8')
    for name in ['documents.jsonl','evidence.jsonl']:
        file=pack/name;rows=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
        rows[0].update(source_path=str(note),file_name=note.name,source_version=file_sha(note),file_type='.md')
        if name=='evidence.jsonl':rows[0]['text']=note.read_text(encoding='utf-8')
        file.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    base=json.loads((pack/'manifest.json').read_text());base['artifact_sha256'].update({n:file_sha(pack/n) for n in ['documents.jsonl','evidence.jsonl']});(pack/'manifest.json').write_text(json.dumps(base))
    folder=tmp_path/'policy';folder.mkdir();entry={'note_path':str(note),'note_version':file_sha(note),'linked_path':str(linked),'linked_version':file_sha(linked),'body_path':str(body),'body_version':file_sha(body),'body_document_id':docs[1]['document_id']}
    policy={'base_candidate_hash':c.candidate_hash,'proof_sha256':{},'exclusions':[],'reference_bindings':[entry]};(folder/'manifest.json').write_text(json.dumps(policy))
    return UnifiedCandidate(pack,encoder,Reranker(),quality_folder=folder),pack,encoder,folder,entry


def test_reference_selects_existing_body_and_preserves_actual_citation(tmp_path):
    c,_,encoder,_,b=reference_candidate(tmp_path);q='《《制度登记》.md》中查找标记是什么？'
    result=c.retrieve(q);items,cards=assemble(result,q)
    assert len(items.items)==1 and cards[0]['source_path']==b['body_path'] and cards[0]['source_version']==b['body_version']
    assert result['reference_resolution'][0]['note_path']==b['note_path'] and '制度登记' not in encoder.calls[0]
    source=next(row for row in c.sources()['items'] if row['source_path']==b['note_path'])
    assert source['body_status']=='已关联原件 · 正文待核'
    browsed=c.source_evidence(source['source_id']);assert browsed['items'][0]['raw_text']==cards[0]['excerpt']
    assert browsed['reference_resolution']['body_source_id']==cards[0]['source_id']
    assert c.documents['0']['source_path']==b['note_path'] and c.scope_documents['0']['source_path']==b['body_path']
    by_path=c.retrieve('《'+Path(b['note_path']).as_posix()+'》中查找标记是什么？')
    assert assemble(by_path)[1][0]['source_path']==b['body_path']
    from app.trial.assisted_chat import AssistedQuery,run_flow
    from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
    from app.answer_engine.llm.llm_provider import UnavailableLLMProvider
    answer=list(run_flow(AssistedQuery(question=q,mode='sources'),c.retrieve,ShadowAnswerGenerator(UnavailableLLMProvider('offline')),lambda *a:None))[-2]['result']
    assert answer['answer_status']=='SOURCES_ONLY' and answer['source_resolution_note'] and answer['debug']['reference_resolution']


@pytest.mark.parametrize('changed',['note_path','linked_path','body_path'])
def test_changed_reference_chain_stops_without_embedding_or_old_body(tmp_path,changed):
    c,_,encoder,_,b=reference_candidate(tmp_path);Path(b[changed]).write_bytes(b'new version')
    result=c.retrieve('《《制度登记》.md》中查找标记是什么？')
    assert result['bundle_status']=='SOURCE_SCOPE_MISSING' and not result['candidate_evidence'] and not encoder.calls
    source=next(row for row in c.sources()['items'] if row['source_path']==b['note_path'])
    assert source['body_status']=='关联版本待核对' and not c.source_evidence(source['source_id'])['items']


@pytest.mark.parametrize('fault',['body_document_id','note_version','linked_version','linked_path','duplicate'])
def test_invalid_reference_bindings_cannot_admit_unbound_sources(tmp_path,fault):
    _,pack,encoder,folder,b=reference_candidate(tmp_path);path=folder/'manifest.json';policy=json.loads(path.read_text());entry=policy['reference_bindings'][0]
    if fault=='duplicate':policy['reference_bindings'].append(dict(entry))
    elif fault=='linked_path':entry[fault]=b['body_path']
    elif fault=='body_document_id':entry[fault]='not-in-candidate'
    else:entry[fault]='f'*64
    path.write_text(json.dumps(policy))
    with pytest.raises(ValueError,match='Reference|Duplicate'):UnifiedCandidate(pack,encoder,Reranker(),quality_folder=folder)
