"""Adapter over the existing frozen hybrid candidate, never a second corpus scanner."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from rank_bm25 import BM25Okapi
from app.bm25 import tokenize
from scripts.run_source_completion_trial import load_base,rows

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/shadow/browser_trial_20261019'
EVAL=ROOT/'evaluation/browser_trial_20261019'
LAYOUT=ROOT/'data/shadow/source_completion_20261018'
SCALAR=ROOT/'data/shadow/scalar_completion_20261019'


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def native_records():
    return list(rows(LAYOUT/'delta_records.jsonl'))+list(rows(SCALAR/'scalar_records.jsonl'))+list(rows(DATA/'scalar_records.jsonl'))


def validate_manifest():
    manifest=read(DATA/'manifest.json')
    for name,digest in manifest['artifact_sha256'].items():
        if sha(DATA/name)!=digest:raise RuntimeError('试用文件版本已变化：'+name)
    for name,digest in manifest['implementation_sha256'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('试用实现已变化，请重新验收后更新试用包。')
    for name,digest in manifest['inherited_manifest_sha256'].items():
        if sha(Path(name))!=digest:raise RuntimeError('继承的索引版本已变化。')
    for name,digest in manifest['inherited_artifact_sha256'].items():
        if sha(Path(name))!=digest:raise RuntimeError('继承的证据或向量已变化。')
    return manifest


def load_candidate():
    manifest=validate_manifest();base,corpus=load_base();delta=native_records()
    candidate=copy.copy(base);candidate.docs=dict(base.docs);candidate.atomic=dict(base.atomic);candidate.chunks=list(base.chunks)
    for r in delta:
        did=r['document_id'];scope=r.get('source_scope') or {}
        candidate.docs[did]={'document_id':did,'source_id':did,'source_version':r['source_version'],'source_path':r['source_path'],'file_name':r['file_name'],'file_type':r['file_type'],'document_type':'PROJECT_CASE','scope':{'project':scope.get('aliases',[])},'authority_level':'UNKNOWN'}
        candidate.atomic[r['evidence_id']]=r
        candidate.atomic[r['evidence_id']]['search_context']=(r.get('scalar') or r.get('layout') or {}).get('source_context',r['text'])
        candidate.chunks.append({'chunk_id':r['evidence_id'],'document_id':did,'source_path':r['source_path'],'file_name':r['file_name'],'section_path':r['heading_path'],'raw_text':r['text']})
    candidate.vectors=np.concatenate([base.vectors,np.load(LAYOUT/'dense_embeddings.npy'),np.load(SCALAR/'dense_embeddings.npy'),np.load(DATA/'dense_embeddings.npy')])
    candidate.bm25=BM25Okapi(corpus+[tokenize(' '.join([r['heading_path']]*5+[r['file_name']]*3+[r.get('retrieval_text') or (r.get('layout') or {}).get('source_context',r['text'])])) for r in delta])
    candidate.layout_records={r['evidence_id']:r for r in delta if r.get('layout') and not r.get('scalar')}
    candidate.scalar_records={r['evidence_id']:r for r in delta if r.get('scalar')};candidate.allow_gold_source_rescue=False
    candidate.candidate_hash=manifest['candidate_hash'];candidate.candidate_revision='ISOLATED_BROWSER_NATIVE_NO_GENERATION'
    return candidate


def retrieve_native(engine,question,vector,allowed):
    bm=np.asarray(engine.bm25.get_scores(tokenize(question)),dtype=np.float32);dense=engine.vectors@vector;scores={}
    for values in [bm,dense]:
        for rank,index in enumerate(np.argsort(-values).tolist(),1):scores[index]=scores.get(index,0)+1/(60+rank)
    order=sorted(scores,key=lambda i:(-scores[i],i))
    return [engine.chunks[i]['chunk_id'] for i in order if engine.chunks[i]['chunk_id'] in allowed][:8]
