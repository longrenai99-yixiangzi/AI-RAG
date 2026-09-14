from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder
from app.ingestion.atomic_evidence import build_atomic_evidence
from app.knowledge_engineering.structured_v2 import build_structured_layer


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
V261_STAGE = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "lsr014_source"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "v2_6_2_sources"
APPROVED = Path(r"D:\设计管理\.ai-growth\parsed\approved-sources")
SOURCES = {
    "b6077e3f74f0a1b7ae9f.md": "c392bc19e997b52f2f31be948ea8876830c0055f612016fd8b1dc119affcb323",
    "cb93c382c9197043cab1.md": "7ce9483b9a83a5a0797c647718e82de2a9e68028a9ffa558c491102d06c29424",
    "f80e5def25e5a56bfc6f.md": "bcc9a3b8685a86085ce26f1b5163406c6db9801a4258778aee98ee912a5ba082",
    "0ee2959550610ce23750.md": "c921b8c3773304cd2ffef8659812d1498317900cbd8892460454b22a6060f89d",
    "2c5dbe10c9b44d1d47d0.md": "2d2a1005a60aae43465dd06dcb633bcd2ad1b1f3fd2812a7ee3b063e2b030cdc",
    "77d7e542b45a93853e16.md": "c78ccf30fb5e64479fba27a4bdf73b6cbc243b4bc31c8a3f2de1415054d48e7c",
    "90b557ce19fb9d757b47.md": "d23adc39ed9e3fd7c13f41b5cb02a9399f813cc902b2c04a9537853586d2ad9e",
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    paths = [APPROVED / name for name in SOURCES]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(missing)
    mismatched = [{"path": str(path), "expected": SOURCES[path.name], "actual": _sha(path)} for path in paths if _sha(path) != SOURCES[path.name]]
    if mismatched:
        raise RuntimeError(f"SOURCE_SHA256_MISMATCH:{mismatched}")
    builder = DocumentIntelligenceV2Builder(APPROVED.parents[1])
    atomic = []
    for path in paths:
        atomic.extend(build_atomic_evidence(path, APPROVED.parents[1]).get("records") or [])
    parsed = builder.build(paths, atomic)
    registry = {}
    admitted = []
    for path in paths:
        digest = SOURCES[path.name]
        source_id = "V262-" + hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:24]
        registry[str(path).casefold()] = {"source_id": source_id, "source_path": str(path), "current_hash": digest, "body_status": "APPROVED_DEV_REMEDIATION", "index_status": "DEV_REMEDIATION_ONLY"}
        admitted.append({"source_id": source_id, "source_path": str(path), "file_name": path.name, "sha256": digest, "approval_status": "APPROVED", "approved_by": "USER_CONFIRMED"})
    for document in parsed["documents"]:
        path = Path(str(document.get("source_path") or ""))
        document.update({"source_id": registry[str(path).casefold()]["source_id"], "source_version": SOURCES[path.name], "source_hash": SOURCES[path.name], "effective_status": "APPROVED_DEV_REMEDIATION"})
    layer = build_structured_layer(parsed["documents"], parsed["sections"], parsed["paragraphs"], parsed["tables"], parsed["table_rows"], parsed["atomic_evidence"], registry)
    STAGING.mkdir(parents=True, exist_ok=True)
    for name in ("documents", "headings", "sections", "paragraphs", "tables", "table_rows", "lineage", "metadata_conflicts", "atomic_evidence"):
        old = _read_jsonl(V261_STAGE / f"{name}.jsonl")
        _write_jsonl(STAGING / f"{name}.jsonl", [*old, *(parsed.get(name) or [])])
    old_chunks = _read_jsonl(V261_STAGE / "semantic_chunks.jsonl")
    _write_jsonl(STAGING / "semantic_chunks.jsonl", [*old_chunks, *layer["semantic_chunks"]])
    _write_jsonl(STAGING / "knowledge_node_bindings.jsonl", [*_read_jsonl(V261_STAGE / "knowledge_node_bindings.jsonl"), *layer["knowledge_node_bindings"]])
    shutil.copyfile(V261_STAGE / "dense_embeddings.npy", STAGING / "dense_embeddings_v2_6_1.npy")
    now = datetime.now(timezone.utc).astimezone().isoformat()
    manifest = {
        "schema_version": "knowledge_os_v2_6_2.dev_remediation_candidate",
        "candidate_id": "V2.6.2-DEV-SOURCE-COVERAGE",
        "captured_at": now,
        "status": "DEV_REMEDIATION_PENDING_EMBEDDING",
        "base_candidate_hash": json.loads((V26 / "remediation_candidate_v2_6_1.json").read_text(encoding="utf-8"))["candidate_hash"],
        "candidate_revision": "V2.6.2_DEV_SOURCE_COVERAGE",
        "source_count_added": len(paths),
        "sources": admitted,
        "parse_counts_added": {name: len(parsed.get(name) or []) for name in ("documents", "sections", "paragraphs", "tables", "table_rows", "atomic_evidence", "metadata_conflicts")},
        "semantic_chunks": {"base_v2_6_1": len(old_chunks), "added": len(layer["semantic_chunks"]), "total": len(old_chunks) + len(layer["semantic_chunks"]), "path": str(STAGING / "semantic_chunks.jsonl")},
        "embedding_status": "PENDING_NEW_SOURCE_EMBEDDING",
        "formal_8000_touched": False,
        "8010_switch_performed": False,
        "approval_scope": "User approved seven SHA-256 versions for V2.6.2_DEV_REMEDIATION only.",
    }
    (V26 / "remediation_candidate_v2_6_2.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (V26 / "remediation_source_approval_v2_6_2.json").write_text(json.dumps({"schema_version": "knowledge_os_v2_6_2.source_approval", "captured_at": now, "approval_status": "APPROVED", "approved_by": "USER_CONFIRMED", "records": admitted, "formal_8000_touched": False, "8010_switch_authorized": False}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "source_count_added": len(paths), "parse_counts_added": manifest["parse_counts_added"], "semantic_chunks": manifest["semantic_chunks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
