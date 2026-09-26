from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.knowledge_engineering.structured_v2 import build_structured_layer


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "v2_6_2_sources"
BASE = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "lsr014_source"
MANIFEST = V26 / "remediation_candidate_v2_6_2.json"
REPORT = V26 / "v2_6_2_candidate_page_chunk_rebuild.json"
ARTIFACTS = Path(r"[LOCAL_PATH_REDACTED]")


def read_rows(path: Path, predicate=lambda row: True) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [row for line in stream if line.strip() if predicate(row := json.loads(line))]


def write_rows(path: Path, rows: list[dict]) -> None:
    temp = path.with_suffix(path.suffix + ".rechunk.tmp")
    temp.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n" for row in rows), encoding="utf-8")
    temp.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidate_hash(manifest: dict, chunks_path: Path, vector_path: Path) -> str:
    material = json.dumps(
        {
            "base": manifest["base_candidate_hash"],
            "sources": manifest["sources"],
            "semantic_chunks_sha256": sha256(chunks_path),
            "dense_embeddings_sha256": sha256(vector_path),
            "revision": "V2.6.2_DEV_SOURCE_COVERAGE",
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def main() -> int:
    if "--execute" not in sys.argv:
        raise SystemExit("Refusing to rewrite staged candidate chunks without --execute.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    chunks_path = STAGING / "semantic_chunks.jsonl"
    vector_path = STAGING / "dense_embeddings.npy"
    bindings_path = STAGING / "knowledge_node_bindings.jsonl"
    old_candidate_hash = str(manifest.get("candidate_hash") or "")
    if manifest.get("status") != "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED" or not old_candidate_hash:
        raise RuntimeError("EXPECTED_FROZEN_EMBEDDED_DEV_CANDIDATE")
    if _candidate_hash(manifest, chunks_path, vector_path) != old_candidate_hash:
        raise RuntimeError("CURRENT_CANDIDATE_HASH_MISMATCH_BEFORE_RECHUNK")

    source_rows = manifest.get("sources") or []
    if not source_rows or any(row.get("approval_status") != "APPROVED" for row in source_rows):
        raise RuntimeError("REMEDIATION_SOURCE_SET_NOT_FULLY_APPROVED")
    approval_path = V26 / "remediation_source_approval_v2_6_2.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approved_pairs = {(str(row.get("source_path") or "").casefold(), str(row.get("sha256") or "")) for row in approval.get("records") or []}
    manifest_pairs = {(str(row.get("source_path") or "").casefold(), str(row.get("sha256") or "")) for row in source_rows}
    if approval.get("approval_status") != "APPROVED" or approved_pairs != manifest_pairs:
        raise RuntimeError("SOURCE_APPROVAL_LEDGER_MISMATCH")
    source_ids = {str(row["source_id"]) for row in source_rows}
    approved_documents = read_rows(STAGING / "documents.jsonl", lambda row: str(row.get("source_id") or "") in source_ids)
    parsed_source_ids = {str(row.get("source_id") or "") for row in approved_documents}
    if not parsed_source_ids <= source_ids:
        raise RuntimeError("STAGED_DOCUMENT_SOURCE_SET_MISMATCH")
    sources_without_document = [row for row in source_rows if str(row["source_id"]) not in parsed_source_ids]
    approved_document_ids = {str(row["document_id"]) for row in approved_documents}
    page_document_ids = set()
    page_marker = re.compile(r"---\s*Page\s+\d+\s*---", re.IGNORECASE)
    with (STAGING / "paragraphs.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            document_id = str(row.get("document_id") or "")
            if document_id in approved_document_ids and page_marker.fullmatch(str(row.get("text") or "").strip()):
                page_document_ids.add(document_id)
    documents = [row for row in approved_documents if str(row["document_id"]) in page_document_ids]
    if not documents:
        raise RuntimeError("NO_APPROVED_PDF_PAGE_MARKERS_FOUND")
    document_ids = {str(row["document_id"]) for row in documents}
    sections = read_rows(STAGING / "sections.jsonl", lambda row: str(row.get("document_id") or "") in document_ids)
    paragraphs = read_rows(STAGING / "paragraphs.jsonl", lambda row: str(row.get("document_id") or "") in document_ids)
    tables = read_rows(STAGING / "tables.jsonl", lambda row: str(row.get("document_id") or "") in document_ids)
    table_rows = read_rows(STAGING / "table_rows.jsonl", lambda row: str(row.get("document_id") or "") in document_ids)
    atomic = read_rows(STAGING / "atomic_evidence.jsonl", lambda row: str(row.get("document_id") or "") in document_ids)
    registry = {
        str(row["source_path"]).casefold(): {
            "source_id": str(row["source_id"]),
            "current_hash": str(row["sha256"]),
            "body_status": "APPROVED_DEV_REMEDIATION",
            "index_status": "DEV_REMEDIATION_ONLY",
        }
        for row in source_rows
    }
    layer = build_structured_layer(documents, sections, paragraphs, tables, table_rows, atomic, registry)

    base_chunks = read_rows(BASE / "semantic_chunks.jsonl")
    old_vectors = np.load(vector_path, mmap_mode="r")
    base_vectors = np.load(STAGING / "dense_embeddings_v2_6_1.npy", mmap_mode="r")
    current_chunks = read_rows(chunks_path)
    old_chunk_count = len(current_chunks)
    if old_vectors.shape != (old_chunk_count, 1024) or base_vectors.shape != (len(base_chunks), 1024):
        raise RuntimeError("PRE_RECHUNK_VECTOR_ALIGNMENT_FAILED")
    if [row["chunk_id"] for row in current_chunks[: len(base_chunks)]] != [row["chunk_id"] for row in base_chunks]:
        raise RuntimeError("BASE_V2_6_1_CHUNKS_NOT_UNCHANGED")
    if not layer["semantic_chunks"]:
        raise RuntimeError("NO_REMEDIATION_CHUNKS_REBUILT")
    if any(str(row.get("document_id") or "") in document_ids for row in base_chunks):
        raise RuntimeError("RECHUNK_TARGET_OVERLAPS_BASE_CANDIDATE")
    old_target_chunk_ids = {str(row["chunk_id"]) for row in current_chunks if str(row.get("document_id") or "") in document_ids}
    preserved_chunks = [row for row in current_chunks if str(row.get("document_id") or "") not in document_ids]
    if not old_target_chunk_ids:
        raise RuntimeError("NO_EXISTING_CHUNKS_FOR_RECHUNK_TARGET")
    if any(str(row.get("duplicate_of") or "") in old_target_chunk_ids for row in preserved_chunks):
        raise RuntimeError("PRESERVED_CHUNK_REFERENCES_REPLACED_DUPLICATE")
    combined_chunks = [*preserved_chunks, *layer["semantic_chunks"]]
    added_chunk_count = len(combined_chunks) - len(base_chunks)
    bindings = read_rows(bindings_path)
    combined_bindings = [
        row for row in bindings
        if not (row.get("object_type") == "SEMANTIC_CHUNK" and str(row.get("object_id") or "") in old_target_chunk_ids)
    ]
    combined_bindings.extend(row for row in layer["knowledge_node_bindings"] if row.get("object_type") == "SEMANTIC_CHUNK")
    del old_vectors, base_vectors

    snapshot = ARTIFACTS / f"V2_6_2_pre_page_chunk_candidate_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    snapshot.mkdir(parents=True, exist_ok=False)
    snapshot_files = [chunks_path, bindings_path, vector_path, MANIFEST, approval_path]
    integrity_report = V26 / "v2_6_2_candidate_integrity.json"
    if integrity_report.exists():
        snapshot_files.append(integrity_report)
    for path in snapshot_files:
        shutil.copy2(path, snapshot / path.name)

    write_rows(chunks_path, combined_chunks)
    write_rows(bindings_path, combined_bindings)
    vector_path.unlink()

    manifest["previous_candidate_hash"] = old_candidate_hash
    manifest["status"] = "DEV_REMEDIATION_PENDING_EMBEDDING"
    manifest.pop("candidate_hash", None)
    manifest.pop("dense_embeddings", None)
    manifest["semantic_chunks"] = {
        "base_v2_6_1": len(base_chunks),
        "added": added_chunk_count,
        "total": len(combined_chunks),
        "path": str(chunks_path),
        "sha256": sha256(chunks_path),
    }
    manifest["chunking_revision"] = "PDF_PAGE_BOUNDARY_PRESERVING"
    manifest["source_set_unchanged"] = True
    manifest["formal_8000_touched"] = False
    manifest["8010_switch_performed"] = False
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "schema_version": "knowledge_os_v2_6_2.candidate_page_chunk_rebuild",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "RECHUNKED_PENDING_EMBEDDING",
        "previous_candidate_hash": old_candidate_hash,
        "previous_chunk_count": old_chunk_count,
        "base_chunk_count_preserved": len(base_chunks),
        "source_set_unchanged": True,
        "remediation_source_count": len(source_rows),
        "parsed_document_count": len(approved_documents),
        "approved_sources_without_parsed_document": [
            {"source_id": row["source_id"], "file_name": row["file_name"]}
            for row in sources_without_document
        ],
        "pdf_page_document_count": len(documents),
        "pdf_page_source_ids": sorted({str(row.get("source_id") or "") for row in documents}),
        "old_chunks_replaced": len(old_target_chunk_ids),
        "new_page_chunk_count": len(layer["semantic_chunks"]),
        "new_total_added_chunk_count": added_chunk_count,
        "new_total_chunk_count": len(combined_chunks),
        "semantic_chunks_sha256": sha256(chunks_path),
        "source_approval_sha256_before": sha256(snapshot / approval_path.name),
        "source_approval_sha256_after": sha256(approval_path),
        "snapshot_dir": str(snapshot),
        "gold_exclusion_or_owner_decisions_changed": False,
        "formal_8000_touched": False,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
