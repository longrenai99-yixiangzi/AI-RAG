"""T05: build and evaluate independent BGE-M3 embeddings for Semantic Chunk V2."""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
OUT = ROOT / "evaluation" / "knowledge_os_v2_1" / "retrieval_ab"
MODEL = ROOT / "models" / "bge-m3"
GOLD = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_gold() -> list[dict]:
    data = yaml.safe_load(GOLD.read_text(encoding="utf-8")) or {}
    return [{"id": row.get("id"), "question": str(row["question"]), "expected_files": [str(value) for value in row.get("expected_files") or []]} for row in data.get("questions") or [] if row.get("question") and row.get("expected_files")]


def evaluate(rows: list[dict], scores: np.ndarray, gold: list[dict]) -> tuple[dict, list[int], list[dict]]:
    ranks: list[int] = []
    details: list[dict] = []
    for index, question in enumerate(gold):
        expected = {value.casefold() for value in question["expected_files"]}
        order = np.argsort(-scores[index])
        rank = 0
        for position, row_index in enumerate(order[:20], start=1):
            if str(rows[int(row_index)].get("file_name") or "").casefold() in expected:
                rank = position
                break
        ranks.append(rank)
        details.append({"question_id": question["id"], "question": question["question"], "expected_files": question["expected_files"], "dense_rank": rank, "top_files": [str(rows[int(row_index)].get("file_name") or "") for row_index in order[:5]]})
    total = len(ranks)
    ndcg = sum((1 / math.log2(rank + 1)) for rank in ranks if rank and rank <= 10) / total if total else 0
    return {"status": "RUN", "evaluated_questions": total, "recall@5": round(sum(1 <= rank <= 5 for rank in ranks) / total, 4) if total else None, "recall@10": round(sum(1 <= rank <= 10 for rank in ranks) / total, 4) if total else None, "recall@20": round(sum(1 <= rank <= 20 for rank in ranks) / total, 4) if total else None, "mrr": round(sum(1 / rank for rank in ranks if rank) / total, 4) if total else None, "ndcg@10": round(ndcg, 4), "miss_count": sum(rank == 0 for rank in ranks)}, ranks, details


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    docs = {str(row.get("document_id")): row for row in read_jsonl(STAGING / "documents.jsonl")}
    for row in chunks:
        row["file_name"] = str(docs.get(str(row.get("document_id")), {}).get("file_name") or "")
    texts = [str(row.get("retrieval_text") or "") for row in chunks]
    text_hashes = [text_hash(text) for text in texts]
    vector_path = OUT / "semantic_v2_embeddings.npy"
    manifest_path = OUT / "embedding_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if vector_path.exists() and manifest.get("chunk_count") == len(chunks) and manifest.get("text_hashes") == text_hashes:
        vectors = np.load(vector_path).astype(np.float32)
        embedding_reused = True
    else:
        if not MODEL.is_dir():
            raise SystemExit(f"BGE-M3 model not found: {MODEL}")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(str(MODEL), device="cpu")
        started = time.perf_counter()
        vectors = np.asarray(model.encode(texts, batch_size=4, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=True), dtype=np.float32)
        np.save(vector_path, vectors)
        manifest = {"schema_version": "knowledge_os_v2_1.embedding", "model": str(MODEL), "embedding_model": "BAAI/bge-m3-local via sentence-transformers", "embedding_version": text_hash((MODEL / "config.json").read_text(encoding="utf-8") if (MODEL / "config.json").exists() else str(MODEL)), "chunk_count": len(chunks), "dimension": int(vectors.shape[1]), "text_hashes": text_hashes, "source": "Semantic Chunk V2 retrieval_text", "parent_document_vector_fallback": False}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        embedding_reused = False
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    vectors = vectors / norms
    gold = load_gold()
    model = locals().get("model")
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(str(MODEL), device="cpu")
    q_started = time.perf_counter()
    queries = np.asarray(model.encode([row["question"] for row in gold], batch_size=4, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)
    q_norms = np.linalg.norm(queries, axis=1, keepdims=True); q_norms[q_norms == 0] = 1; queries = queries / q_norms
    scores = queries @ vectors.T
    metric, ranks, details = evaluate(chunks, scores, gold)
    payload = {"schema_version": "knowledge_os_v2_1.dense.metrics", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "embedding_reused": embedding_reused, "embedding_manifest": str(manifest_path), "query_encoding_seconds": round(time.perf_counter() - q_started, 3), "metrics": metric, "ranks": ranks, "details": details}
    (OUT / "dense_v2_metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"embedding_reused": embedding_reused, "chunks": len(chunks), "gold": len(gold), "metrics": metric, "vector_path": str(vector_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
