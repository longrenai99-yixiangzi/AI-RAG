from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.retrieval.dense_provider import BGEM3DenseProvider


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "v2_6_2_sources"
MODEL = ROOT / "models" / "bge-m3"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest_path = V26 / "remediation_candidate_v2_6_2.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "DEV_REMEDIATION_PENDING_EMBEDDING":
        raise RuntimeError("V2_6_2_CANDIDATE_NOT_PENDING_EMBEDDING")
    chunks = _read_jsonl(STAGING / "semantic_chunks.jsonl")
    vector_path = STAGING / "dense_embeddings.npy"
    existing = np.load(vector_path).astype(np.float32) if vector_path.exists() else np.load(STAGING / "dense_embeddings_v2_6_1.npy").astype(np.float32)
    base_count = int(existing.shape[0])
    if existing.ndim != 2 or existing.shape[1] != 1024 or base_count > len(chunks):
        raise RuntimeError(f"V2_6_2_BASE_VECTOR_MISMATCH:{existing.shape}:{len(chunks)}:{base_count}")
    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_2_remediation_embedding", use_fp16=False, batch_size=32)
    try:
        fresh = np.asarray(provider.embed_documents([str(row.get("retrieval_text") or "") for row in chunks[base_count:]]), dtype=np.float32)
    finally:
        provider.close()
    if fresh.shape != (len(chunks) - base_count, 1024) or not np.isfinite(fresh).all():
        raise RuntimeError(f"V2_6_2_NEW_VECTOR_MISMATCH:{fresh.shape}")
    norms = np.linalg.norm(fresh, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError("V2_6_2_ZERO_EMBEDDING_VECTOR")
    vectors = np.concatenate((existing, fresh / norms), axis=0)
    np.save(vector_path, vectors)
    now = datetime.now(timezone.utc).astimezone().isoformat()
    candidate_material = json.dumps({"base": manifest["base_candidate_hash"], "sources": manifest["sources"], "semantic_chunks_sha256": _sha(STAGING / "semantic_chunks.jsonl"), "dense_embeddings_sha256": _sha(vector_path), "revision": "V2.6.2_DEV_SOURCE_COVERAGE"}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    manifest.update({"status": "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED", "embedded_at": now, "embedding_status": "PASS", "dense_embeddings": {"path": str(vector_path), "sha256": _sha(vector_path), "shape": list(vectors.shape), "normalized_new_vectors": True, "model": "BAAI/bge-m3", "base_vectors_reused": base_count, "new_vectors_written": len(fresh)}, "candidate_hash": hashlib.sha256(candidate_material).hexdigest(), "candidate_revision": "V2.6.2_DEV_SOURCE_COVERAGE", "formal_8000_touched": False, "8010_switch_performed": False})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "vectors": list(vectors.shape), "base_vectors_reused": base_count, "new_vectors_written": len(fresh), "candidate_hash": manifest["candidate_hash"], "formal_8000_touched": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
