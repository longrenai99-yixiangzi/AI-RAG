from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    matrix = json.loads((V23 / "retrieval_matrix.json").read_text(encoding="utf-8"))
    if matrix.get("best_post_reranker") != "RRF_k60":
        raise RuntimeError("candidate winner is not the evaluated RRF_k60 path")
    manifest = {
        "schema_version": "knowledge_os_v2_3.retrieval_candidate_manifest",
        "status": "FROZEN",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "gold_confirmed": matrix.get("gold_count"),
        "retrieval": {"bm25": {"section_path": 5, "file_name": 3, "knowledge_type": 2, "raw_text": 1}, "dense": {"model": "BAAI/bge-m3", "dimension": 1024, "vectors": 8902}, "fusion": {"type": "RRF", "k": 60}, "reranker": {"enabled": False, "reason": "Reranker reduced MRR from 0.5073 to 0.4683 on confirmed Retrieval Gold."}},
        "artifacts": {"chunks": {"path": str(ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl"), "sha256": sha(ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl")}, "dense_embeddings": {"path": str(V23 / "dense_embeddings.npy"), "sha256": sha(V23 / "dense_embeddings.npy")}, "retrieval_matrix": {"path": str(V23 / "retrieval_matrix.json"), "sha256": sha(V23 / "retrieval_matrix.json")}},
        "runtime": {"formal_qdrant_write": False, "formal_8000_touched": False, "provider_http_requests": 0},
    }
    (V23 / "candidate_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
