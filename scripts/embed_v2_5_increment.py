from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"
OLD = ROOT / "data" / "shadow" / "knowledge_v2_staging"
MODEL = ROOT / "models" / "bge-m3"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    old_chunks = read_jsonl(OLD / "semantic_chunks.jsonl")
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    old_vectors = np.load(V23 / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
    old_by_id = {str(row.get("chunk_id")): old_vectors[index] for index, row in enumerate(old_chunks)}
    new_indexes = [index for index, row in enumerate(chunks) if str(row.get("chunk_id")) not in old_by_id]
    import torch
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(str(MODEL), device="cuda", model_kwargs={"torch_dtype": torch.float16})
    vectors = np.zeros((len(chunks), old_vectors.shape[1]), dtype=np.float32)
    for index, row in enumerate(chunks):
        if str(row.get("chunk_id")) in old_by_id:
            vectors[index] = old_by_id[str(row.get("chunk_id"))]
    failed = []
    for start in range(0, len(new_indexes), 4):
        indexes = new_indexes[start : start + 4]
        try:
            encoded = model.encode([str(chunks[index].get("retrieval_text") or "") for index in indexes], batch_size=len(indexes), normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
            encoded = np.asarray(encoded, dtype=np.float32)
            if encoded.ndim != 2 or encoded.shape[0] != len(indexes) or not np.isfinite(encoded).all():
                raise ValueError("invalid_embedding_output")
            for index, vector in zip(indexes, encoded, strict=True):
                vectors[index] = vector
        except Exception as error:
            failed.extend({"chunk_id": chunks[index].get("chunk_id"), "error": f"{type(error).__name__}: {error}"} for index in indexes)
        if (start // 4 + 1) % 50 == 0 or start + len(indexes) == len(new_indexes):
            print(f"incremental_embedding={min(start + len(indexes), len(new_indexes))}/{len(new_indexes)}", flush=True)
    del model
    torch.cuda.empty_cache()
    old_equal = all(np.array_equal(vectors[index], old_by_id[str(row.get("chunk_id"))]) for index, row in enumerate(chunks) if str(row.get("chunk_id")) in old_by_id)
    np.save(STAGING / "dense_embeddings.npy", vectors)
    now = datetime.now(timezone.utc).astimezone().isoformat()
    report = {"schema_version": "knowledge_os_v2_5.embedding_increment_report", "captured_at": now, "status": "PASS" if not failed and old_equal else "FAIL", "old_chunk_count": len(old_chunks), "new_chunk_count": len(chunks), "new_vectors_written": len(new_indexes) - len(failed), "new_vectors_pending": len(failed), "old_vectors_reused": len(old_chunks), "old_vectors_changed": 0 if old_equal else "UNKNOWN", "old_vectors_equal": old_equal, "failed_embeddings": failed, "model": "BAAI/bge-m3", "input": "retrieval_text", "batch_size": 4, "formal_8000_touched": False}
    (V25 / "embedding_increment_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "old_chunk_count", "new_chunk_count", "new_vectors_written", "new_vectors_pending", "old_vectors_reused", "old_vectors_changed", "old_vectors_equal")}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
