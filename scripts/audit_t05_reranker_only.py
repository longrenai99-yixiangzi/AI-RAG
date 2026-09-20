"""Run the real reranker in its own process after BGE-M3 memory is released."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t05"
SECTION_DIR = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "section_index"
RERANKER_PATH = ROOT / "models" / "bge-reranker-v2-m3"

from scripts.audit_t05_retrieval_model_audit import mrr, ndcg_at, recall_at


def main() -> int:
    records = [json.loads(line) for line in (SECTION_DIR / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    inputs = json.loads((OUT / "rerank_inputs.json").read_text(encoding="utf-8"))
    audit_path = OUT / "retrieval_model_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    from app.retrieval.reranker_provider import BGERerankerProvider

    reranker = BGERerankerProvider(str(RERANKER_PATH), use_fp16=False)
    reranker.load()
    pairs, layouts = [], []
    for item in inputs:
        indices = [int(value) for value in item["section_indices"]]
        start = len(pairs)
        pairs.extend([[item["question"], str(records[index].get("section_content_text") or records[index].get("section_search_text") or "")[:512]] for index in indices])
        layouts.append((item, indices, start, len(pairs)))
    assert reranker.model is not None
    started = time.perf_counter()
    raw_scores = reranker.model.compute_score(pairs, batch_size=8, max_length=128, normalize=False)  # type: ignore[attr-defined]
    all_scores = [float(raw_scores)] if isinstance(raw_scores, (int, float)) else [float(value) for value in raw_scores]
    ranks, hits, details = [], [], []
    for number, (item, indices, start, end) in enumerate(layouts, start=1):
        scores = all_scores[start:end]
        order = [index for _, index in sorted(zip(scores or [], indices), key=lambda pair: -pair[0])]
        expected = set(item["expected_files"])
        rank = next((position for position, index in enumerate(order, start=1) if str(records[index].get("file_name") or "") in expected), 0)
        flags = [str(records[index].get("file_name") or "") in expected for index in order[:20]]
        ranks.append(rank)
        hits.append(flags)
        details.append({"question_id": item["question_id"], "question": item["question"], "expected_files": item["expected_files"], "first_hit_rank": rank, "top_files": [str(records[index].get("file_name") or "") for index in order[:5]]})
        if number % 10 == 0:
            print(f"[T05-D] {number}/{len(inputs)}", flush=True)

    metric = {
        "status": "RUN",
        "execution": "SEPARATE_PROCESS_REAL_RERANKER",
        "rerank_pool": 30,
        "max_length": 128,
        "batch_size": 8,
        "evaluated_questions": len(ranks),
        "recall@5": round(recall_at(ranks, 5), 4),
        "recall@10": round(recall_at(ranks, 10), 4),
        "recall@20": round(recall_at(ranks, 20), 4),
        "mrr": round(mrr(ranks), 4),
        "ndcg@10": round(ndcg_at(hits, 10), 4),
        "rerank@5_hit_rate": round(recall_at(ranks, 5), 4),
        "miss_count": sum(rank == 0 for rank in ranks),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }
    audit["captured_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    audit["metrics"]["D_RERANK"] = metric
    for row, rank in zip(audit.get("per_question", []), ranks, strict=False):
        row["reranker_rank"] = rank
    by_id = {row["question_id"]: row for row in details}
    for row in audit.get("recall_miss_cases", []):
        if row["question_id"] in by_id:
            row["reranker_rank"] = by_id[row["question_id"]]["first_hit_rank"]
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "reranker_only_results.json").write_text(json.dumps({"captured_at": audit["captured_at"], "model": str(RERANKER_PATH), "metrics": metric, "details": details}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metric, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
