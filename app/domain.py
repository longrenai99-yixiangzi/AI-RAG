from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceBlock:
    document_id: str
    source_path: str
    file_name: str
    text: str
    heading_path: str = ""
    location: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    ordinal: int
    source_path: str
    file_name: str
    text: str
    heading_path: str
    location: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedDocument:
    document_id: str
    source_path: str
    file_name: str
    file_type: str
    sha256: str
    file_size: int
    mtime_ns: int
    blocks: list[SourceBlock]
    parse_status: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    needs_ocr: bool = False


@dataclass(slots=True)
class SearchHit:
    chunk: Chunk
    score: float
    dense_rank: int | None = None
    bm25_rank: int | None = None
    reranker_score: float | None = None
