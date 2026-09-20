from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
BASE_GOLD = ROOT / "evaluation" / "knowledge_os_v2_1" / "gold" / "retrieval_gold.jsonl"
REPLACEMENTS = V23 / "gold" / "replacement_candidates.jsonl"
DECISIONS = ROOT / "evaluation" / "knowledge_os_v2_2" / "gold" / "review_decisions.jsonl"
MODEL = ROOT / "models" / "bge-m3"
RERANKER = ROOT / "models" / "bge-reranker-v2-m3"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def norm(value: object) -> str:
    return "".join(str(value or "").casefold().split())


def basename(value: object) -> str:
    return str(value or "").replace("/", "\\").rsplit("\\", 1)[-1].casefold()


def confirmed_gold() -> list[dict]:
    latest: dict[str, dict] = {}
    for row in read_jsonl(DECISIONS):
        latest[str(row.get("question_id"))] = row
    rows = read_jsonl(ROOT / "evaluation" / "knowledge_os_v2_1" / "gold" / "retrieval_gold.jsonl") + read_jsonl(REPLACEMENTS)
    output = []
    seen: set[str] = set()
    for row in rows:
        qid = str(row.get("question_id") or "")
        status = str((latest.get(qid) or {}).get("verification_status") or row.get("verification_status") or "")
        if status not in {"CONFIRMED", "OWNER_CONFIRMED"} or qid in seen:
            continue
        seen.add(qid)
        source = row.get("candidate_source") or {}
        expected_files = list(source.get("files") or row.get("acceptable_sources") or [])
        expected_sections = []
        if source.get("section"):
            expected_sections.append(str(source["section"]))
        expected_sections.extend(str(item if isinstance(item, str) else (item.get("section_path") or item.get("section") or "")) for item in row.get("acceptable_sections") or [])
        output.append({"id": qid, "question": str(row.get("question") or ""), "files": expected_files, "sections": [item for item in expected_sections if item], "candidate_source": source})
    if len(output) != 50:
        raise RuntimeError(f"Retrieval Gold confirmed count is {len(output)}, expected 50")
    return output


def matches(chunk: dict, gold: dict) -> tuple[bool, bool, bool]:
    chunk_file = basename(chunk.get("file_name") or chunk.get("source_path"))
    file_match = any(chunk_file == basename(item) for item in gold["files"] if basename(item))
    chunk_section = norm(chunk.get("section_path"))
    section_match = file_match and (not gold["sections"] or any(norm(section) in chunk_section or chunk_section in norm(section) for section in gold["sections"]))
    table = gold.get("candidate_source", {}).get("table") or {}
    row_match = section_match and (not table or (str(chunk.get("table_id") or "") == str(table.get("table_id") or "") or str(table.get("row") or "") in str(chunk.get("raw_text") or "")))
    if file_match and table.get("table_id") and str(chunk.get("table_id") or "") == str(table.get("table_id")):
        section_match = True
        row_match = not table.get("row") or str(table.get("row")) in str(chunk.get("raw_text") or "") or str(table.get("table_id")) == str(chunk.get("table_id"))
    return file_match, section_match, row_match


def rank_metrics(order: list[int], chunks: list[dict], gold: list[dict], *, limit: int = 20) -> tuple[dict, list[dict]]:
    records = []
    file_ranks, section_ranks, row_ranks = [], [], []
    for item in gold:
        file_rank = section_rank = row_rank = 0
        for position, index in enumerate(order[:limit], start=1):
            file_match, section_match, row_match = matches(chunks[int(index)], item)
            if file_match and not file_rank:
                file_rank = position
            if section_match and not section_rank:
                section_rank = position
            if row_match and not row_rank:
                row_rank = position
        file_ranks.append(file_rank); section_ranks.append(section_rank); row_ranks.append(row_rank)
        records.append({"question_id": item["id"], "expected_files": item["files"], "expected_sections": item["sections"], "file_rank": file_rank, "section_rank": section_rank, "row_rank": row_rank, "top_files": [chunks[int(index)].get("file_name") for index in order[:5]]})
    def metric(values: list[int]) -> dict:
        total = len(values)
        return {"recall@5": round(sum(1 <= value <= 5 for value in values) / total, 4), "recall@10": round(sum(1 <= value <= 10 for value in values) / total, 4), "recall@20": round(sum(1 <= value <= 20 for value in values) / total, 4), "mrr": round(sum(1 / value for value in values if value) / total, 4), "ndcg@10": round(sum(1 / math.log2(value + 1) for value in values if value and value <= 10) / total, 4), "miss": sum(value == 0 for value in values)}
    return {"evaluated": len(gold), "file": metric(file_ranks), "section": metric(section_ranks), "row": metric(row_ranks)}, records


def rrf_order(orders: list[list[int]], k: int) -> list[int]:
    scores: dict[int, float] = {}
    for order in orders:
        for rank, index in enumerate(order, start=1):
            scores[index] = scores.get(index, 0.0) + 1.0 / (k + rank)
    return [index for index, _ in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]


def main() -> int:
    started = time.perf_counter()
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    docs = {str(row.get("document_id")): row for row in read_jsonl(STAGING / "documents.jsonl")}
    for chunk in chunks:
        doc = docs.get(str(chunk.get("document_id")), {})
        chunk["file_name"] = str(doc.get("file_name") or "")
        chunk["source_path"] = str(doc.get("source_path") or "")
    gold = confirmed_gold()
    vectors = np.load(V23 / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
    if vectors.shape[0] != len(chunks):
        raise RuntimeError(f"dense/chunk mismatch: {vectors.shape[0]} != {len(chunks)}")
    weighted_texts = [" ".join([str(row.get("section_path") or "")] * 5 + [str(row.get("file_name") or "")] * 3 + [str((row.get("knowledge_type") or {}).get("value") or "")] * 2 + [str(row.get("raw_text") or "")]) for row in chunks]
    bm25 = BM25Okapi([tokenize(text) or ["_empty_"] for text in weighted_texts])
    encoder_started = time.perf_counter()
    from sentence_transformers import SentenceTransformer
    encoder = SentenceTransformer(str(MODEL), device="cuda", model_kwargs={"torch_dtype": __import__("torch").float16})
    queries = np.asarray(encoder.encode([item["question"] for item in gold], batch_size=4, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)
    del encoder
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass
    dense_orders = []
    bm25_orders = []
    bm25_scores = []
    dense_scores = []
    for row, query in zip(gold, queries, strict=True):
        bm_scores = np.asarray(bm25.get_scores(tokenize(row["question"]) or ["_empty_"]), dtype=np.float32)
        dense = np.asarray(vectors @ query, dtype=np.float32)
        bm_order = np.argsort(-bm_scores).tolist(); dense_order = np.argsort(-dense).tolist()
        bm25_orders.append(bm_order); dense_orders.append(dense_order); bm25_scores.append(bm_scores); dense_scores.append(dense)
    versions: dict[str, dict] = {}
    per_version: dict[str, list[dict]] = {}
    def record_version(name: str, orders: list[list[int]]) -> None:
        ranks = []
        for order, item in zip(orders, gold, strict=True):
            metrics, records = rank_metrics(order, chunks, [item])
            ranks.append(records[0])
        summary, _ = rank_metrics(orders[0], chunks, gold) if False else ({}, [])
        file_ranks = [row["file_rank"] for row in ranks]; section_ranks = [row["section_rank"] for row in ranks]; row_ranks = [row["row_rank"] for row in ranks]
        def metric(values: list[int]) -> dict:
            total = len(values); return {"recall@5": round(sum(1 <= value <= 5 for value in values) / total, 4), "recall@10": round(sum(1 <= value <= 10 for value in values) / total, 4), "recall@20": round(sum(1 <= value <= 20 for value in values) / total, 4), "mrr": round(sum(1 / value for value in values if value) / total, 4), "ndcg@10": round(sum(1 / math.log2(value + 1) for value in values if value and value <= 10) / total, 4), "miss": sum(value == 0 for value in values)}
        versions[name] = {"metrics": {"evaluated": len(gold), "file": metric(file_ranks), "section": metric(section_ranks), "row": metric(row_ranks)}, "latency_p50_ms": None, "latency_p95_ms": None}
        per_version[name] = ranks
    record_version("BM25", bm25_orders); record_version("Dense", dense_orders)
    for weight in (0.7, 0.5, 0.3):
        orders = []
        for bm_scores, dense in zip(bm25_scores, dense_scores, strict=True):
            def scale(values: np.ndarray) -> np.ndarray:
                low, high = float(values.min()), float(values.max()); return (values - low) / (high - low) if high > low else np.zeros_like(values)
            hybrid = weight * scale(bm_scores) + (1 - weight) * scale(dense); orders.append(np.argsort(-hybrid).tolist())
        record_version(f"Hybrid_BM25_{weight:.1f}_Dense_{1-weight:.1f}", orders)
    for k in (20, 40, 60):
        orders = [rrf_order([bm, dense], k) for bm, dense in zip(bm25_orders, dense_orders, strict=True)]
        record_version(f"RRF_k{k}", orders)
    best_name = max(versions, key=lambda name: (versions[name]["metrics"]["file"]["mrr"], versions[name]["metrics"]["file"]["recall@5"], versions[name]["metrics"]["file"]["recall@10"]))
    reranker_report = {"status": "NOT_RUN", "reason": "Best pre-reranker version is recorded; reranker runs in a separate controlled phase."}
    payload = {"schema_version": "knowledge_os_v2_3.retrieval_matrix", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "PASS", "gold_count": len(gold), "gold_ids": [item["id"] for item in gold], "versions": versions, "best_pre_reranker": best_name, "reranker": reranker_report, "encoder_query_seconds": round(time.perf_counter() - encoder_started, 3), "dense_vectors": {"path": str(V23 / "dense_embeddings.npy"), "count": int(vectors.shape[0]), "dimension": int(vectors.shape[1])}, "runtime": {"formal_qdrant_write": False, "formal_8000_touched": False, "provider_http_requests": 0}, "per_question": per_version}
    (V23 / "retrieval_matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (V23 / "retrieval_gold_snapshot.json").write_text(json.dumps({"captured_at": payload["captured_at"], "count": len(gold), "ids": [item["id"] for item in gold]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "gold_count": len(gold), "best_pre_reranker": best_name, "versions": {key: value["metrics"]["file"] for key, value in versions.items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
