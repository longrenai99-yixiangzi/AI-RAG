from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    source = json.loads((V23 / "candidate_manifest.json").read_text(encoding="utf-8"))
    if source.get("status") != "FROZEN" or source.get("retrieval", {}).get("fusion", {}).get("k") != 60:
        raise RuntimeError("V2.3 candidate is not the frozen RRF(k=60) candidate")
    chunks = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl"
    vectors = V23 / "dense_embeddings.npy"
    payload = {
        "schema_version": "knowledge_os_v2_4.candidate_frozen_manifest",
        "status": "FROZEN",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() or None,
        "source_hash": sha(chunks),
        "chunk_version": "structured_knowledge.v2",
        "index_hash": sha(chunks),
        "embedding_model": source["retrieval"]["dense"]["model"],
        "embedding_version": source["artifacts"]["dense_embeddings"]["sha256"],
        "bm25_config": source["retrieval"]["bm25"],
        "rrf_config": source["retrieval"]["fusion"],
        "validator_config": {"false_reject_target": 0.10},
        "candidate_hash": hashlib.sha256(json.dumps(source["retrieval"], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "dense_vectors": {"path": str(vectors), "sha256": sha(vectors), "count": source["retrieval"]["dense"]["vectors"]},
        "reranker": source["retrieval"]["reranker"],
        "runtime": {"formal_8000_touched": False, "formal_qdrant_write": False, "candidate_parameter_changes": False},
    }
    V24.mkdir(parents=True, exist_ok=True)
    (V24 / "candidate_frozen_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
