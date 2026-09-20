from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2_3"
MODEL = ROOT / "models" / "bge-m3"
CHUNKS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl"


def gpu_memory() -> dict:
    return {"allocated_bytes": torch.cuda.memory_allocated(0), "reserved_bytes": torch.cuda.memory_reserved(0), "allocated_mb": round(torch.cuda.memory_allocated(0) / 1024**2, 2), "reserved_mb": round(torch.cuda.memory_reserved(0) / 1024**2, 2)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = {"schema_version": "knowledge_os_v2_3.dense_smoke", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "torch": torch.__version__, "torch_cuda": torch.version.cuda, "cuda_available": bool(torch.cuda.is_available()), "tests": []}
    if not torch.cuda.is_available():
        payload["status"] = "CUDA_GATE_FAIL"
        (OUT / "dense_smoke_test.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2)); return 2
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(str(MODEL), device="cuda", model_kwargs={"torch_dtype": torch.float16})
    for requested in (8, 32, 100):
        texts = [str(row.get("retrieval_text") or "") for row in chunks[:requested]]
        batch = 4
        started = time.perf_counter()
        try:
            vectors = model.encode(texts, batch_size=batch, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
            elapsed = time.perf_counter() - started
            row = {"requested": requested, "encoded": len(vectors), "dimension": int(vectors.shape[1]), "batch_size": batch, "seconds": round(elapsed, 3), "ms_per_item": round(elapsed * 1000 / len(vectors), 3), "nan": bool(not torch.isfinite(torch.tensor(vectors)).all()), "memory": gpu_memory(), "status": "PASS"}
        except RuntimeError as error:
            if "out of memory" in str(error).lower():
                torch.cuda.empty_cache()
                row = {"requested": requested, "batch_size": batch, "status": "OOM", "error": str(error)[:500], "memory": gpu_memory()}
            else:
                raise
        payload["tests"].append(row)
    payload["status"] = "PASS" if all(row.get("status") == "PASS" for row in payload["tests"]) else "FAIL"
    (OUT / "dense_smoke_test.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
