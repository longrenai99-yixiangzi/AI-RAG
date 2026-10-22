"""Build an isolated filtered trial index and replay existing real questions locally."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['CUDA_VISIBLE_DEVICES'] = ''
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from rank_bm25 import BM25Okapi
from app.bm25 import tokenize
from app.config import Settings
from app.knowledge_contract import KnowledgeContract
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.trial.live_shadow_v25 import V25LiveShadow, REMEDIATION_MANIFESTS

OUT = ROOT/'data/shadow/platform_compat_20261018'
REPORT = ROOT/'evaluation/platform_compat_20261018'


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def inherited_approvals():
    approved = {}
    for manifest_path in REMEDIATION_MANIFESTS:
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('status') != 'DEV_REMEDIATION_EMBEDDED_NOT_RELEASED':
            continue
        vector_path = Path(manifest['dense_embeddings']['path'])
        sources = manifest.get('sources') or [manifest.get('source') or {}]
        sources = {str(Path(s.get('source_path','')).resolve()).casefold():s for s in sources if s.get('approval_status') == 'APPROVED'}
        for doc in jsonl(vector_path.parent/'documents.jsonl'):
            path = Path(doc['source_path'])
            approval = sources.get(str(path.resolve()).casefold())
            if approval and path.is_file() and approval.get('sha256') == hashlib.sha256(path.read_bytes()).hexdigest():
                approved[str(doc['document_id'])] = {'manifest':str(manifest_path), 'approved_cache_path':str(path), 'sha256':approval['sha256']}
        break
    return approved


def build_candidate(base, contract):
    inherited = inherited_approvals()
    admitted = {}
    excluded = []
    for key, doc in base.docs.items():
        path = Path(doc['source_path'])
        allowed, reason = contract.decision(path)
        # Existing approval is reused only for the exact, still-present approved cache version.
        if not allowed and key in inherited and reason not in {'navigation_only','excluded_root'}:
            allowed, reason = True, 'existing_explicit_source_approval'
        if allowed:
            admitted[key] = {'reason':reason, 'approval':inherited.get(key)}
        else:
            excluded.append({'document_id':key, 'source_path':str(path), 'reason':reason})
    candidate = copy.copy(base)
    candidate.docs = {key:doc for key,doc in base.docs.items() if key in admitted}
    indices = [i for i,c in enumerate(base.chunks) if str(c['document_id']) in admitted]
    if not indices:
        raise RuntimeError('No eligible trial chunks; existing indexes retained')
    candidate.chunks = [base.chunks[i] for i in indices]
    candidate.vectors = base.vectors[indices].copy()
    ids = {str(c['chunk_id']) for c in candidate.chunks}
    candidate.atomic = {key:record for key,record in base.atomic.items() if key in ids}
    candidate.structured_rows = [r for r in base.structured_rows if str(r.get('document_id')) in admitted]
    weighted = [' '.join([str(r.get('section_path') or '')]*5+[str(r.get('file_name') or '')]*3+[str((r.get('knowledge_type') or {}).get('value') or '')]*2+[str(r.get('raw_text') or '')]) for r in candidate.chunks]
    corpus = [tokenize(text) or ['_empty_'] for text in weighted]
    candidate.bm25 = BM25Okapi(corpus)
    candidate.candidate_hash = hashlib.sha256((base.candidate_hash+contract.path.read_text(encoding='utf-8')+''.join(sorted(ids))).encode()).hexdigest()
    candidate.candidate_revision = 'PLATFORM_COMPAT_OFFLINE_NOT_DEPLOYED'
    OUT.mkdir(parents=True, exist_ok=False)
    for name, rows in [('documents',list(candidate.docs.values())),('semantic_chunks',candidate.chunks),('structured_rows',candidate.structured_rows)]:
        (OUT/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    np.save(OUT/'dense_embeddings.npy',candidate.vectors)
    save_json(OUT/'bm25.json',{'chunk_ids':[c['chunk_id'] for c in candidate.chunks], 'corpus':corpus})
    manifest = {'status':'OFFLINE_CANDIDATE_NOT_DEPLOYED', 'base_candidate_hash':base.candidate_hash, 'candidate_hash':candidate.candidate_hash, 'contract_sha256':hashlib.sha256(contract.path.read_bytes()).hexdigest(), 'documents_before':len(base.docs), 'documents_after':len(candidate.docs), 'chunks_before':len(base.chunks), 'chunks_after':len(candidate.chunks), 'excluded_documents':excluded, 'admission':admitted, 'vector_values_reused_without_reembedding':True, 'bm25_rebuilt':True, 'formal_index_written':False, 'live_8010_switched':False}
    manifest['artifact_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}
    save_json(OUT/'manifest.json',manifest)
    return candidate, manifest


def citation_checks(result, engine):
    checks = []
    for cite in result.get('v2_citations') or []:
        ids = cite.get('evidence_ids') or [cite.get('evidence_id')]
        evidence = [engine.atomic[str(key)] for key in ids if str(key) in engine.atomic]
        path = cite.get('source_path') or (evidence[0].get('source_path') if evidence else '')
        checks.append({'source_path':path, 'exists':bool(path and Path(path).is_file()), 'has_location':bool(cite.get('display_location') or cite.get('location') or cite.get('section_path') or (evidence and evidence[0].get('location'))), 'citation':cite})
    return checks


def main():
    if OUT.exists():
        raise RuntimeError('Isolated candidate already exists; do not overwrite a reviewed candidate')
    contract = KnowledgeContract(Settings.load().vault_root)
    print('Loading existing frozen evidence and vector values; no external model requests',flush=True)
    base = V25LiveShadow()
    candidate, manifest = build_candidate(base,contract)
    print(json.dumps({k:manifest[k] for k in ['documents_before','documents_after','chunks_before','chunks_after']},ensure_ascii=False),flush=True)
    review = json.loads((ROOT/'evaluation/knowledge_os_v2_6/v2_6_2_current_candidate_live_shadow_manual_review.json').read_text(encoding='utf-8'))
    questions = list({r['question']:r for r in review['records']}.values())
    encoder = BGEM3DenseProvider(Settings.load().embedding_model, batch_size=1)
    results = []
    try:
        for i, record in enumerate(questions,1):
            question = record['question']
            vector = encoder.embed_query(question)
            before = base.run(question,{},query_vector=vector,include_trace=True)
            after = candidate.run(question,{},query_vector=vector,include_trace=True)
            citations = citation_checks(after,candidate)
            result = {'review_id':record['review_id'], 'question':question, 'baseline':before, 'candidate':after, 'same_answer':before.get('v2_answer')==after.get('v2_answer'), 'status_regression':before.get('v2_answer_status') in {'ANSWERED','FACT_RESULT'} and after.get('v2_answer_status') not in {'ANSWERED','FACT_RESULT'}, 'citation_checks':citations, 'historical_reference_answer':record.get('answer'), 'historical_reference_is_current_gold':False}
            results.append(result)
            save_json(REPORT/'replay.json',results)
            print(f"replay {i}/{len(questions)} {record['review_id']} {before.get('v2_answer_status')} -> {after.get('v2_answer_status')}",flush=True)
    finally:
        encoder.close()
    summary = {'questions':len(results), 'same_answer':sum(r['same_answer'] for r in results), 'status_regressions':sum(r['status_regression'] for r in results), 'candidate_statuses':dict(Counter(r['candidate'].get('v2_answer_status') for r in results)), 'missing_citation_files':sum(not c['exists'] for r in results for c in r['citation_checks']), 'citations_without_location':sum(not c['has_location'] for r in results for c in r['citation_checks']), 'business_correctness':'PENDING_REVIEW; structural validation is not business correctness', 'deployment':'NOT_DEPLOYED', 'formal_index_written':False, 'provider_http_calls':0}
    summary['release_gate'] = 'BLOCKED_REQUIRES_BUSINESS_REVIEW' if not summary['status_regressions'] else 'BLOCKED_REGRESSION'
    save_json(REPORT/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
