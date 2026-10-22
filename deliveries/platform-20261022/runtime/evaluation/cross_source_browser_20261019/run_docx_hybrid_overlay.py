"""Replay the immutable encoded delta while separating duplicate source versions."""
import gc,hashlib,json,re,sys,time
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from evaluation.cross_source_browser_20261019 import run_docx_hybrid as prior
from app.retrieval.named_source_scope import resolve_named_scope,ranking_question,path_key
from app.knowledge_contract import KnowledgeContract
from app.bm25 import tokenize
import numpy as np
from rank_bm25 import BM25Okapi


def effective_indices(records,documents,contract):
    admitted={};reasons={}
    for did,d in documents.items():
        _,reason=contract.decision(Path(d['source_path']))
        versions={str(d[k]).lower() for k in ('source_version','source_hash','content_hash','sha256') if re.fullmatch('[a-fA-F0-9]{64}',str(d.get(k,'')))}
        reasons[did]='NAVIGATION_OR_EXCLUDED' if reason in {'navigation_only','excluded_root'} else 'UNKNOWN_CATALOG_VERSION' if len(versions)!=1 else None
        if not reasons[did]:admitted[did]=(path_key(d['source_path']),next(iter(versions)))
    selected=[];seen=set();excluded=Counter()
    for i,r in enumerate(records):
        did=r['document_id'];expected=admitted.get(did)
        if not expected:excluded[reasons.get(did) or 'MISSING_CATALOG_DOCUMENT']+=1;continue
        identity=(path_key(r['source_path']),r.get('source_version'))
        if identity!=expected:excluded['NOT_CATALOG_VERSION_OR_PATH']+=1;continue
        key=(*identity,r['evidence_id'])
        if key in seen:excluded['DUPLICATE_SAME_VERSION']+=1;continue
        seen.add(key);selected.append(i)
    return selected,dict(excluded)


def main():
    m,delta,delta_vectors=prior.load_delta();out=prior.REPORT
    if (out/'recall.json').exists():raise RuntimeError('First hybrid recall already exists')
    from app.trial.native_workbench_candidate import load_candidate
    from app.config import Settings
    started=time.perf_counter();engine=load_candidate();contract=KnowledgeContract(Settings.load().vault_root)
    affected={path_key(c['source_path']) for c in delta}
    retained=[i for i,c in enumerate(engine.chunks) if path_key(c['source_path']) not in affected]
    chunks=[engine.chunks[i] for i in retained]+delta;records=[]
    for c in chunks:
        # Frozen base IDs can occur in multiple versions: bind evidence to its own vector row.
        if c.get('source_version'):
            r={**c,'evidence_id':c['chunk_id'],'text':c['raw_text'],'heading_path':c['section_path'],'location':{'section':c['section_path'],'table_id':c.get('table_id')}}
        else:r=dict(engine.atomic[c['chunk_id']])
        records.append(r)
    selected,excluded=effective_indices(records,engine.docs,contract)
    assert len(chunks)==32837 and len(delta)==528
    assert len({records[i]['evidence_id'] for i in selected})==len(selected)
    corpus=[];vector_rows=[];bindings=[]
    for i in selected:
        if i<len(retained):
            old_index=retained[i];freq=engine.bm25.doc_freqs[old_index]
            corpus.append([word for word,count in freq.items() for _ in range(count)])
            vector_rows.append(engine.vectors[old_index]);origin={'base_row':old_index}
        else:
            new_index=i-len(retained);corpus.append(tokenize(prior.text(delta[new_index])))
            vector_rows.append(delta_vectors[new_index]);origin={'delta_row':new_index}
        r=records[i];bindings.append({'chunk_id':r['evidence_id'],'source_version':r['source_version'],'document_id':r['document_id'],**origin})
    vectors=np.asarray(vector_rows,dtype=np.float32);del vector_rows
    for i,b in enumerate(bindings):
        if 'base_row' in b:assert np.array_equal(vectors[i],engine.vectors[b['base_row']])
        else:assert np.array_equal(vectors[i],delta_vectors[b['delta_row']])
    records=[records[i] for i in selected]
    del engine.bm25;gc.collect();bm25=BM25Okapi(corpus);del corpus;gc.collect()
    prior.save(out/'effective_vector_bindings.json',bindings)
    overlay={'delta_hash':m['candidate_hash'],'base_hash':engine.candidate_hash,'contract_sha256':prior.sha(contract.path),'script_sha256':prior.sha(Path(__file__)),'effective_bindings_sha256':prior.sha(out/'effective_vector_bindings.json'),'physical_rows':len(chunks),'effective_rows':len(records),'excluded_rows':excluded,'existing_vector_values_unchanged':True,'corpus_statistics_rebuilt_after_filtering':True,'formal_index_written':False,'new_generation_calls':0}
    overlay['candidate_hash']=hashlib.sha256(json.dumps(overlay,sort_keys=True).encode()).hexdigest()
    prior.save(out/'overlay_manifest.json',overlay)
    load_ms=round((time.perf_counter()-started)*1000,2);results=[]
    for q,v in zip(prior.read(out/'questions.json'),np.load(prior.DATA/'query_vectors.npy'),strict=True):
        start=time.perf_counter();scope=resolve_named_scope(q['question'],engine.docs);allowed=scope['allowed_paths']
        mask=[i for i,r in enumerate(records) if allowed is None or path_key(r['source_path']) in allowed]
        sparse=bm25.get_scores(tokenize(ranking_question(q['question'],engine.docs)));dense=vectors@v
        orders={name:sorted(mask,key=lambda i:(-values[i],i)) for name,values in [('sparse',sparse),('dense',dense)]};fusion={}
        for order in orders.values():
            for rank,i in enumerate(order,1):fusion[i]=fusion.get(i,0)+1/(60+rank)
        orders['hybrid']=sorted(fusion,key=lambda i:(-fusion[i],i))
        channels={name:[{**records[i],'role':'DIRECT','score':float(fusion[i] if name=='hybrid' else sparse[i] if name=='sparse' else dense[i])} for i in order[:20]] for name,order in orders.items()}
        results.append({**q,'source_scope':scope,'eligible_chunks':len(mask),'channels':channels,'elapsed_recall_ms':round((time.perf_counter()-start)*1000,2)})
        print('VERSION_BOUND_RECALL',q['id'],len(mask),flush=True)
    prior.save(out/'recall.json',results)
    assert prior.sha(contract.path)==overlay['contract_sha256']
    prior.save(out/'recall_seal.json',{'recall_sha256':prior.sha(out/'recall.json'),'delta_hash':m['candidate_hash'],'base_hash':engine.candidate_hash,'overlay_hash':overlay['candidate_hash'],'overlay_manifest_sha256':prior.sha(out/'overlay_manifest.json'),'base_load_and_overlay_ms':load_ms,'removed_old_word_chunks':len(engine.chunks)-len(retained),'new_word_chunks':len(delta),'retained_vector_rows':sum('base_row' in b for b in bindings),'retained_vectors_bitwise_equal':True,'total_effective_chunks':len(records),'private_reference_used':False})
    prior.verify()


if __name__=='__main__':main()
