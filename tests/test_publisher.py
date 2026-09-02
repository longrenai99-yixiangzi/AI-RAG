import json
from pathlib import Path

from app.ingestion.pipeline import run_document_pipeline
from app.ingestion.publisher.index_adapter import IndexAdapter
from app.ingestion.publisher.publish_validator import validate_publish_input
from app.ingestion.publisher.staging_reader import read_staging_json


def _staging_record() -> dict:
    root = Path(__file__).parent / "fixtures"
    path = root / "markdown" / "normal.md"
    result = run_document_pipeline(root, files=[path])
    return result.documents[0].staging_json()


def test_staging_reader_reads_pipeline_json_without_writing() -> None:
    payload = _staging_record()
    staging = read_staging_json(json.dumps(payload, ensure_ascii=False))

    assert staging.schema_version == "staging.v1"
    assert staging.status == "parsed"
    assert staging.source_blocks
    assert staging.chunks


def test_publish_validator_accepts_valid_staging() -> None:
    staging = read_staging_json(_staging_record())

    result = validate_publish_input(staging)

    assert result.valid is True
    assert result.errors == []


def test_index_adapter_links_qdrant_and_bm25_to_chunk_id() -> None:
    staging = read_staging_json(_staging_record())

    plan = IndexAdapter().build_plan(staging)

    assert len(plan.qdrant_payloads) == len(staging.chunks)
    assert len(plan.bm25_records) == len(staging.chunks)
    assert plan.qdrant_payloads[0]["chunk_id"] == staging.chunks[0]["chunk_id"]
    assert plan.qdrant_payloads[0]["metadata"]["file_type"] == ".md"
    assert plan.bm25_records[0]["chunk_id"] == staging.chunks[0]["chunk_id"]


def test_publish_validator_rejects_duplicate_chunk_ids() -> None:
    payload = _staging_record()
    payload["chunks"].append(dict(payload["chunks"][0]))
    staging = read_staging_json(payload)

    result = validate_publish_input(staging)

    assert result.valid is False
    assert any("Chunk ID 重复" in error for error in result.errors)


def test_publish_validator_rejects_error_staging() -> None:
    payload = _staging_record()
    payload["status"] = "read_error"
    payload["error"] = "fixture error"
    staging = read_staging_json(payload)

    result = validate_publish_input(staging)

    assert result.valid is False
    assert any("状态不可发布" in error for error in result.errors)
