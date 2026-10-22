"""Build the small native delta over existing indexes, then replay the frozen 54 questions."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from app.ingestion.scalar_evidence import extract_scalars
from app.trial.native_workbench_candidate import DATA,EVAL,LAYOUT,SCALAR,read,sha,load_candidate
from app.trial.native_workbench_worker import answer
from scripts.run_source_completion_trial import LocalDenseCPU,model_digest,save,checkpoint


def build(resume=False):
    if (DATA/'manifest.json').exists() or DATA.exists() and not resume:raise RuntimeError('Refusing frozen candidate overwrite')
    DATA.mkdir(parents=True,exist_ok=resume)
    configs=read(EVAL/'blind_sources_verified.json')+read(EVAL/'blind2_sources_verified.json')
    parents=[];records=[]
    for config in configs:
        native,facts=extract_scalars(config);parents+=native;records+=facts
    queries=read(SCALAR/'questions.json')+read(EVAL/'blind_protocol.json')['questions']+read(EVAL/'blind_round2_protocol.json')['questions']
    if not resume:
        for name,values in [('native_parents.jsonl',parents),('scalar_records.jsonl',records)]:
            (DATA/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values),encoding='utf-8')
        save(DATA/'source_scope.json',configs);save(DATA/'questions.json',queries)
    else:
        assert read(DATA/'questions.json')==queries
        assert [json.loads(l) for l in (DATA/'scalar_records.jsonl').read_text(encoding='utf-8').splitlines()]==records
    model=model_digest();assert model==read(SCALAR/'manifest.json')['embedding_model_sha256']
    prior_queries=read(SCALAR/'questions.json');known={r['question']:v for r,v in zip(prior_queries,np.load(SCALAR/'query_vectors.npy'),strict=True)}
    texts=[r['retrieval_text'] for r in records];key=hashlib.sha256(json.dumps([model,texts],ensure_ascii=False).encode()).hexdigest()
    vectors=checkpoint(DATA/'vector_checkpoint',key)
    qkey=hashlib.sha256(json.dumps([model,[q['question'] for q in queries]],ensure_ascii=False).encode()).hexdigest();qvectors=checkpoint(DATA/'query_checkpoint',qkey)
    encoder=LocalDenseCPU()
    try:
        for text in texts[len(vectors):]:
            assert len(encoder.tokenizer(text)['input_ids'])<=256
            vectors.append(encoder.embed_query(text));checkpoint(DATA/'vector_checkpoint',key,vectors)
        for q in queries[len(qvectors):]:
            assert len(encoder.tokenizer(q['question'])['input_ids'])<=256
            qvectors.append(known[q['question']].tolist() if q['question'] in known else encoder.embed_query(q['question']));checkpoint(DATA/'query_checkpoint',qkey,qvectors)
            print(f'query {len(qvectors)}/{len(queries)}',flush=True)
    finally:encoder.close()
    np.save(DATA/'dense_embeddings.npy',np.asarray(vectors,dtype=np.float32));np.save(DATA/'query_vectors.npy',np.asarray(qvectors,dtype=np.float32))
    engine_files=['app/ingestion/layout_evidence.py','app/ingestion/scalar_evidence.py','app/scalar_answers.py','app/layout_answers.py','app/retrieval/query_planner_v1.py','app/trial/live_shadow_v25.py','app/verified_answer_engine_v2.py','scripts/run_verified_answer_engine_v2.py','scripts/run_source_completion_trial.py','app/trial/native_workbench_candidate.py','app/trial/native_workbench_worker.py']
    manifests=[LAYOUT/'manifest.json',SCALAR/'manifest.json',ROOT/'data/shadow/platform_compat_20261018/manifest.json']
    inherited=[LAYOUT/'delta_records.jsonl',LAYOUT/'dense_embeddings.npy',SCALAR/'scalar_records.jsonl',SCALAR/'dense_embeddings.npy']
    metadata={'status':'ISOLATED_BROWSER_CANDIDATE_NOT_DEPLOYED','new_native_parents':len(parents),'new_scalar_records':len(records),'sources':configs,'model_sha256':model,
              'implementation_sha256':{p:sha(ROOT/p) for p in engine_files},'inherited_manifest_sha256':{str(p):sha(p) for p in manifests},'inherited_artifact_sha256':{str(p):sha(p) for p in inherited},
              'artifact_sha256':{p.name:sha(p) for p in DATA.iterdir() if p.is_file()},'blind_first_pass_not_rewritten':True,'formal_switch':False}
    metadata['candidate_hash']=hashlib.sha256(json.dumps(metadata,sort_keys=True,ensure_ascii=False).encode()).hexdigest();save(DATA/'manifest.json',metadata)
    print(f'browser delta ready: {len(records)} native facts; {len(queries)} queries',flush=True)


def replay():
    engine=load_candidate();results=[];queries=read(DATA/'questions.json')
    for q,v in zip(queries,np.load(DATA/'query_vectors.npy'),strict=True):
        result=answer(engine,q['question'],v)
        results.append({**q,'result':result});save(EVAL/'replay.json',results)
        print(f'{len(results)}/{len(queries)} {q["id"]} {result["status"]}',flush=True)
    save(EVAL/'replay_summary.json',{'questions':len(results),'candidate_hash':engine.candidate_hash,'no_provider_calls':True,'formal_switch':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['build','replay']);parser.add_argument('--resume',action='store_true');a=parser.parse_args()
    build(a.resume) if a.mode=='build' else replay()
