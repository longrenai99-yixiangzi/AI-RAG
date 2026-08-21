from __future__ import annotations

from pathlib import Path

import yaml

from .bm25 import BM25Index
from .config import Settings
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
        settings: Settings | None = None,
    ) -> None:
        self.database = database
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.bm25 = bm25
        self.reranker = reranker
        self.settings = settings
        self.routing_rules = self._load_routing_rules(settings)
        self.project_aliases = self._load_project_aliases(settings)

    @staticmethod
    def _load_routing_rules(settings: Settings | None) -> dict[str, dict[str, object]]:
        if settings is None:
            return {}
        path: Path = settings.routing_policy_path
        if not path.exists():
            return {}
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return payload.get("questions", {})

    def _route(self, question: str) -> tuple[str | None, dict[str, object]]:
        folded = question.casefold()
        for route_id, rule in self.routing_rules.items():
            query = str(rule.get("query", "")).casefold()
            expansions = [str(item).casefold() for item in rule.get("query_expansion", [])]
            if (query and query in folded) or any(item in folded for item in expansions):
                return route_id, rule
        return None, {}

    @staticmethod
    def _load_project_aliases(settings: Settings | None) -> list[dict[str, object]]:
        if settings is None or not settings.routing_policy_path.exists():
            return []
        payload = yaml.safe_load(settings.routing_policy_path.read_text(encoding="utf-8")) or {}
        return payload.get("project_aliases", [])

    def _expand_project_aliases(self, question: str) -> list[str]:
        folded = question.casefold()
        expansion: list[str] = []
        for item in self.project_aliases:
            aliases = [str(value) for value in item.get("aliases", [])]
            if any(alias.casefold() in folded for alias in aliases):
                expansion.extend([str(item.get("canonical", "")), *aliases])
        return [value for value in expansion if value]

    @staticmethod
    def _routing_tier(hit: SearchHit, rule: dict[str, object]) -> int:
        haystack = " ".join(
            (hit.chunk.file_name, hit.chunk.source_path, hit.chunk.heading_path)
        ).casefold()
        if any(str(value).casefold() in haystack for value in rule.get("not_primary", [])):
            return -1
        if any(str(value).casefold() in haystack for value in rule.get("preferred", [])):
            return 2
        if any(str(value).casefold() in haystack for value in rule.get("acceptable", [])):
            return 1
        return 0

    @staticmethod
    def _deduplicate_by_file(hits: list[SearchHit], limit: int, per_file: int = 2) -> list[SearchHit]:
        selected: list[SearchHit] = []
        counts: dict[str, int] = {}
        for hit in hits:
            key = hit.chunk.source_path.casefold()
            if counts.get(key, 0) >= per_file:
                continue
            selected.append(hit)
            counts[key] = counts.get(key, 0) + 1
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _evidence_score(hit: SearchHit, rule: dict[str, object]) -> int:
        terms = [str(item).casefold() for item in rule.get("evidence_terms", []) if str(item).strip()]
        if not terms:
            return 0
        haystack = " ".join((hit.chunk.text, hit.chunk.heading_path)).casefold()
        return sum(term in haystack for term in terms)

    def ready(self) -> bool:
        return bool(self.database.stats()["chunks"] and self.bm25.ready)

    def search(
        self, question: str, dense_limit: int = 20, bm25_limit: int = 20, final_limit: int = 8
    ) -> tuple[list[SearchHit], dict[str, int | bool]]:
        route_id, route = self._route(question)
        expansion = [str(item) for item in route.get("query_expansion", [])]
        expansion.extend(self._expand_project_aliases(question))
        expansion_text = " ".join(expansion)
        dense_query = f"{question} {expansion_text}".strip()
        bm25_query = dense_query
        dense_pairs = self.vector_store.query(
            self.embedding_service.embed_query(dense_query), limit=dense_limit
        )
        bm25_pairs = self.bm25.search(bm25_query, limit=bm25_limit)
        dense_ids = [chunk_id for chunk_id, _ in dense_pairs]
        bm25_ids = [chunk_id for chunk_id, _ in bm25_pairs]
        dense_rank = {chunk_id: rank for rank, chunk_id in enumerate(dense_ids, start=1)}
        bm25_rank = {chunk_id: rank for rank, chunk_id in enumerate(bm25_ids, start=1)}
        fused = reciprocal_rank_fusion([dense_ids, bm25_ids])
        candidate_ids = [chunk_id for chunk_id, _ in fused[: max(dense_limit, bm25_limit)]]
        forced_ids = self.database.find_chunk_ids(
            source_terms=[str(item) for item in route.get("preferred", [])],
            text_terms=[str(item) for item in route.get("evidence_terms", [])],
        )
        for chunk_id in forced_ids:
            if chunk_id not in candidate_ids:
                candidate_ids.append(chunk_id)
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
        eligible = [hit for hit in hits if self._routing_tier(hit, route) >= 0]
        if eligible:
            hits = eligible
        rerank_scores = self.reranker.score(question, [hit.chunk.text for hit in hits])
        if rerank_scores is not None:
            for hit, score in zip(hits, rerank_scores, strict=True):
                hit.reranker_score = score
        hits.sort(
            key=lambda hit: (
                self._routing_tier(hit, route),
                self._evidence_score(hit, route),
                hit.reranker_score if hit.reranker_score is not None else hit.score,
            ),
            reverse=True,
        )
        hits = self._deduplicate_by_file(hits, final_limit)
        return hits, {
            "dense_hits": len(dense_pairs),
            "bm25_hits": len(bm25_pairs),
            "fused_hits": len(hits),
            "reranker_used": rerank_scores is not None,
            "routing_rule": route_id or "none",
            "clarification_required": bool(route.get("clarification_required", False)),
        }
