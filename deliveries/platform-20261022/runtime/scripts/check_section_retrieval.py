"""Offline recall and subsection rerank over the existing 8878 candidate; no generation."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='')
import numpy as np
from app.bm25 import tokenize
from app.retrieval.anchored_sections import sections_for,expand_candidates

OUT=ROOT/'evaluation/section_retrieval_20261019'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare():
    if OUT.exists():raise ValueError('Do not overwrite the first diagnostic inputs')
    OUT.mkdir()
    packet=read(ROOT/'evaluation/unified_colleague_flow_20261019/generation2_requests_for_review.json')
    md=Path(packet[0]['private_binding'][0]['source_path'])
    from app.ingestion.loaders.markdown_loader import MarkdownLoader
    old=MarkdownLoader().load(md,'section-diagnostic')
    original=Path(old.front_matter['source_path'])
    sections=sections_for(md,original);save('sections.json',sections)
    questions=[
        ('K01','给排水设计管理的四项管控要点是什么？请与业务板块区分。','7、给排水专业','7.1'),
        ('K02','暖通初步设计阶段应重点关注什么？','6、暖通空调专业','6.3'),
        ('D03','给排水方案阶段，地方政策和市政条件需要核查哪些方面？','7、给排水专业','7.2'),
        ('D04','暖通施工图阶段有哪些设计管控要点？','6、暖通空调专业','6.4'),
        ('D05','给排水初步设计阶段，成本控制有哪些方向？','7、给排水专业','7.3'),
        ('D06','给排水专业的四大业务板块分别是什么？','7、给排水专业','7.1'),
    ]
    save('questions.json',[{'id':i,'question':q,'kind':'KNOWN_TOPIC_DEVELOPMENT_DIAGNOSTIC_NOT_BLIND_GOLD'} for i,q,_,_ in questions])
    save('references_private.json',[{'id':i,'target_section_id':next(s['section_id'] for s in sections if parent in s['heading_path'] and s['title'].startswith(prefix))} for i,q,parent,prefix in questions])
    save('input_seal.json',{str(p):sha(p) for p in [md,original,OUT/'sections.json',OUT/'questions.json',OUT/'references_private.json',Path(__file__),ROOT/'app/retrieval/anchored_sections.py']})
    save('structure_summary.json',{'legacy_markdown_blocks':len(old.blocks),'new_section_packages':len(sections),'word_declared':sum(s['heading_origin']=='WORD_DECLARED_OUTLINE' for s in sections),'inferred_numbered':sum(s['heading_origin']!='WORD_DECLARED_OUTLINE' for s in sections),'originals_modified':False,'new_document_embeddings':0,'real_generation_calls':0})
    from scripts.run_source_completion_trial import LocalDenseCPU
    encoder=LocalDenseCPU();queries=read(OUT/'questions.json');vectors=[]
    try:
        for q in queries:
            assert len(encoder.tokenizer(q['question'])['input_ids'])<=256
            vectors.append(encoder.embed_query(q['question']));print('QUERY_VECTOR',q['id'],flush=True)
    finally:encoder.close()
    np.save(OUT/'query_vectors.npy',np.asarray(vectors,dtype=np.float32))
    save('query_vector_seal.json',{'questions_sha256':sha(OUT/'questions.json'),'vectors_sha256':sha(OUT/'query_vectors.npy'),'encoding':'existing LocalDenseCPU BF16 CLS FP32 normalized; CPU only'})


def verify():
    assert all(sha(Path(p))==value for p,value in read(OUT/'input_seal.json').items()),'diagnostic inputs changed'
    seal=read(OUT/'query_vector_seal.json')
    assert seal['questions_sha256']==sha(OUT/'questions.json') and seal['vectors_sha256']==sha(OUT/'query_vectors.npy')


def recall():
    verify()
    if (OUT/'first_recall.json').exists():raise ValueError('First recall is immutable')
    from app.trial.native_workbench_candidate import load_candidate
    started=time.perf_counter();engine=load_candidate();loaded_ms=(time.perf_counter()-started)*1000
    vectors=np.load(OUT/'query_vectors.npy');results=[]
    for q,vector in zip(read(OUT/'questions.json'),vectors,strict=True):
        start=time.perf_counter();bm=np.asarray(engine.bm25.get_scores(tokenize(q['question'])),dtype=np.float32);dense=engine.vectors@vector;scores={}
        for values in (bm,dense):
            for rank,index in enumerate(np.argsort(-values).tolist(),1):scores[index]=scores.get(index,0)+1/(60+rank)
        order=sorted(scores,key=lambda i:(-scores[i],i))[:50]
        candidates=[{**engine.atomic[engine.chunks[i]['chunk_id']],'score':scores[i],'role':'DIRECT'} for i in order]
        results.append({**q,'full_corpus_chunks':len(engine.chunks),'recall_ms':round((time.perf_counter()-start)*1000,2),'candidate_evidence':candidates})
        print('FULL_CORPUS_RECALL',q['id'],len(candidates),flush=True)
    save('first_recall.json',results);save('recall_seal.json',{'first_recall_sha256':sha(OUT/'first_recall.json'),'candidate_hash':engine.candidate_hash,'load_ms':loaded_ms,'source_filter_applied':False,'reference_answers_loaded':False,'candidate_entry':'existing native_workbench_candidate.load_candidate; not 8010 default V2 runtime'})


def rerank():
    verify()
    if (OUT/'first_rerank.json').exists():raise ValueError('First rerank is immutable')
    assert sha(OUT/'first_recall.json')==read(OUT/'recall_seal.json')['first_recall_sha256']
    import torch
    torch.set_num_threads(2)
    from app.retrieval.reranker_provider import BGERerankerProvider
    provider=BGERerankerProvider(ROOT/'models/bge-reranker-v2-m3',use_fp16=False,max_length=1024)
    provider.load();tokenizer=provider.model.tokenizer
    sections=read(OUT/'sections.json');results=[]
    try:
        for row in read(OUT/'first_recall.json'):
            start=time.perf_counter();candidates=expand_candidates(row['candidate_evidence'],sections)
            passages=[];owners=[];max_pair_tokens=0
            for i,c in enumerate(candidates):
                text=(c.get('heading_path') or '')+'\n'+c['text']
                offsets=tokenizer(text,add_special_tokens=False,return_offsets_mapping=True)['offset_mapping']
                for n in range(0,len(offsets),700):
                    part=offsets[n:n+700];passage=text[part[0][0]:part[-1][1]]
                    size=len(tokenizer.encode(row['question'],add_special_tokens=False))+len(tokenizer.encode(passage,add_special_tokens=False))+tokenizer.num_special_tokens_to_add(pair=True)
                    assert size<=1024,'reranker pair would be truncated'
                    max_pair_tokens=max(max_pair_tokens,size);passages.append(passage);owners.append(i)
            scores=provider.score(row['question'],passages);best={}
            for i,score in zip(owners,scores,strict=True):best[i]=max(best.get(i,float('-inf')),score)
            ranked=[{**candidates[i],'reranker_score':best[i]} for i in sorted(best,key=lambda i:-best[i])]
            results.append({'id':row['id'],'question':row['question'],'expanded_candidates':len(candidates),'scoring_passages':len(passages),'max_pair_tokens':max_pair_tokens,'truncated_pairs':0,'rerank_ms':round((time.perf_counter()-start)*1000,2),'candidate_evidence':ranked[:8],'all_ranked_ids':[c['evidence_id'] for c in ranked]})
            print('SECTION_RERANK',row['id'],ranked[0].get('heading_path'),flush=True)
    finally:provider.close()
    save('first_rerank.json',results)
    # References are opened only after retrieval/reranking is complete.
    references={q['id']:q['target_section_id'] for q in read(OUT/'references_private.json')}
    summary=[]
    for row in results:
        target='section-'+references[row['id']];rank=next((i for i,e in enumerate(row['all_ranked_ids'],1) if e==target),None)
        summary.append({'id':row['id'],'expected_section_rank':rank,'target_in_top8':rank is not None and rank<=8,'first_section_path':row['candidate_evidence'][0].get('heading_path')})
    save('assessment.json',{'queries':summary,'full_corpus_recall':True,'new_document_embeddings':0,'new_query_embeddings':len(results),'public_model_calls':0,'new_generation_calls':0,'reranker_pairs_truncated':0,'business_accuracy_not_measured':True,'owner_accepted':False,'runtime_switch':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','recall','rerank']);a=p.parse_args()
    globals()[a.stage]()
