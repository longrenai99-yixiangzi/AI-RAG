from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.chunker import chunk_blocks
from app.ingestion.pipeline import PipelineResult, run_document_pipeline
from app.ingestion.publisher.index_adapter import IndexAdapter
from app.ingestion.publisher.publish_validator import validate_publish_input
from app.ingestion.publisher.staging_reader import read_staging_json
from app.ingestion.shadow.comparison import LegacyDocument, ShadowComparison, compare_shadow_runs
from app.parsers import parse_file


@dataclass(slots=True)
class ShadowRun:
    new_pipeline: PipelineResult
    legacy_documents: list[LegacyDocument]
    comparison: ShadowComparison


def run_shadow_pipeline(
    root: Path,
    *,
    files: Iterable[Path],
    max_file_size_mb: int = 150,
) -> ShadowRun:
    """Compare new pipeline output with a read-only legacy parser projection."""

    selected = list(files)
    new_pipeline = run_document_pipeline(root, files=selected)
    legacy_documents: list[LegacyDocument] = []
    adapter_counts = [0, 0, 0]

    for document in new_pipeline.documents:
        staging = read_staging_json(document.staging_json())
        validation = validate_publish_input(staging)
        if validation.valid:
            plan = IndexAdapter().build_plan(staging)
            adapter_counts[0] += len(plan.qdrant_payloads)
            adapter_counts[1] += len(plan.bm25_records)
            adapter_counts[2] += len(plan.qdrant_payloads)

    for path in selected:
        try:
            parsed = parse_file(path, max_file_size_mb)
            legacy_documents.append(
                LegacyDocument(
                    path=str(path),
                    file_type=path.suffix.lower(),
                    status=parsed.parse_status,
                    chunks=chunk_blocks(parsed.blocks) if parsed.parse_status == "parsed" else [],
                    error=parsed.error,
                )
            )
        except Exception as error:
            legacy_documents.append(
                LegacyDocument(
                    path=str(path),
                    file_type=path.suffix.lower(),
                    status="read_error",
                    error=f"{type(error).__name__}: {error}",
                )
            )

    comparison = compare_shadow_runs(
        new_pipeline.documents,
        legacy_documents,
        adapter_counts=tuple(adapter_counts),
    )
    return ShadowRun(
        new_pipeline=new_pipeline,
        legacy_documents=legacy_documents,
        comparison=comparison,
    )
