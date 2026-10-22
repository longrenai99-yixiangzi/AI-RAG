"""Isolated scalar delta and mixed real/holdout replay; originals and live services stay read-only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize
from app.ingestion.scalar_evidence import extract_scalars
from app.scalar_answers import scalar_proposal
from app.layout_answers import layout_proposal,layout_count_mismatch
from app.retrieval.query_planner_v1 import plan_query
from scripts.run_source_completion_trial import LocalDenseCPU,checkpoint,load_base,model_digest,rows,save

PREVIOUS=ROOT/'data/shadow/source_completion_20261018'
OUT=ROOT/'data/shadow/scalar_completion_20261019'
REPORT=ROOT/'evaluation/scalar_completion_20261019'
REVIEW=ROOT/'evaluation/source_completion_20261018/owner_review_reconciliation.json'


def sources():
    by_id={r['id']:r for r in json.loads(REVIEW.read_text(encoding='utf-8'))['records']}
    scope={
        'LS-CUR-018':{'aliases':['数字经济产业园项目一期工程','数字经济产业园项目','数字经济产业园'],'phases':['一期'],'admitted_locations':[{'slide':8}]},
        'LS-CUR-020':{'aliases':['旧改标包27项目','丰台区长辛店项目','丰台区长辛店街道工程总承包（EPC）项目'],'packages':[27],'admitted_locations':[{'slide':9}],'source_anomaly':'同页表格合计与正文合同金额不一致；保留源内异常，合同金额按正文及既有确认，未改原表。'},
        'LS-CUR-025':{'aliases':['泸州市垃圾焚烧发电厂扩能工程项目','泸州垃圾焚烧发电厂扩能项目'],'admitted_locations':[{'table':16}]},
        'LS-CUR-024':{'aliases':['西安医学院第一附属医院沣东院区（一期）项目','沣东医院项目','沣东院区项目'],'phases':['一期'],'admitted_locations':[{'page':33}],'source_anomaly':'材料同页开工和地下室封顶日期先后存在异常；这里只转述材料列示的提前天数，不能据此证明因果。'},
    }
    result=[]
    for rid,extra in scope.items():
        original=by_id[rid]['original_sources'][0];project=plan_query(by_id[rid]['question']).project[0]
        aliases=list(dict.fromkeys([project,*extra['aliases']]))
        config={'path':original['path'],'sha256':original['sha256'],'scope':{'project':project,'aliases':aliases,'phases':extra.get('phases',[]),'packages':extra.get('packages',[]),'source_anomaly':extra.get('source_anomaly','')},'admitted_locations':extra['admitted_locations'],'scope_basis':'Existing Owner-confirmed source and location; metadata only, no answer field imported.'}
        if rid=='LS-CUR-025':
            config['unit_confirmations']=[{'source_sha256':original['sha256'],'location':{'table':16,'row':2,'column':3},'raw_unit':'W','unit':'万元','authority':'PRIOR_OWNER_CONFIRMED_EXACT_CELL','record':str(REVIEW),'primary_id':'LS-CUR-004'}]
        result.append(config)
    return result


def question_set():
    old=json.loads((PREVIOUS/'questions.json').read_text(encoding='utf-8'))
    corrected=json.loads((ROOT/'evaluation/source_completion_20261018/corrected_question_input.json').read_text(encoding='utf-8'))
    extra=[
        ('SC-H01','数字经济产业园项目一期工程，初设概算总投资是多少万元？'),
        ('SC-H02','数字经济产业园项目一期工程，工程费是多少万元？'),
        ('SC-H03','数字经济产业园一期初设概算费用是多少亿元？'),
        ('SC-H04','旧改标包27项目的合同金额是多少万元？'),
        ('SC-H05','泸州市垃圾焚烧发电厂扩能工程项目的填埋场边坡支护优化，创效金额是多少万元？'),
        ('SC-H06','沣东医院项目一期，地下室封顶提前多少天？'),
        ('SC-H07','数字经济产业园一期初设概算总投资、工程费和初设概算费用分别是多少万元？'),
        ('SC-H08','沣东医院项目一期，主体结构提前多少天封顶？'),
        ('SC-N01','数字经济产业园二期初设概算费用是多少万元？'),
        ('SC-N02','丰台区长辛店项目标包28，合同金额是多少万元？'),
        ('SC-N03','泸州市垃圾焚烧发电厂扩能工程项目，填埋场防渗结构优化，创效多少万元？'),
        ('SC-N04','数字经济产业园一期合同金额是多少万元？'),
        ('SC-N05','武汉数字经济产业园项目一期工程，初设概算费用是多少万元？'),
        ('SC-N06','泸州市垃圾焚烧发电厂扩能工程项目，填埋场边坡支护优化，创效多少万元，并说明负责人？'),
    ]
    return [*old,corrected,*[{'id':i,'question':q,'kind':'scalar_boundary' if i.startswith('SC-N') else 'scalar_holdout'} for i,q in extra]]


def build(resume=False):
    if (OUT/'manifest.json').exists() or (OUT.exists() and not resume):raise RuntimeError('Refusing overwrite of scalar candidate')
    OUT.mkdir(parents=True,exist_ok=resume);REPORT.mkdir(parents=True,exist_ok=True)
    configs=sources();parents=[];facts=[]
    for cfg in configs:
        native,extracted=extract_scalars(cfg);parents+=native;facts+=extracted
        print(f'native source read: {Path(cfg["path"]).name}; parents={len(native)} scalar_facts={len(extracted)}',flush=True)
    if not resume:
        save(OUT/'source_scope.json',configs)
        for name,records in [('native_parents.jsonl',parents),('scalar_records.jsonl',facts)]:
            (OUT/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
        save(OUT/'questions.json',question_set())
    else:
        assert json.loads((OUT/'source_scope.json').read_text(encoding='utf-8'))==configs
        assert list(rows(OUT/'scalar_records.jsonl'))==facts
        assert json.loads((OUT/'questions.json').read_text(encoding='utf-8'))==question_set()
    queries=question_set();known={r['question']:v for r,v in zip(json.loads((PREVIOUS/'questions.json').read_text(encoding='utf-8')),np.load(PREVIOUS/'query_vectors.npy'),strict=True)}
    cq=json.loads((ROOT/'evaluation/source_completion_20261018/corrected_question_input.json').read_text(encoding='utf-8'))
    known[cq['question']]=np.load(ROOT/'evaluation/source_completion_20261018/corrected_question_vector.npy')[0]
    digest=model_digest();texts=[r['retrieval_text'] for r in facts]
    prior_questions=[r['question'] for r in json.loads((PREVIOUS/'questions.json').read_text(encoding='utf-8'))]
    expected_key=hashlib.sha256(json.dumps([digest,'BF16_CLS_FP32_NORM_256',prior_questions],ensure_ascii=False).encode()).hexdigest()
    assert json.loads((PREVIOUS/'query_vector_checkpoint.json').read_text(encoding='utf-8'))['key']==expected_key
    assert cq['model_sha256']==digest
    key=hashlib.sha256(json.dumps([digest,'BF16_CLS_FP32_NORM_256',texts],ensure_ascii=False).encode()).hexdigest()
    vectors=checkpoint(OUT/'vector_checkpoint',key)
    encoder=LocalDenseCPU()
    try:
        for i,text in enumerate(texts[len(vectors):],len(vectors)+1):
            assert len(encoder.tokenizer(text)['input_ids'])<=256
            vectors.append(encoder.embed_query(text));checkpoint(OUT/'vector_checkpoint',key,vectors)
            print(f'scalar embed {i}/{len(texts)}',flush=True)
        np.save(OUT/'dense_embeddings.npy',np.asarray(vectors,dtype=np.float32))
        qkey=hashlib.sha256(json.dumps([digest,[r['question'] for r in queries]],ensure_ascii=False).encode()).hexdigest()
        query_vectors=checkpoint(OUT/'query_checkpoint',qkey)
        for i,q in enumerate(queries[len(query_vectors):],len(query_vectors)+1):
            assert len(encoder.tokenizer(q['question'])['input_ids'])<=256
            query_vectors.append(known[q['question']].tolist() if q['question'] in known else encoder.embed_query(q['question']))
            checkpoint(OUT/'query_checkpoint',qkey,query_vectors)
            print(f'query vector {i}/{len(queries)}',flush=True)
        np.save(OUT/'query_vectors.npy',np.asarray(query_vectors,dtype=np.float32))
    finally:encoder.close()
    assert np.isfinite(vectors).all() and np.isfinite(query_vectors).all()
    save(OUT/'manifest.json',{'status':'OFFLINE_SCALAR_NOT_DEPLOYED','native_parent_records':len(parents),'scalar_fact_records':len(facts),'sources':configs,'embedding_model_sha256':digest,'previous_manifest_sha256':hashlib.sha256((PREVIOUS/'manifest.json').read_bytes()).hexdigest(),'no_answer_fields_imported':True,'new_facts_not_auto_approved':True,'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}})
    print('scalar build complete',flush=True)


def replay():
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['artifact_sha256'].items():
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==digest,name
    assert hashlib.sha256((PREVIOUS/'manifest.json').read_bytes()).hexdigest()==manifest['previous_manifest_sha256']
    print('loading isolated base; encoding process has exited',flush=True)
    base,corpus=load_base();layout=list(rows(PREVIOUS/'delta_records.jsonl'));scalars=list(rows(OUT/'scalar_records.jsonl'));delta=layout+scalars
    candidate=copy.copy(base);candidate.docs=dict(base.docs);candidate.atomic=dict(base.atomic);candidate.chunks=list(base.chunks)
    for r in delta:
        scope=r.get('source_scope') or {};did=r['document_id']
        candidate.docs[did]={'document_id':did,'source_id':did,'source_version':r['source_version'],'source_path':r['source_path'],'file_name':r['file_name'],'file_type':r['file_type'],'document_type':'PROJECT_CASE','scope':{'project':scope.get('aliases',[])},'authority_level':'UNKNOWN'}
        candidate.atomic[r['evidence_id']]=r
        candidate.atomic[r['evidence_id']]['search_context']=(r.get('scalar') or r.get('layout') or {}).get('source_context',r['text'])
        candidate.chunks.append({'chunk_id':r['evidence_id'],'document_id':did,'source_path':r['source_path'],'file_name':r['file_name'],'section_path':r['heading_path'],'raw_text':r['text']})
    candidate.vectors=np.concatenate([base.vectors,np.load(PREVIOUS/'dense_embeddings.npy'),np.load(OUT/'dense_embeddings.npy')])
    candidate.bm25=BM25Okapi(corpus+[tokenize(' '.join([r['heading_path']]*5+[r['file_name']]*3+[r.get('retrieval_text') or (r.get('layout') or {}).get('source_context',r['text'])])) for r in delta])
    candidate.layout_records={r['evidence_id']:r for r in layout};candidate.scalar_records={r['evidence_id']:r for r in scalars};candidate.allow_gold_source_rescue=False
    code_names=['app/ingestion/scalar_evidence.py','app/scalar_answers.py','app/layout_answers.py','app/retrieval/query_planner_v1.py','app/verified_answer_engine_v2.py','app/trial/live_shadow_v25.py',str(Path(__file__).relative_to(ROOT))]
    code_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in code_names}
    candidate.candidate_hash=hashlib.sha256(json.dumps([base.candidate_hash,manifest,code_hashes],sort_keys=True).encode()).hexdigest();candidate.candidate_revision='SCALAR_NATIVE_OFFLINE_GOLD_RESCUE_DISABLED'
    results=[];queries=json.loads((OUT/'questions.json').read_text(encoding='utf-8'))
    for q,v in zip(queries,np.load(OUT/'query_vectors.npy'),strict=True):
        before=base.run(q['question'],{},query_vector=v.tolist(),include_trace=True)
        scalar=scalar_proposal(q['question'],scalars);plan=plan_query(q['question']).to_dict()
        supported=scalar is not None or layout_proposal(q['question'],plan,layout) is not None or layout_count_mismatch(q['question'],plan,layout) is not None
        after=candidate.run(q['question'],{},query_vector=v.tolist(),include_trace=True) if supported else before
        results.append({**q,'new_route_supported':supported,'scalar_route_supported':scalar is not None,'baseline':before,'candidate':after,'status_regression':before['v2_answer_status']=='ANSWERED' and after['v2_answer_status']!='ANSWERED'})
        save(REPORT/'replay.json',results)
        print(f'{len(results)}/{len(queries)} {q["id"]} {before["v2_answer_status"]} -> {after["v2_answer_status"]} {after["trace_context"]["generation_mode"]}',flush=True)
    save(REPORT/'summary.json',{'status':'OFFLINE_REVIEW_REQUIRED','questions':len(results),'candidate_hash':candidate.candidate_hash,'implementation_sha256':code_hashes,'scalar_route_count':sum(r['scalar_route_supported'] for r in results),'status_downgrades_including_expected_boundary_corrections':[r['id'] for r in results if r['status_regression']],'gold_source_rescue_enabled_for_candidate':False,'legacy_fallback_retains_historical_rules':True,'formal_8000_touched':False,'live_8010_switched':False,'provider_http_calls':0})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['build','replay']);parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    build(args.resume) if args.mode=='build' else replay()
