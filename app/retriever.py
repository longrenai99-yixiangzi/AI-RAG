from __future__ import annotations

from .bm25 import BM25Index
from .database import IndexDatabase
from .domain import SearchHit
from .embeddings import EmbeddingService, RerankerService
from .vector_store import VectorStore


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], rank_constant: int = 60
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (rank_constant + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


class Retriever:
    def __init__(
        self,
        database: IndexDatabase,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        bm25: BM25Index,
        reranker: RerankerService,
    ) -> None:
        self.database = database
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.bm25 = bm25
        self.reranker = reranker

    def ready(self) -> bool:
        return bool(self.database.stats()["chunks"] and self.bm25.ready)

    def search(
        self, question: str, dense_limit: int = 20, bm25_limit: int = 20, final_limit: int = 8
    ) -> tuple[list[SearchHit], dict[str, int | bool]]:
        dense_pairs = self.vector_store.query(
            self.embedding_service.embed_query(question), limit=dense_limit
        )
        bm25_pairs = self.bm25.search(question, limit=bm25_limit)
        dense_ids = [chunk_id for chunk_id, _ in dense_pairs]
        bm25_ids = [chunk_id for chunk_id, _ in bm25_pairs]
        dense_rank = {chunk_id: rank for rank, chunk_id in enumerate(dense_ids, start=1)}
        bm25_rank = {chunk_id: rank for rank, chunk_id in enumerate(bm25_ids, start=1)}
        fused = reciprocal_rank_fusion([dense_ids, bm25_ids])
        candidate_ids = [chunk_id for chunk_id, _ in fused[: max(dense_limit, bm25_limit)]]
        chunks = self.database.get_chunks(candidate_ids)
        fused_scores = dict(fused)
        hits = [
            SearchHit(
                chunk=chunk,
                score=fused_scores.get(chunk.chunk_id, 0.0),
                dense_rank=dense_rank.get(chunk.chunk_id),
                bm25_rank=bm25_rank.get(chunk.chunk_id),
            )
            for chunk in chunks
        ]
        rerank_scores = self.reranker.score(question, [hit.chunk.text for hit in hits])
        if rerank_scores is not None:
            for hit, score in zip(hits, rerank_scores, strict=True):
                hit.reranker_score = score
            hits.sort(
                key=lambda hit: hit.reranker_score
                if hit.reranker_score is not None
                else float("-inf"),
                reverse=True,
            )
        else:
            hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:final_limit], {
            "dense_hits": len(dense_pairs),
            "bm25_hits": len(bm25_pairs),
            "fused_hits": len(hits),
            "reranker_used": rerank_scores is not None,
        }
