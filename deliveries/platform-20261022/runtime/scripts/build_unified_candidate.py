"""Freeze the corrected overlay once; future requests do not scan original documents."""
import gc,hashlib,json,os,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='')
import numpy as np
from app.retrieval.unified_candidate import effective_indices,file_sha,path_key,declared_version
from app.knowledge_contract import KnowledgeContract
from app.config import Settings
from app.bm25 import tokenize

OUT=ROOT/'data/shadow/unified_entry_20261020';REPORT=ROOT/'evaluation/unified_entry_20261020'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    if OUT.exists():raise RuntimeError('Candidate already exists; refusing overwrite')
    OUT.mkdir();REPORT.mkdir(parents=True,exist_ok=True)
    from app.trial.native_workbench_candidate import load_candidate
    from evaluation.cross_source_browser_20261019.run_docx_hybrid import load_delta,text
    m,delta,new_vectors=load_delta();base=load_candidate();contract=KnowledgeContract(Settings.load().vault_root)
    affected={path_key(c['source_path']) for c in delta};retained=[i for i,c in enumerate(base.chunks) if path_key(c['source_path']) not in affected]
    chunks=[base.chunks[i] for i in retained]+delta;records=[]
    for c in chunks:
        if c.get('source_version'):
            loc={'section':c['section_path']}
            if c.get('table_id'):loc['table_id']=c['table_id']
            r={**c,'evidence_id':c['chunk_id'],'text':c['raw_text'],'heading_path':c['section_path'],'location':loc}
        else:r=dict(base.atomic[c['chunk_id']])
        records.append(r)
    selected,excluded=effective_indices(records,base.docs,contract)
    actual={};source_checks=[]
    for did in sorted({records[i]['document_id'] for i in selected}):
        doc=base.docs[did];p=Path(doc['source_path']);key=path_key(p)
        if key not in actual:
            try:actual[key]=file_sha(p)
            except OSError:actual[key]=None
        source_checks.append({'document_id':did,'source_path':str(p),'indexed_version':declared_version(doc),'actual_version':actual[key],'matched':actual[key]==declared_version(doc)})
        if len(source_checks)%50==0:print('SOURCE_VERSION_CHECK',len(source_checks),flush=True)
    matched={c['document_id'] for c in source_checks if c['matched']};active=[i for i in selected if records[i]['document_id'] in matched]
    excluded['SOURCE_BYTES_CHANGED_OR_MISSING']=len(selected)-len(active)
    corpus=[];vectors=[];bindings=[];rows=[]
    for i in active:
        r=records[i];r['source_id']=r.get('source_id') or base.docs[r['document_id']].get('source_id') or r['document_id'];rows.append(r)
        if i<len(retained):
            old=retained[i];freq=base.bm25.doc_freqs[old];corpus.append([t for t,n in freq.items() for _ in range(n)]);vectors.append(base.vectors[old]);origin={'base_row':old}
        else:
            j=i-len(retained);corpus.append(tokenize(text(delta[j])));vectors.append(new_vectors[j]);origin={'delta_row':j}
        bindings.append({'evidence_id':r['evidence_id'],'source_version':r['source_version'],**origin})
    assert len({r['evidence_id'] for r in rows})==len(rows)
    matrix=np.asarray(vectors,dtype=np.float32)
    for i,b in enumerate(bindings):
        assert np.array_equal(matrix[i],base.vectors[b['base_row']] if 'base_row' in b else new_vectors[b['delta_row']])
    np.save(OUT/'dense_embeddings.npy',matrix)
    docs={r['document_id']:base.docs[r['document_id']] for r in rows}
    for name,items in [('documents',list(docs.values())),('evidence',rows)]:
        (OUT/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in items),encoding='utf-8')
    save(OUT/'bm25.json',{'chunk_ids':[r['evidence_id'] for r in rows],'corpus':corpus})
    supported={(path_key(r['source_path']),r['source_version']) for r in rows}
    sections=[s for s in read(ROOT/'evaluation/section_retrieval_20261019/sections.json') if (path_key(s['source_path']),s['source_version']) in supported]
    save(OUT/'sections.json',sections);save(OUT/'vector_bindings.json',bindings);save(REPORT/'source_version_preflight.json',source_checks)
    artifacts={p.name:file_sha(p) for p in OUT.iterdir() if p.is_file()}
    material={'artifact_sha256':artifacts,'contract_path':str(contract.path),'contract_sha256':file_sha(contract.path),'inherited_candidate_hash':base.candidate_hash,'word_delta_hash':m['candidate_hash'],'embedding_model_digest':m['model_digest']}
    manifest={**material,'candidate_hash':hashlib.sha256(json.dumps(material,sort_keys=True).encode()).hexdigest(),'status':'ISOLATED_UNIFIED_NOT_DEPLOYED','documents':len(docs),'records':len(rows),'sections':len(sections),'excluded_rows':excluded,'reused_vector_rows':len(rows),'new_document_embeddings':0,'new_model_calls':0,'build_code_sha256':file_sha(Path(__file__))}
    save(OUT/'manifest.json',manifest);print(json.dumps({k:manifest[k] for k in ['candidate_hash','documents','records','excluded_rows','new_document_embeddings']},ensure_ascii=False),flush=True)
