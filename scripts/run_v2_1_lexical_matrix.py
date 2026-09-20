"""T06/T09 lexical matrix; Dense-dependent variants remain explicit NOT_RUN."""

from __future__ import annotations

import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
NODE_UPDATES = ROOT / "evaluation" / "knowledge_os_v2_1" / "node_binding" / "chunk_node_updates.jsonl"
OUT = ROOT / "evaluation" / "knowledge_os_v2_1" / "retrieval_ab"
GOLD = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"


ALIASES = {"接口": "设计接口 提资", "提资": "设计接口 接口资料", "设计任务书": "任务书 设计要求", "限额设计": "控概 设计优化", "方案比选": "方案优化 技术经济比较", "设计风险": "风险清单 风险管控", "EPC": "工程总承包", "设计评估": "成果评审"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def gold() -> list[dict]:
    data = yaml.safe_load(GOLD.read_text(encoding="utf-8")) or {}
    return [{"id": row.get("id"), "question": str(row["question"]), "expected_files": [str(value) for value in row.get("expected_files") or []]} for row in data.get("questions") or [] if row.get("question") and row.get("expected_files")]


def metrics(rows: list[dict], texts: list[str], questions: list[dict], query_transform=lambda q: q) -> tuple[dict, list[int], list[float]]:
    model = BM25Okapi([tokenize(text) or ["_empty_"] for text in texts])
    ranks: list[int] = []
    elapsed: list[float] = []
    for question in questions:
        started = time.perf_counter()
        scores = model.get_scores(tokenize(query_transform(question["question"])) or ["_empty_"])
        order = np.argsort(-scores)[:20]
        elapsed.append((time.perf_counter() - started) * 1000)
        expected = {value.casefold() for value in question["expected_files"]}
        rank = next((position for position, index in enumerate(order, start=1) if str(rows[int(index)].get("file_name") or "").casefold() in expected), 0)
        ranks.append(rank)
    total = len(ranks)
    ndcg = sum((1 / math.log2(rank + 1)) for rank in ranks if rank and rank <= 10) / total if total else 0
    return {"status": "RUN", "evaluated": total, "recall@5": round(sum(1 <= rank <= 5 for rank in ranks) / total, 4) if total else None, "recall@10": round(sum(1 <= rank <= 10 for rank in ranks) / total, 4) if total else None, "recall@20": round(sum(1 <= rank <= 20 for rank in ranks) / total, 4) if total else None, "mrr": round(sum(1 / rank for rank in ranks if rank) / total, 4) if total else None, "ndcg@10": round(ndcg, 4), "latency_p50_ms": round(statistics.median(elapsed), 3) if elapsed else None, "latency_p95_ms": round(float(np.percentile(elapsed, 95)), 3) if elapsed else None, "miss": sum(rank == 0 for rank in ranks)}, ranks, elapsed


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    docs = {str(row.get("document_id")): row for row in read_jsonl(STAGING / "documents.jsonl")}
    updates = {str(row.get("chunk_id")): row for row in read_jsonl(NODE_UPDATES)}
    for row in chunks:
        doc = docs.get(str(row.get("document_id")), {})
        row["file_name"] = str(doc.get("file_name") or "")
        inferred = (doc.get("metadata") or {}).get("inferred") or {}
        row["project"] = inferred.get("project", {}).get("value")
        row["organization"] = inferred.get("organization", {}).get("value")
        row["node_text"] = " ".join(updates.get(str(row.get("chunk_id")), {}).get("knowledge_node_ids") or [])
        row["knowledge_type_value"] = str((row.get("knowledge_type") or {}).get("value") or "")
    questions = gold()
    l1 = [str(row.get("retrieval_text") or "") for row in chunks]
    l2 = [" ".join([str(row.get("section_path") or "")] * 5 + [str(row.get("file_name") or "")] * 3 + [row["knowledge_type_value"]] * 2 + [str(row.get("raw_text") or "")]) for row in chunks]
    l3 = [" ".join([l2[index], str(row.get("project") or ""), str(row.get("organization") or ""), row["node_text"]]) for index, row in enumerate(chunks)]
    def expand(question: str) -> str:
        additions = [alias for term, alias in ALIASES.items() if term.casefold() in question.casefold()]
        return question + " " + " ".join(additions)
    l4 = l3
    matrix = {}
    ranks = {}
    for key, texts, transform in (("L1_current_bm25_v2", l1, lambda q: q), ("L2_section_title_path", l2, lambda q: q), ("L3_metadata_node_soft_boost", l3, lambda q: q), ("L4_business_dictionary_alias", l4, expand)):
        result, result_ranks, _ = metrics(chunks, texts, questions, transform)
        matrix[key] = {"chunk": "semantic_v2", "retrieval": key, "fusion": "none", "reranker": "off", "metrics": result}
        ranks[key] = result_ranks
    diffs = []
    base = ranks["L1_current_bm25_v2"]
    for index, question in enumerate(questions):
        row = {"question_id": question["id"], "question": question["question"], "L1_rank": base[index], "versions": {key: ranks[key][index] for key in ranks}}
        row["wins"] = [key for key in ranks if ranks[key][index] and (not base[index] or ranks[key][index] < base[index])]
        row["losses"] = [key for key in ranks if base[index] and (not ranks[key][index] or ranks[key][index] > base[index])]
        diffs.append(row)
    payload = {"schema_version": "knowledge_os_v2_1.lexical_matrix", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "gold": {"path": str(GOLD), "count": len(questions), "status": "PROVISIONAL_EXPECTED_FILES"}, "versions": matrix, "per_question_diff": diffs, "dense": {"status": "NOT_RUN_RESOURCE_LIMIT"}, "weighted_hybrid": {"status": "NOT_RUN_DENSE_BLOCKED"}, "rrf": {"status": "NOT_RUN_DENSE_BLOCKED"}, "reranker": {"status": "NOT_RUN_DENSE_BLOCKED"}}
    (OUT / "lexical_matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value["metrics"] for key, value in matrix.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
