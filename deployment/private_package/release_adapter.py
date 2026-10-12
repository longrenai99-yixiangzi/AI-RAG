import hashlib
import json
import os
import threading
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
EXPECTED_HASH = os.environ.get("RAG_EXPECTED_CANDIDATE_HASH", "")
QUERY_LOCK = threading.Lock()


class TaskbookDraftRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    project: str = Field(min_length=1, max_length=120)
    stage: Literal['方案设计', '初步设计', '施工图设计']
    source_id: str = Field(default='', max_length=128)
    source_version: str = Field(default='', max_length=64)
    current_inputs: dict[str, str] = Field(default_factory=dict, max_length=10)


class AssessmentHandoffRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    project_id: str = Field(min_length=1,max_length=120)
    source_version: str = Field(min_length=64,max_length=64)
    selected_ids: list[str] = Field(min_length=1,max_length=200)
    updates: dict[str,dict[str,str]] = Field(default_factory=dict,max_length=200)


class SchemeComparisonRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    project_id: str = Field(min_length=1,max_length=120)
    source_version: str = Field(min_length=64,max_length=64)
    topic_id: str = Field(min_length=1,max_length=80)
    common: dict[str,str] = Field(default_factory=dict,max_length=5)
    options: list[dict[str,str]] = Field(default_factory=lambda:[{},{}],min_length=2,max_length=2)


def source_key(path, version):
    return str(path).replace("/", "\\").rstrip("\\").casefold() + "|" + str(version)


def preview_asset(root: Path, primary: dict, version: str, kind: str):
    ref = next((r for r in primary.values() if r.get('sha256') == version and r.get('verified')), None)
    if not ref:
        raise HTTPException(404, '原件版本未核对。')
    original = (root / ref['frozen_path']).resolve()
    body = (root / 'primary_sources' / (version + '.body.json')).resolve()
    if not original.is_relative_to(root / 'primary_sources') or not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != version:
        raise HTTPException(409, 'PRIMARY_SOURCE_VERSION_CHANGED')
    if not body.is_file():
        raise HTTPException(404, '本原件没有附属阅读材料。')
    payload = json.loads(body.read_text(encoding='utf-8'))
    if payload.get('source', {}).get('source_version') != version:
        raise HTTPException(409, '正文与附件版本不一致。')
    asset = next((a for a in payload.get('preview_assets') or [] if a.get('kind') == kind), None)
    if not asset:
        raise HTTPException(404, '本版本未登记该阅读材料。')
    path = (root / 'primary_sources' / asset['file_name']).resolve()
    if not path.is_relative_to(root / 'primary_sources') or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != asset.get('sha256'):
        raise HTTPException(409, '阅读材料版本校验未通过。')
    return path, asset


def create_app(state_root=None):
    from app.trial import v2
    from app.trial import live_shadow_v25 as shadow
    from app.trial.knowledge_store import TrialKnowledgeStore
    from app.retrieval import retrieval_trace
    from app.trial.runtime_reporting import source_counts, feedback_view, feedback_counts, knowledge_view
    from app.ingestion.atomic_search import search_record_role, search_match_kind, document_title_matches
    from app.trial.project_navigation import load_navigation, question_project, record_in_project, subject_records, page_number

    state = Path(state_root or ROOT / "mutable").resolve()
    v2.KNOWLEDGE_STORE = TrialKnowledgeStore(state / "knowledge_os/state.json")
    v2.TRIAL = state / "query_audit"
    v2.GROWTH = state / "growth"
    for name, filename in {
        "FEEDBACK_CANDIDATES": "feedback_growth_candidates.jsonl",
        "FEEDBACK_CASES": "feedback_regression_cases.jsonl",
        "FEEDBACK_RUNS": "feedback_regression_runs.jsonl",
        "RAG_DEFECTS": "rag_system_defects.jsonl",
        "SOURCE_CLOSURE_REGISTER": "source_closure_register.jsonl",
        "TRIAL_FEEDBACK_QUESTIONS": "trial_feedback_questions.jsonl",
    }.items():
        setattr(v2, name, state / "growth" / filename)
    shadow.RUNS = state / "shadow/live_shadow_runs.jsonl"
    shadow.REMEDIATION_MANIFESTS = (ROOT / "evaluation/knowledge_os_v2_6/remediation_candidate_v2_6_2.json",)
    original_origin = shadow._restore_source_origin

    def keep_indexed_version_path(record):
        restored = original_origin(record)
        restored["source_path"] = record.get("source_path")
        return restored

    shadow._restore_source_origin = keep_indexed_version_path
    retrieval_trace.TRACE_DIR = state / "traces"
    retrieval_trace.TRACE_FILE = state / "traces.jsonl"
    metadata_path = ROOT / "release_metadata.json"
    release_metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    annotations_path = ROOT / "release_feedback_status.json"
    feedback_annotations = json.loads(annotations_path.read_text(encoding="utf-8")) if annotations_path.is_file() else {}
    display_path = ROOT / "knowledge_display.json"
    display_annotations = json.loads(display_path.read_text(encoding="utf-8")) if display_path.is_file() else {}
    service_kind = os.environ.get("RAG_RELEASE_SERVICE_KIND", "PREVIEW")
    formal_authorized = service_kind == "FORMAL" and os.environ.get("RAG_RELEASE_AUTHORIZED") == "1"
    if service_kind == "FORMAL" and not formal_authorized:
        raise RuntimeError("FORMAL_REPORTING_RUNTIME_REQUIRES_AUTHORIZED_ENTRY")

    def release_identity():
        package_path = ROOT.parent / "PACKAGE_MANIFEST_PRIVATE.json"
        return {
            "release_name": release_metadata.get("release_name", "已采用固定版本"),
            "release_status": "APPROVED_DEPLOYED" if formal_authorized else "PREVIEW_PENDING_OWNER_ADOPTION",
            "service_kind": service_kind,
            "service_port": int(os.environ.get("RAG_RELEASE_SERVICE_PORT", str(v2.CONFIG.port))),
            "package_manifest_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest() if package_path.is_file() else None,
            "code_base_commit": release_metadata.get("code_base_commit", "5fee334cf274be302db31a56c1942967a45b18a2"),
        }
    manifest = json.loads(shadow.REMEDIATION_MANIFESTS[0].read_text(encoding="utf-8"))
    isolated_source_ids = {source['source_id'] for source in manifest.get('sources') or [] if source.get('usage_scope') == 'OFFLINE_AND_ISOLATED_PREVIEW_ONLY'}
    if manifest["candidate_hash"] != EXPECTED_HASH or v2._primary_mode() != v2.V262_CANDIDATE_MODE:
        raise RuntimeError("DEPLOYMENT_IDENTITY_MISMATCH")
    originals = json.loads((ROOT / "frozen_sources/catalog.json").read_text(encoding="utf-8"))["records"]
    ui = ROOT / "knowledge-ui/dist"
    primary = json.loads((ROOT / "primary_sources/catalog.json").read_text(encoding="utf-8"))["records"]
    exact_records = {}
    navigation = load_navigation(ROOT, EXPECTED_HASH)

    @lru_cache(maxsize=None)
    def frozen_ok(path, version):
        row = originals.get(source_key(path, version), {})
        relative = row.get("frozen_path")
        if not relative:
            return False
        file = (ROOT / relative).resolve()
        return file.is_relative_to(ROOT / "frozen_sources") and file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == version

    def engine():
        candidate = v2._candidate_primary_runtime()[0]
        if candidate.candidate_hash != EXPECTED_HASH:
            raise RuntimeError("ACTUAL_CANDIDATE_MISMATCH")
        return candidate

    @lru_cache(maxsize=1)
    def catalog():
        rows = {}
        for record in engine().atomic.values():
            sid = str(record.get("source_id") or "")
            path, version = str(record.get("source_path") or ""), str(record.get("source_version") or "")
            parts = Path(path.replace('\\', '/')).parts
            source_type = " / ".join(parts[parts.index('raw')+1:-1]) if 'raw' in parts else "待分类"
            key = (sid, version)
            row = rows.setdefault(key, {
                "source_id": sid, "source_path": path, "source_version": version,
                "current_hash": version, "file_name": record.get("file_name") or Path(path).name,
                "file_type": Path(path).suffix.lower(), "chunk_count": 0,
                "body_status": "INDEXED", "index_status": "INDEXED",
                "approval_status": "ISOLATED_SOURCE_READING_AUTHORIZED_NOT_OWNER_FACT_CONFIRMED" if sid in isolated_source_ids else "FROZEN_OWNER_APPROVED", "runtime_mode": v2.V262_CANDIDATE_MODE,
                "runtime_status": "ACTIVE_FROZEN_CANDIDATE" if frozen_ok(path, version) else "SOURCE_VERSION_CHANGED",
                "runtime_source_version": version,
                "candidate_hash": EXPECTED_HASH,
                "version_note": "本版来源文件已保存版本副本" if frozen_ok(path, version) else "旧来源版本已变化，无法核实；此版引用受限",
                "source_role": search_record_role(record),
                "source_type": "已审核知识" if (record.get("knowledge_card") or {}).get("approval_status") == "OWNER_CONFIRMED" else source_type,
            })
            row["chunk_count"] += 1
            if not frozen_ok(path, version):
                row["index_status"] = "SOURCE_VERSION_CHANGED"
        return list(rows.values())

    def select_source(sid, version=""):
        choices = [row for row in catalog() if row["source_id"] == sid and (not version or row["source_version"] == version)]
        if not choices:
            raise HTTPException(404, "SOURCE_NOT_IN_CURRENT_CANDIDATE")
        if len(choices) != 1:
            raise HTTPException(409, "EXPLICIT_SOURCE_VERSION_REQUIRED")
        return choices[0]

    original_answer = v2._candidate_primary_answer

    def checked_answer(question):
        result = original_answer(question)
        bad = []
        for citation in result.get("citations") or []:
            record = engine().evidence_record(str(citation.get("evidence_id") or "")) or next((row for row in result["debug"]["evidence_bundle"].get("verified_evidence") or [] if row.get("evidence_id") == citation.get("evidence_id")), {})
            for field in ("source_id", "source_path", "source_version", "file_name", "location"):
                citation[field] = citation.get(field) or record.get(field)
            citation["excerpt"] = citation.get("excerpt") or str(record.get("raw_text") or record.get("text") or "")[:1600]
            if record:
                exact_records[str(citation.get("evidence_id") or "")] = {**record, "source_id": citation.get("source_id"), "source_path": citation.get("source_path"), "source_version": citation.get("source_version")}
            if not frozen_ok(citation.get("source_path") or "", citation.get("source_version") or ""):
                bad.append(citation)
        if bad:
            state.joinpath("guard").mkdir(parents=True, exist_ok=True)
            state.joinpath("guard", uuid.uuid4().hex + ".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            result.update(answer="当前候选引用中的原件版本无法核实，暂不能据此确认答案；请提交具体问题，由受控复核处理。", answer_status="INSUFFICIENT_EVIDENCE", status_label="证据不足", claims=[], citations=[], claim_evidence_map={}, source_versions=[], failure_reason="SOURCE_VERSION_CHANGED", failure_message="冻结索引与可核实原件版本不一致。")
            result["debug"]["evidence_bundle"]["bundle_status"] = "SOURCE_VERSION_CHANGED"
            result["debug"]["deployment_version_guard"] = {"rejected": True, "unverified_source_count": len(bad)}
        result["debug"]["runtime_pointer"].update(release_identity())
        result["debug"]["runtime_pointer"]["deployment_adapter"] = "FROZEN_RUNTIME_REPORTING_RELEASE"
        return result

    v2._candidate_primary_answer = checked_answer

    @asynccontextmanager
    async def lifespan(app):
        candidate, dense = v2._candidate_primary_runtime()
        if candidate.candidate_hash != EXPECTED_HASH:
            raise RuntimeError("ACTUAL_CANDIDATE_MISMATCH")
        dense.load()
        app.state.candidate_ready = True
        yield
        app.state.candidate_ready = False

    app = FastAPI(title="设计管理知识库 · 本批修复试用" if service_kind == "PREVIEW" else "设计管理知识库 · 正式使用", lifespan=lifespan)
    app.state.candidate_ready = False

    @app.middleware("http")
    async def frozen_release_scope(request: Request, call_next):
        # Draft generation is stateless; source and knowledge writes remain blocked.
        if request.method not in {"GET", "HEAD"} and request.url.path not in {"/api/v2/query", "/api/v2/feedback", "/api/query", "/api/chat", "/api/v2/taskbook/draft", "/api/v2/assessment-handoff/draft", "/api/v2/scheme-comparison/draft"}:
            return JSONResponse({"detail": "FROZEN_RELEASE_COLLECTS_FEEDBACK_ONLY"}, status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    @app.get("/api/status")
    @app.get("/api/deployment/identity")
    def identity():
        candidate, dense = v2._candidate_primary_runtime()
        ready = bool(app.state.candidate_ready and dense.ready and candidate.candidate_hash == EXPECTED_HASH)
        return {"status": "ok" if ready else "not_ready", "service_ready": ready, "runtime_mode": v2.V262_CANDIDATE_MODE, "candidate_hash": candidate.candidate_hash, **release_identity(), "deployment_adapter": "FROZEN_RUNTIME_REPORTING_RELEASE", "retrieval_vectors": int(candidate.vectors.shape[0]), "overlay_vectors": int(manifest["dense_embeddings"]["shape"][0]), "legacy_unavailable_versions_retired": len(candidate.retired_source_versions), "active_source_version_unavailable": sum(row["index_status"] == "SOURCE_VERSION_CHANGED" for row in catalog()), "runtime_cards": len(v2._candidate_knowledge_items()), "provider_http_enabled": False, "formal_legacy_qdrant_and_sqlite_write": False}

    @app.get("/api/v2/enabled")
    def enabled():
        return {"enabled": True, "scope": "ISOLATED_PREVIEW" if service_kind == "PREVIEW" else "LOOPBACK_APPROVED_PACKAGE", "dense_runtime": "LOCAL_BGE_M3_FP32", "candidate_hash": EXPECTED_HASH}

    @app.get("/api/v2/runtime-capabilities")
    def capabilities():
        return {
            **release_identity(), "candidate_hash": EXPECTED_HASH,
            "display_name": "本批修复试用 · 待采用" if service_kind == "PREVIEW" else "正式使用 · 已采用版本",
            "features": {"dashboard": True, "framework": True, "topics": True, "ai_query": True, "taskbook_draft": True, "sources": True, "search": True, "diagnostics": True, "feedback_records": True, "feedback_record": True, "batch": False, "gold_review": False, "projects": True, "periods": True, "favorites": False, "recent": False, "growth_queue": True, "knowledge_management_write": False},
        }

    def current_feedback():
        rows = feedback_view(v2.feedback_workflow()["items"], feedback_annotations, EXPECTED_HASH)
        for row in rows:
            path, version = row.get("source_path"), row.get("verified_source_version")
            if path and version:
                source = next((item for item in catalog() if source_key(item["source_path"], item["source_version"]) == source_key(path, version)), None)
                if source:
                    row.update(source=source, source_runtime_status=source["index_status"])
        return rows

    @app.get("/api/v2/feedback-workflow")
    def feedback_workflow():
        rows = current_feedback()
        return {"items": rows, "summary": feedback_counts(rows), "candidate_hash": EXPECTED_HASH}

    @app.post("/api/v2/query")
    @app.post("/api/query")
    @app.post("/api/chat")
    def query(request: v2.V2QueryRequest):
        with QUERY_LOCK:
            return v2.query(request)

    @app.get("/api/v2/knowledge/overview")
    def overview():
        summary = feedback_counts(current_feedback())
        return {**v2.KNOWLEDGE_STORE.overview(), **source_counts(catalog()), "runtime_mode": v2.V262_CANDIDATE_MODE, "candidate_hash": EXPECTED_HASH, "active_knowledge": len(v2._candidate_knowledge_items()), "pending_candidate_knowledge": 0, "pending_feedback": summary["pending"], "feedback_summary": summary, "frozen_release": True, **release_identity()}

    @app.get("/api/v2/knowledge/items")
    def items():
        return {"items": knowledge_view(v2._candidate_knowledge_items(), display_annotations, EXPECTED_HASH), "candidate_hash": EXPECTED_HASH}

    @app.get("/api/v2/knowledge/search")
    def search(q: str, limit: int = 20, project_id: str = "", mode: Literal['documents','content']='documents'):
        maximum = max(1, min(limit, 50))
        project = next((p for p in navigation['projects'] if p['id']==project_id),None) if project_id else question_project(q,navigation)
        if project_id and not project:
            raise HTTPException(400,'当前项目资料归属尚未核对。')
        subject_query=q
        if project:
            if project_id and any(p['id']!=project_id and any(alias in q for alias in p['aliases']) for p in navigation['projects']):
                raise HTTPException(400,'关键词中的项目与当前选择不同，请切换项目或选择全库搜索。')
            for alias in sorted([project['name'],*project['aliases'],*v2.plan_query(q).project],key=len,reverse=True):
                subject_query=subject_query.replace(alias,'')
            subject_query=subject_query.strip(' ：:')
        if mode=='documents':
            documents={}
            registrations=[]
            for source in catalog():
                if source['index_status']!='INDEXED' or not document_title_matches(source['file_name'],subject_query or q):
                    continue
                if project and not record_in_project(source,project):continue
                if source['source_type']=='已审核知识' or source['source_role']=='NAVIGATION':continue
                if source['file_type']=='.md':
                    registrations.append({**source,'note':'资料登记或文字摘录；不据此确认对应原件已可读。','reader_url':'/read?'+urlencode({'source':source['source_id'],'version':source['source_version']})})
                    continue
                documents[source_key(source['source_path'],source['source_version'])]={**source,'note':'同版文件已在当前资料索引中，可读正文并打开原文件。','reader_url':'/read?'+urlencode({'source':source['source_id'],'version':source['source_version']}),'file_url':'/api/v2/knowledge/sources/'+source['source_id']+'/file?source_version='+source['source_version']}
            if not project or any(s.get('primary_version') for s in project['sources']):
                for ref in primary.values():
                    if project and not any(s.get('primary_version') == ref.get('sha256') for s in project['sources']):continue
                    if not ref.get('verified') or not document_title_matches(Path(ref['source_path']).name,subject_query or q):continue
                    file=(ROOT/ref['frozen_path']).resolve()
                    if not file.is_relative_to(ROOT/'primary_sources') or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=ref['sha256']:continue
                    key=source_key(ref['source_path'],ref['sha256'])
                    if key in documents:continue
                    version=ref['sha256'];preview=ROOT/'primary_sources'/(version+'.body.json')
                    documents[key]={'file_name':Path(ref['source_path']).name,'source_version':version,'source_path':ref['source_path'],'reader_url':'/read?primary='+version if preview.is_file() else None,'file_url':'/api/v2/knowledge/primary-sources/'+version,'note':ref.get('note') or '同版参考原件可读；不等于整份原件已经用于自动问答。'}
            values=sorted(documents.values(),key=lambda s:s['file_name'])
            return {'items':[],'documents':values[:maximum],'document_total':len(values),'registrations':registrations,'related_items':[],'readable_originals':[],'query':q,'mode':mode,'project':project and {'id':project['id'],'name':project['name']},'candidate_hash':EXPECTED_HASH}
        # Rank within the selected project before taking a result limit.
        matches = v2._search_candidate_atomic_evidence(engine(), subject_query or q, len(engine().chunks)) if q.strip() else []
        results = []
        for row in matches:
            record = row["record"]
            if project and not record_in_project(record,project):
                continue
            if not frozen_ok(record.get("source_path"), record.get("source_version")):
                continue
            card = record.get("knowledge_card") or {}
            display = (display_annotations.get("records") or {}).get(card.get("id"), {})
            body=str(record.get('raw_text') or '')
            terms=[term for term in v2.tokenize(subject_query or q) if len(term)>=2 and term not in {'设计','项目','年度','期间','资料'}]
            hit=next((body.find(term) for term in terms if term in body),0)
            start=max(0,hit-160)
            evidence = {**record, "source_role": search_record_role(record), "excerpt": body[start:start+1800], "match_kind":row.get('match_kind') or search_match_kind(record,subject_query or q)}
            if display_annotations.get("candidate_hash") == EXPECTED_HASH and display.get("source_version") == record.get("source_version") and display.get("content_sha256") == hashlib.sha256(str(record.get("raw_text") or "").encode('utf-8')).hexdigest():
                evidence.update(display_title=display.get("title"), context_status=display.get("context_status"))
            refs={ref.get('sha256') for ref in card.get('primary_sources') or []}
            readable=[s for s in catalog() if s['source_version'] in refs and (not project or record_in_project(s,project))]
            if readable:
                evidence['body_source']=sorted(readable,key=lambda s:s['file_type']!='.md')[0]
            results.append({"type": "EVIDENCE", "score": row["score"], "evidence": evidence})
        direct=[r for r in results if r['evidence']['match_kind'] in {'DIRECT','BODY'}]
        related=[r for r in results if r['evidence']['match_kind']=='RELATED']
        readable_originals=[]
        if not project:
            for ref in primary.values():
                version=ref.get('sha256') or ''
                preview=ROOT/'primary_sources'/(version+'.body.json')
                name=Path(ref['source_path']).name
                if ref.get('verified') and preview.is_file() and search_match_kind({'file_name':name,'raw_text':''},q)=='DIRECT':
                    indexed = any(row['source_version']==version and source_key(row['source_path'], version)==source_key(ref['source_path'], version) for row in catalog())
                    note = '同版原件正文已进入本轮试运行检索；不代表全部图表已核验。' if indexed else '同版原件可读；整份原件尚未新增到主答索引。'
                    readable_originals.append({'file_name':name,'source_version':version,'reader_url':'/read?primary='+version,'file_url':'/api/v2/knowledge/primary-sources/'+version,'note':note})
        return {"items": direct[:maximum], "related_items":related[:min(maximum,8)], "readable_originals":readable_originals, "query": q, "mode":mode, "project":project and {'id':project['id'],'name':project['name']}, "candidate_hash": EXPECTED_HASH}

    def indexed_records():
        return [engine().atomic[str(c['chunk_id'])] for c in engine().chunks if str(c['chunk_id']) in engine().atomic]

    def bound_sources(project):
        result = []
        for source in project['sources']:
            if source.get('primary_version'):
                ref = next((r for r in primary.values() if r.get('sha256') == source['primary_version'] and r.get('verified') and source_key(r['source_path'], r['sha256']) == source_key(source['source_path'], source['source_version'])), None)
                if not ref:raise HTTPException(409, '项目参考原件版本未核对。')
                result.append(dict(source))
            else:
                result.append({**select_source(source['source_id'],source['source_version']),'role':source['role']})
        return result

    @app.get('/api/v2/knowledge/projects')
    def projects():
        return {'items':[{**p,'sources':bound_sources(p)} for p in navigation['projects']],'candidate_hash':EXPECTED_HASH,'coverage':'已按原件核对归属的项目；各项目的问答或只读范围分别标明，不是全库项目清单。'}

    @app.get('/api/v2/knowledge/projects/{project_id}')
    def project_detail(project_id: str, subject: str=''):
        project=next((p for p in navigation['projects'] if p['id']==project_id),None)
        if not project:raise HTTPException(404,'项目资料归属尚未核对。')
        selected=next((s for s in project['subjects'] if s['id']==subject),None) if subject else project['subjects'][0]
        if not selected:raise HTTPException(404,'未登记该事项。')
        records=subject_records(indexed_records(),project,selected)
        return {'project':{**project,'sources':bound_sources(project)},'subject':selected,'items':[{**r,'excerpt':r['raw_text'],'page':page_number(r)} for r in records],'candidate_hash':EXPECTED_HASH}

    @app.get('/api/v2/knowledge/periods')
    def periods():
        return {'items':navigation['periods'],'candidate_hash':EXPECTED_HASH,'coverage':'按部门、年份和期间浏览整份资料；尚未生成完整指标台账。'}

    @app.get('/api/v2/knowledge/nodes/{node_id}/project-resources')
    def node_project_resources(node_id: str):
        mapping={'design-planning-1':['assessment'],'design-bid-3':['contract'],'design-planning-4':['plan'],'design-process-4':['plan'],'design-bid-4':['resources'],'design-resource-1':['resources'],'design-bid-2':['overview'],'design-planning-5':['optimization'],'design-planning-6':['optimization'],'design-result-library-3':['optimization'],'design-result-library-2':['overview','metrics'],'design-planning-7':['cost'],'design-process-8':['risk'],'design-bid-5':['risk']}
        return {'items':[{'project_id':p['id'],'project_name':p['name'],'subject':s} for p in navigation['projects'] for s in p['subjects'] if s['id'] in mapping.get(node_id,[])],'note':'本批按已核对项目事项关联；无卡片不代表没有资料。'}

    @app.get('/api/v2/knowledge/sources/{source_id}/body')
    def source_body(source_id: str, source_version: str):
        source=select_source(source_id,source_version)
        if not frozen_ok(source['source_path'],source_version):raise HTTPException(409,'SOURCE_VERSION_CHANGED')
        preview=ROOT/'primary_sources'/(source_version+'.body.json')
        if source['file_type'] in {'.docx','.xlsx'} and source_id in isolated_source_ids and preview.is_file():
            payload=json.loads(preview.read_text(encoding='utf-8'))
            if payload.get('source_version')!=source_version:raise HTTPException(409,'WORD_BODY_PREVIEW_VERSION_MISMATCH' if source['file_type']=='.docx' else 'WORKBOOK_BODY_PREVIEW_VERSION_MISMATCH')
            return {**payload,'source':source,'candidate_hash':EXPECTED_HASH}
        text=None
        if source['file_type']=='.md':
            text=(ROOT/originals[source_key(source['source_path'],source_version)]['frozen_path']).read_text(encoding='utf-8-sig')
        records=[r for r in indexed_records() if r.get('source_id')==source_id and r.get('source_version')==source_version]
        records.sort(key=lambda r:(page_number(r) or 0,(r.get('location') or {}).get('line_start') or 0))
        period=next((p for p in navigation['periods'] if p['source']['source_id']==source_id and p['source']['source_version']==source_version),None)
        sections=[]
        if period and text:
            import re
            marker=re.search(r'2026\s*年主要工作安排' if period['year']==2025 else r'三\s*、\s*下半年工作安排',text)
            if marker:
                sections=[{'name':'本期完成情况及分析（保留预计值等原文口径）','text':text[:marker.start()]},{'name':'后续工作安排（计划，不作为本期实绩）','text':text[marker.start():]}]
        return {'source':source,'text':text,'period':period,'sections':sections,'items':[{**r,'page':page_number(r)} for r in records],'note':'显示同版已提取文字；图片、图表和排版以原文件为准。','candidate_hash':EXPECTED_HASH}

    @app.get("/api/v2/knowledge/sources")
    def sources(query="", file_type="", limit: int = 50, offset: int = 0):
        rows = [row for row in catalog() if (not query or query.casefold() in (row["file_name"] + row["source_path"]).casefold()) and (not file_type or row["file_type"] == file_type.lower())]
        return {"items": rows[max(0, offset):max(0, offset) + max(1, min(limit, 500))], "total": len(rows), "candidate_hash": EXPECTED_HASH}

    def assessment_case(project_id):
        from app.assessment_handoff import load_case
        if not any(p['id']==project_id and p.get('assessment_handoff_available') for p in navigation['projects']):
            raise HTTPException(404,'本项目暂未提供评估任务准备资料。')
        try:return load_case(ROOT,project_id,navigation)
        except ValueError as error:raise HTTPException(409,str(error)) from error

    @app.get('/api/v2/assessment-handoff/projects/{project_id}')
    def assessment_handoff_case(project_id: str):
        return {**assessment_case(project_id),'candidate_hash':EXPECTED_HASH}

    @app.post('/api/v2/assessment-handoff/draft')
    def assessment_handoff_draft(request: AssessmentHandoffRequest):
        from app.assessment_handoff import build_handoff,render_handoff
        import base64,io,zipfile
        case=assessment_case(request.project_id)
        if request.source_version!=case['source']['source_version']:
            raise HTTPException(409,'评估版本已变化，请刷新核对。')
        try:draft=build_handoff(case,request.source_version,request.selected_ids,request.updates)
        except ValueError as error:raise HTTPException(422,str(error)) from error
        documents=render_handoff(draft);archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
            for name,text in documents.items():bundle.writestr(name,text)
            bundle.writestr('技术记录.json',json.dumps(draft,ensure_ascii=False,indent=2))
        return {'draft':draft,'documents':documents,'source_reader_url':'/read?primary='+request.source_version,
                'download_base64':base64.b64encode(archive.getvalue()).decode('ascii'),'candidate_hash':EXPECTED_HASH,
                'source_writeback':False,'knowledge_published':False,'task_dispatched':False}

    @app.get('/api/v2/scheme-comparison/projects/{project_id}')
    def scheme_comparison_case(project_id: str):
        from app.scheme_comparison import comparison_topics
        if not any(p['id']==project_id and p.get('scheme_comparison_available') for p in navigation['projects']):
            raise HTTPException(404,'本项目尚未整理同版比选议题。')
        try:prepared=comparison_topics(assessment_case(project_id))
        except ValueError as error:raise HTTPException(409,str(error)) from error
        return {**prepared,'candidate_hash':EXPECTED_HASH}

    @app.post('/api/v2/scheme-comparison/draft')
    def scheme_comparison_draft(request: SchemeComparisonRequest):
        from app.scheme_comparison import build_comparison,render_comparison
        import base64,io,zipfile
        scheme_comparison_case(request.project_id)
        case=assessment_case(request.project_id)
        if request.source_version!=case['source']['source_version']:
            raise HTTPException(409,'比选原件版本已变化，请刷新核对。')
        try:draft=build_comparison(case,request.source_version,request.topic_id,request.common,request.options)
        except ValueError as error:raise HTTPException(422,str(error)) from error
        documents=render_comparison(draft);archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
            for name,text in documents.items():bundle.writestr(name,text)
            bundle.writestr('技术记录.json',json.dumps(draft,ensure_ascii=False,indent=2))
        return {'draft':draft,'documents':documents,'download_base64':base64.b64encode(archive.getvalue()).decode('ascii'),
                'source_reader_url':'/read?primary='+request.source_version,'candidate_hash':EXPECTED_HASH,
                'source_writeback':False,'knowledge_published':False,'recommended_option':None}

    @app.get('/api/v2/taskbook/sources')
    def taskbook_sources():
        from app.taskbook_drafting import FIELDS
        docs = {r.get('source_id'): engine().docs.get(str(r.get('document_id')), {}) for r in engine().atomic.values()}
        items = []
        for source in catalog():
            if source['file_type'] != '.docx' or '设计任务书' not in source['file_name']:
                continue
            doc = docs.get(source['source_id'], {})
            names = ((doc.get('document_profile') or {}).get('project') or {}).get('value') or []
            names = [name for name in names if len(name) >= 3 and name in source['file_name'] and 'XXX' not in name]
            stage = next((stage for stage in ('方案设计', '初步设计', '施工图设计') if stage in source['file_name']), None)
            if names and stage:
                items.append({**source, 'project': max(names, key=len), 'stage': stage})
        return {'items': items, 'fields': [{'id': key, 'label': label} for key, _, label, _, _ in FIELDS], 'candidate_hash': EXPECTED_HASH}

    @app.post('/api/v2/taskbook/draft')
    def taskbook_draft(request: TaskbookDraftRequest):
        from app.taskbook_drafting import source_units, build_taskbook_draft, render_taskbook_draft, render_source_evidence
        from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
        if any(len(value) > 6000 for value in request.current_inputs.values()):
            raise HTTPException(422, '单项补充内容过长，请分项整理。')
        units = []; notes = []; reader = None
        if request.source_id:
            option = next((item for item in taskbook_sources()['items'] if item['source_id'] == request.source_id), None)
            if not option or option['source_version'] != request.source_version:
                raise HTTPException(409, '来源或版本不匹配，请重新选择。')
            if option['project'] != request.project.strip() or option['stage'] != request.stage:
                raise HTTPException(422, '来源与所选项目或阶段不一致，不能混用。')
            ref = originals[source_key(option['source_path'], option['source_version'])]
            file = (ROOT / ref['frozen_path']).resolve()
            if not file.is_relative_to(ROOT / 'frozen_sources') or hashlib.sha256(file.read_bytes()).hexdigest() != request.source_version:
                raise HTTPException(409, '原件版本校验未通过。')
            parsed = DocumentIntelligenceV2Builder(ROOT).build([file], [])
            if not parsed['documents'] or parsed['documents'][0]['parse_status'] != 'parsed':
                raise HTTPException(422, '当前原件未能完整解析，未生成草稿。')
            doc = parsed['documents'][0]
            doc.update(source_path=option['source_path'], file_name=option['file_name'])
            doc.setdefault('document_profile', {})['project'] = {'value': [option['project']]}
            units = source_units(parsed, project=option['project'], stage=request.stage, source_path=option['source_path'], source_version=request.source_version, source_sha256=hashlib.sha256(file.read_bytes()).hexdigest())
            reviewed = json.loads((ROOT / 'taskbook_review_notes.json').read_text(encoding='utf-8')).get(request.source_version, [])
            for note in reviewed:
                matched = [unit for unit in units if unit['text_sha256'] in note['anchors']]
                if {unit['text_sha256'] for unit in matched} != set(note['anchors']):
                    raise HTTPException(409, '待核事项与当前原文未能对应，未生成草稿。')
                notes.append({'title': note['title'], 'reason': note['reason'], 'unit_ids': [unit['unit_id'] for unit in matched]})
            reader = '/read?' + urlencode({'source': request.source_id, 'version': request.source_version})
        elif request.source_version:
            raise HTTPException(422, '请同时选择来源文件。')
        try:
            draft = build_taskbook_draft(project=request.project.strip(), stage=request.stage, units=units, current_inputs=request.current_inputs, review_notes=notes)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        import base64, io, zipfile
        markdown = render_taskbook_draft(draft, '来源核对表.md')
        evidence_markdown = render_source_evidence(draft)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('编制草稿.md', markdown)
            bundle.writestr('来源核对表.md', evidence_markdown)
            bundle.writestr('技术记录.json', json.dumps(draft, ensure_ascii=False, indent=2))
        return {'draft': draft, 'markdown': markdown, 'evidence_markdown': evidence_markdown, 'source_reader_url': reader, 'source_writeback': False, 'knowledge_published': False, 'candidate_hash': EXPECTED_HASH, 'download_base64': base64.b64encode(archive.getvalue()).decode('ascii')}

    @app.get("/api/v2/knowledge/sources/{source_id}/evidence")
    def evidence(source_id: str, evidence_id="", source_version="", limit: int = 12):
        source = select_source(source_id, source_version)
        if source["index_status"] != "INDEXED":
            raise HTTPException(409, "SOURCE_VERSION_CHANGED")
        records = [row for row in engine().atomic.values() if row.get("source_id") == source_id and row.get("source_version") == source["source_version"] and (not evidence_id or row["evidence_id"] == evidence_id)]
        if evidence_id and not records:
            row = exact_records.get(evidence_id) or engine().evidence_record(evidence_id,source_id,source['source_version'])
            if row and row.get("source_id") == source_id and row.get("source_version") == source["source_version"]:
                records = [row]
        if evidence_id and not records:
            raise HTTPException(404, "EXACT_EVIDENCE_NOT_IN_SOURCE_VERSION")
        return {"source": source, "items": [{**row, "excerpt": str(row.get("raw_text") or row.get("text") or "")[:1600]} for row in records[:max(1, min(limit, 50))]], "candidate_hash": EXPECTED_HASH}

    @app.get("/api/v2/knowledge/sources/{source_id}/file")
    def original_file(source_id: str, source_version: str):
        source = select_source(source_id, source_version)
        if not frozen_ok(source["source_path"], source_version):
            raise HTTPException(409, "SOURCE_VERSION_CHANGED")
        frozen = originals[source_key(source["source_path"], source_version)]["frozen_path"]
        return FileResponse(ROOT / frozen, filename=Path(source["source_path"]).name)

    @app.get("/api/v2/knowledge/sources/{source_id}")
    def source(source_id: str, source_version=""):
        return {"source": select_source(source_id, source_version), "candidate_hash": EXPECTED_HASH}

    @app.get("/api/v2/knowledge/primary-sources/{version}")
    def primary_file(version: str):
        ref = next((row for row in primary.values() if row.get("sha256") == version and row.get("verified")), None)
        if not ref or not ref.get("frozen_path"):
            raise HTTPException(404, "PRIMARY_SOURCE_VERSION_NOT_FROZEN")
        file = (ROOT / ref["frozen_path"]).resolve()
        if not file.is_relative_to(ROOT / "primary_sources") or hashlib.sha256(file.read_bytes()).hexdigest() != version:
            raise HTTPException(409, "PRIMARY_SOURCE_VERSION_CHANGED")
        return FileResponse(file, filename=Path(ref["source_path"]).name)

    @app.get('/api/v2/knowledge/primary-sources/{version}/artifact/{kind}')
    def primary_artifact(version: str, kind: str):
        path, asset = preview_asset(ROOT, primary, version, kind)
        return FileResponse(path, filename=asset['download_name'], media_type=asset['media_type'], content_disposition_type='inline' if asset['media_type'].startswith('image/') else 'attachment')

    @app.get('/api/v2/knowledge/primary-sources/{version}/body')
    def primary_body(version: str):
        ref=next((r for r in primary.values() if r.get('sha256')==version and r.get('verified')),None)
        if not ref:raise HTTPException(404,'原件版本未核对。')
        original=(ROOT/ref['frozen_path']).resolve()
        preview=(ROOT/'primary_sources'/(version+'.body.json')).resolve()
        if not original.is_relative_to(ROOT/'primary_sources') or not preview.is_relative_to(ROOT/'primary_sources') or not preview.is_file():
            raise HTTPException(404,'本原件尚未生成正文预览。')
        if hashlib.sha256(original.read_bytes()).hexdigest()!=version:raise HTTPException(409,'PRIMARY_SOURCE_VERSION_CHANGED')
        payload=json.loads(preview.read_text(encoding='utf-8'))
        if payload['source']['source_version']!=version:raise HTTPException(409,'正文预览版本不一致。')
        return {**payload,'primary_version':version,'candidate_hash':EXPECTED_HASH}

    app.include_router(v2.router)
    app.mount("/assets", StaticFiles(directory=ui / "assets"), name="assets")

    @app.get("/{client_path:path}", include_in_schema=False)
    def page(client_path: str):
        if client_path.startswith("api/"):
            raise HTTPException(404, "API_NOT_AVAILABLE_IN_THIS_RELEASE")
        return FileResponse(ui / "index.html")

    return app
