from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_evidence import build_atomic_evidence
from app.knowledge_engineering.structured_v2 import build_structured_layer
from scripts.realign_v2_6_2_candidate_embeddings import candidate_hash


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "v2_6_2_sources"
MANIFEST = V26 / "remediation_candidate_v2_6_2.json"
APPROVAL = V26 / "remediation_source_approval_v2_6_2.json"
REPORT = V26 / "v2_6_2_wps_source_parse_repair.json"
ARTIFACTS = Path(r"[LOCAL_PATH_REDACTED]")


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def append_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if "--execute" not in sys.argv:
        raise SystemExit("Refusing to add an approved WPS parse result without --execute.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") != "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED" or not manifest.get("candidate_hash"):
        raise RuntimeError("EXPECTED_CURRENT_EMBEDDED_DEV_CANDIDATE")
    if candidate_hash(manifest, STAGING / "semantic_chunks.jsonl", STAGING / "dense_embeddings.npy") != manifest["candidate_hash"]:
        raise RuntimeError("CURRENT_CANDIDATE_HASH_MISMATCH")
    sources = manifest.get("sources") or []
    matches = [row for row in sources if str(row.get("file_name") or "").lower().endswith(".wps")]
    if len(matches) != 1 or matches[0].get("approval_status") != "APPROVED":
        raise RuntimeError(f"EXPECTED_ONE_APPROVED_WPS_SOURCE:{len(matches)}")
    source = matches[0]
    path = Path(source["source_path"])
    if not path.is_file() or sha256(path) != source["sha256"]:
        raise RuntimeError("APPROVED_WPS_SOURCE_HASH_MISMATCH")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    approval_pairs = {(str(row.get("source_path") or "").casefold(), str(row.get("sha256") or "")) for row in approval.get("records") or []}
    if approval.get("approval_status") != "APPROVED" or (str(source["source_path"]).casefold(), str(source["sha256"])) not in approval_pairs:
        raise RuntimeError("WPS_SOURCE_APPROVAL_RECORD_MISSING")
    if any(str(row.get("source_id") or "") == source["source_id"] for row in read_rows(STAGING / "documents.jsonl")):
        raise RuntimeError("WPS_SOURCE_ALREADY_HAS_STAGED_DOCUMENT")

    atomic = build_atomic_evidence(path, Path(r"[LOCAL_PATH_REDACTED]"))
    if atomic.get("status") != "parsed" or not atomic.get("records"):
        raise RuntimeError(f"WPS_ATOMIC_PARSE_FAILED:{atomic.get('status')}:{atomic.get('error')}")
    parsed = DocumentIntelligenceV2Builder(Path(r"[LOCAL_PATH_REDACTED]")).build([path], atomic["records"])
    if len(parsed.get("documents") or []) != 1 or parsed["documents"][0].get("content_hash") != source["sha256"]:
        raise RuntimeError("WPS_DOCUMENT_PARSE_OR_HASH_FAILED")
    document = parsed["documents"][0]
    document.update({
        "source_id": source["source_id"],
        "source_version": source["sha256"],
        "source_hash": source["sha256"],
        "effective_status": "APPROVED_DEV_REMEDIATION",
    })
    registry = {str(source["source_path"]).casefold(): {
        "source_id": source["source_id"],
        "current_hash": source["sha256"],
        "body_status": "APPROVED_DEV_REMEDIATION",
        "index_status": "DEV_REMEDIATION_ONLY",
    }}
    layer = build_structured_layer(
        [document], parsed["sections"], parsed["paragraphs"], parsed["tables"],
        parsed["table_rows"], parsed["atomic_evidence"], registry,
    )
    if not parsed["paragraphs"] or not layer["semantic_chunks"]:
        raise RuntimeError("WPS_PARSE_PRODUCED_NO_SEARCHABLE_CONTENT")

    snapshot = ARTIFACTS / f"V2_6_2_pre_wps_candidate_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    snapshot.mkdir(parents=True, exist_ok=False)
    snapshot_names = (
        "documents.jsonl", "headings.jsonl", "sections.jsonl", "paragraphs.jsonl",
        "lineage.jsonl", "metadata_conflicts.jsonl", "atomic_evidence.jsonl",
        "semantic_chunks.jsonl", "knowledge_node_bindings.jsonl", "dense_embeddings.npy",
    )
    for name in snapshot_names:
        shutil.copy2(STAGING / name, snapshot / name)
    shutil.copy2(MANIFEST, snapshot / MANIFEST.name)
    shutil.copy2(APPROVAL, snapshot / APPROVAL.name)

    records = {
        "documents.jsonl": parsed["documents"],
        "headings.jsonl": parsed["headings"],
        "sections.jsonl": parsed["sections"],
        "paragraphs.jsonl": parsed["paragraphs"],
        "lineage.jsonl": parsed["lineage"],
        "metadata_conflicts.jsonl": parsed["metadata_conflicts"],
        "atomic_evidence.jsonl": parsed["atomic_evidence"],
        "semantic_chunks.jsonl": layer["semantic_chunks"],
        "knowledge_node_bindings.jsonl": layer["knowledge_node_bindings"],
    }
    for name, rows in records.items():
        append_rows(STAGING / name, rows)

    manifest["previous_candidate_hash"] = manifest["candidate_hash"]
    manifest["status"] = "DEV_REMEDIATION_PENDING_EMBEDDING"
    manifest.pop("candidate_hash", None)
    manifest.pop("dense_embeddings", None)
    chunks_path = STAGING / "semantic_chunks.jsonl"
    chunk_count = sum(1 for line in chunks_path.open(encoding="utf-8") if line.strip())
    manifest["semantic_chunks"] = {
        **(manifest.get("semantic_chunks") or {}),
        "added": int((manifest.get("semantic_chunks") or {}).get("added") or 0) + len(layer["semantic_chunks"]),
        "total": chunk_count,
        "path": str(chunks_path),
        "sha256": sha256(chunks_path),
    }
    manifest["approved_wps_source_parsed"] = source["source_id"]
    manifest["source_set_unchanged"] = True
    manifest["formal_8000_touched"] = False
    manifest["8010_switch_performed"] = False
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "schema_version": "knowledge_os_v2_6_2.approved_wps_source_parse_repair",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "PARSED_STAGED_PENDING_EMBEDDING",
        "previous_candidate_hash": manifest["previous_candidate_hash"],
        "source_id": source["source_id"],
        "file_name": source["file_name"],
        "source_path": source["source_path"],
        "source_sha256": source["sha256"],
        "atomic_record_count": len(parsed["atomic_evidence"]),
        "paragraph_count": len(parsed["paragraphs"]),
        "new_chunk_count": len(layer["semantic_chunks"]),
        "new_candidate_chunk_count": chunk_count,
        "approval_sha256_before": sha256(snapshot / APPROVAL.name),
        "approval_sha256_after": sha256(APPROVAL),
        "snapshot_dir": str(snapshot),
        "gold_exclusion_or_owner_decisions_changed": False,
        "formal_8000_touched": False,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
