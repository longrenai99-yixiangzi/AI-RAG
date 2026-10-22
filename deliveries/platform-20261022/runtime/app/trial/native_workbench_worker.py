"""One-job CPU workers, following the existing structure-workbench isolation pattern."""
import argparse
import json
from pathlib import Path
import sys

from app.trial.native_workbench_candidate import DATA,EVAL,load_candidate,native_records,read
from app.scalar_answers import scalar_proposal
from app.layout_answers import layout_proposal,layout_count_mismatch
from app.retrieval.query_planner_v1 import plan_query
from scripts.run_source_completion_trial import LocalDenseCPU,model_digest


def scoped_question(question,source_id):
    if source_id and not (plan_query(question).project or plan_query(question).entities):
        scope=next((r['source_scope']['project'] for r in native_records() if r['source_id']==source_id and r.get('source_scope')),None)
        if scope:return scope+'，'+question
    return question


def answer(engine,question,vector,mode='answer',source_id=''):
    from app.trial.native_workbench_candidate import retrieve_native
    allowed={r['evidence_id']:r for r in native_records() if not source_id or r['source_id']==source_id}
    if mode=='sources':
        ids=retrieve_native(engine,question,vector,set(allowed))
        return {'question':question,'status':'SOURCES_ONLY','answer':'以下仅为检索原文，尚未组织业务回答。','citations':[{'evidence_id':i} for i in ids],'mode':'sources','generation_enabled':False}
    scalars={k:r for k,r in engine.scalar_records.items() if k in allowed};layouts={k:r for k,r in engine.layout_records.items() if k in allowed}
    plan=plan_query(question).to_dict()
    supported=scalar_proposal(question,list(scalars.values())) or layout_proposal(question,plan,list(layouts.values())) or layout_count_mismatch(question,plan,list(layouts.values()))
    if not supported:
        return {'question':question,'status':'INSUFFICIENT_EVIDENCE','answer':'本轮接入的原文结构尚不足以回答这个问题。可切换“只查原文”核对；这不表示整个知识库没有资料。','citations':[],'mode':'answer','generation_enabled':False}
    original_scalars,original_layout=engine.scalar_records,engine.layout_records
    engine.scalar_records=scalars;engine.layout_records=layouts
    try:result=engine.run(question,{},query_vector=vector.tolist(),include_trace=True)
    finally:engine.scalar_records,engine.layout_records=original_scalars,original_layout
    if result['trace_context']['generation_mode'] not in {'NATIVE_SCALAR_ISOLATED_TRIAL','NATIVE_LAYOUT_ISOLATED_TRIAL'} or not result['validation']['valid']:
        return {'question':question,'status':'INSUFFICIENT_EVIDENCE','answer':'未取得可完成原文核对的证据，已阻止用旧回退答案替代本次结果。','citations':[],'mode':'answer','generation_enabled':False}
    assert not result['owner_answer_gold_source_rescue']['invoked'] and not result['approved_gold_source_rescue']['invoked']
    assert all(c['evidence_id'] in allowed for c in result['v2_citations'])
    return {'question':question,'status':result['v2_answer_status'],'answer':result['v2_answer'],'citations':result['v2_citations'],'mode':'answer','generation_enabled':False,'trace':result['trace_context'],'candidate_hash':engine.candidate_hash}


def main():
    import numpy as np
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['encode','answer']);parser.add_argument('job');args=parser.parse_args()
    job=Path(args.job).resolve()
    if job.parent!= (EVAL/'jobs').resolve():raise ValueError('Only isolated job folders are allowed')
    request=read(job/'request.json')
    question=scoped_question(request['question'],request.get('source_id',''))
    if args.phase=='encode':
        if model_digest()!=read(DATA/'manifest.json')['model_sha256']:raise RuntimeError('Embedding model changed; query/index spaces cannot be mixed')
        encoder=LocalDenseCPU()
        try:
            assert len(encoder.tokenizer(question)['input_ids'])<=256,'问题过长，不能静默截断。'
            np.save(job/'query.npy',np.asarray(encoder.embed_query(question),dtype=np.float32))
        finally:encoder.close()
    else:
        result=answer(load_candidate(),question,np.load(job/'query.npy'),request['mode'],request.get('source_id',''))
        (job/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
