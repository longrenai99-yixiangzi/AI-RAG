from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
MANIFEST = V26 / "remediation_candidate_v2_6_2.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    vector_path = Path(manifest["dense_embeddings"]["path"])
    chunk_path = Path(manifest["semantic_chunks"]["path"])
    sources = []
    for item in manifest["sources"]:
        path = Path(item["source_path"])
        actual = sha256(path) if path.exists() else None
        sources.append({"file_name": item["file_name"], "exists": path.exists(), "hash_match": actual == item["sha256"], "approval_status": item.get("approval_status")})
    vectors = np.load(vector_path, mmap_mode="r")
    chunk_count = jsonl_count(chunk_path)
    source_pass = all(item["exists"] and item["hash_match"] and item["approval_status"] == "APPROVED" for item in sources)
    vector_pass = list(vectors.shape) == [chunk_count, 1024]
    payload = {
        "schema_version": "knowledge_os_v2_6_2.candidate_integrity",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidate_hash": manifest["candidate_hash"],
        "source_count": len(sources),
        "approved_sources_pass": source_pass,
        "vector_shape": list(vectors.shape),
        "semantic_chunk_count": chunk_count,
        "vector_chunk_alignment_pass": vector_pass,
        "status": "PASS" if source_pass and vector_pass and manifest.get("status") == "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED" else "FAIL",
        "formal_8000_touched": False,
        "8010_switch_authorized": False,
        "sources": sources,
    }
    out = V26 / "v2_6_2_candidate_integrity.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "candidate_hash", "source_count", "vector_shape", "semantic_chunk_count")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
