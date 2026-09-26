from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from app.retrieval.dense_provider import BGEM3DenseProvider


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "v2_6_2_sources"
MANIFEST = V26 / "remediation_candidate_v2_6_2.json"
REBUILD_REPORT = V26 / "v2_6_2_candidate_page_chunk_rebuild.json"
REPORT = V26 / "v2_6_2_candidate_embedding_realign.json"
MODEL = ROOT / "models" / "bge-m3"
ARTIFACTS = Path(r"[LOCAL_PATH_REDACTED]")


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def candidate_hash(manifest: dict, chunks_path: Path, vectors_path: Path) -> str:
    material = json.dumps(
        {
            "base": manifest["base_candidate_hash"],
            "sources": manifest["sources"],
            "semantic_chunks_sha256": sha256(chunks_path),
            "dense_embeddings_sha256": sha256(vectors_path),
            "revision": "V2.6.2_DEV_SOURCE_COVERAGE",
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def align_embeddings(
    old_chunks: list[dict],
    old_vectors: np.ndarray,
    new_chunks: list[dict],
    embed_missing: Callable[[list[str]], np.ndarray],
) -> tuple[np.ndarray, int, int]:
    if old_vectors.ndim != 2 or old_vectors.shape[0] != len(old_chunks):
        raise ValueError("OLD_VECTOR_ALIGNMENT_FAILED")
    old_index = {str(row["chunk_id"]): i for i, row in enumerate(old_chunks)}
    if len(old_index) != len(old_chunks):
        raise ValueError("DUPLICATE_OLD_CHUNK_ID")
    vectors = np.empty((len(new_chunks), old_vectors.shape[1]), dtype=np.float32)
    missing_positions, missing_texts = [], []
    reused = 0
    for position, row in enumerate(new_chunks):
        old_position = old_index.get(str(row["chunk_id"]))
        if old_position is None:
            missing_positions.append(position)
            missing_texts.append(str(row.get("retrieval_text") or ""))
            continue
        old_row = old_chunks[old_position]
        if old_row.get("raw_text") != row.get("raw_text") or old_row.get("retrieval_text") != row.get("retrieval_text"):
            raise ValueError(f"REUSED_CHUNK_CONTENT_CHANGED:{row['chunk_id']}")
        vectors[position] = old_vectors[old_position]
        reused += 1
    if missing_texts:
        fresh = np.asarray(embed_missing(missing_texts), dtype=np.float32)
        if fresh.shape != (len(missing_texts), old_vectors.shape[1]) or not np.isfinite(fresh).all():
            raise ValueError(f"NEW_VECTOR_ALIGNMENT_FAILED:{fresh.shape}")
        norms = np.linalg.norm(fresh, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("ZERO_NEW_VECTOR")
        vectors[missing_positions] = fresh / norms
    if not np.isfinite(vectors).all() or np.any(np.linalg.norm(vectors, axis=1) == 0):
        raise ValueError("FINAL_VECTOR_VALIDATION_FAILED")
    return vectors, reused, len(missing_texts)


def main() -> int:
    if "--execute" not in sys.argv or "--previous-snapshot" not in sys.argv:
        raise SystemExit("Use --execute --previous-snapshot <d6bc snapshot directory>.")
    previous = Path(sys.argv[sys.argv.index("--previous-snapshot") + 1])
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    old_manifest_path = previous / "remediation_candidate_v2_6_2.json"
    old_chunks_path = previous / "semantic_chunks.jsonl"
    old_vectors_path = previous / "dense_embeddings.npy"
    chunks_path = STAGING / "semantic_chunks.jsonl"
    vectors_path = STAGING / "dense_embeddings.npy"
    pending_embedding = manifest.get("status") == "DEV_REMEDIATION_PENDING_EMBEDDING"
    if not pending_embedding and (manifest.get("status") != "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED" or not manifest.get("candidate_hash")):
        raise RuntimeError("CURRENT_CANDIDATE_NOT_EMBEDDED")
    if not pending_embedding and candidate_hash(manifest, chunks_path, vectors_path) != manifest["candidate_hash"]:
        raise RuntimeError("CURRENT_CANDIDATE_HASH_MISMATCH")
    old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
    old_chunks, new_chunks = read_rows(old_chunks_path), read_rows(chunks_path)
    old_vectors = np.load(old_vectors_path, mmap_mode="r")
    if not str(old_manifest.get("dense_embeddings", {}).get("runtime") or "").startswith("CPU_FP32"):
        raise RuntimeError("PREVIOUS_CANDIDATE_NOT_CPU_FP32")
    if old_manifest.get("base_candidate_hash") != manifest.get("base_candidate_hash"):
        raise RuntimeError("BASE_CANDIDATE_CHANGED")
    source_pairs = lambda rows: {(str(row.get("source_path") or "").casefold(), str(row.get("sha256") or "")) for row in rows}
    if source_pairs(old_manifest.get("sources") or []) != source_pairs(manifest.get("sources") or []):
        raise RuntimeError("CANDIDATE_SOURCE_SET_CHANGED")

    provider = BGEM3DenseProvider(MODEL, collection_name="v2_6_2_cpu_delta_reembed", use_fp16=False, batch_size=32)
    try:
        vectors, reused, written = align_embeddings(old_chunks, old_vectors, new_chunks, provider.embed_documents)
    finally:
        provider.close()
    del old_vectors

    previous_hash = str(manifest.get("candidate_hash") or manifest.get("previous_candidate_hash") or old_manifest["candidate_hash"])
    intermediate = ARTIFACTS / f"V2_6_2_cuda_fp16_intermediate_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    intermediate.mkdir(parents=True, exist_ok=False)
    shutil.copy2(vectors_path, intermediate / vectors_path.name)
    shutil.copy2(MANIFEST, intermediate / MANIFEST.name)
    temp_vectors = vectors_path.with_name("dense_embeddings.cpu_fp32.tmp.npy")
    with temp_vectors.open("wb") as stream:
        np.save(stream, vectors)
    temp_vectors.replace(vectors_path)

    now = datetime.now(timezone.utc).astimezone().isoformat()
    manifest["previous_vector_candidate_hash"] = old_manifest["candidate_hash"]
    manifest["dense_embeddings"] = {
        "path": str(vectors_path),
        "sha256": sha256(vectors_path),
        "shape": list(vectors.shape),
        "normalized_new_vectors": True,
        "model": "BAAI/bge-m3",
        "base_vectors_reused": reused,
        "new_vectors_written": written,
        "runtime": "CPU_FP32_DELTA_REUSE",
        "embedding_source_candidate_hash": old_manifest["candidate_hash"],
    }
    manifest["candidate_hash"] = candidate_hash(manifest, chunks_path, vectors_path)
    manifest["status"] = "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED"
    manifest["embedded_at"] = now
    manifest["embedding_status"] = "PASS"
    manifest["formal_8000_touched"] = False
    manifest["8010_switch_performed"] = False
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "schema_version": "knowledge_os_v2_6_2.candidate_embedding_realign",
        "captured_at": now,
        "status": "PASS",
        "previous_candidate_hash": old_manifest["candidate_hash"],
        "replaced_intermediate_candidate_hash": previous_hash,
        "candidate_hash": manifest["candidate_hash"],
        "old_vector_runtime": old_manifest["dense_embeddings"]["runtime"],
        "new_vector_runtime": "CPU_FP32_DELTA_REUSE",
        "old_chunk_count": len(old_chunks),
        "new_chunk_count": len(new_chunks),
        "reused_same_chunk_vectors": reused,
        "new_cpu_fp32_vectors": written,
        "intermediate_cuda_snapshot": str(intermediate),
        "formal_8000_touched": False,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if REBUILD_REPORT.exists():
        rebuilt = json.loads(REBUILD_REPORT.read_text(encoding="utf-8"))
        rebuilt.update({"status": "RECHUNKED_EMBEDDED", "candidate_hash": manifest["candidate_hash"], "embedding_runtime": "CPU_FP32_DELTA_REUSE"})
        REBUILD_REPORT.write_text(json.dumps(rebuilt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
