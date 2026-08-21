from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.answer import generate_answer
from app.bm25 import BM25Index
from app.config import Settings
from app.database import IndexDatabase
from app.embeddings import EmbeddingService, RerankerService
from app.llm import LLMClient
from app.retriever import Retriever
from app.vector_store import VectorStore


QUESTIONS = [
    "EPC项目设计策划有哪些主要管理动作？",
    "3262设计管理动作有哪些关键要求？",
    "设计评审的主要检查内容是什么？",
    "设计计划和设计进度如何管理？",
    "设计价值创造有哪些常见做法？",
]


def main() -> None:
    settings = Settings.load()
    database = IndexDatabase(settings.database_path)
    vector_store = VectorStore(settings.qdrant_path)
    bm25 = BM25Index(settings.bm25_path)
    if not bm25.load():
        raise RuntimeError("BM25 index is not ready")
    embedding = EmbeddingService(settings)
    reranker = RerankerService(settings)
    retriever = Retriever(database, vector_store, embedding, bm25, reranker, settings)
    client = LLMClient(settings)
    results: list[dict[str, object]] = []
    try:
        for question in QUESTIONS:
            hits, retrieval = retriever.search(question, dense_limit=20, bm25_limit=20, final_limit=8)
            answer = generate_answer(question, hits, client)
            results.append(
                {
                    "question": question,
                    "retrieval": retrieval,
                    "citation_valid": answer.citation_valid,
                    "request_id": answer.request_id,
                    "elapsed_ms": answer.elapsed_ms,
                    "answer": answer.answer,
                    "citations": answer.citations,
                }
            )
    finally:
        vector_store.close()
    settings.ensure_runtime_directories()
    output = settings.report_root / f"chat-smoke-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output.write_text(json.dumps({"llm_called": True, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(output), "questions": len(results), "citation_valid": all(r["citation_valid"] for r in results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
