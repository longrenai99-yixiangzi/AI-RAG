from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.retrieval.dense_provider import BGEM3DenseProvider


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
MANIFEST = V26 / "remediation_candidate_v2_6_1.json"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "lsr014_source"
MODEL = ROOT / "models" / "bge-m3"
APPROVED_SHA256 = "e51a58bc0a5865620202c0ef39a0597b1e0e3853f48007647dec496121a0b176"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunks() -> list[dict]:
    path = STAGING / "semantic_chunks.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = manifest["source"]
    if source.get("sha256") != APPROVED_SHA256:
        raise RuntimeError("SOURCE_HASH_DOES_NOT_MATCH_USER_APPROVAL")
    chunks = _chunks()
    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_1_remediation_embedding", use_fp16=False, batch_size=4)
    try:
        vectors = np.asarray(provider.embed_documents([str(row.get("retrieval_text") or "") for row in chunks]), dtype=np.float32)
    finally:
        provider.close()
    if vectors.shape != (len(chunks), 1024) or not np.isfinite(vectors).all():
        raise RuntimeError(f"INVALID_EMBEDDING_SHAPE:{vectors.shape}")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError("ZERO_EMBEDDING_VECTOR")
    vectors = vectors / norms
    vector_path = STAGING / "dense_embeddings.npy"
    np.save(vector_path, vectors)
    now = datetime.now(timezone.utc).astimezone().isoformat()
    approval = {
        "schema_version": "knowledge_os_v2_6_1.remediation_source_approval",
        "recorded_at": now,
        "source_path": source["source_path"],
        "sha256": APPROVED_SHA256,
        "approval_status": "APPROVED",
        "approved_by": "USER_CONFIRMED",
        "scope": "V2.6.1_DEV_REMEDIATION only; not an 8010 switch or 8000 write authorization.",
    }
    candidate_material = json.dumps({"base": manifest["base_candidate_hash"], "source_sha256": APPROVED_SHA256, "semantic_chunks_sha256": _sha(STAGING / "semantic_chunks.jsonl"), "dense_embeddings_sha256": _sha(vector_path), "revision": "V2.6.1_DEV_PERIOD_SCOPE_RESCUE"}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    source.update({"approval_status": "APPROVED", "approved_by": "USER_CONFIRMED", "approved_at": now, "effective_status": "APPROVED_DEV_REMEDIATION"})
    manifest.update({
        "status": "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED",
        "approved_at": now,
        "embedding_status": "PASS",
        "dense_embeddings": {"path": str(vector_path), "sha256": _sha(vector_path), "shape": list(vectors.shape), "normalized": True, "model": "BAAI/bge-m3"},
        "candidate_hash": hashlib.sha256(candidate_material).hexdigest(),
        "candidate_revision": "V2.6.1_DEV_PERIOD_SCOPE_RESCUE",
        "formal_8000_touched": False,
        "8010_switch_performed": False,
    })
    (V26 / "remediation_source_approval.json").write_text(json.dumps(approval, ensure_ascii=False, indent=2), encoding="utf-8")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "approval_status": source["approval_status"], "vectors": list(vectors.shape), "candidate_hash": manifest["candidate_hash"], "formal_8000_touched": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
