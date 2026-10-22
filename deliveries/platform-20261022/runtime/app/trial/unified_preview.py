"""Opt-in local preview; never mounted into existing resident services automatically."""
import os,json
from contextlib import asynccontextmanager
from pathlib import Path
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='0')
from fastapi import FastAPI,HTTPException,Query,Request
from pydantic import BaseModel,Field
import threading
from fastapi.responses import HTMLResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from app.retrieval.unified_candidate import UnifiedCandidate
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.reranker_provider import BGERerankerProvider
from app.trial.assisted_chat import router
from app.trial.knowledge_store import TrialKnowledgeStore
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import UnavailableLLMProvider
from app.config import Settings
ROOT=Path(__file__).resolve().parents[2];HERE=ROOT/'evaluation/unified_entry_20261020'
dense=BGEM3DenseProvider(Settings.load().embedding_model,use_fp16=True,batch_size=2)
reranker=BGERerankerProvider(ROOT/'models/bge-reranker-v2-m3',use_fp16=True,max_length=1024)
candidate=UnifiedCandidate(ROOT/'data/shadow/unified_entry_20261020_r1',dense,reranker,personnel_folder=ROOT/'data/shadow/personnel_scope_20261020',quality_folder=ROOT/'data/shadow/reference_binding_20261021',scalar_links=json.loads((ROOT/'evaluation/platform_closeout_20261022/source_scopes.json').read_text(encoding='utf-8')))
inference_lock=threading.Lock()

@asynccontextmanager
async def lifespan(app):
    import torch
    torch.set_num_threads(4)
    dense.embed_query('本地设计管理检索启动检查');reranker.score('设计管理',['本机候选索引启动检查。'])
    yield
    dense.close();reranker.close()

app=FastAPI(lifespan=lifespan);app.include_router(router)
def serialized_retrieve(question):
    with inference_lock:return candidate.retrieve(question)
app.state.assisted_retrieve=serialized_retrieve
app.state.assisted_store=TrialKnowledgeStore(HERE/'preview_state.json')
app.state.assisted_generator=ShadowAnswerGenerator(UnavailableLLMProvider('统一候选已启用真实本地检索，未启用公网生成。'))
UI=HERE/'ui-dist';app.mount('/assets',StaticFiles(directory=UI/'assets'),name='assets')

@app.get('/api/v2/unified/status')
def status():return {'candidate_hash':candidate.candidate_hash,'records':len(candidate.records),'personnel_scope_records':len(candidate.personnel.records),'personnel_index_sha256':candidate.personnel.manifest['records_sha256'],'sources':candidate.sources(limit=1)['total'],'source_extract_enabled':True,'model_http_enabled':False,'same_candidate_for_sources_and_retrieval':True}

class LocalFeatures(BaseModel):
    texts:list[str]=Field(min_length=1,max_length=32)
    question:str=Field(default='',max_length=2000)

@app.post('/api/v2/unified/local-features')
def local_features(value:LocalFeatures,request:Request):
    if request.client.host not in {'127.0.0.1','::1'} or request.headers.get('X-Platform-Request')!='1':raise HTTPException(403,'仅允许本机工作台')
    if any(not t.strip() or len(t)>12000 for t in value.texts):raise HTTPException(422,'文本为空或过长')
    with inference_lock:
        return {'model_digest':candidate.manifest['embedding_model_digest'],**({'scores':reranker.score(value.question,value.texts)} if value.question else {'vectors':dense.embed_documents(value.texts)})}

@app.get('/api/v2/knowledge/sources')
def sources(query:str='',file_type:str='',offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
    return candidate.sources(query,file_type,offset,limit)

@app.get('/api/v2/knowledge/sources/{source_id}/evidence')
def evidence(source_id:str,limit:int=Query(12,ge=1,le=100)):
    if source_id not in candidate.by_source:raise HTTPException(404,'本候选未登记该来源')
    return candidate.source_evidence(source_id,limit)

@app.get('/api/v2/unified/source-snapshot/{source_id}')
def source_snapshot(source_id:str,request:Request):
    if request.client.host not in {'127.0.0.1','::1'} or request.headers.get('X-Platform-Request')!='1':raise HTTPException(403,'仅允许本机工作台')
    indices=candidate.by_source.get(source_id,[])
    if not indices or len(indices)>3000:raise HTTPException(422,'来源不存在或超过单份增量上限，未截断入库')
    rows=[candidate.records[i] for i in indices]
    if any(r['source_path'].replace('\\','/').lower() in {p.replace('\\','/').lower() for p in candidate.reference_only} for r in rows):raise HTTPException(422,'仅链接登记卡不能当作正文入库')
    pairs=[(i,r) for i,r in zip(indices,rows) if r['evidence_id'] not in candidate.quality_exclusions]
    return {'records':[r for _,r in pairs],'vectors':[candidate.vectors[i].tolist() for i,_ in pairs], 'model_digest':candidate.manifest['embedding_model_digest'],'candidate_hash':candidate.candidate_hash}

@app.get('/api/v2/feedback-workflow')
def feedback():return {'items':[]}

@app.get('/{path:path}')
def page(path):
    if path.startswith('api/'):return JSONResponse({'detail':'本隔离预览仅开放来源浏览与原文问答，不执行发布或写入操作。'},status_code=404)
    banner='<aside style="position:relative;z-index:99999;background:#fff2c6;color:#5f4500;padding:9px;text-align:center;font:14px system-ui">统一候选离线预览：知识资产与问答使用同一索引；已核对人数可摘录回答，公网生成未启用。分类页仍仅作导航。</aside>'
    return HTMLResponse((UI/'index.html').read_text(encoding='utf-8').replace('<body>','<body>'+banner))
