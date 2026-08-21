from __future__ import annotations

import json
import re
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from .domain import Chunk


def tokenize(text: str) -> list[str]:
    """Keep Chinese terms, English identifiers, and numeric codes searchable."""
    jieba_terms = [term.strip().lower() for term in jieba.lcut(text) if term.strip()]
    identifiers = re.findall(r"[A-Za-z][A-Za-z0-9_./-]*|\d+(?:\.\d+)?", text)
    return [*jieba_terms, *(term.lower() for term in identifiers)]


class BM25Index:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.chunk_ids: list[str] = []
        self.corpus: list[list[str]] = []
        self.model: BM25Okapi | None = None

    @property
    def ready(self) -> bool:
        return bool(self.model and self.chunk_ids)

    def build(self, chunks: list[Chunk]) -> None:
        self.chunk_ids = [chunk.chunk_id for chunk in chunks]
        self.corpus = [tokenize(chunk.text) or ["_empty_"] for chunk in chunks]
        self.model = BM25Okapi(self.corpus) if self.corpus else None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"chunk_ids": self.chunk_ids, "corpus": self.corpus}, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self) -> bool:
        if not self.path.exists():
            return False
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.chunk_ids = payload["chunk_ids"]
        self.corpus = payload["corpus"]
        self.model = BM25Okapi(self.corpus) if self.corpus else None
        return self.ready

    def search(
        self,
        query: str,
        limit: int = 20,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        if not self.ready or self.model is None:
            return []
        scores = self.model.get_scores(tokenize(query) or ["_empty_"])
        ranked_indexes = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        eligible = [
            index
            for index in ranked_indexes
            if scores[index] > 0 and (allowed_ids is None or self.chunk_ids[index] in allowed_ids)
        ]
        return [
            (self.chunk_ids[index], float(scores[index]))
            for index in eligible[:limit]
        ]
