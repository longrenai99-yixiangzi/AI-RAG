from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from app.ingestion.pipeline import PipelineDocument
from app.ingestion.metadata.validator import validate_metadata


@dataclass(slots=True)
class LegacyDocument:
    path: str
    file_type: str
    status: str
    chunks: list[Any] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class ShadowComparison:
    new_document_count: int
    legacy_document_count: int
    new_chunk_count: int
    legacy_chunk_count: int
    stable_chunk_id_count: int
    chunk_id_stability_rate: float
    source_path_document_match_count: int
    source_path_document_match_rate: float
    source_path_match_count: int
    source_path_match_rate: float
    new_location_complete_count: int
    legacy_location_complete_count: int
    new_metadata_complete_count: int
    new_metadata_coverage_rate: float
    new_exception_file_count: int
    legacy_exception_file_count: int
    adapter_chunk_count: int
    adapter_bm25_record_count: int
    adapter_qdrant_payload_count: int
    per_file: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_shadow_runs(
    new_documents: Sequence[PipelineDocument],
    legacy_documents: Sequence[LegacyDocument],
    *,
    adapter_counts: tuple[int, int, int] = (0, 0, 0),
) -> ShadowComparison:
    new_chunks = [chunk for document in new_documents for chunk in document.chunks]
    legacy_chunks = [chunk for document in legacy_documents for chunk in document.chunks]
    new_by_id = {chunk.chunk_id: chunk for chunk in new_chunks}
    legacy_by_id = {chunk.chunk_id: chunk for chunk in legacy_chunks}
    stable_ids = set(new_by_id) & set(legacy_by_id)
    source_path_matches = sum(
        new_by_id[chunk_id].source_path == legacy_by_id[chunk_id].source_path
        for chunk_id in stable_ids
    )
    new_locations = sum(bool(chunk.location) for chunk in new_chunks)
    legacy_locations = sum(bool(chunk.location) for chunk in legacy_chunks)
    new_metadata = sum(
        1
        for document in new_documents
        for metadata in document.chunk_metadata.values()
        if validate_metadata(metadata).valid
    )

    new_paths = {str(document.path) for document in new_documents}
    legacy_paths = {document.path for document in legacy_documents}
    document_path_matches = len(new_paths & legacy_paths)
    per_file: list[dict[str, Any]] = []
    for path in sorted(new_paths | legacy_paths):
        new_doc = next((doc for doc in new_documents if str(doc.path) == path), None)
        legacy_doc = next((doc for doc in legacy_documents if doc.path == path), None)
        new_ids = {chunk.chunk_id for chunk in new_doc.chunks} if new_doc else set()
        legacy_ids = {chunk.chunk_id for chunk in legacy_doc.chunks} if legacy_doc else set()
        per_file.append(
            {
                "path": path,
                "new_status": new_doc.status if new_doc else "missing",
                "legacy_status": legacy_doc.status if legacy_doc else "missing",
                "new_source_blocks": len(new_doc.source_blocks) if new_doc else 0,
                "new_chunks": len(new_ids),
                "legacy_chunks": len(legacy_ids),
                "stable_chunk_ids": len(new_ids & legacy_ids),
                "new_metadata_complete": (
                    all(validate_metadata(new_doc.metadata).valid for _ in new_ids)
                    if new_doc and new_ids
                    else bool(new_doc and not new_ids)
                ),
            }
        )

    return ShadowComparison(
        new_document_count=len(new_documents),
        legacy_document_count=len(legacy_documents),
        new_chunk_count=len(new_chunks),
        legacy_chunk_count=len(legacy_chunks),
        stable_chunk_id_count=len(stable_ids),
        chunk_id_stability_rate=(len(stable_ids) / len(legacy_chunks)) if legacy_chunks else 1.0,
        source_path_document_match_count=document_path_matches,
        source_path_document_match_rate=(
            document_path_matches / max(len(new_paths), len(legacy_paths))
            if new_paths or legacy_paths
            else 1.0
        ),
        source_path_match_count=source_path_matches,
        source_path_match_rate=(source_path_matches / len(stable_ids)) if stable_ids else 1.0,
        new_location_complete_count=new_locations,
        legacy_location_complete_count=legacy_locations,
        new_metadata_complete_count=new_metadata,
        new_metadata_coverage_rate=(new_metadata / len(new_chunks)) if new_chunks else 1.0,
        new_exception_file_count=sum(_is_exception(document.status) for document in new_documents),
        legacy_exception_file_count=sum(_is_exception(document.status) for document in legacy_documents),
        adapter_chunk_count=adapter_counts[0],
        adapter_bm25_record_count=adapter_counts[1],
        adapter_qdrant_payload_count=adapter_counts[2],
        per_file=per_file,
    )


def _is_exception(status: str) -> bool:
    return status not in {"parsed", "empty"}
