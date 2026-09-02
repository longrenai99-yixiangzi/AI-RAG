from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


STAGING_SCHEMA_VERSION = "staging.v1"


@dataclass(slots=True)
class StagingDocument:
    status: str
    metadata: dict[str, Any]
    source_blocks: list[dict[str, Any]]
    chunks: list[dict[str, Any]]
    error: str | None = None
    schema_version: str = STAGING_SCHEMA_VERSION


def read_staging_json(source: Mapping[str, Any] | Path | str) -> StagingDocument:
    """Read a staging mapping, JSON string, or JSON file without writing anything."""

    payload: Mapping[str, Any]
    if isinstance(source, Path):
        payload = json.loads(source.read_text(encoding="utf-8"))
    elif isinstance(source, str):
        candidate = Path(source)
        if candidate.exists() and candidate.is_file():
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            payload = json.loads(source)
    else:
        payload = source

    return StagingDocument(
        status=str(payload.get("status", "")),
        metadata=dict(payload.get("metadata") or {}),
        source_blocks=[dict(item) for item in payload.get("source_blocks", [])],
        chunks=[dict(item) for item in payload.get("chunks", [])],
        error=payload.get("error"),
        schema_version=str(payload.get("schema_version", "")),
    )
