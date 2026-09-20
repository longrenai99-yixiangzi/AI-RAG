from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize
from app.retrieval.reranker_provider import BGERerankerProvider
from scripts.run_v2_3_retrieval_matrix import confirmed_gold, matches, read_jsonl, rrf_order


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
MODEL = ROOT / "models" / "bge-m3"
RERANKER = ROOT / "models" / "bge-reranker-v2-m3"


def main() -> int:
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    docs = {str(row.get("document_id")): row for row in read_jsonl(STAGING / "documents.jsonl")}
    for chunk in chunks:
        doc = docs.get(str(chunk.get("document_id")), {})
        chunk["file_name"] = str(doc.get("file_name") or "")
        chunk["source_path"] = str(doc.get("source_path") or "")
    gold = confirmed_gold()
    vectors = np.load(V23 / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
    weighted = [" ".join([str(row.get("section_path") or "")] * 5 + [str(row.get("file_name") or "")] * 3 + [str((row.get("knowledge_type") or {}).get("value") or "")] * 2 + [str(row.get("raw_text") or "")]) for row in chunks]
    bm25 = BM25Okapi([tokenize(text) or ["_empty_"] for text in weighted])
    import torch
    from sentence_transformers import SentenceTransformer
    encoder = SentenceTransformer(str(MODEL), device="cuda", model_kwargs={"torch_dtype": torch.float16})
    queries = np.asarray(encoder.encode([item["question"] for item in gold], batch_size=4, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)
    del encoder
    torch.cuda.empty_cache()
    pre_orders = []
    for item, query in zip(gold, queries, strict=True):
        bm = np.asarray(bm25.get_scores(tokenize(item["question"]) or ["_empty_"]) , dtype=np.float32)
        dense = np.asarray(vectors @ query, dtype=np.float32)
        pre_orders.append(rrf_order([np.argsort(-bm).tolist(), np.argsort(-dense).tolist()], 60)[:20])
    provider = BGERerankerProvider(RERANKER, use_fp16=True, max_length=512)
    rerank_orders = []
    for item, order in zip(gold, pre_orders, strict=True):
        passages = ["[文档] " + str(chunks[index].get("file_name") or "") + "\n[章节] " + str(chunks[index].get("section_path") or "") + "\n[正文] " + str(chunks[index].get("raw_text") or "")[:1200] for index in order]
        scores = provider.score(item["question"], passages) or [0.0] * len(order)
        rerank_orders.append([index for _, index in sorted(zip(scores, order), key=lambda pair: (-pair[0], pair[1]))])
    provider.close()
    def metrics(orders: list[list[int]]) -> dict:
        files, sections, rows = [], [], []
        for order, item in zip(orders, gold, strict=True):
            found = [0, 0, 0]
            for position, index in enumerate(order, start=1):
                file_match, section_match, row_match = matches(chunks[index], item)
                for flag, slot in ((file_match, 0), (section_match, 1), (row_match, 2)):
                    if flag and found[slot] == 0:
                        found[slot] = position
            files.append(found[0]); sections.append(found[1]); rows.append(found[2])
        def one(values: list[int]) -> dict:
            total = len(values)
            return {"recall@5": round(sum(1 <= value <= 5 for value in values) / total, 4), "recall@10": round(sum(1 <= value <= 10 for value in values) / total, 4), "recall@20": round(sum(1 <= value <= 20 for value in values) / total, 4), "mrr": round(sum(1 / value for value in values if value) / total, 4), "ndcg@10": round(sum(1 / math.log2(value + 1) for value in values if value and value <= 10) / total, 4), "miss": sum(value == 0 for value in values)}
        return {"evaluated": len(gold), "file": one(files), "section": one(sections), "row": one(rows)}
    pre_metrics = metrics(pre_orders); post_metrics = metrics(rerank_orders)
    matrix_path = V23 / "retrieval_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["reranker"] = {"status": "RUN", "model": str(RERANKER), "pre_rerank": pre_metrics, "post_rerank": post_metrics, "enabled": post_metrics["file"]["mrr"] > pre_metrics["file"]["mrr"]}
    matrix["best_post_reranker"] = "RRF_k60+Reranker" if matrix["reranker"]["enabled"] else matrix.get("best_pre_reranker")
    matrix["captured_at_reranker"] = datetime.now(timezone.utc).astimezone().isoformat()
    matrix_path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pre_rerank": pre_metrics["file"], "post_rerank": post_metrics["file"], "reranker_enabled": matrix["reranker"]["enabled"], "best": matrix["best_post_reranker"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
