from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import torch

from app.config import Settings
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hierarchical_v1 import HierarchicalIndex, _bm25_pairs, _dense_pairs, _soft_boost
from app.retrieval.query_planner_v1 import plan_query
from app.retrieval.rrf import reciprocal_rank_fusion


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "evaluation" / "hierarchical_retrieval_v1_stabilization"
SHADOW_DIR = PROJECT_ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"
GOLD_DIR = PROJECT_ROOT / "evaluation" / "business_gold_v2"
FOCUS_IDS = {"BA-001", "BA-002", "BA-004", "BA-008", "BA-010"}


def main() -> int:
    gold = _read_json(GOLD_DIR / "owner_approved_gold_manifest.json")["records"]
    prior_matrix = {item["question_id"]: item for item in _read_json(EVAL_DIR / "ba_retrieval_matrix.json")["records"]}
    baseline = {item["question_id"]: item for item in _read_json(GOLD_DIR / "gold_evaluation_matrix.json")["records"]}
    index = HierarchicalIndex.load(SHADOW_DIR)
    settings = Settings.load()
    snapshot = _snapshot()
    provider = BGEM3DenseProvider(
        settings.embedding_model,
        collection_name="metric_integrity_query_replay_only",
        use_fp16=bool(torch.cuda.is_available()),
        batch_size=4,
    )
    plans = [plan_query(item["question"]) for item in gold]
    try:
        query_vectors = provider.embed_documents([plan.normalized_question for plan in plans])
    finally:
        provider.close()

    rows = []
    for item, plan, query_vector in zip(gold, plans, query_vectors, strict=True):
        pure = _pure_document_candidates(index, plan, query_vector)
        assisted = index._rank_documents(plan, query_vector, limit=20)
        source = str(item["gold_primary_source"])
        pure_rank = _source_rank(pure, source)
        assisted_rank = _source_rank(assisted, source)
        old_rank = prior_matrix[item["question_id"]]["document_rank"]
        if baseline[item["question_id"]].get("runtime_source_available"):
            assert assisted_rank == old_rank, f"section-assisted replay changed {item['question_id']}: {assisted_rank} != {old_rank}"
        rows.append({
            "question_id": item["question_id"],
            "question": item["question"],
            "query_id": plan.query_id,
            "pure_document_rank": pure_rank,
            "section_assisted_document_rank": assisted_rank,
            "prior_section_assisted_document_rank": old_rank,
            "hierarchical_section_rank": prior_matrix[item["question_id"]]["hierarchical_section_rank"],
            "evidence_rank": prior_matrix[item["question_id"]]["hierarchical_evidence_rank"],
            "pure_top20": _compact(pure),
            "section_assisted_top20": _compact(assisted),
        })

    eligible = [row for row in rows if baseline[row["question_id"]].get("runtime_source_available")]
    pure_metrics = _recall(eligible, "pure_document_rank")
    assisted_metrics = _recall(eligible, "section_assisted_document_rank")
    dense = _read_json(EVAL_DIR / "section_dense_coverage_corrected.json")
    prior_metrics = _read_json(EVAL_DIR / "retrieval_metrics.json")
    conclusion = _conclusion(pure_metrics, assisted_metrics)
    purity = {
        "schema_version": "hierarchical_retrieval.v1.document_stage_purity.replayed",
        "query_embedding_model": "BGE-M3",
        "model_path": str(settings.embedding_model),
        "query_count": len(rows),
        "index_snapshot": snapshot,
        "document_stage_behavior": {
            "pure_document": "Document BM25 + Document Dense + fixed Document Profile Soft Boost. No query-time Section BM25/Dense ranking or section RRF source.",
            "section_assisted": "Current 020C.1 Document stage: Document BM25/Dense plus full-corpus Section BM25/Dense collapsed to parent Documents before RRF.",
            "fixed_metadata_note": "Both paths retain the identical persisted Document metadata and Soft Boost configuration. document_type_facets are treated as fixed Document Index metadata; no query-time Section rank enters the Pure path.",
        },
        "pure_document_retrieval": pure_metrics,
        "section_assisted_document_retrieval": assisted_metrics,
        "focus_questions": [row for row in rows if row["question_id"] in FOCUS_IDS],
    }
    acceptance = {
        "schema_version": "hierarchical_retrieval.v1.acceptance_gate_corrected",
        "registration_page_dominance": {
            "observed": prior_metrics["registration"]["dominance_rate"],
            "corrected_predicate": "registration.dominance_rate.rate == 0",
            "result": "PASS" if prior_metrics["registration"]["dominance_rate"]["rate"] == 0 else "FAIL",
        },
        "section_dense": {
            "direct_section_dense_coverage": dense["direct_section_dense_coverage"],
            "effective_section_vector_availability": dense["effective_section_vector_availability"],
            "direct_coverage_is_not_replaced_by_fallback": True,
        },
        "global_rescue": {
            "gold_dependency": prior_metrics["global_rescue"]["gold_dependency"],
            "excluded_from_pure_document_recall": True,
        },
        "document_stage_conclusion": conclusion,
        "execution_boundary": {
            "provider_http_requests": 0,
            "network_access": False,
            "formal_qdrant_write": False,
            "retriever_code_changed": False,
            "root002_refreshed": False,
            "root003_scanned": False,
        },
    }
    audit = {
        "schema_version": "hierarchical_retrieval.v1.metric_integrity_audit.replayed",
        "retrieval_effect_recomputed": False,
        "query_embedding_replayed": True,
        "query_embedding_model": "BGE-M3",
        "model_path": str(settings.embedding_model),
        "query_count": len(rows),
        "index_snapshot": snapshot,
        "provider_http_requests": 0,
        "network_access": False,
        "formal_qdrant_write": False,
        "retriever_code_changed": False,
        "document_stage_conclusion": conclusion,
    }
    _write_json(EVAL_DIR / "metric_integrity_audit.json", audit)
    _write_json(EVAL_DIR / "document_stage_purity.json", purity)
    _write_json(EVAL_DIR / "acceptance_gate_corrected.json", acceptance)
    _write_jsonl(EVAL_DIR / "document_stage_purity_replay.jsonl", rows)
    (PROJECT_ROOT / "docs" / "HIERARCHICAL_RETRIEVAL_METRIC_INTEGRITY_AUDIT.md").write_text(
        _report(purity, dense, acceptance), encoding="utf-8"
    )
    assert len(rows) == 10
    assert acceptance["global_rescue"]["gold_dependency"]["rate"] == 0.0
    assert acceptance["registration_page_dominance"]["result"] == "PASS"
    print(json.dumps({"conclusion": conclusion, "query_count": len(rows), "provider_http_requests": 0}, ensure_ascii=False))
    return 0


def _pure_document_candidates(index: HierarchicalIndex, plan: Any, query_vector: list[float]) -> list[dict[str, Any]]:
    document_ids = {str(item["document_id"]) for item in index.documents}
    bm25_pairs = _bm25_pairs(index.documents, index.document_bm25, "document_id", "document_search_text", plan.normalized_question, document_ids)
    dense_pairs = _dense_pairs(index.documents, index.document_vectors, query_vector, document_ids, "document_id")
    bm25_scores = dict(bm25_pairs)
    dense_scores = dict(dense_pairs)
    rrf = reciprocal_rank_fusion({"document_bm25": [item_id for item_id, _ in bm25_pairs], "document_dense": [item_id for item_id, _ in dense_pairs]})
    rows = []
    for item in rrf:
        record = index.document_by_id[item.chunk_id]
        boost, trace = _soft_boost(record, plan)
        rows.append({
            "document_id": item.chunk_id,
            "source_path": record.get("source_path"),
            "file_name": record.get("file_name"),
            "bm25_rank": item.ranks.get("document_bm25"),
            "bm25_score": bm25_scores.get(item.chunk_id),
            "dense_rank": item.ranks.get("document_dense"),
            "dense_score": dense_scores.get(item.chunk_id),
            "rrf_score": item.score,
            "planner_boost": boost,
            "planner_match": trace,
        })
    rows.sort(key=lambda row: (-(row["rrf_score"] + row["planner_boost"]), row["document_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def _source_rank(rows: list[dict[str, Any]], source_path: str) -> int | None:
    normalized = str(source_path).replace("/", "\\").rstrip("\\").casefold()
    return min((row["rank"] for row in rows if str(row.get("source_path") or "").replace("/", "\\").rstrip("\\").casefold() == normalized), default=None)


def _recall(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    return {
        "definition": field,
        "eligible_questions": len(rows),
        "recall_at_1": _rate(sum(row[field] is not None and row[field] <= 1 for row in rows), len(rows)),
        "recall_at_3": _rate(sum(row[field] is not None and row[field] <= 3 for row in rows), len(rows)),
        "recall_at_5": _rate(sum(row[field] is not None and row[field] <= 5 for row in rows), len(rows)),
        "recall_at_10": _rate(sum(row[field] is not None and row[field] <= 10 for row in rows), len(rows)),
    }


def _conclusion(pure: dict[str, Any], assisted: dict[str, Any]) -> str:
    if pure["recall_at_5"]["rate"] >= 0.8:
        return "HIERARCHICAL_DOCUMENT_STAGE_VALID"
    if assisted["recall_at_5"]["rate"] >= 0.8:
        return "SECTION_ASSISTED_DOCUMENT_STAGE_VALID"
    return "HIERARCHICAL_DOCUMENT_STAGE_STILL_WEAK"


def _snapshot() -> dict[str, Any]:
    files = [
        SHADOW_DIR / "document_index" / "records.jsonl",
        SHADOW_DIR / "document_index" / "vectors.npy",
        SHADOW_DIR / "document_index" / "bm25.json",
        SHADOW_DIR / "section_index" / "records.jsonl",
        SHADOW_DIR / "section_index" / "vectors.npy",
    ]
    parts = {str(path.relative_to(PROJECT_ROOT)): _sha256(path) for path in files}
    fingerprint = hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()
    return {"fingerprint": fingerprint, "files": parts}


def _compact(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: row.get(key) for key in ("rank", "document_id", "file_name", "source_path", "bm25_rank", "dense_rank", "rrf_score", "planner_boost")} for row in rows[:20]]


def _report(purity: dict[str, Any], dense: dict[str, Any], acceptance: dict[str, Any]) -> str:
    pure = purity["pure_document_retrieval"]
    assisted = purity["section_assisted_document_retrieval"]
    focus = "\n".join(f"| {row['question_id']} | {row['pure_document_rank']} | {row['section_assisted_document_rank']} | {row['hierarchical_section_rank']} | {row['evidence_rank']} |" for row in purity["focus_questions"])
    return "\n".join([
        "# HIERARCHICAL RETRIEVAL METRIC INTEGRITY AUDIT",
        "",
        "> TASK-020C.1.1。本次仅使用当前本地 BGE-M3 为 BA-001～BA-010 的 10 个冻结问题生成 Query Embedding；没有网络访问、LLM/Live Provider、Qdrant 写入、Index 更新、Retriever 改动、Root-002 refresh 或 Root-003 scan。",
        "",
        "## 1. Registration 指标",
        "",
        f"- 观测值：{acceptance['registration_page_dominance']['observed']}。正确判断 `rate == 0`，结果：**{acceptance['registration_page_dominance']['result']}**。",
        "",
        "## 2. Section Dense 覆盖率",
        "",
        f"- Direct Section Dense Count：{dense['direct_section_dense_count']}；Eligible Direct Count：{dense['direct_section_dense_eligible_count']}。",
        f"- Parent Document Vector Fallback Count：{dense['parent_document_vector_fallback_count']}。",
        f"- Excluded / Eligible Sections：{dense['excluded_section_count']} / {dense['eligible_section_count']}。",
        f"- Direct Section Dense Coverage：{dense['direct_section_dense_coverage']['rate']}。",
        f"- Effective Section Vector Availability：{dense['effective_section_vector_availability']['rate']}。",
        f"- 回退原因：{dense['fallback_root_cause']['reason']}",
        "",
        "## 3. Document Stage 纯度",
        "",
        "- A. 是：Section-Assisted 路径在 Document TopK 前计算全库 Section Query 相关性。",
        "- B. 是：全库 Section Rank 被折叠为父 Document 信号并参与 Document RRF。",
        "- C. 是：因此 Section-Assisted 路径不是纯 Document Retrieval。",
        "- D. Pure 路径不使用任何 Query-time Section BM25/Dense 排名，也不使用 Global Rescue；两路径仅共享冻结 Document Index Metadata/Soft Boost。",
        "",
        "## 4. 同口径指标",
        "",
        "| 路径 | Recall@1 | Recall@3 | Recall@5 | Recall@10 |",
        "|---|---:|---:|---:|---:|",
        f"| Pure Document Retrieval | {pure['recall_at_1']['rate']} | {pure['recall_at_3']['rate']} | {pure['recall_at_5']['rate']} | {pure['recall_at_10']['rate']} |",
        f"| Section-Assisted Document Retrieval | {assisted['recall_at_1']['rate']} | {assisted['recall_at_3']['rate']} | {assisted['recall_at_5']['rate']} | {assisted['recall_at_10']['rate']} |",
        "",
        "## 5. BA 专项",
        "",
        "| BA | Pure Document Rank | Section-Assisted Document Rank | Hierarchical Section Rank | Evidence Rank |",
        "|---|---:|---:|---:|---:|",
        focus,
        "",
        "## 6. 执行记录",
        "",
        f"- query_embedding_model：{purity['query_embedding_model']}；model_path：`{purity['model_path']}`；query_count：{purity['query_count']}。",
        f"- index_snapshot fingerprint：`{purity['index_snapshot']['fingerprint']}`。",
        "- provider_http_requests=0；network_access=false；formal_qdrant_write=false；retriever_code_changed=false。",
        f"- Global Rescue Gold Dependency：{acceptance['global_rescue']['gold_dependency']['rate']}，未计入 Pure Document Recall。",
        "",
        "## 7. 最终结论",
        "",
        f"**{acceptance['document_stage_conclusion']}**",
        "",
        "TASK-020C.1.1 = COMPLETE",
        "",
    ])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / max(1, denominator), 4)}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
