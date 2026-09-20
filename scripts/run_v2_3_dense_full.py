from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
OUT = ROOT / "evaluation" / "knowledge_os_v2_3"
BATCH_DIR = OUT / "embedding_batches"
MODEL = ROOT / "models" / "bge-m3"
CHECKPOINT = OUT / "embedding_checkpoint.json"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True); BATCH_DIR.mkdir(parents=True, exist_ok=True)
    chunks = [json.loads(line) for line in (STAGING / "semantic_chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = [str(row.get("retrieval_text") or "") for row in chunks]
    hashes = [digest(text) for text in texts]
    existing = json.loads(CHECKPOINT.read_text(encoding="utf-8")) if CHECKPOINT.exists() else {}
    same_job = existing.get("chunk_count") == len(chunks) and existing.get("text_hashes") == hashes and existing.get("model") == str(MODEL)
    batch_size = int(existing.get("batch_size") or 16)
    completed = int(existing.get("encoded_count") or 0) if same_job else 0
    if not same_job:
        existing = {"schema_version": "knowledge_os_v2_3.embedding_checkpoint", "model": str(MODEL), "embedding_model": "BAAI/bge-m3 via sentence-transformers", "chunk_count": len(chunks), "text_hashes": hashes, "encoded_count": 0, "failed_count": 0, "batch_size": batch_size, "batches": [], "status": "RUNNING"}
        for path in BATCH_DIR.glob("vectors_*.npy"): path.unlink()
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(str(MODEL), device="cuda", model_kwargs={"torch_dtype": torch.float16})
    failures = list(existing.get("failures") or [])
    started = time.perf_counter()
    index = completed
    while index < len(chunks):
        current_batch = min(batch_size, len(chunks) - index)
        while True:
            try:
                torch.cuda.empty_cache()
                vectors = model.encode(texts[index : index + current_batch], batch_size=current_batch, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
                vectors = np.asarray(vectors, dtype=np.float32)
                if vectors.ndim != 2 or vectors.shape[0] != current_batch or not np.isfinite(vectors).all():
                    raise ValueError("invalid_embedding_output")
                break
            except RuntimeError as error:
                if "out of memory" not in str(error).lower() or current_batch <= 1:
                    failures.append({"start": index, "count": current_batch, "error": str(error)[:500]}); current_batch = 0; break
                current_batch = max(1, current_batch // 2); batch_size = current_batch; torch.cuda.empty_cache()
        if current_batch == 0:
            index += 1; existing["failed_count"] = len(failures); continue
        batch_path = BATCH_DIR / f"vectors_{index:05d}.npy"
        np.save(batch_path, vectors)
        index += len(vectors)
        existing.update({"encoded_count": index, "failed_count": len(failures), "batch_size": batch_size, "last_chunk_id": chunks[index - 1].get("chunk_id"), "batches": [*existing.get("batches", []), {"start": index - len(vectors), "count": len(vectors), "path": str(batch_path), "seconds": None}]})
        atomic_json(CHECKPOINT, existing)
        print(f"encoded {index}/{len(chunks)} batch={batch_size} elapsed={time.perf_counter() - started:.1f}s", flush=True)
    arrays = [np.load(path) for path in sorted(BATCH_DIR.glob("vectors_*.npy"))]
    matrix = np.vstack(arrays) if arrays else np.empty((0, 1024), dtype=np.float32)
    np.save(OUT / "dense_embeddings.npy", matrix)
    manifest_path = OUT / "dense_embedding_manifest.jsonl"
    created_at = datetime.now(timezone.utc).astimezone().isoformat()
    manifest_path.write_text("".join(json.dumps({"chunk_id": row.get("chunk_id"), "embedding_model": "BAAI/bge-m3", "embedding_version": digest((MODEL / 'config.json').read_text(encoding='utf-8') if (MODEL / 'config.json').exists() else str(MODEL)), "embedding_dimension": int(matrix.shape[1]) if matrix.ndim == 2 and matrix.shape[0] else 0, "retrieval_text_hash": hashes[index], "vector_status": "WRITTEN" if i < len(matrix) else "FAILED", "created_at": created_at}, ensure_ascii=False, separators=(",", ":")) + "\n" for i, (row, index) in enumerate(zip(chunks, range(len(chunks)), strict=True))), encoding="utf-8")
    existing.update({"encoded_count": len(matrix), "failed_count": len(failures), "failures": failures, "status": "PASS" if len(matrix) == len(chunks) and not failures else "PARTIAL", "completed_at": created_at, "embedding_path": str(OUT / 'dense_embeddings.npy')})
    atomic_json(CHECKPOINT, existing)
    report = {"schema_version": "knowledge_os_v2_3.dense_embedding_report", "captured_at": created_at, "status": existing["status"], "device": torch.cuda.get_device_name(0), "torch": torch.__version__, "torch_cuda": torch.version.cuda, "gpu_used": True, "chunk_count": len(chunks), "vectors_written": len(matrix), "failed_embeddings": len(failures), "dimension": int(matrix.shape[1]) if matrix.ndim == 2 and matrix.shape[0] else 0, "batch_size": batch_size, "checkpoint": str(CHECKPOINT), "embedding_manifest": str(manifest_path)}
    (OUT / "dense_embedding_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
