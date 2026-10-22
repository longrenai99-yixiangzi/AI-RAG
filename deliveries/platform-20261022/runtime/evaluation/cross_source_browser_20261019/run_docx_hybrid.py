"""Isolated Word delta: encode full text, replace both old channels, replay without generation."""
import argparse,gc,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='')
import numpy as np
HERE=Path(__file__).resolve().parent
DATA=ROOT/'data/shadow/docx_context_20261020'
REPORT=ROOT/'evaluation/docx_hybrid_20261020'
SPARSE=HERE/'corrected_sparse_complete_20261020'

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(p)
def text(c):return c['file_name']+'\n'+c['section_path']+'\n'+c['raw_text']

def verify():
    assert all(sha(Path(p))==h for p,h in read(HERE/'first_cross_execution_seal.json').items())
    assert all(sha(Path(p))==h for p,h in read(SPARSE/'receipt.json')['code_sha256'].items())
    assert all(sha(Path(c['source']))==c['source_sha256'] for c in read(HERE/'docx_corrected_cache_20261020/checks.json')['checks'])
    if (DATA/'input_seal.json').exists():
        assert all(sha(Path(p))==h for p,h in read(DATA/'input_seal.json').items())

def encode():
    verify()
    if (DATA/'manifest.json').exists():raise RuntimeError('Completed candidate already exists; do not overwrite')
    from scripts.run_source_completion_trial import LocalDenseCPU,checkpoint,model_digest
    from app.retrieval.named_source_scope import ranking_question
    DATA.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    catalog=read(HERE/'cross_catalog_snapshot.json')
    questions=read(HERE/'cross_questions.json')+[
        {'id':'P01','question':'示例厂房项目由谁统筹技术和设计，配置多少人？'},
        {'id':'P02','question':'示例训练馆项目由谁牵头设计管理，配置多少人？'}]
    if (REPORT/'questions.json').exists():assert read(REPORT/'questions.json')==questions
    else:save(REPORT/'questions.json',questions)
    inputs=[SPARSE/'structured.json',SPARSE/'sparse_index.json',SPARSE/'receipt.json',HERE/'cross_catalog_snapshot.json',REPORT/'questions.json',Path(__file__)]
    inputs.extend(Path(p) for p in read(SPARSE/'receipt.json')['code_sha256'])
    seal={str(p):sha(p) for p in inputs}
    if (DATA/'input_seal.json').exists():assert read(DATA/'input_seal.json')==seal
    else:save(DATA/'input_seal.json',seal)
    chunks=read(SPARSE/'structured.json')['semantic_chunks'];ids=[c['chunk_id'] for c in chunks]
    assert len(set(ids))==len(ids)==528
    texts=[text(c) for c in chunks];weight_hash=model_digest()
    runtime='BGE_M3_CPU_BF16_CLS_FP32_NORM_FULLTEXT_MAX1024'
    key=hashlib.sha256(json.dumps([weight_hash,runtime,seal,ids,texts],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    vectors=checkpoint(DATA/'document_checkpoint',key);encoder=LocalDenseCPU();started=time.perf_counter()
    try:
        lengths=[len(encoder.tokenizer(t)['input_ids']) for t in texts]
        assert max(lengths)<=1024,'Input too long; stop rather than truncate'
        for start in range(len(vectors),len(texts),4):
            batch=texts[start:start+4]
            with encoder.torch.inference_mode():
                tokens=encoder.tokenizer(batch,padding=True,truncation=False,return_tensors='pt')
                v=encoder.model(**tokens).last_hidden_state[:,0].float()
                v=encoder.torch.nn.functional.normalize(v,p=2,dim=1).cpu().numpy()
            assert v.shape==(len(batch),1024) and np.isfinite(v).all()
            assert np.allclose(np.linalg.norm(v,axis=1),1,atol=.001)
            vectors.extend(v.tolist())
            checkpoint(DATA/'document_checkpoint',key,vectors)
            if len(vectors)%32==0 or len(vectors)==len(texts):print('WORD_EMBED',len(vectors),'/',len(texts),flush=True)
        query_texts=[ranking_question(q['question'],catalog) for q in questions]
        assert all(len(encoder.tokenizer(q)['input_ids'])<=256 for q in query_texts)
        query_vectors=np.asarray([encoder.embed_query(q) for q in query_texts],dtype=np.float32)
    finally:encoder.close()
    np.save(DATA/'dense_embeddings.npy',np.asarray(vectors,dtype=np.float32));np.save(DATA/'query_vectors.npy',query_vectors)
    save(DATA/'chunk_bindings.json',[{'row':i,'chunk_id':c['chunk_id'],'document_id':c['document_id'],'source_path':c['source_path'],'source_version':c['source_version'],'text_sha256':hashlib.sha256(text(c).encode()).hexdigest(),'input_tokens':lengths[i]} for i,c in enumerate(chunks)])
    artifacts={p.name:sha(p) for p in DATA.iterdir() if p.is_file() and p.name!='manifest.json'}
    material={'artifacts':artifacts,'base_manifest_sha256':sha(ROOT/'data/shadow/browser_trial_20261019/manifest.json'),'model_digest':weight_hash,'runtime':runtime}
    save(DATA/'manifest.json',{'status':'OFFLINE_WORD_DELTA_EMBEDDED_NOT_DEPLOYED',**material,'candidate_hash':hashlib.sha256(json.dumps(material,sort_keys=True).encode()).hexdigest(),'documents':2,'new_document_vectors':len(vectors),'new_query_vectors':len(questions),'new_generation_calls':0,'max_input_tokens':max(lengths),'inputs_over_old_256_limit':sum(n>256 for n in lengths),'truncated_inputs':0,'elapsed_encode_ms':round((time.perf_counter()-started)*1000,2)})
    verify();print('WORD_EMBED_COMPLETE',flush=True)

def load_delta():
    verify();m=read(DATA/'manifest.json')
    assert all(sha(DATA/name)==h for name,h in m['artifacts'].items())
    chunks=read(SPARSE/'structured.json')['semantic_chunks'];vectors=np.load(DATA/'dense_embeddings.npy')
    bindings=read(DATA/'chunk_bindings.json')
    assert vectors.shape==(len(chunks),1024) and np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors,axis=1),1,atol=.001)
    for i,(c,b) in enumerate(zip(chunks,bindings,strict=True)):
        assert b['row']==i and b['chunk_id']==c['chunk_id'] and b['source_version']==c['source_version']
        assert b['text_sha256']==hashlib.sha256(text(c).encode()).hexdigest()
    return m,chunks,vectors

def recall():
    m,delta,delta_vectors=load_delta()
    if (REPORT/'recall.json').exists():raise RuntimeError('First hybrid recall already exists')
    from app.trial.native_workbench_candidate import load_candidate
    from app.retrieval.named_source_scope import resolve_named_scope,ranking_question,path_key
    from app.bm25 import tokenize
    from rank_bm25 import BM25Okapi
    started=time.perf_counter();engine=load_candidate()
    affected={path_key(c['source_path']) for c in delta};keep=[i for i,c in enumerate(engine.chunks) if path_key(c['source_path']) not in affected]
    # BM25 needs token counts, not token order; retain every unchanged document's exact bag.
    corpus=[[word for word,count in engine.bm25.doc_freqs[i].items() for _ in range(count)] for i in keep]
    corpus.extend(tokenize(text(c)) for c in delta)
    chunks=[engine.chunks[i] for i in keep]+delta
    vectors=np.concatenate([engine.vectors[keep],delta_vectors])
    assert len(chunks)==len(corpus)==len(vectors)==32837
    assert len({c['chunk_id'] for c in chunks})==len(chunks)
    assert np.array_equal(vectors[:len(keep)],engine.vectors[keep])
    del engine.bm25;gc.collect();bm25=BM25Okapi(corpus);del corpus;gc.collect()
    queries=read(REPORT/'questions.json');query_vectors=np.load(DATA/'query_vectors.npy')
    results=[];load_ms=round((time.perf_counter()-started)*1000,2)
    for q,query_vector in zip(queries,query_vectors,strict=True):
        start=time.perf_counter();scope=resolve_named_scope(q['question'],engine.docs);allowed=scope['allowed_paths']
        mask=[i for i,c in enumerate(chunks) if allowed is None or path_key(c['source_path']) in allowed]
        scores=bm25.get_scores(tokenize(ranking_question(q['question'],engine.docs)));dense=vectors@query_vector
        orders={k:sorted(mask,key=lambda i:(-values[i],i)) for k,values in [('sparse',scores),('dense',dense)]}
        fusion={}
        for order in orders.values():
            for rank,i in enumerate(order,1):fusion[i]=fusion.get(i,0)+1/(60+rank)
        orders['hybrid']=sorted(fusion,key=lambda i:(-fusion[i],i))
        channels={}
        for channel,order in orders.items():
            candidates=[]
            for i in order[:20]:
                c=chunks[i]
                if path_key(c['source_path']) in affected:
                    row={**c,'evidence_id':c['chunk_id'],'text':c['raw_text'],'heading_path':c['section_path'],'location':{'section':c['section_path'],'table_id':c.get('table_id')}}
                else:row=dict(engine.atomic[c['chunk_id']])
                row.update(role='DIRECT',score=float(fusion[i] if channel=='hybrid' else (scores[i] if channel=='sparse' else dense[i])))
                candidates.append(row)
            channels[channel]=candidates
        results.append({**q,'source_scope':scope,'eligible_chunks':len(mask),'channels':channels,'elapsed_recall_ms':round((time.perf_counter()-start)*1000,2)})
        print('WORD_RECALL',q['id'],len(mask),flush=True)
    save(REPORT/'recall.json',results)
    save(REPORT/'recall_seal.json',{'recall_sha256':sha(REPORT/'recall.json'),'delta_hash':m['candidate_hash'],'base_hash':engine.candidate_hash,'frozen_base_manifest_sha256':m['base_manifest_sha256'],'base_load_and_overlay_ms':load_ms,'removed_old_word_chunks':len(engine.chunks)-len(keep),'new_word_chunks':len(delta),'retained_vector_rows':len(keep),'retained_vectors_bitwise_equal':True,'total_chunks':len(chunks),'private_reference_used':False})

def rank():
    m,_,_=load_delta();seal=read(REPORT/'recall_seal.json')
    assert seal['recall_sha256']==sha(REPORT/'recall.json') and seal['delta_hash']==m['candidate_hash']
    if (REPORT/'results.json').exists():raise RuntimeError('First hybrid rank already exists')
    import torch
    torch.set_num_threads(2)
    from app.retrieval.focused_candidate import FocusedCandidate
    from app.retrieval.section_scope import SectionTitleIndex
    from app.retrieval.reranker_provider import BGERerankerProvider
    from app.trial.assisted_chat import assemble
    provider=BGERerankerProvider(ROOT/'models/bge-reranker-v2-m3',use_fp16=False,max_length=1024)
    candidate=FocusedCandidate([],SectionTitleIndex([]),provider,documents=read(HERE/'cross_catalog_snapshot.json'));results=[]
    try:
        for row in read(REPORT/'recall.json'):
            channels={}
            for name,candidates in row['channels'].items():
                start=time.perf_counter();bundle=candidate.rank(row['question'],candidates);evidence,cards=assemble(bundle,row['question'])
                channels[name]={'bundle':bundle,'evidence_ids':[r.chunk_id for r in evidence.items],'cards':cards,'rank_ms':round((time.perf_counter()-start)*1000,2)}
            results.append({'id':row['id'],'question':row['question'],'channels':channels})
            save(REPORT/'results.json',results);print('WORD_RANK',row['id'],channels['hybrid']['evidence_ids'],flush=True)
    finally:provider.close()
    refs={r['id']:r for r in read(HERE/'cross_references_private.json')}
    refs.update(P01=refs['X01'],P02=refs['X02']);checks=[]
    for row in results:
        ref=refs[row['id']];channels={}
        for name,result in row['channels'].items():
            cards=result['cards'];channels[name]=(not cards and result['bundle']['bundle_status']==ref['expected_scope']) if ref['expected_chunk_id'] is None else bool(cards and cards[0]['file_name']==ref['target_name'] and all(t in cards[0]['excerpt'].replace(' ','') for t in ref['expected_terms']))
        checks.append({'id':row['id'],'source_and_text_matched':channels})
    save(REPORT/'assessment.json',{'checks':checks,'known_repairs_and_paraphrases_not_independent_business_holdout':True,'answer_generation_measured':False,'private_references_used_during_retrieval':False,'new_generation_calls':0,'delta_hash':m['candidate_hash']})
    verify()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['encode','recall','rank']);args=p.parse_args();globals()[args.stage]()
