from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.ingestion.publisher.staging_reader import StagingDocument


@dataclass(slots=True)
class IndexAdapterPlan:
    """Pure publish plan; it contains no vectors and performs no storage writes."""

    qdrant_payloads: list[dict[str, Any]] = field(default_factory=list)
    bm25_records: list[dict[str, Any]] = field(default_factory=list)


class IndexAdapter:
    """Convert Staging JSON to future index payloads without opening either index."""

    def build_plan(self, staging: StagingDocument) -> IndexAdapterPlan:
        qdrant_payloads: list[dict[str, Any]] = []
        bm25_records: list[dict[str, Any]] = []
        for chunk in staging.chunks:
            metadata = dict(chunk.get("metadata") or staging.metadata)
            chunk_id = str(chunk.get("chunk_id", ""))
            qdrant_payloads.append(self.qdrant_payload(chunk, metadata))
            bm25_records.append(self.bm25_record(chunk, metadata))
        return IndexAdapterPlan(qdrant_payloads=qdrant_payloads, bm25_records=bm25_records)

    @staticmethod
    def qdrant_payload(chunk: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
        """Return the future payload; the point ID remains the Chunk chunk_id."""

        return {
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "file_name": chunk.get("file_name"),
            "source_path": chunk.get("source_path"),
            "heading_path": chunk.get("heading_path", ""),
            "location": dict(chunk.get("location") or {}),
            "file_type": metadata.get("file_type"),
            "metadata": dict(metadata),
        }

    @staticmethod
    def bm25_record(chunk: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
        """Return a BM25 record whose stable primary key is chunk_id."""

        return {
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "text": chunk.get("text", ""),
            "metadata": dict(metadata),
        }
