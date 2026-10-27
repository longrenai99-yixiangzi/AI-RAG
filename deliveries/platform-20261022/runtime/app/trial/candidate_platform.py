"""Direct local adapter and opt-in single-user management; model approval is separate."""
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import threading

from fastapi.responses import JSONResponse
from app.answer_engine.llm.answer_generator import ShadowAnswerGenerator
from app.answer_engine.llm.llm_provider import UnavailableLLMProvider
from .assisted_chat import AssistedQuery,run_flow
from .platform_app import create_app
from .platform_existing import ExistingKnowledge

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'evaluation/platform_490_quality_20261024'
PACKAGE=BASE/'candidate_compatibility_01'
HOME=PACKAGE/'platform_trial_01'


class CandidateKnowledge(ExistingKnowledge):
    def __init__(self,candidate):
        self.candidate=candidate;self.lock=threading.Lock()
        self.generator=ShadowAnswerGenerator(UnavailableLLMProvider('本入口未开启模型执行'))

    def status(self):
        c=self.candidate
        return {'candidate_hash':c.candidate_hash,'content_revision':getattr(c,'content_revision','UNSPECIFIED'),'runtime_spec_sha256':getattr(c,'runtime_spec_sha256',None),'records':len(c.records),'sources':c.sources(limit=1)['total'],
                'model_http_enabled':False,'same_candidate_for_sources_and_retrieval':True,'source_extract_enabled':True,'source_version_filter_enabled':True,
                **({'text_cleanup':c.text_cleanup} if getattr(c,'text_cleanup',None) else {}),
                **({'paragraph_repair':c.paragraph_repair} if getattr(c,'paragraph_repair',None) else {}),
                **({'native_tables':c.native_tables} if getattr(c,'native_tables',None) else {}),
                **({'flowcharts':c.flowcharts} if getattr(c,'flowcharts',None) else {}),
                **({'additional_paragraph_repair':c.additional_paragraph_repair} if getattr(c,'additional_paragraph_repair',None) else {}),
                **({'reviewed_flow_relations':{k:v for k,v in c.reviewed_flow_relations.items() if k!='relations'}} if getattr(c,'reviewed_flow_relations',None) else {}),
                **({'reviewed_tables':c.reviewed_tables} if getattr(c,'reviewed_tables',None) else {})}

    def sources(self,query='',offset=0,limit=50,file_type=''):
        return self.candidate.sources(query,file_type,offset,limit)

    def evidence(self,source_id):
        if source_id not in self.candidate.by_source:raise KeyError(source_id)
        return self.candidate.source_evidence(source_id,100)

    def retrieve(self,question,request_id,*,source_versions=None):
        data=AssistedQuery(question=question,request_id=request_id,mode='sources',source_versions=source_versions)
        with self.lock:
            events=list(run_flow(data,self.candidate.retrieve,self.generator,lambda *_:None))
        result=next((e['result'] for e in events if e.get('type')=='result'),None)
        if result is None:raise ValueError('新候选未返回完整检索结果')
        return self.bind_catalog_citations(result)

    def features(self,texts,question=''):
        with self.lock:
            values={'scores':self.candidate.focused.reranker.score(question,texts)} if question else {'vectors':self.candidate.encoder.embed_documents(texts)}
        return {'model_digest':self.candidate.manifest['embedding_model_digest'],**values}
    def source_snapshot(self,source_id):
        c=self.candidate;indices=c.by_source.get(source_id,[])
        if not indices or len(indices)>3000:raise ValueError('来源不存在或超过单份3000片段上限，未截断入库')
        rows=[c.records[i] for i in indices]
        from app.retrieval.named_source_scope import path_key
        if any(path_key(r['source_path']) in c.reference_only for r in rows):raise ValueError('仅链接登记卡不能作为正文入库')
        versions={(r['source_path'],r['source_version']) for r in rows}
        if any(not self.version_current({'source_path':p,'current_hash':v}) for p,v in versions):raise ValueError('原件版本已变化，未复用旧索引')
        pairs=[(i,r) for i,r in zip(indices,rows) if r['evidence_id'] not in c.quality_exclusions]
        if not pairs:raise ValueError('来源没有通过正文质量筛查的片段')
        return {'records':[dict(r) for _,r in pairs],'vectors':[c.vectors[i].tolist() for i,_ in pairs],
                'model_digest':c.manifest['embedding_model_digest'],'candidate_hash':c.candidate_hash}


def create_candidate_app(state_path,candidate,ui_dist=None,contract_path=None,*,daily_policy=None,administrator_enabled=False):
    existing=CandidateKnowledge(candidate)
    app=create_app(state_path,ui_dist,contract_path,existing,generation_execution_enabled=False,daily_policy=daily_policy)
    @app.middleware('http')
    async def management_boundary(request,call_next):
        allowed={'/api/platform/query','/api/platform/query-feedback','/api/platform/generation-preview'}
        if request.url.path=='/api/platform/daily-model-policy' and request.method=='POST':
            if (await request.json()).get('action')=='pause':allowed.add(request.url.path)
        if not administrator_enabled and request.method not in {'GET','HEAD'} and request.url.path not in allowed:
            return JSONResponse({'detail':'此入口未开放资料管理操作；日常模型答复仅按已批准策略运行，手动模型执行仍关闭。'},status_code=403)
        response=await call_next(request)
        if request.url.path=='/api/platform/state' and response.status_code==200:
            data=json.loads(b''.join([part async for part in response.body_iterator]))
            if administrator_enabled:
                data['notice']='本机单人管理模式：可导入、审核发布及撤回恢复；导入不自动扩大模型白名单。'+('模型额度见日常策略。' if daily_policy else '公网模型未开启。')+'工作区备份不包含原资料库和本地模型。'
            else:
                data['notice']='新候选试用：模型是否启用及剩余额度见问答页策略；导入、手动模型执行和发布入口保持关闭。' if daily_policy else '新候选只读试用：可查原文和保存本入口反馈；模型未开启，不会收费。人工校正尚未发布为自动答复。'
            data['capabilities'].update(incremental_index=administrator_enabled,parsing=administrator_enabled,read_only_source_trial=not administrator_enabled,administrator_operations_enabled=administrator_enabled)
            return JSONResponse(data)
        return response
    return app


def trial_app():
    import os
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',CUDA_VISIBLE_DEVICES='0')
    import torch
    from app.retrieval.unified_candidate import UnifiedCandidate
    from app.retrieval.dense_provider import BGEM3DenseProvider
    from app.retrieval.reranker_provider import BGERerankerProvider
    spec_raw=(HOME/'prepared.json').read_bytes()
    spec=json.loads(spec_raw)
    for p,h in spec['proof_sha256'].items():
        with Path(p).open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==h,'试用包版本已变，请重新核对'
    torch.set_num_threads(2)
    dense=BGEM3DenseProvider(ROOT/'models/bge-m3',use_fp16=True,batch_size=4)
    reranker=BGERerankerProvider(ROOT/'models/bge-reranker-v2-m3',use_fp16=True,max_length=1024)
    candidate=UnifiedCandidate(PACKAGE/'index',dense,reranker,personnel_folder=PACKAGE/'personnel',quality_folder=PACKAGE/'quality',scalar_links=json.loads((ROOT/'evaluation/platform_closeout_20261022/source_scopes.json').read_text(encoding='utf-8')),text_cleanup_folder=spec.get('text_cleanup_folder'),paragraph_repair_folder=spec.get('paragraph_repair_folder'),native_table_folder=spec.get('native_table_folder'),flowchart_folder=spec.get('flowchart_folder'),additional_paragraph_folder=spec.get('additional_paragraph_folder'),reviewed_table_folder=spec.get('reviewed_table_folder'),flow_relations_folder=spec.get('flow_relations_folder'))
    assert candidate.candidate_hash==spec['candidate_hash']
    candidate.content_revision=spec.get('additional_content_revision','UNSPECIFIED')
    candidate.runtime_spec_sha256=hashlib.sha256(spec_raw).hexdigest()
    policy_path=HOME/'active_daily_policy.json'
    policy=json.loads(policy_path.read_text(encoding='utf-8')) if policy_path.exists() else None
    admin_path=HOME/'administrator_approval.json'
    admin=json.loads(admin_path.read_text(encoding='utf-8')) if admin_path.exists() else {}
    if admin.get('approved') and admin.get('candidate_hash')!=candidate.candidate_hash:raise ValueError('管理员授权与候选版本不符')
    ui_path=Path(spec.get('ui_dist') or ROOT/'evaluation/concise_trial_20261022/platform-dist').resolve()
    if not ui_path.is_relative_to(ROOT/'evaluation'):raise ValueError('本机界面路径不在已核试用目录')
    for asset in (ui_path.rglob('*') if spec.get('ui_dist') else []):
        if asset.is_file() and str(asset) not in spec['proof_sha256']:raise ValueError('界面存在未固定版本的资源')
    app=create_candidate_app(HOME/'state.json',candidate,ui_path,Path(candidate.manifest['contract_path']),daily_policy=policy,administrator_enabled=admin.get('approved') is True)
    old_lifespan=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(instance):
        try:
            dense.load();reranker.load()
            async with old_lifespan(instance):yield
        finally:dense.close();reranker.close()
    app.router.lifespan_context=lifespan
    return app
