from __future__ import annotations

import json
from datetime import datetime

from app.bm25 import BM25Index
from app.config import Settings
from app.database import IndexDatabase
from app.embeddings import EmbeddingService, RerankerService
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
    retriever = Retriever(
        database,
        vector_store,
        EmbeddingService(settings),
        bm25,
        RerankerService(settings),
        settings,
    )
    results: list[dict[str, object]] = []
    qdrant_points = vector_store.count()
    try:
        for question in QUESTIONS:
            hits, meta = retriever.search(question, dense_limit=20, bm25_limit=20, final_limit=8)
            results.append(
                {
                    "question": question,
                    "meta": meta,
                    "hits": [
                        {
                            "rank": rank,
                            "file": hit.chunk.file_name,
                            "heading": hit.chunk.heading_path,
                            "location": hit.chunk.location,
                            "rrf_score": hit.score,
                            "dense_rank": hit.dense_rank,
                            "bm25_rank": hit.bm25_rank,
                        }
                        for rank, hit in enumerate(hits, 1)
                    ],
                }
            )
    finally:
        vector_store.close()
    settings.ensure_runtime_directories()
    output = settings.report_root / f"retrieval-sample-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    payload = {
        "status": "retrieval_only",
        "reranker": "off",
        "llm_called": False,
        "documents": database.stats()["documents"],
        "chunks": database.stats()["chunks"],
        "qdrant_points": qdrant_points,
        "results": results,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(output), "questions": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
