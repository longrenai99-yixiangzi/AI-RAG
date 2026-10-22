"""Native-source delta trial. Build embeddings separately from the bounded-memory replay."""
from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['CUDA_VISIBLE_DEVICES']=''
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np
from rank_bm25 import BM25Okapi
from app.bm25 import tokenize
from app.config import Settings
from app.ingestion.layout_evidence import pdf_evidence,pptx_evidence
from app.layout_answers import layout_proposal
from app.retrieval.query_planner_v1 import plan_query
from app.trial.live_shadow_v25 import V25LiveShadow,_location

BASE=ROOT/'data/shadow/platform_compat_20261018'
OUT=ROOT/'data/shadow/source_completion_20261018'
REPORT=ROOT/'evaluation/source_completion_20261018'
PACK=Path(r'D:\example-vault/.ai-growth/reviews/20261018/首批8项原文核验与候选知识.json')


def rows(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():yield json.loads(line)


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)


def checkpoint(prefix,key,vectors=None):
    data_path=prefix.with_suffix('.npy');meta_path=prefix.with_suffix('.json')
    if vectors is None:
        if not data_path.exists() or not meta_path.exists():return []
        meta=json.loads(meta_path.read_text(encoding='utf-8'))
        if meta['key']!=key:raise RuntimeError('Embedding checkpoint input/model changed')
        data=np.load(data_path)
        if len(data)<meta['count']:raise RuntimeError('Incomplete embedding checkpoint')
        return data[:meta['count']].tolist()
    temporary=data_path.with_suffix('.npy.tmp')
    with temporary.open('wb') as stream:np.save(stream,np.asarray(vectors,dtype=np.float32))
    temporary.replace(data_path);save(meta_path,{'key':key,'count':len(vectors)})


def model_digest():
    model=Path(Settings.load().embedding_model);h=hashlib.sha256()
    for path in sorted([*model.glob('*.bin'),*model.glob('*.safetensors'),model/'config.json',model/'tokenizer.json']):
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def questions():
    baseline=json.loads((ROOT/'evaluation/platform_compat_20261018/replay.json').read_text(encoding='utf-8'))
    actual=[{'id':r['review_id'],'question':r['question'],'kind':'existing_real_question'} for r in baseline]
    holdouts=[
        ('HO-01','这份冷却塔选型案例比较了哪两种设备？','冷却塔'),
        ('HO-02','冷却塔比选中还有哪些方案可选？','冷却塔'),
        ('HO-03','暖通专业初设阶段要重点管控哪5个方面？','暖通'),
        ('HO-04','请列出暖通初步设计管控的五项要点','暖通'),
        ('HO-05','给排水的四个设计管控模块分别是什么？','给排水模块'),
        ('HO-06','给排水设计管控有哪些模块？','给排水模块'),
        ('HO-07','给排水设计管控有哪些要点？','给排水要点'),
        ('HO-08','目前EPC管理的问题主要体现在哪三个方面？','EPC困难'),
        ('NEG-01','暖通初步设计阶段管控有哪六个方面？','wrong_count'),
        ('NEG-02','暖通施工图阶段有哪五个管控方面？','wrong_stage'),
        ('NEG-03','空调水泵选型比选有哪些方案？','wrong_object'),
        ('NEG-04','暖通初步设计管控哪五个方面，并说明负责人？','compound_request'),
    ]
    return actual+[{'id':i,'question':q,'kind':'constructed_boundary' if i.startswith('NEG') else 'constructed_paraphrase','target':t} for i,q,t in holdouts]


class LocalDenseCPU:
    """BGE-M3's CLS pooling, with BF16 CPU weights to avoid a second 2.3GB FP32 model."""
    def __init__(self):
        import torch
        from transformers import AutoModel,AutoTokenizer
        self.torch=torch;torch.set_num_threads(2)
        path=str(Settings.load().embedding_model)
        self.tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True)
        self.model=AutoModel.from_pretrained(path,torch_dtype=torch.bfloat16,low_cpu_mem_usage=True,local_files_only=True).eval()

    def embed_query(self,text):
        with self.torch.inference_mode():
            encoded=self.tokenizer([text],padding=True,truncation=True,max_length=256,return_tensors='pt')
            vector=self.model(**encoded).last_hidden_state[:,0].float()
            return self.torch.nn.functional.normalize(vector,p=2,dim=1)[0].tolist()

    def close(self):
        del self.model;gc.collect()


def build(resume=False):
    if OUT.exists() and (not resume or (OUT/'manifest.json').exists()):raise RuntimeError('Delta candidate already exists; refusing overwrite')
    OUT.mkdir(parents=True,exist_ok=resume)
    pack=json.loads(PACK.read_text(encoding='utf-8'))
    inputs={s['path']:s['sha256'] for r in pack['records'] if r['evidence_status']=='EVIDENCE_LOCATED_NOT_OWNER_APPROVED' for s in r['original_sources']}
    all_records=[]
    if resume:
        all_records=list(rows(OUT/'native_records.jsonl'))
        for record in all_records:
            if inputs.get(record['source_path']) != record['source_version']:raise RuntimeError('Partial extraction version mismatch')
    for filename,digest in inputs.items():
        path=Path(filename)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('Source version changed: '+filename)
        if not resume:
            print('native_parse '+path.name,flush=True)
            all_records.extend(pdf_evidence(path) if path.suffix=='.pdf' else pptx_evidence(path))
    if not resume:(OUT/'native_records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in all_records),encoding='utf-8')
    indexed=[r for r in all_records if (r.get('layout') or {}).get('kind') in {'list_group','comparison_options'}]
    if not resume:(OUT/'delta_records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in indexed),encoding='utf-8')
    query_rows=questions()
    if not resume:save(OUT/'questions.json',query_rows)
    elif json.loads((OUT/'questions.json').read_text(encoding='utf-8'))!=query_rows:raise RuntimeError('Partial query set changed')
    print(f'native_records={len(all_records)} indexed_regions={len(indexed)}',flush=True)
    inputs_text=[r['heading_path']+'\n'+'；'.join(item['text'] for item in r['layout']['items']) for r in indexed]
    weight_digest=model_digest()
    key=hashlib.sha256(json.dumps([weight_digest,'BF16_CLS_FP32_NORM_256',inputs_text],ensure_ascii=False).encode()).hexdigest()
    query_key=hashlib.sha256(json.dumps([weight_digest,'BF16_CLS_FP32_NORM_256',[r['question'] for r in query_rows]],ensure_ascii=False).encode()).hexdigest()
    vectors=checkpoint(OUT/'delta_vector_checkpoint',key)
    query_vectors=checkpoint(OUT/'query_vector_checkpoint',query_key)
    print(f'checkpoint_resume delta={len(vectors)}/{len(indexed)} queries={len(query_vectors)}/{len(query_rows)}',flush=True)
    encoder=LocalDenseCPU()
    try:
        for i,text in enumerate(inputs_text[len(vectors):],len(vectors)+1):
            vector=encoder.embed_query(text)
            assert len(vector)==1024 and np.isfinite(vector).all() and abs(np.linalg.norm(vector)-1)<.001
            vectors.append(vector)
            checkpoint(OUT/'delta_vector_checkpoint',key,vectors)
            if i%10==0:print(f'delta_embed {i}/{len(indexed)}',flush=True)
        np.save(OUT/'dense_embeddings.npy',np.asarray(vectors,dtype=np.float32))
        assert all(len(encoder.tokenizer(r['question'])['input_ids'])<=256 for r in query_rows),'Query would be truncated'
        for r in query_rows[len(query_vectors):]:
            query_vectors.append(encoder.embed_query(r['question']));checkpoint(OUT/'query_vector_checkpoint',query_key,query_vectors)
        np.save(OUT/'query_vectors.npy',np.asarray(query_vectors,dtype=np.float32))
    finally:encoder.close()
    save(OUT/'manifest.json',{'status':'OFFLINE_NATIVE_SOURCE_DELTA_NOT_DEPLOYED','source_sha256':inputs,'native_records':len(all_records),'indexed_regions':len(indexed),'embedding_runtime':'BGE-M3 CPU BF16 weights; CLS pooling; FP32 normalized vectors; both comparison branches use identical query vectors','base_manifest_sha256':hashlib.sha256((BASE/'manifest.json').read_bytes()).hexdigest(),'candidate_answer_fields_read':False,'gold_runtime_injection':0,'formal_8000_touched':False,'live_8010_switched':False,'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}})
    print('delta build complete',flush=True)


class RowOffsets:
    def __init__(self,source,path):
        self.source=source
        self.db=sqlite3.connect(path)
        source_identity=json.dumps([str(source.resolve()),source.stat().st_size,source.stat().st_mtime_ns])
        if self.db.execute("select count(*) from sqlite_master where name='offsets'").fetchone()[0]:
            meta=self.db.execute("select count(*) from sqlite_master where name='complete'").fetchone()[0]
            if not meta or self.db.execute('select identity from complete').fetchone() != (source_identity,):
                raise RuntimeError('Incomplete or stale row-offset cache; refusing reuse')
            return
        self.db.execute('create table offsets (source text, start integer, length integer)')
        with source.open('rb') as stream:
            while True:
                start=stream.tell();line=stream.readline()
                if not line:break
                value=json.loads(line)
                self.db.execute('insert into offsets values (?,?,?)',(value.get('source_path'),start,len(line)))
        self.db.execute('create index source_offsets on offsets(source)')
        self.db.execute('create table complete (identity text)');self.db.execute('insert into complete values (?)',(source_identity,));self.db.commit()

    def for_candidates(self,candidates):
        paths={c.get('source_path') for c in candidates if c.get('source_path')}
        result=[]
        offsets=[]
        for path in paths:offsets.extend(self.db.execute('select start,length from offsets where source=?',(path,)))
        with self.source.open('rb') as stream:
            for start,length in sorted(offsets):
                stream.seek(start);result.append(json.loads(stream.read(length)))
        return result


def load_base():
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((BASE/'manifest.json').read_bytes()).hexdigest()==manifest['base_manifest_sha256']
    for name,digest in manifest['artifact_sha256'].items():
        if hashlib.sha256((OUT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Delta artifact changed: '+name)
    engine=V25LiveShadow.__new__(V25LiveShadow)
    base_manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in base_manifest['artifact_sha256'].items():
        h=hashlib.sha256()
        with (BASE/name).open('rb') as stream:
            for block in iter(lambda:stream.read(1048576),b''):h.update(block)
        if h.hexdigest()!=digest:raise RuntimeError('Base artifact changed: '+name)
    engine.manifest=base_manifest;engine.candidate_hash=base_manifest['candidate_hash'];engine.candidate_revision='PLATFORM_COMPAT_OFFLINE_BASE'
    engine.docs={str(r['document_id']):r for r in rows(BASE/'documents.jsonl')}
    engine.chunks=list(rows(BASE/'semantic_chunks.jsonl'))
    engine.atomic={str(c['chunk_id']):{'evidence_id':str(c['chunk_id']),'source_id':c.get('source_id') or c['document_id'],'source_version':c.get('source_version'),'document_id':c['document_id'],'section_id':c.get('section_id'),'table_id':c.get('table_id'),'source_path':c['source_path'],'file_name':c['file_name'],'file_type':c.get('file_type'),'heading_path':c.get('section_path') or '', 'location':_location(c.get('section_path') or '',c.get('table_id')),'text':c.get('raw_text') or c.get('retrieval_text') or '', 'raw_text':c.get('raw_text') or c.get('retrieval_text') or '', 'search_context':c.get('retrieval_text') or '', 'lineage_status':'LINEAGE_CONFIRMED'} for c in engine.chunks}
    engine.vectors=np.load(BASE/'dense_embeddings.npy',mmap_mode='r')
    compact_path=OUT/'base_bm25.compact.json'
    if not compact_path.exists():
        with (BASE/'bm25.json').open(encoding='utf-8') as src,compact_path.open('w',encoding='utf-8') as dst:
            for line in src:dst.write(line.strip())
    payload=json.loads(compact_path.read_text(encoding='utf-8'))
    assert payload['chunk_ids']==[c['chunk_id'] for c in engine.chunks]
    corpus=payload['corpus'];del payload
    for i,tokens in enumerate(corpus):corpus[i]=[sys.intern(t) for t in tokens]
    gc.collect();engine.bm25=BM25Okapi(corpus)
    engine.structured_rows=RowOffsets(BASE/'structured_rows.jsonl',OUT/'row_offsets.sqlite3')
    return engine,corpus


def encode_correction():
    correction=json.loads((REPORT/'owner_question_correction.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(Path(correction['source_path']).read_bytes()).hexdigest()==correction['source_sha256']
    encoder=LocalDenseCPU()
    try:
        question=correction['corrected_question']
        assert len(encoder.tokenizer(question)['input_ids'])<=256
        vector=np.asarray([encoder.embed_query(question)],dtype=np.float32)
        assert vector.shape==(1,1024) and np.isfinite(vector).all() and abs(np.linalg.norm(vector)-1)<.001
        np.save(REPORT/'corrected_question_vector.npy',vector)
        save(REPORT/'corrected_question_input.json',{'id':'LS-CUR-028-CORRECTED','question':question,'kind':'owner_corrected_real_question','source_sha256':correction['source_sha256'],'correction_sha256':hashlib.sha256((REPORT/'owner_question_correction.json').read_bytes()).hexdigest(),'model_sha256':model_digest(),'vector_sha256':hashlib.sha256((REPORT/'corrected_question_vector.npy').read_bytes()).hexdigest()})
    finally:encoder.close()
    print('corrected question encoded separately; frozen 28-question set unchanged',flush=True)


def replay(corrected=False):
    print('loading isolated base; model process already exited',flush=True)
    base,corpus=load_base();delta=list(rows(OUT/'delta_records.jsonl'))
    candidate=copy.copy(base);candidate.docs=dict(base.docs);candidate.atomic=dict(base.atomic);candidate.chunks=list(base.chunks)
    for record in delta:
        did=record['document_id'];candidate.docs[did]={'document_id':did,'source_id':did,'source_version':record['source_version'],'source_path':record['source_path'],'file_name':record['file_name'],'file_type':record['file_type'],'document_type':'TRAINING' if record['file_type']=='.pptx' else 'PROJECT_CASE','scope':{},'authority_level':'UNKNOWN'}
        candidate.atomic[record['evidence_id']]=record
        candidate.atomic[record['evidence_id']]['search_context']=(record.get('layout') or {}).get('source_context',record['text'])
        candidate.chunks.append({'chunk_id':record['evidence_id'],'document_id':did,'source_id':did,'source_version':record['source_version'],'source_path':record['source_path'],'file_name':record['file_name'],'section_path':record['heading_path'],'raw_text':record['text'],'knowledge_type':{'value':'native_layout'}})
    candidate.vectors=np.concatenate([base.vectors,np.load(OUT/'dense_embeddings.npy')])
    delta_corpus=[tokenize(' '.join([r['heading_path']]*5+[r['file_name']]*3+[(r.get('layout') or {}).get('source_context',r['text'])])) for r in delta]
    candidate.bm25=BM25Okapi(corpus+delta_corpus);candidate.layout_records={r['evidence_id']:r for r in delta}
    candidate.candidate_hash=hashlib.sha256((base.candidate_hash+hashlib.sha256((OUT/'delta_records.jsonl').read_bytes()).hexdigest()).encode()).hexdigest();candidate.candidate_revision='NATIVE_LAYOUT_DELTA_OFFLINE_NOT_DEPLOYED'
    if corrected:
        query=json.loads((REPORT/'corrected_question_input.json').read_text(encoding='utf-8'))
        assert hashlib.sha256((REPORT/'owner_question_correction.json').read_bytes()).hexdigest()==query['correction_sha256']
        assert hashlib.sha256((REPORT/'corrected_question_vector.npy').read_bytes()).hexdigest()==query['vector_sha256']
        query_rows=[query];query_vectors=np.load(REPORT/'corrected_question_vector.npy')
    else:
        query_rows=json.loads((OUT/'questions.json').read_text(encoding='utf-8'));query_vectors=np.load(OUT/'query_vectors.npy')
    results=[];prefix='corrected_question_' if corrected else ''
    for i,(query,vector) in enumerate(zip(query_rows,query_vectors,strict=True),1):
        before=base.run(query['question'],{},query_vector=vector.tolist(),include_trace=True)
        supported=layout_proposal(query['question'],plan_query(query['question']).to_dict(),delta) is not None
        after=candidate.run(query['question'],{},query_vector=vector.tolist(),include_trace=True) if supported else before
        result={**query,'native_route_supported':supported,'baseline':before,'candidate':after,'status_regression':before['v2_answer_status']=='ANSWERED' and after['v2_answer_status']!='ANSWERED'}
        results.append(result);save(REPORT/(prefix+'replay.json'),results)
        print(f"replay {i}/{len(query_rows)} {query['id']} {before['v2_answer_status']} -> {after['v2_answer_status']}",flush=True)
    save(REPORT/(prefix+'summary.json'),{'status':'OFFLINE_REVIEW_REQUIRED','questions':len(results),'status_regressions':sum(r['status_regression'] for r in results),'base_candidate_hash':base.candidate_hash,'candidate_hash':candidate.candidate_hash,'real_questions':sum(r['kind'] in {'existing_real_question','owner_corrected_real_question'} for r in results),'native_route_count':sum(r['native_route_supported'] for r in results),'formal_8000_touched':False,'live_8010_switched':False,'new_native_path_answer_lookup':False,'legacy_fallback_retains_historical_rules':True,'provider_http_calls':0})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['build','replay','encode-correction','replay-correction']);parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    if args.mode=='build':build(args.resume)
    elif args.mode=='encode-correction':encode_correction()
    else:replay(corrected=args.mode=='replay-correction')
