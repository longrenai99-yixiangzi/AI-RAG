"""Loopback-only asynchronous workbench; originals and existing services remain read-only."""
from __future__ import annotations
import asyncio
from datetime import datetime,timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from typing import Literal
import uuid

from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from pydantic import BaseModel,Field,ConfigDict

from app.trial.native_workbench_candidate import ROOT,DATA,EVAL,native_records,read,sha,validate_manifest
from scripts.run_source_completion_trial import save

PORT=8878
PAGE=ROOT/'app/trial/static/native_workbench'
JOBS=EVAL/'jobs'
app=FastAPI(title='原文问答独立试用',docs_url=None,redoc_url=None,openapi_url=None)
gate=asyncio.Semaphore(1)
tasks=set()


class Question(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    question:str=Field(min_length=1,max_length=1000)
    mode:Literal['answer','sources']='answer'
    source_id:str=''


def catalog():
    validate_manifest()
    return {r['source_id']:{'id':r['source_id'],'file_name':r['file_name'],'path':r['source_path'],'sha256':r['source_version'],'scope':r.get('source_scope') or {}}
            for r in native_records()}


def job_folder(job_id):
    try:
        if uuid.UUID(job_id).hex!=job_id:raise ValueError()
    except ValueError:raise HTTPException(404,'未找到本机问题记录。')
    path=JOBS/job_id
    if not (path/'state.json').is_file():raise HTTPException(404,'未找到本机问题记录。')
    return path


def project_result(result):
    value={k:v for k,v in result.items() if k!='trace'}
    records={r['evidence_id']:r for r in native_records()}
    if any(c['evidence_id'] not in records for c in result.get('citations',[])):
        raise RuntimeError('Worker returned unregistered evidence')
    versions={records[c['evidence_id']]['source_path']:records[c['evidence_id']]['source_version'] for c in result.get('citations',[])}
    if any(sha(Path(path))!=digest for path,digest in versions.items()):
        return {'question':result['question'],'status':'SOURCE_SCOPE_MISSING','answer':'原件版本已变化，已阻断旧索引回答。请先核对并更新独立候选。','citations':[],'mode':result['mode'],'generation_enabled':False}
    value['citations']=[{**c,'file_name':records[c['evidence_id']]['file_name'],'source_id':records[c['evidence_id']]['source_id'],
                         'location':records[c['evidence_id']]['location'],'source_version':records[c['evidence_id']]['source_version']}
                        for c in result.get('citations',[]) if c['evidence_id'] in records]
    return value


@app.middleware('http')
async def local_only(request:Request,call_next):
    origin=f'http://127.0.0.1:{PORT}'
    if request.headers.get('host')!=f'127.0.0.1:{PORT}' or (request.method=='POST' and request.headers.get('origin')!=origin):
        return JSONResponse({'detail':'仅允许本机试用页访问。'},status_code=403)
    if request.method=='POST':
        try:size=int(request.headers.get('content-length','0'))
        except ValueError:size=0
        if not 0<size<=8192 or request.headers.get('content-type')!='application/json':
            return JSONResponse({'detail':'请求格式或长度无效。'},status_code=400)
    response=await call_next(request)
    response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
                             'Cross-Origin-Resource-Policy':'same-origin',
                             'Content-Security-Policy':"default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
    return response


@app.on_event('startup')
def recover_interrupted_jobs():
    JOBS.mkdir(parents=True,exist_ok=True)
    for path in JOBS.glob('*/state.json'):
        state=read(path)
        if state['status'] in {'queued','running'}:
            state.update(status='error',stage='上次试用进程已中断',error='问题记录已保留，请重新提交；没有自动重试或调用对话模型。')
            save(path,state)


@app.get('/')
def home():return FileResponse(PAGE/'index.html')


@app.get('/assets/{name}')
def asset(name:str):
    if name not in {'app.js','style.css'}:raise HTTPException(404)
    return FileResponse(PAGE/name)


@app.get('/api/status')
def status():
    m=validate_manifest()
    recent=sorted(JOBS.glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30] if JOBS.exists() else []
    done=[read(p) for p in recent if read(p).get('encoding_completed')]
    return {'kind':'ISOLATED_NATIVE_WORKBENCH','candidate_hash':m['candidate_hash'],'generation_enabled':False,
            'sources':list(catalog().values()),'embedding':'本地BGE-M3 · CPU','embedding_state':'本入口已完成实际编码' if done else '模型文件已校验，等待首次试用编码',
            'formal_switched':False,'response_mode':'原文提取与核对；不调用对话模型'}


@app.get('/api/questions')
def history():
    records=[read(p) for p in JOBS.glob('*/state.json')] if JOBS.exists() else []
    return sorted(records,key=lambda r:r.get('created_at',''),reverse=True)[:20]


@app.get('/api/past-generation')
def past_generation():
    folder=Path(r'D:/example-data/source-f9173837')
    receipt=read(folder/'GENERATION_FINAL_RECEIPT.json')
    report=folder/'状态边界4题模型原答与核对_20261018.md'
    if receipt['artifact_sha256'].get(str(report))!=sha(report):raise HTTPException(409,'历史生成记录版本不符，未展示。')
    return {'notice':'10月18日已授权的4题历史模型原答与复核记录；不是本次实时回答，未新增模型调用，也不等于Owner业务验收。',
            'text':report.read_text(encoding='utf-8'),'new_model_calls':0,'owner_accepted':False}


@app.get('/api/questions/{job_id}')
def question_state(job_id:str):return read(job_folder(job_id)/'state.json')


async def run_job(folder):
    state=read(folder/'state.json')
    try:
        if state['mode']=='answer' and re.search(r'相差|差额|差多少|合计|总计|平均|占比|增长率|哪个更|之和|最终结算|是否已|是否已经|真实合同|已确认|已批准',state['question']):
            state.update(status='complete',stage='已说明本轮核对范围',result={'question':state['question'],'mode':'answer','status':'UNSUPPORTED_TASK',
                         'answer':'本入口尚未验收汇总、差额、比较或现实履约状态判断，不能把列出原文数值当成已完成这类问题。可切换“只查原文”核对依据。','citations':[],'generation_enabled':False})
            return
        async with gate:
            for phase,label in [('encode','正在本机编码问题'),('answer','正在检索原文并核对')]:
                state.update(status='running',stage=label);save(folder/'state.json',state)
                env={**os.environ,'PYTHONIOENCODING':'utf-8','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','CUDA_VISIBLE_DEVICES':''}
                proc=await asyncio.create_subprocess_exec(sys.executable,'-B','-m','app.trial.native_workbench_worker',phase,str(folder),cwd=str(ROOT),env=env,
                                                         stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                try:stdout,stderr=await asyncio.wait_for(proc.communicate(),timeout=240)
                except asyncio.TimeoutError:
                    proc.kill();await proc.communicate();raise RuntimeError('LOCAL_WORKER_TIMEOUT')
                (folder/(phase+'.log')).write_bytes(stdout+b'\n'+stderr)
                if proc.returncode:raise RuntimeError('LOCAL_WORKER_FAILED')
                if phase=='encode':state['encoding_completed']=True
            result=read(folder/'result.json');state.update(status='complete',stage='原文核对完成',result=project_result(result))
    except Exception as exc:
        state.update(status='error',stage='本次执行失败',error='本机执行未完成，不能把它当成无资料。可缩短问题后重试；错误记录已保留。',error_code=type(exc).__name__)
    finally:save(folder/'state.json',state)


@app.post('/api/questions',status_code=202)
async def submit(q:Question):
    validate_manifest()
    if q.source_id and q.source_id not in catalog():raise HTTPException(400,'资料范围无效。')
    if len(tasks)>=4:raise HTTPException(429,'已有问题在处理，请稍后再试。')
    folder=JOBS/uuid.uuid4().hex;folder.mkdir(parents=True)
    request=q.model_dump();save(folder/'request.json',request)
    state={'id':folder.name,**request,'status':'queued','stage':'问题已保存，等待本机处理','created_at':datetime.now(timezone.utc).isoformat()}
    save(folder/'state.json',state)
    task=asyncio.create_task(run_job(folder));tasks.add(task);task.add_done_callback(tasks.discard)
    return state


@app.get('/api/evidence/{evidence_id}')
def evidence(evidence_id:str):
    validate_manifest()
    record=next((r for r in native_records() if r['evidence_id']==evidence_id),None)
    if not record:raise HTTPException(404,'没有该版本的证据。')
    if sha(Path(record['source_path']))!=record['source_version']:raise HTTPException(409,'原件版本已变化，已阻断旧引用。')
    return {'id':evidence_id,'file_name':record['file_name'],'location':record['location'],'source_version':record['source_version'],
            'source_id':record['source_id'],'text':(record.get('scalar') or record.get('layout') or {}).get('source_context',record['text'])}


@app.get('/api/sources/{source_id}/file')
def original(source_id:str):
    source=catalog().get(source_id)
    if not source:raise HTTPException(404)
    path=Path(source['path'])
    if sha(path)!=source['sha256']:raise HTTPException(409,'原件版本已变化，下载已阻断。')
    return FileResponse(path,filename=source['file_name'])


@app.get('/api/evidence/{evidence_id}/preview')
def preview(evidence_id:str):
    validate_manifest()
    record=next((r for r in native_records() if r['evidence_id']==evidence_id),None)
    if not record:raise HTTPException(404)
    path=Path(record['source_path'])
    if sha(path)!=record['source_version']:raise HTTPException(409,'原件版本变化。')
    page=record['location'].get('slide') or record['location'].get('page')
    if not page or path.suffix.lower() not in {'.pptx','.pdf'}:raise HTTPException(404,'此类原件请查看表行文本或下载原件。')
    output=EVAL/'previews'/f'{record["source_version"]}-{page}.png';output.parent.mkdir(exist_ok=True)
    if not output.exists():
        if path.suffix.lower()=='.pdf':
            import pymupdf
            with pymupdf.open(path) as doc:doc[page-1].get_pixmap(matrix=pymupdf.Matrix(1.6,1.6)).save(output)
        else:
            run=subprocess.run(['officecli','view',str(path),'screenshot','--page',str(page),'--render','html','-o',str(output)],
                               env={**os.environ,'OFFICECLI_NO_AUTO_RESIDENT':'1'},capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if run.returncode or not output.exists():raise HTTPException(503,'原页预览未完成；仍可查看文本与下载原件。')
        if sha(path)!=record['source_version']:raise HTTPException(409,'预览时原件版本发生变化。')
    return FileResponse(output,media_type='image/png')
