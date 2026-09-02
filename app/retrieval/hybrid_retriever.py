from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.bm25 import BM25Index
from app.domain import Chunk, SearchHit
from app.retrieval.query_analyzer import QueryAnalysis, analyze_query
from app.retrieval.reranker import RerankerProvider
from app.retrieval.rrf import reciprocal_rank_fusion


class DenseProvider(Protocol):
    def search(self, question: str, limit: int) -> list[tuple[str, float]]: ...


class MockDenseProvider:
    """Test-only Dense interface; it never loads a model or connects to Qdrant."""

    def __init__(self, results: dict[str, list[tuple[str, float]]] | None = None) -> None:
        self.results = results or {}

    def search(self, question: str, limit: int) -> list[tuple[str, float]]:
        return self.results.get(question, [])[:limit]


@dataclass(slots=True)
class RetrievalResult:
    analysis: QueryAnalysis
    hits: list[SearchHit]
    debug: dict[str, int | bool | str] = field(default_factory=dict)


class HybridRetriever:
    """Shadow Hybrid Retriever: real BM25 plus an injectable Dense provider."""

    def __init__(
        self,
        bm25: BM25Index,
        chunks: list[Chunk],
        dense: DenseProvider | None = None,
        reranker: RerankerProvider | None = None,
    ) -> None:
        self.bm25 = bm25
        self.chunks = {chunk.chunk_id: chunk for chunk in chunks}
        self.dense = dense or MockDenseProvider()
        self.reranker = reranker

    def search(
        self,
        question: str,
        *,
        bm25_limit: int = 20,
        dense_limit: int = 20,
        rerank_limit: int = 20,
        final_limit: int = 5,
    ) -> RetrievalResult:
        analysis = analyze_query(question)
        bm25_pairs = self.bm25.search(analysis.search_text, limit=bm25_limit)
        dense_pairs = self.dense.search(question, limit=dense_limit)
        bm25_ids = [chunk_id for chunk_id, _ in bm25_pairs]
        dense_ids = [chunk_id for chunk_id, _ in dense_pairs]
        fused = reciprocal_rank_fusion({"bm25": bm25_ids, "dense": dense_ids})
        bm25_ranks = {chunk_id: rank for rank, chunk_id in enumerate(bm25_ids, start=1)}
        dense_ranks = {chunk_id: rank for rank, chunk_id in enumerate(dense_ids, start=1)}
        hits: list[SearchHit] = []
        for candidate in fused:
            chunk = self.chunks.get(candidate.chunk_id)
            if chunk is None:
                continue
            hits.append(
                SearchHit(
                    chunk=chunk,
                    score=candidate.score,
                    bm25_rank=bm25_ranks.get(chunk.chunk_id),
                    dense_rank=dense_ranks.get(chunk.chunk_id),
                )
            )
        reranker_used = False
        candidates = hits[:rerank_limit]
        if self.reranker is not None and candidates:
            rerank_scores = self.reranker.score(
                question, [hit.chunk.text for hit in candidates]
            )
            if rerank_scores is not None and len(rerank_scores) == len(candidates):
                for hit, score in zip(candidates, rerank_scores, strict=True):
                    hit.reranker_score = score
                candidates.sort(
                    key=lambda hit: hit.reranker_score
                    if hit.reranker_score is not None
                    else float("-inf"),
                    reverse=True,
                )
                reranker_used = True

        return RetrievalResult(
            analysis=analysis,
            hits=candidates[:final_limit],
            debug={
                "bm25_hits": len(bm25_pairs),
                "dense_hits": len(dense_pairs),
                "fused_hits": len(fused),
                "reranker_used": reranker_used,
                "metadata_filter_used": False,
            },
        )
