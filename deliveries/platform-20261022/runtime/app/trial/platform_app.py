"""Local platform workbench. Run with one worker, loopback only. No vault imports."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import base64
import zipfile
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, field_validator
import httpx

from .platform_store import PlatformConflict, PlatformStore

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "evaluation" / "platform_workbench_20261021"


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    actor: str = Field(default="本机负责人", min_length=1, max_length=80)
    revision: int = Field(default=0, ge=0)


class SourceInput(Input):
    name: str = Field(min_length=1, max_length=300)
    reference: str = Field(default="", max_length=2000)
    version_label: str = Field(min_length=1, max_length=120)
    product_line: str = Field(default="通用", min_length=1, max_length=80)


class CandidateInput(Input):
    action_id: str = Field(default="", max_length=30)
    project_id: str = Field(default="", max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)
    source_id: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(min_length=1, max_length=20000)
    required_terms: list[str] = Field(min_length=1, max_length=30)
    applicability: str = Field(min_length=1, max_length=2000)
    @field_validator("required_terms")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        if any(not t.strip() or len(t) > 300 for t in values):
            raise ValueError("关键事实不能为空或超过300字。")
        return list(dict.fromkeys(t.strip() for t in values))


class Operation(Input):
    action: Literal["submit", "approve", "reject", "publish", "withdraw", "rollback"]
    note: str = Field(default="", max_length=2000)
    confirmed: bool = False
    target_version: int = Field(default=0, ge=0)


class ProjectInput(Input):
    name: str = Field(min_length=1, max_length=300)
    product_line: str = Field(min_length=1, max_length=80)
    stage: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)
    status: Literal["ACTIVE", "ARCHIVED"] = "ACTIVE"


class PersonalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite: bool | None = None
    visit: bool = False


class ExistingQuery(Input):
    question: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class ExistingFeedback(Input):
    query_run_id: str = Field(pattern=r"^QR_[a-f0-9]{32}$")
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    kind: Literal["ANSWER_CORRECTION", "RETRIEVAL_ERROR", "CITATION_ERROR", "MISSING_MATERIAL", "USEFUL"]
    comment: str = Field(default="", max_length=2000)
    citation_id: str = Field(default="", max_length=80)
    expected_answer: str = Field(default="", max_length=20000)
    applicability: str = Field(default="", max_length=2000)
    required_terms: list[str] = Field(default_factory=list, max_length=30)
    _terms = field_validator("required_terms")(CandidateInput.clean_terms.__func__)


class ImportUpload(Input):
    file_name: str = Field(min_length=1,max_length=200)
    content_base64: str = Field(min_length=1,max_length=35_000_000)


class ExistingImport(Input):
    source_id: str = Field(min_length=1,max_length=100)


class JobAction(Input):
    action: Literal['activate','withdraw','retry','cancel']


class RestoreInput(Input):
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmed: bool = False


class PrepareGeneration(Input):
    query_run_id: str = Field(pattern=r'^QR_[a-f0-9]{32}$')


class RunGeneration(Input):
    packet_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    approved: bool = False
    max_budget_cny: Literal[1] = 1


class PricingInput(Input):
    confirmed:bool=False
    input_usd_per_million:float=Field(gt=0,le=10000,allow_inf_nan=False)
    output_usd_per_million:float=Field(gt=0,le=10000,allow_inf_nan=False)
    fx_ceiling:float=Field(gt=0,le=100,allow_inf_nan=False)


def load_definitions(contract_path: Path | None) -> dict:
    if contract_path is None:
        return {"actions": [], "products": [], "taxonomy": [], "version": "NOT_CONNECTED"}
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    vault = contract_path.parents[2]
    refs = [(vault / contract[key]).resolve() for key in ("taxonomy_ref", "architecture_ref")]
    if any(not p.is_relative_to((vault / ".ai-growth" / "config").resolve()) for p in refs):
        raise ValueError("分类定义路径越界。")
    taxonomy, architecture = [json.loads(p.read_text(encoding="utf-8")) for p in refs]
    if len(taxonomy["actions"]) != 13 or len(architecture["product_lines"]) != 13:
        raise ValueError("共用分类定义不符合13动作、13产品线约定。")
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in [contract_path, *refs])).hexdigest()
    return {"actions": taxonomy["actions"], "products": architecture["product_lines"], "taxonomy": taxonomy["nodes"], "version": digest}


def create_app(state_path: Path, ui_dist: Path | None = None, contract_path: Path | None = None, existing=None, provider_factory=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(instance):
        try:yield
        finally:
            if getattr(instance.state,'lifecycle',None):instance.state.lifecycle.close()
    app = FastAPI(title="设计管理平台 · 隔离功能工作台",lifespan=lifespan)
    store = PlatformStore(state_path)
    app.state.platform_store = store
    definitions = load_definitions(contract_path)
    lifecycle = None
    generation = None
    if existing:
        from .platform_lifecycle import PlatformLifecycle
        from .platform_generation import GenerationWorkflow
        lifecycle = PlatformLifecycle(store,existing)
        app.state.lifecycle=lifecycle
        def citation_current(c):
            if c.get('knowledge_id'):
                row=next((k for k in store.snapshot()['knowledge'] if k['knowledge_id']==c['knowledge_id']),None)
                if not row or row['status']!='ACTIVE' or row['version']!=c.get('knowledge_version'):return False
            if c.get('source_id','').startswith('INC_'):
                source=lifecycle.catalog(c['source_id'])
                if not source or source[0]['status']!='ACTIVE':return False
            return existing.version_current({'source_path':c.get('source_path'),'current_hash':c.get('source_version')})
        generation=GenerationWorkflow(store,citation_current,provider_factory)

    def check_metadata(value) -> None:
        if hasattr(value, "action_id") and value.action_id and value.action_id not in {a["id"] for a in definitions["actions"]}:
            raise ValueError("管理动作不在共用分类定义中。")
        if hasattr(value, "product_line") and definitions["products"] and value.product_line not in {"通用", *(p["name"] for p in definitions["products"])}:
            raise ValueError("产品线不在共用分类定义中。")

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.headers.get("host", "")
        hostname = urlsplit("http://" + host).hostname
        if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail": "仅供本机使用"}, status_code=403)
        if hostname not in {"127.0.0.1", "localhost", "testserver", "::1"}:
            return JSONResponse({"detail": "不允许的主机"}, status_code=403)
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            if (origin and origin != f"{request.url.scheme}://{host}") or request.headers.get("x-platform-request") != "1":
                return JSONResponse({"detail": "请从本机平台页面操作"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(PlatformConflict)
    async def conflict(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(_request, _exc):
        return JSONResponse({"detail": "记录不存在"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(httpx.HTTPError)
    async def upstream_unavailable(_request, _exc):
        return JSONResponse({"detail": "现有检索服务暂时不可用，管理记录仍保留。"}, status_code=503)

    @app.exception_handler(OSError)
    async def local_io_failed(_request,_exc):
        return JSONResponse({'detail':'本地文件读写未完成，请检查磁盘空间、文件名长度或访问权限；未确认本次保存成功。'},status_code=503)

    @app.exception_handler(zipfile.BadZipFile)
    async def corrupt_backup(_request,_exc):
        return JSONResponse({'detail':'备份压缩文件已损坏，未执行恢复。'},status_code=422)

    @app.get("/api/platform/state")
    def state():
        runtime_info = None
        if existing:
            try:
                runtime_info = {"ready": True, **existing.status()}
            except (httpx.HTTPError, ValueError):
                runtime_info = {"ready": False, "error": "现有检索服务暂时不可用，管理记录仍保留。"}
        return {**store.snapshot(), "definitions": definitions, "mode": "ISOLATED_MANAGEMENT", "notice": "独立功能工作台：仅保存本工作台录入内容，共用分类定义只读；未连接现有资料、检索索引或模型。",
                **({"mode": "EXISTING_CONTENT_TRIAL", "runtime": runtime_info, "notice": "现有资料工作版：复用已有索引，支持原文摘录、数值换算和经人工审核的知识检索。模型整理需逐次审批，未开启连续调用；发布和撤回仅作用于本地试用知识层。"} if existing else {}),
                "capabilities": {"source_io": bool(existing), "existing_index_read": bool(existing), "incremental_index": bool(existing), "generation_requires_per_request_approval":bool(existing), "parsing": bool(existing), "real_index": False, "public_model": False, "formal_publish": False}}

    @app.get("/api/platform/export")
    def export():
        return JSONResponse({"platform_schema": 1, **state()}, headers={"Content-Disposition": 'attachment; filename="platform-snapshot.json"'})

    @app.post("/api/platform/sources")
    def source_create(value: SourceInput):
        check_metadata(value)
        return store.save_source(value.model_dump(exclude={"actor", "revision"}), value.actor)

    @app.put("/api/platform/sources/{source_id}")
    def source_update(source_id: str, value: SourceInput):
        check_metadata(value)
        return store.save_source(value.model_dump(exclude={"actor", "revision"}), value.actor, source_id=source_id, revision=value.revision)

    @app.post("/api/platform/sources/{source_id}/withdraw")
    def source_withdraw(source_id: str, value: Operation):
        if value.action != "withdraw":
            raise HTTPException(422, "操作不匹配")
        return store.source_withdraw(source_id, value.revision, value.actor, value.note)

    @app.post("/api/platform/candidates")
    def candidate_create(value: CandidateInput):
        check_metadata(value)
        return store.save_candidate(value.model_dump(exclude={"actor", "revision"}), value.actor)

    @app.put("/api/platform/candidates/{candidate_id}")
    def candidate_update(candidate_id: str, value: CandidateInput):
        check_metadata(value)
        return store.save_candidate(value.model_dump(exclude={"actor", "revision"}), value.actor, candidate_id=candidate_id, revision=value.revision)

    @app.post("/api/platform/candidates/{candidate_id}/actions")
    def candidate_action(candidate_id: str, value: Operation):
        row = next((c for c in store.snapshot()["candidates"] if c["candidate_id"] == candidate_id), None)
        if row and existing and row.get("origin_citation") and value.action in {"submit", "approve", "publish"}:
            source = store.source(row["source_id"])
            if not existing.version_current(source):
                raise PlatformConflict("原件版本已变或不可读取，不能继续审核发布。")
        return store.candidate_action(candidate_id, value.action, value.revision, value.actor, value.note, value.confirmed)

    @app.post("/api/platform/knowledge/{knowledge_id}/actions")
    def knowledge_action(knowledge_id: str, value: Operation):
        row = next((k for k in store.snapshot()["knowledge"] if k["knowledge_id"] == knowledge_id), None)
        if row and existing and row.get("origin_citation") and value.action == "rollback" and not existing.version_current(store.source(row["source_id"])):
            raise PlatformConflict("原件版本已变，不能恢复旧回答。")
        return store.knowledge_action(knowledge_id, value.action, value.revision, value.actor, value.note, value.target_version)

    @app.post("/api/platform/projects")
    def project_create(value: ProjectInput):
        check_metadata(value)
        return store.save_project(value.model_dump(exclude={"actor", "revision"}), value.actor)

    @app.put("/api/platform/projects/{project_id}")
    def project_update(project_id: str, value: ProjectInput):
        check_metadata(value)
        return store.save_project(value.model_dump(exclude={"actor", "revision"}), value.actor, project_id=project_id, revision=value.revision)

    @app.post("/api/platform/knowledge/{knowledge_id}/personal")
    def personal(knowledge_id: str, value: PersonalInput):
        return store.personal_action(knowledge_id, favorite=value.favorite, visit=value.visit)

    @app.get("/api/platform/search")
    def search(q: str = Query(min_length=1, max_length=2000), product_line: str = "", action_id: str = "", project_id: str = ""):
        return {"mode": "PUBLISHED_KEYWORD_SEARCH", "items": store.published_search(q, product_line=product_line, action_id=action_id, project_id=project_id,source_check=existing.version_current if existing else None),
                "notice": "仅检索本工作台已发布且来源版本仍有效的知识；关键词匹配，不是模型生成回答。"}

    if existing:
        from .platform_existing import source_extract

        @app.get("/api/platform/library")
        def existing_library(q: str = Query(default="", max_length=1000), offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100), file_type: str = ""):
            base=existing.sources(query=q, offset=offset, limit=limit, file_type=file_type)
            added=[s for s in lifecycle.catalog() if q.casefold() in s['file_name'].casefold() and (not file_type or s['file_name'].lower().endswith(file_type))]
            base['items']+=added[max(0,offset-base['total']):max(0,offset-base['total'])+max(0,limit-len(base['items']))]
            return {**base,'total':base['total']+len(added)}

        @app.get("/api/platform/library/{source_id}/evidence")
        def existing_evidence(source_id: str):
            if source_id.startswith('INC_'):
                job=next((j for j in store.snapshot()['jobs'] if j.get('source_id')==source_id),None)
                if not job:raise KeyError(source_id)
                return {'items':[{'evidence_id':r['evidence_id'],'excerpt':r['text'],'heading_path':r.get('heading_path'),'location':r.get('location')} for r in lifecycle.package(job)['records'][:100]]}
            return existing.evidence(source_id)

        @app.get("/api/platform/library/{source_id}/original")
        def existing_original(source_id: str):
            source = lifecycle.catalog(source_id)[0] if source_id.startswith('INC_') and lifecycle.catalog(source_id) else existing.catalog_source(source_id)
            if not existing.version_current(source):
                raise PlatformConflict("原件当前版本与索引不同或不可读取，已停止打开旧版引用。")
            return FileResponse(source["source_path"])

        @app.get("/api/platform/runs/{run_id}")
        def query_run(run_id: str):
            row = store.query_run(run_id)
            if row is None:
                raise KeyError(run_id)
            return row

        @app.post("/api/platform/query")
        def existing_query(value: ExistingQuery):
            row, created = store.begin_run(value.request_id, value.question, value.actor)
            if not created:
                if row["status"] == "RUNNING":
                    raise PlatformConflict("问题仍在处理，请刷新历史记录，未重复检索。")
                return row
            try:
                reviewed = store.reviewed_answers(value.question, existing.version_current)
                if len(reviewed) > 1:
                    result = {"answer_status": "REVIEW_CONFLICT", "answer": "同一问题有多条有效审核答案，请先核对适用范围并撤回重复项。", "citations": []}
                elif reviewed:
                    knowledge = reviewed[0]
                    result = {"answer_status": "REVIEWED_ANSWER", "status_label": "人工审核答案 · 原问题匹配", "answer": knowledge["content"],
                              "citations": [knowledge["origin_citation"]], "knowledge_id": knowledge["knowledge_id"], "knowledge_version": knowledge["version"],
                              "applicability": knowledge["applicability"], "generation_mode": "HUMAN_REVIEWED_EXACT_QUESTION"}
                else:
                    base=existing.retrieve(value.question, value.request_id)
                    cards=base.get('citations',[])
                    disabled={s['source_id'] for s in store.snapshot()['sources'] if s.get('status')!='REGISTERED'}
                    cards=[c for c in cards if c['source_id'] not in disabled]
                    added=lifecycle.retrieve(value.question) if hasattr(existing,'features') else []
                    route=base.get('debug',{}).get('scope_resolution',{})
                    if route.get('status') in {'AMBIGUOUS_PROJECT_SELECTOR','CONFLICTING_EVIDENCE'}:
                        added=[]
                    allowed=(route.get('source_scope') or base.get('debug',{}).get('source_scope') or {}).get('allowed_paths')
                    if allowed:
                        paths={str(Path(p)).replace('\\','/').casefold() for p in allowed}
                        names={Path(p).name.casefold() for p in allowed}
                        added=[r for r in added if r['source_path'].replace('\\','/').casefold() in paths or r['file_name'].casefold() in names]
                    seen={(c['source_version'],c['excerpt']) for c in cards}
                    for record in added:
                        duplicate=(record['source_version'],record['text']) in seen
                        if duplicate and not record.get('knowledge_id'):continue
                        card={'source_id':record['source_id'],'source_version':record['source_version'],'source_path':record['source_path'],'file_name':record['file_name'],
                              'evidence_id':record['evidence_id'],'excerpt':record['text'],'display_location':record.get('heading_path') or json.dumps(record.get('location',{}),ensure_ascii=False),
                              'answer_usage':record['answer_usage'],'evidence_kind':'REVIEWED_KNOWLEDGE' if record.get('knowledge_id') else 'INCREMENTAL_SOURCE'}
                        if record.get('knowledge_id'):
                            knowledge=next(k for k in store.snapshot()['knowledge'] if k['knowledge_id']==record['knowledge_id'])
                            card.update(knowledge_id=record['knowledge_id'],knowledge_version=knowledge['version'],origin_excerpt=knowledge['origin_citation']['excerpt'],applicability=knowledge['applicability'])
                        if duplicate:
                            next(c for c in cards if (c['source_version'],c['excerpt'])==(record['source_version'],record['text'])).update(card)
                        else:
                            cards.append(card);seen.add((record['source_version'],record['text']))
                    for i,c in enumerate(cards,1):c['citation_id']='S'+str(i)
                    has_primary=any(c.get('answer_usage')=='PRIMARY' for c in cards)
                    base.update(citations=cards)
                    if any(r['answer_usage']=='PRIMARY' for r in added):base['answer_status']='SOURCES_ONLY'
                    result=source_extract(base,value.question)
                    if any(c.get('evidence_kind')=='REVIEWED_KNOWLEDGE' and c.get('answer_usage')=='PRIMARY' for c in cards):
                        result.update(status_label='原文与已审核知识检索结果 · 待核对适用范围',notice='本题同时检索原有资料与已审核知识；审核知识是经审查的派生内容，原件引用用于追溯。')
                return store.finish_run(row["query_run_id"], result, error=result.get("answer_status") == "PIPELINE_ERROR")
            except Exception as error:
                return store.finish_run(row["query_run_id"], {"answer_status": "PIPELINE_ERROR", "answer": "本次检索未完成，问题已保存。可刷新记录查看状态；没有自动重试或调用公网模型。", "citations": [], "error_type": type(error).__name__}, error=True)

        @app.post("/api/platform/query-feedback")
        def existing_feedback(value: ExistingFeedback):
            values = value.model_dump(exclude={"actor", "revision"})
            previous = store.feedback("FB_" + value.request_id)
            if previous:
                if previous["submitted_values"] != values:
                    raise PlatformConflict("反馈编号已用于其他内容。")
                return previous
            row = store.query_run(value.query_run_id)
            if not row or row["status"] == "RUNNING":
                raise PlatformConflict("本题尚未取得可反馈的处理记录。")
            citation = next((c for c in row.get("result", {}).get("citations", []) if c["citation_id"] == value.citation_id), None)
            source = None
            if value.expected_answer and value.kind == "ANSWER_CORRECTION":
                if not citation:
                    raise ValueError("建立更正候选需要选定本题的真实引用。")
                source = lifecycle.catalog(citation['source_id'])[0] if citation['source_id'].startswith('INC_') and lifecycle.catalog(citation['source_id']) else existing.catalog_source(citation["source_id"])
                if source["current_hash"] != citation["source_version"] or not existing.version_current(source):
                    raise PlatformConflict("反馈引用版本已失效，需重新检索核查。")
            return store.existing_feedback(values, citation, source, value.actor)

        @app.post('/api/platform/imports')
        def import_upload(value:ImportUpload):
            try:data=base64.b64decode(value.content_base64,validate=True)
            except ValueError:raise HTTPException(422,'文件编码不合法')
            return lifecycle.enqueue(value.file_name,data,value.actor)

        @app.post('/api/platform/imports/from-existing')
        def import_existing(value:ExistingImport):
            source=existing.catalog_source(value.source_id)
            if not existing.version_current(source):raise PlatformConflict('现有原件版本已变，未建立入库任务。')
            return lifecycle.enqueue(source['file_name'],Path(source['source_path']).read_bytes(),value.actor,value.source_id)

        @app.post('/api/platform/imports/{job_id}/actions')
        def import_action(job_id:str,value:JobAction):return lifecycle.job_action(job_id,value.action,value.actor)

        @app.post('/api/platform/generation-preview')
        def prepare_generation(value:PrepareGeneration):return generation.prepare(value.query_run_id)

        @app.get('/api/platform/generation-pricing')
        def generation_pricing():return generation.pricing()

        @app.post('/api/platform/generation-pricing')
        def update_generation_pricing(value:PricingInput):
            if not value.confirmed:raise HTTPException(403,'需确认已核对官方价格，系统不会自动假定旧价格仍有效。')
            return generation.update_pricing(value.model_dump(exclude={'actor','revision','confirmed'}),value.actor)

        @app.get('/api/platform/generation/{preview_id}')
        def generation_detail(preview_id:str):
            return store._read()['generations'][preview_id]

        @app.post('/api/platform/generation/{preview_id}/run')
        def run_generation(preview_id:str,value:RunGeneration):
            if not value.approved:raise HTTPException(403,'需明确同意本批外发范围与1元预算。')
            return generation.run(preview_id,value.packet_sha256,value.actor)

    @app.get('/api/platform/backups')
    def backups():
        from .platform_backup import list_backups
        return {'items':list_backups(store)}

    @app.post('/api/platform/backups')
    def backup(value:Input):
        from .platform_backup import create_backup
        return create_backup(store)

    @app.post('/api/platform/backups/{backup_id}/restore')
    def restore(backup_id:str,value:RestoreInput):
        if not value.confirmed:raise HTTPException(403,'恢复会切回管理状态，须明确确认。')
        from .platform_backup import restore_backup
        return restore_backup(store,backup_id,value.sha256,value.actor)

    @app.get("/api/{unknown:path}")
    def unknown_api(unknown: str):
        raise HTTPException(404, "此工作台尚未接入该接口")

    entry = ui_dist / "platform.html" if ui_dist else None
    if entry and entry.is_file():
        app.mount("/assets", StaticFiles(directory=ui_dist / "assets"), name="assets")
        @app.get("/{client_path:path}")
        def frontend(client_path: str):
            return FileResponse(entry,headers={'Cache-Control':'no-store'})
    return app


def seed_demo(store: PlatformStore) -> None:
    if store.path.exists():
        return
    source = store.save_source({"name": "【演示】设计协调办法", "reference": "演示数据，无真实附件", "version_label": "演示第1版", "product_line": "通用"}, "系统演示")
    store.save_candidate({"question": "【演示】设计协调会如何留存结论？", "answer": "演示规定：设计协调会应形成会议纪要，并记录责任人和完成期限。",
                          "source_id": source["source_id"], "location": "演示第3条", "excerpt": "演示规定：设计协调会应形成会议纪要，并记录责任人和完成期限。",
                          "required_terms": ["会议纪要", "责任人", "完成期限"], "applicability": "仅用于验证平台流程，不作为业务制度。"}, "系统演示")


# Explicit launcher only: importing this module never initializes or reads a business vault.
def demo_app() -> FastAPI:
    result = create_app(WORKSPACE / "demo_state.json", WORKSPACE / "platform-dist", Path("D:/example-vault/.ai-growth/config/knowledge-platform-contract-v1.json"))
    seed_demo(result.state.platform_store)
    return result


def live_app() -> FastAPI:
    from .platform_existing import ExistingKnowledge
    return create_app(ROOT / "evaluation/platform_existing_content_20261021/live_state.json", WORKSPACE / "platform-dist",
                      Path("D:/example-vault/.ai-growth/config/knowledge-platform-contract-v1.json"), ExistingKnowledge())
