from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping, Sequence

from app.domain import Chunk, SourceBlock


STAGING_SCHEMA_VERSION = "staging.v1"


def build_staging_record(
    *,
    status: str,
    source_blocks: Sequence[SourceBlock],
    chunks: Sequence[Chunk],
    metadata: Mapping[str, Any],
    chunk_metadata: Mapping[str, Mapping[str, Any]],
    error: str | None = None,
) -> dict[str, Any]:
    """Build an in-memory JSON-compatible staging record; no file or index is written."""

    return {
        "schema_version": STAGING_SCHEMA_VERSION,
        "status": status,
        "metadata": dict(metadata),
        "source_blocks": [_dataclass_dict(block) for block in source_blocks],
        "chunks": [
            {
                **_dataclass_dict(chunk),
                "metadata": dict(chunk_metadata.get(chunk.chunk_id, metadata)),
            }
            for chunk in chunks
        ],
        "error": error,
    }


def _dataclass_dict(value: Any) -> dict[str, Any]:
    if not is_dataclass(value):
        raise TypeError(f"staging value must be a dataclass: {type(value).__name__}")
    return asdict(value)
