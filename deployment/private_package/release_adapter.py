import hashlib
import json
import threading
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
EXPECTED_HASH = "3626608a3d853f7bd1b107c35046a1098c2c025dbd1c883f157c4e952084f37b"
QUERY_LOCK = threading.Lock()


def source_key(path, version):
    return str(path).replace("/", "\\").rstrip("\\").casefold() + "|" + str(version)


def create_app(state_root=None):
    from app.trial import v2
    from app.trial import live_shadow_v25 as shadow
    from app.trial.knowledge_store import TrialKnowledgeStore
    from app.retrieval import retrieval_trace

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
    manifest = json.loads(shadow.REMEDIATION_MANIFESTS[0].read_text(encoding="utf-8"))
    if manifest["candidate_hash"] != EXPECTED_HASH or v2._primary_mode() != v2.V262_CANDIDATE_MODE:
        raise RuntimeError("DEPLOYMENT_IDENTITY_MISMATCH")
    originals = json.loads((ROOT / "frozen_sources/catalog.json").read_text(encoding="utf-8"))["records"]
    ui = ROOT / "knowledge-ui/dist"
    primary = json.loads((ROOT / "primary_sources/catalog.json").read_text(encoding="utf-8"))["records"]
    exact_records = {}

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
            key = (sid, version)
            row = rows.setdefault(key, {
                "source_id": sid, "source_path": path, "source_version": version,
                "current_hash": version, "file_name": record.get("file_name") or Path(path).name,
                "file_type": Path(path).suffix.lower(), "chunk_count": 0,
                "body_status": "INDEXED", "index_status": "INDEXED",
                "approval_status": "FROZEN_823D", "runtime_mode": v2.V262_CANDIDATE_MODE,
                "runtime_status": "ACTIVE_FROZEN_CANDIDATE" if frozen_ok(path, version) else "SOURCE_VERSION_CHANGED",
                "runtime_source_version": version,
                "candidate_hash": EXPECTED_HASH,
                "version_note": "本版来源文件已保存版本副本" if frozen_ok(path, version) else "旧来源版本已变化，无法核实；此版引用受限",
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
        result["debug"]["runtime_pointer"]["deployment_adapter"] = "NEW11_20CARD_READ_ONLY_RELEASE"
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

    app = FastAPI(title="设计管理知识库 · 已批准版本", lifespan=lifespan)
    app.state.candidate_ready = False

    @app.middleware("http")
    async def frozen_release_scope(request: Request, call_next):
        if request.method not in {"GET", "HEAD"} and request.url.path not in {"/api/v2/query", "/api/v2/feedback", "/api/query", "/api/chat"}:
            return JSONResponse({"detail": "FROZEN_RELEASE_COLLECTS_FEEDBACK_ONLY"}, status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    @app.get("/api/status")
    @app.get("/api/deployment/identity")
    def identity():
        candidate, dense = v2._candidate_primary_runtime()
        ready = bool(app.state.candidate_ready and dense.ready and candidate.candidate_hash == EXPECTED_HASH)
        return {"status": "ok" if ready else "not_ready", "service_ready": ready, "runtime_mode": v2.V262_CANDIDATE_MODE, "candidate_hash": candidate.candidate_hash, "code_base_commit": "5fee334cf274be302db31a56c1942967a45b18a2", "deployment_adapter": "LIMIT_REMEDIATION_READ_ONLY_RELEASE", "retrieval_vectors": int(candidate.vectors.shape[0]), "overlay_vectors": 28302, "legacy_unavailable_versions_retired": len(candidate.retired_source_versions), "active_source_version_unavailable": sum(row["index_status"] == "SOURCE_VERSION_CHANGED" for row in catalog()), "runtime_cards": len(v2._candidate_knowledge_items()), "provider_http_enabled": False, "formal_legacy_qdrant_and_sqlite_write": False}

    @app.get("/api/v2/enabled")
    def enabled():
        return {"enabled": True, "scope": "8000_LOOPBACK_APPROVED_PACKAGE", "dense_runtime": "LOCAL_BGE_M3_FP32", "candidate_hash": EXPECTED_HASH}

    @app.post("/api/v2/query")
    @app.post("/api/query")
    @app.post("/api/chat")
    def query(request: v2.V2QueryRequest):
        with QUERY_LOCK:
            return v2.query(request)

    @app.get("/api/v2/knowledge/overview")
    def overview():
        return {**v2.KNOWLEDGE_STORE.overview(), "sources": len(catalog()), "runtime_mode": v2.V262_CANDIDATE_MODE, "candidate_hash": EXPECTED_HASH, "active_knowledge": len(v2._candidate_knowledge_items()), "pending_candidate_knowledge": 0, "frozen_release": True}

    @app.get("/api/v2/knowledge/items")
    def items():
        return {"items": v2._candidate_knowledge_items(), "candidate_hash": EXPECTED_HASH}

    @app.get("/api/v2/knowledge/search")
    def search(q: str, limit: int = 20):
        maximum = max(1, min(limit, 50))
        matches = v2._search_candidate_atomic_evidence(engine(), q, maximum * 3) if q.strip() else []
        return {"items": [{"type": "EVIDENCE", "score": row["score"], "evidence": {**row["record"], "excerpt": str(row["record"].get("raw_text") or "")[:500]}} for row in matches if frozen_ok(row["record"].get("source_path"), row["record"].get("source_version"))][:maximum], "query": q, "candidate_hash": EXPECTED_HASH}

    @app.get("/api/v2/knowledge/sources")
    def sources(query="", file_type="", limit: int = 50, offset: int = 0):
        rows = [row for row in catalog() if (not query or query.casefold() in (row["file_name"] + row["source_path"]).casefold()) and (not file_type or row["file_type"] == file_type.lower())]
        return {"items": rows[max(0, offset):max(0, offset) + max(1, min(limit, 500))], "total": len(rows), "candidate_hash": EXPECTED_HASH}

    @app.get("/api/v2/knowledge/sources/{source_id}/evidence")
    def evidence(source_id: str, evidence_id="", source_version="", limit: int = 12):
        source = select_source(source_id, source_version)
        if source["index_status"] != "INDEXED":
            raise HTTPException(409, "SOURCE_VERSION_CHANGED")
        records = [row for row in engine().atomic.values() if row.get("source_id") == source_id and row.get("source_version") == source["source_version"] and (not evidence_id or row["evidence_id"] == evidence_id)]
        if evidence_id and not records:
            row = exact_records.get(evidence_id)
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

    app.include_router(v2.router)
    app.mount("/assets", StaticFiles(directory=ui / "assets"), name="assets")

    @app.get("/{client_path:path}", include_in_schema=False)
    def page(client_path: str):
        if client_path.startswith("api/"):
            raise HTTPException(404, "API_NOT_AVAILABLE_IN_THIS_RELEASE")
        return FileResponse(ui / "index.html")

    return app
