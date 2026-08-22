from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .answer import generate_answer
from .bm25 import BM25Index
from .config import Settings
from .database import IndexDatabase
from .embeddings import EmbeddingService, ModelUnavailable, RerankerService
from .llm import LLMClient, LLMError
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
    query_lock: threading.Lock


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2_000)


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
        retriever=Retriever(database, vector_store, embedding, bm25, reranker),
        query_lock=threading.Lock(),
    )
    try:
        yield
    finally:
        vector_store.close()


def _services(app: FastAPI) -> Services:
    return app.state.services


def create_app() -> FastAPI:
    app = FastAPI(title="AI设计管理知识库", version="0.1.0", lifespan=lifespan)
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
            "index": services.database.stats(),
        }

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        services = _services(app)
        llm_ok = (
            await asyncio.to_thread(services.llm.health_check)
            if services.settings.api_ready
            else False
        )
        try:
            vector_ok = services.vector_store.count() >= 0
        except Exception:
            vector_ok = False
        vault_ok = services.settings.vault_root.is_dir()
        payload = {
            "status": "ok" if all((llm_ok, services.embedding.ready, vector_ok, vault_ok)) else "degraded",
            "llm": llm_ok,
            "embedding": services.embedding.ready,
            "vector_db": vector_ok,
            "vault": vault_ok,
            "index": services.database.stats(),
        }
        if services.embedding.error:
            payload["embedding_error"] = services.embedding.error
        if services.llm.last_error:
            payload["llm_error"] = services.llm.last_error
        return payload

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> dict[str, object]:
        services = _services(app)
        if not services.retriever.ready():
            raise HTTPException(
                status_code=409,
                detail="尚未建立可用索引。请先停止服务并运行 python -m scripts.index_vault。",
            )

        def answer_in_worker() -> tuple[object, dict[str, int | bool]]:
            with services.query_lock:
                hits, retrieval = services.retriever.search(request.question)
                return generate_answer(request.question, hits, services.llm), retrieval

        try:
            answer, retrieval = await asyncio.to_thread(answer_in_worker)
        except (ModelUnavailable, LLMError) as error:
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
        }

    return app


app = create_app()
