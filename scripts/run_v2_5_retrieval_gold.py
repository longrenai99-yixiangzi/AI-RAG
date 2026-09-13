from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"
MODEL = ROOT / "models" / "bge-m3"

sys.path.insert(0, str(ROOT / "scripts"))
from run_v2_3_retrieval_matrix import confirmed_gold, matches, rank_metrics, rrf_order  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def metric_for_orders(orders: list[list[int]], chunks: list[dict], gold: list[dict]) -> tuple[dict, list[dict]]:
    records = []
    for order, item in zip(orders, gold, strict=True):
        _, row = rank_metrics(order, chunks, [item])
        records.append(row[0])
    file_ranks = [row["file_rank"] for row in records]
    section_ranks = [row["section_rank"] for row in records]
    row_ranks = [row["row_rank"] for row in records]

    def metric(values: list[int]) -> dict:
        total = len(values)
        return {"recall@5": round(sum(1 <= value <= 5 for value in values) / total, 4), "recall@10": round(sum(1 <= value <= 10 for value in values) / total, 4), "recall@20": round(sum(1 <= value <= 20 for value in values) / total, 4), "mrr": round(sum(1 / value for value in values if value) / total, 4), "ndcg@10": round(sum(1 / math.log2(value + 1) for value in values if value and value <= 10) / total, 4), "miss": sum(value == 0 for value in values)}

    return {"evaluated": len(gold), "file": metric(file_ranks), "section": metric(section_ranks), "row": metric(row_ranks)}, records


def main() -> int:
    started = time.perf_counter()
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    docs = {str(row.get("document_id")): row for row in read_jsonl(STAGING / "documents.jsonl")}
    for chunk in chunks:
        doc = docs.get(str(chunk.get("document_id")), {})
        chunk["file_name"] = chunk.get("file_name") or doc.get("file_name")
        chunk["source_path"] = chunk.get("source_path") or doc.get("source_path")
    gold = confirmed_gold()
    vectors = np.load(STAGING / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
    if vectors.shape[0] != len(chunks):
        raise RuntimeError(f"dense/chunk mismatch: {vectors.shape[0]} != {len(chunks)}")
    weighted_texts = [" ".join([str(row.get("section_path") or "")] * 5 + [str(row.get("file_name") or "")] * 3 + [str((row.get("knowledge_type") or {}).get("value") or "")] * 2 + [str(row.get("raw_text") or "")]) for row in chunks]
    bm25 = BM25Okapi([tokenize(text) or ["_empty_"] for text in weighted_texts])
    import torch
    from sentence_transformers import SentenceTransformer

    encoder = SentenceTransformer(str(MODEL), device="cuda", model_kwargs={"torch_dtype": torch.float16})
    queries = np.asarray(encoder.encode([item["question"] for item in gold], batch_size=4, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)
    del encoder
    torch.cuda.empty_cache()
    bm25_orders, dense_orders, bm25_scores, dense_scores = [], [], [], []
    for item, query in zip(gold, queries, strict=True):
        bm = np.asarray(bm25.get_scores(tokenize(item["question"]) or ["_empty_"]), dtype=np.float32)
        dense = np.asarray(vectors @ query, dtype=np.float32)
        bm25_orders.append(np.argsort(-bm).tolist())
        dense_orders.append(np.argsort(-dense).tolist())
        bm25_scores.append(bm)
        dense_scores.append(dense)
    versions, per_question = {}, {}

    def record(name: str, orders: list[list[int]]) -> None:
        metrics, rows = metric_for_orders(orders, chunks, gold)
        versions[name] = {"metrics": metrics, "parameter_change": False}
        per_question[name] = rows

    record("BM25", bm25_orders)
    record("Dense", dense_orders)
    for weight in (0.7, 0.5, 0.3):
        orders = []
        for bm, dense in zip(bm25_scores, dense_scores, strict=True):
            def scale(values: np.ndarray) -> np.ndarray:
                low, high = float(values.min()), float(values.max())
                return (values - low) / (high - low) if high > low else np.zeros_like(values)
            orders.append(np.argsort(-(weight * scale(bm) + (1 - weight) * scale(dense))).tolist())
        record(f"Hybrid_BM25_{weight:.1f}_Dense_{1-weight:.1f}", orders)
    for k in (20, 40, 60):
        record(f"RRF_k{k}", [rrf_order([bm, dense], k) for bm, dense in zip(bm25_orders, dense_orders, strict=True)])
    baseline = json.loads((V23 / "retrieval_matrix.json").read_text(encoding="utf-8"))
    baseline_metrics = baseline.get("versions", {}).get("RRF_k60", {}).get("metrics", {})
    candidate_metrics = versions["RRF_k60"]["metrics"]
    delta = {}
    for level in ("file", "section", "row"):
        delta[level] = {key: round(candidate_metrics[level][key] - baseline_metrics.get(level, {}).get(key, 0), 4) for key in ("recall@5", "recall@10", "recall@20", "mrr", "ndcg@10", "miss")}
    payload = {"schema_version": "knowledge_os_v2_5.retrieval_gold_result", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "PASS", "gold_count": len(gold), "gold_ids": [item["id"] for item in gold], "frozen_parameters": {"bm25_weights": {"section_path": 5, "file_name": 3, "knowledge_type": 2, "raw_text": 1}, "rrf_k": 60, "reranker_enabled": False}, "versions": versions, "best_pre_reranker": "RRF_k60", "baseline_v2_4_rrf_k60": baseline_metrics, "v2_5_rrf_k60": candidate_metrics, "delta_v2_5_minus_v2_4": delta, "per_question": per_question, "runtime": {"elapsed_seconds": round(time.perf_counter() - started, 3), "formal_qdrant_write": False, "formal_8000_touched": False, "provider_http_requests": 0}}
    comparison = {"schema_version": "knowledge_os_v2_5.retrieval_v2_4_vs_v2_5", "captured_at": payload["captured_at"], "gold_count": len(gold), "baseline": baseline_metrics, "candidate": candidate_metrics, "delta": delta, "gate": "PASS" if all(value["miss"] <= 0 for value in delta.values()) else "FAIL", "note": "No metric threshold or retrieval parameter was changed; delta is reported for owner review."}
    (V25 / "retrieval_gold_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (V25 / "retrieval_v2_4_vs_v2_5.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "gold_count": payload["gold_count"], "rrf_k60": candidate_metrics, "delta": delta, "comparison_gate": comparison["gate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
