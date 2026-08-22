from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .answer import evidence_only_answer, generate_answer
from .bm25 import BM25Index
from .config import Settings
from .database import IndexDatabase
from .embeddings import EmbeddingService, ModelUnavailable, RerankerService
from .growth import GrowthManager
from .llm import LLMClient, LLMError
from .query_analyzer import analyze_question
from .retriever import Retriever
from .vector_store import VectorStore


STATIC_ROOT = Path(__file__).parent / "static"


@dataclass(slots=True)
class Services:
    settings: Settings
    database: IndexDatabase
    vector_store: VectorStore
    embedding: EmbeddingService
    reranker: RerankerService
    bm25: BM25Index
    llm: LLMClient
    retriever: Retriever
    growth: GrowthManager
    query_lock: threading.Lock


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2_000)


class GapStatusRequest(BaseModel):
    status: Literal["OPEN", "REVIEWING", "RESOLVED", "IGNORED"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.load()
    settings.ensure_runtime_directories()
    database = IndexDatabase(settings.database_path)
    vector_store = VectorStore(settings.qdrant_path)
    bm25 = BM25Index(settings.bm25_path)
    try:
        bm25.load()
    except Exception:
        # A stale local cache must not prevent the diagnostic page from opening.
        bm25 = BM25Index(settings.bm25_path)
    embedding = EmbeddingService(settings)
    try:
        embedding.load()
    except ModelUnavailable:
        pass
    reranker = RerankerService(settings)
    llm = LLMClient(settings)
    app.state.services = Services(
        settings=settings,
        database=database,
        vector_store=vector_store,
        embedding=embedding,
        reranker=reranker,
        bm25=bm25,
        llm=llm,
        retriever=Retriever(database, vector_store, embedding, bm25, reranker, settings),
        growth=GrowthManager(database, settings.data_root),
        query_lock=threading.Lock(),
    )
    try:
        yield
    finally:
        vector_store.close()


def _services(app: FastAPI) -> Services:
    return app.state.services


def create_app() -> FastAPI:
    app = FastAPI(title="AI设计管理知识库", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="static")

    @app.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        services = _services(app)
        return {
            "vault": str(services.settings.vault_root),
            "api_configured": services.settings.api_ready,
            "embedding_ready": services.embedding.ready,
            "embedding_device": services.embedding.device,
            "reranker_mode": services.settings.reranker_mode,
            "reranker_ready": services.reranker.ready,
            "reranker_model_available": services.settings.reranker_model_path.joinpath("model.safetensors").is_file(),
            "index": services.database.stats(),
            "ocr_provider": services.settings.ocr_provider,
            "metadata_rules": str(services.settings.metadata_rules_path),
        }

    @app.get("/api/health")
    async def health(probe_llm: bool = Query(default=False)) -> dict[str, object]:
        services = _services(app)
        llm_probe = "skipped"
        llm_ok: bool | None = None
        if not services.settings.api_ready:
            llm_ok = False
            llm_probe = "not_configured"
        elif probe_llm:
            llm_probe = "completed"
            try:
                llm_ok = await asyncio.wait_for(
                    asyncio.to_thread(services.llm.health_check, 5.0),
                    timeout=6.0,
                )
            except (asyncio.TimeoutError, LLMError):
                llm_ok = False
                llm_probe = "timeout_or_failed"
        try:
            vector_ok = services.vector_store.count() >= 0
        except Exception:
            vector_ok = False
        vault_ok = services.settings.vault_root.is_dir()
        infrastructure_ok = all((services.embedding.ready, vector_ok, vault_ok))
        payload = {
            "status": "ok" if infrastructure_ok and (llm_ok is not False or not probe_llm) else "degraded",
            "llm": llm_ok,
            "llm_configured": services.settings.api_ready,
            "llm_probe": llm_probe,
            "embedding": services.embedding.ready,
            "vector_db": vector_ok,
            "vault": vault_ok,
            "reranker": services.reranker.ready,
            "reranker_model_available": services.settings.reranker_model_path.joinpath("model.safetensors").is_file(),
            "reranker_mode": services.settings.reranker_mode,
            "index": services.database.stats(),
            "ocr_provider": services.settings.ocr_provider,
        }
        if services.embedding.error:
            payload["embedding_error"] = services.embedding.error
        if services.llm.last_error:
            payload["llm_error"] = services.llm.last_error
        return payload

    @app.get("/api/growth")
    async def growth() -> dict[str, object]:
        return _services(app).database.growth_snapshot()

    @app.get("/api/documents")
    async def documents(
        query: str = Query(default="", max_length=200),
        limit: int = Query(default=200, ge=1, le=500),
        board: str | None = Query(default=None, max_length=40),
        knowledge_type: str | None = Query(default=None, max_length=40),
        building_type: str | None = Query(default=None, max_length=40),
        project_stage: str | None = Query(default=None, max_length=40),
        document_level: str | None = Query(default=None, max_length=40),
    ) -> dict[str, object]:
        return {
            "items": _services(app).database.list_documents(
                query,
                limit,
                board=board,
                knowledge_type=knowledge_type,
                building_type=building_type,
                project_stage=project_stage,
                document_level=document_level,
            )
        }

    @app.get("/api/facts/conflicts")
    async def fact_conflicts() -> dict[str, object]:
        return {"items": _services(app).database.fact_conflicts()}

    @app.post("/api/growth/gaps/{gap_id}/status")
    async def update_gap_status(gap_id: str, request: GapStatusRequest) -> dict[str, object]:
        updated = _services(app).database.update_gap_status(gap_id, request.status)
        if updated is None:
            raise HTTPException(status_code=404, detail="知识缺口不存在。")
        return updated

    @app.get("/api/growth/candidates/{candidate_id}")
    async def growth_candidate(candidate_id: str) -> dict[str, object]:
        snapshot = _services(app).database.growth_snapshot()
        item = next(
            (row for row in snapshot["gaps"] if row.get("candidate_id") == candidate_id),
            None,
        )
        if not item:
            raise HTTPException(status_code=404, detail="候选知识不存在。")
        path = Path(str(item.get("candidate_path", "")))
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        return {"candidate": item, "content": content}

    @app.post("/api/growth/candidates/{candidate_id}/formal-draft")
    async def formal_draft(candidate_id: str) -> dict[str, object]:
        try:
            return _services(app).growth.create_formal_draft(candidate_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> dict[str, object]:
        services = _services(app)
        if not services.retriever.ready():
            raise HTTPException(
                status_code=409,
                detail="尚未建立可用索引。请先停止服务并运行 python -m scripts.index_vault。",
            )

        def answer_in_worker() -> tuple[object | None, dict[str, object], dict[str, object], str | None, Exception | None]:
            with services.query_lock:
                try:
                    hits, retrieval = services.retriever.search(request.question)
                except Exception as error:
                    retrieval = {
                        "fused_hits": 0,
                        "query_analysis": analyze_question(
                            request.question,
                            services.settings.metadata_rules_path,
                        ).to_dict(),
                    }
                    growth = services.growth.record(
                        question=request.question,
                        retrieval=retrieval,
                        answer=None,
                        citations=[],
                        citation_valid=None,
                        error=error,
                    )
                    return None, retrieval, growth, None, error
                try:
                    answer = generate_answer(
                        request.question,
                        hits,
                        services.llm,
                        retrieval.get("query_analysis"),
                    )
                    error = None
                except (ModelUnavailable, LLMError) as caught:
                    answer = evidence_only_answer(hits, str(caught))
                    warning = str(caught)
                    error = None
                else:
                    warning = None
                growth = services.growth.record(
                    question=request.question,
                    retrieval=retrieval,
                    answer=answer.answer if answer else None,
                    citations=answer.citations if answer else [],
                    citation_valid=answer.citation_valid if answer else None,
                    error=error,
                )
                return answer, retrieval, growth, warning, error

        try:
            answer, retrieval, growth_result, warning, error = await asyncio.to_thread(answer_in_worker)
        except Exception as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if error is not None:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {
            "answer": answer.answer,
            "citations": answer.citations,
            "citation_valid": answer.citation_valid,
            "retrieval": retrieval,
            "model": services.settings.chat_model,
            "request_id": answer.request_id,
            "elapsed_ms": answer.elapsed_ms,
            "reranker_warning": services.reranker.error if not retrieval["reranker_used"] else None,
            "llm_warning": warning,
            "growth": growth_result,
        }

    return app


app = create_app()
