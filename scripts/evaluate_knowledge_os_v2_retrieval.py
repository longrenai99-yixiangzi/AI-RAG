"""T06-T10 first staging run: lexical V2 and a frozen-section comparison."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
SECTION_INDEX = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "section_index" / "records.jsonl"
GOLD = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"
OUT = ROOT / "evaluation" / "knowledge_os_v2" / "retrieval"


def digest(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            h.update(block)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def questions() -> list[dict]:
    data = yaml.safe_load(GOLD.read_text(encoding="utf-8")) or {}
    return [{"id": row.get("id"), "question": str(row["question"]), "expected_files": [str(value).strip() for value in row.get("expected_files") or [] if str(value).strip()]} for row in data.get("questions") or [] if row.get("question") and row.get("expected_files")]


def metrics(rows: list[dict], texts: list[str], gold: list[dict], *, topk: int = 20) -> tuple[dict, list[int]]:
    model = BM25Okapi([tokenize(text) or ["_empty_"] for text in texts])
    ranks: list[int] = []
    for item in gold:
        expected = {name.casefold() for name in item["expected_files"]}
        scores = model.get_scores(tokenize(item["question"]) or ["_empty_"])
        order = np.argsort(-scores)[:topk]
        rank = 0
        for position, index in enumerate(order, start=1):
            if str(rows[int(index)].get("file_name") or "").casefold() in expected:
                rank = position
                break
        ranks.append(rank)
    total = len(ranks)
    ndcg = sum((1 / math.log2(rank + 1)) for rank in ranks if rank and rank <= 10) / total if total else 0
    result = {"evaluated": total, "recall@5": round(sum(1 <= rank <= 5 for rank in ranks) / total, 4) if total else None, "recall@10": round(sum(1 <= rank <= 10 for rank in ranks) / total, 4) if total else None, "recall@20": round(sum(1 <= rank <= 20 for rank in ranks) / total, 4) if total else None, "mrr": round(sum(1 / rank for rank in ranks if rank) / total, 4) if total else None, "ndcg@10": round(ndcg, 4), "miss": sum(rank == 0 for rank in ranks)}
    return result, ranks


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = load_jsonl(STAGING / "semantic_chunks.jsonl")
    docs = {str(row.get("document_id")): row for row in load_jsonl(STAGING / "documents.jsonl")}
    for chunk in chunks:
        chunk["file_name"] = str(docs.get(str(chunk.get("document_id")), {}).get("file_name") or "")
    gold = questions()

    section_rows = load_jsonl(SECTION_INDEX)
    section_texts = [str(row.get("section_search_text") or row.get("text") or "") for row in section_rows]
    section_metrics, section_ranks = metrics(section_rows, section_texts, gold)

    weighted_texts = []
    for row in chunks:
        # Explicit field repetition is an experiment, not a final hard-coded ranking policy.
        weighted_texts.append(" ".join([str(row.get("section_path") or "")] * 5 + [str(row.get("file_name") or "")] * 3 + [str(row.get("knowledge_type", {}).get("value") or "")] * 2 + [str(row.get("raw_text") or "")]))
    v2_metrics, v2_ranks = metrics(chunks, weighted_texts, gold)
    index_payload = {"schema_version": "knowledge_v2_staging.bm25", "chunk_version": "structured_knowledge.v2", "field_weights": {"section_path": 5, "file_name": 3, "knowledge_type": 2, "raw_text": 1}, "chunk_ids": [row.get("chunk_id") for row in chunks], "texts": weighted_texts}
    index_path = STAGING / "bm25_v2.json"
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    matrix = {"schema_version": "knowledge_os_v2.retrieval_ab", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "gold": {"path": str(GOLD), "count": len(gold), "status": "PROVISIONAL_EXPECTED_FILES"}, "versions": {"A_frozen_section_bm25": {"chunk": "frozen_section", "retrieval": "BM25_existing", "fusion": "none", "reranker": "off", "metrics": section_metrics, "ranks": section_ranks}, "C_semantic_v2_bm25_v2": {"chunk": "semantic_v2", "retrieval": "BM25_V2_weighted_fields", "fusion": "none", "reranker": "off", "metrics": v2_metrics, "ranks": v2_ranks}, "D_semantic_v2_dense": {"status": "NOT_RUN"}, "E_semantic_v2_rrf": {"status": "NOT_RUN"}, "F_reranker": {"status": "NOT_RUN"}}, "artifacts": {"git_head": head, "v1_section_index_sha256": digest(SECTION_INDEX), "v2_bm25_index_sha256": digest(index_path), "v2_chunk_count": len(chunks), "legacy_index_touched": False, "runtime_enabled": False}}
    (OUT / "ab_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    report = f"""# Retrieval V2 A/B Report\n\n- Gold: {len(gold)} provisional expected-file questions; no expected section/answer claims were invented.\n- A Frozen Section BM25: Recall@5 {section_metrics['recall@5']:.2%}, Recall@10 {section_metrics['recall@10']:.2%}, Recall@20 {section_metrics['recall@20']:.2%}, MRR {section_metrics['mrr']:.4f}, nDCG@10 {section_metrics['ndcg@10']:.4f}.\n- C Semantic Chunk V2 BM25: Recall@5 {v2_metrics['recall@5']:.2%}, Recall@10 {v2_metrics['recall@10']:.2%}, Recall@20 {v2_metrics['recall@20']:.2%}, MRR {v2_metrics['mrr']:.4f}, nDCG@10 {v2_metrics['ndcg@10']:.4f}.\n- Field experiment: section path ×5, file name ×3, knowledge type ×2, raw text ×1.\n\nDense, RRF, and reranker versions are deliberately `NOT_RUN`; this report does not authorize runtime switching. Gold remains provisional until owner confirmation.\n"""
    (ROOT / "docs" / "RETRIEVAL_V2_AB_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"gold": len(gold), "section": section_metrics, "semantic_v2": v2_metrics, "index": str(index_path), "report": str(ROOT / 'docs' / 'RETRIEVAL_V2_AB_REPORT.md')}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
