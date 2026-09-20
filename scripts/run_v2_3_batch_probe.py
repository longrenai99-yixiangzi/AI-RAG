from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl"
OUT = ROOT / "evaluation" / "knowledge_os_v2_3" / "batch_probe.json"
MODEL = ROOT / "models" / "bge-m3"


def main() -> int:
    rows = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()][:100]
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(str(MODEL), device="cuda", model_kwargs={"torch_dtype": torch.float16})
    results = []
    for batch in (4, 8, 16):
        torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        try:
            vectors = model.encode([str(row.get("retrieval_text") or "") for row in rows], batch_size=batch, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
            results.append({"batch_size": batch, "status": "PASS", "seconds": round(time.perf_counter() - started, 3), "dimension": int(vectors.shape[1]), "peak_allocated_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 2), "peak_reserved_mb": round(torch.cuda.max_memory_reserved() / 1024**2, 2)})
        except RuntimeError as error:
            results.append({"batch_size": batch, "status": "OOM" if "out of memory" in str(error).lower() else "FAIL", "error": str(error)[:400]})
            torch.cuda.empty_cache()
    selected = max((row["batch_size"] for row in results if row["status"] == "PASS"), default=1)
    payload = {"schema_version": "knowledge_os_v2_3.batch_probe", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "device": torch.cuda.get_device_name(0), "sample_count": len(rows), "results": results, "selected_batch_size": selected}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
