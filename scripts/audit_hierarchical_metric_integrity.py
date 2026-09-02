from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "evaluation" / "hierarchical_retrieval_v1_stabilization"
SHADOW_DIR = PROJECT_ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"
GOLD_DIR = PROJECT_ROOT / "evaluation" / "business_gold_v2"
FOCUS_IDS = {"BA-001", "BA-002", "BA-004", "BA-008", "BA-010"}


def main() -> int:
    metrics = _read_json(EVAL_DIR / "retrieval_metrics.json")
    matrix = _read_json(EVAL_DIR / "ba_retrieval_matrix.json")["records"]
    traces = _read_jsonl(EVAL_DIR / "retrieval_traces.jsonl")
    gold = {item["question_id"]: item for item in _read_json(GOLD_DIR / "owner_approved_gold_manifest.json")["records"]}
    dense = _dense_coverage()
    purity = _document_stage_purity(metrics, matrix, traces, gold)
    acceptance = _acceptance(metrics, dense, purity)
    audit = {
        "schema_version": "hierarchical_retrieval.v1.metric_integrity_audit",
        "retrieval_effect_recomputed": False,
        "provider_called": False,
        "root002_refreshed": False,
        "root003_scanned": False,
        "registration_gate": acceptance["registration_page_dominance"],
        "document_stage_conclusion": acceptance["document_stage_conclusion"],
        "notes": [
            "This audit only reads persisted TASK-020C.1 artifacts.",
            "Pure Document Dense ranks cannot be reconstructed because query vectors and complete document-dense rankings were not persisted; this audit does not call a provider to regenerate them.",
        ],
    }
    _write_json(EVAL_DIR / "metric_integrity_audit.json", audit)
    _write_json(EVAL_DIR / "document_stage_purity.json", purity)
    _write_json(EVAL_DIR / "section_dense_coverage_corrected.json", dense)
    _write_json(EVAL_DIR / "acceptance_gate_corrected.json", acceptance)
    (PROJECT_ROOT / "docs" / "HIERARCHICAL_RETRIEVAL_METRIC_INTEGRITY_AUDIT.md").write_text(
        _report(audit, dense, purity, acceptance), encoding="utf-8"
    )
    assert acceptance["registration_page_dominance"]["result"] == "PASS"
    assert metrics["global_rescue"]["gold_dependency"]["rate"] == 0.0
    print(json.dumps({"conclusion": acceptance["document_stage_conclusion"], "provider_called": False}, ensure_ascii=False))
    return 0


def _dense_coverage() -> dict[str, Any]:
    rows = _read_jsonl(SHADOW_DIR / "section_index" / "records.jsonl")
    reason = Counter()
    direct = direct_eligible = fallback = fallback_eligible = missing = eligible = excluded = 0
    for row in rows:
        source = str(row.get("dense_vector_source") or "MISSING")
        is_eligible = bool(row.get("dense_eligible"))
        if source == "SECTION_DIRECT":
            direct += 1
            direct_eligible += int(is_eligible)
        elif source == "PARENT_DOCUMENT_FALLBACK":
            fallback += 1
            fallback_eligible += int(is_eligible)
        else:
            missing += 1
        if is_eligible:
            eligible += 1
        else:
            excluded += 1
            reason[str(row.get("dense_exclusion_reason") or "UNKNOWN")] += 1
    return {
        "schema_version": "hierarchical_retrieval.v1.section_dense_coverage_corrected",
        "direct_section_dense_count": direct,
        "direct_section_dense_eligible_count": direct_eligible,
        "parent_document_vector_fallback_count": fallback,
        "parent_document_vector_fallback_eligible_count": fallback_eligible,
        "excluded_section_count": excluded,
        "eligible_section_count": eligible,
        "missing_section_vector_count": missing,
        "direct_section_dense_coverage": _rate(direct_eligible, eligible),
        "effective_section_vector_availability": _rate(direct_eligible + fallback_eligible, eligible),
        "excluded_reason": dict(sorted(reason.items())),
        "fallback_root_cause": {
            "count": fallback,
            "reason": "Root-001 V2 Section boundaries cannot be matched to a legacy Qdrant chunk by exact heading path, page, or sheet in app/retrieval/hierarchical_v1.py::_match_root1_section. The Shadow index therefore uses the existing parent-document vector as an explicitly labeled fallback. No section embedding was added in this task.",
        },
        "interpretation": "Parent-document fallback is excluded from Direct Section Dense Coverage and included only in Effective Section Vector Availability.",
    }


def _document_stage_purity(
    metrics: dict[str, Any],
    matrix: list[dict[str, Any]],
    traces: list[dict[str, Any]],
    gold: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_question = {trace["question_id"]: trace for trace in traces}
    by_matrix = {row["question_id"]: row for row in matrix}
    focus = []
    for question_id in sorted(FOCUS_IDS):
        trace = by_question[question_id]
        source = str(gold[question_id]["gold_primary_source"]).casefold()
        candidate = next((item for item in trace["document_candidates"] if str(item.get("source_path") or "").casefold() == source), None)
        representation = (candidate or {}).get("representation_trace") or {}
        row = by_matrix[question_id]
        focus.append({
            "question_id": question_id,
            "pure_document_rank": None,
            "pure_document_rank_status": "NOT_RECONSTRUCTABLE_FROM_PERSISTED_TRACE",
            "document_bm25_rank": representation.get("document_bm25_rank"),
            "document_dense_rank": representation.get("document_dense_rank"),
            "section_assisted_document_rank": row["document_rank"],
            "best_section_bm25_rank": representation.get("best_section_bm25_rank"),
            "best_section_dense_rank": representation.get("best_section_dense_rank"),
            "hierarchical_section_rank": row["hierarchical_section_rank"],
            "evidence_rank": row["hierarchical_evidence_rank"],
        })
    return {
        "schema_version": "hierarchical_retrieval.v1.document_stage_purity",
        "document_stage_behavior": {
            "full_corpus_section_query_relevance_before_document_topk": True,
            "section_rank_collapsed_to_parent_document_before_document_topk": True,
            "document_topk_uses_section_signal": True,
            "implementation": "HierarchicalIndex._rank_documents computes document BM25/Dense plus all-section BM25/Dense, collapses each section list to its parent document with _collapse_section_pairs, and passes all four rank lists to reciprocal_rank_fusion before Document TopK is selected.",
        },
        "pure_document_retrieval": {
            "definition": "Document BM25 + Document Dense + Document Profile Soft Boost only",
            "recall_at_1": None,
            "recall_at_3": None,
            "recall_at_5": None,
            "recall_at_10": None,
            "status": "NOT_RECONSTRUCTABLE_FROM_PERSISTED_TRACE",
            "reason": "TASK-020C.1 persisted only the final Section-assisted Top20 document candidates and their per-candidate native ranks. It did not persist query vectors or complete document-only dense rankings. Recomputing exact pure recall would require embedding the queries again, which this task forbids.",
        },
        "section_assisted_document_retrieval": {
            "definition": "Document BM25/Dense + best-section BM25/Dense + Document Profile Soft Boost",
            "recall_at_1": metrics["document"]["recall_at_1"],
            "recall_at_3": metrics["document"]["recall_at_3"],
            "recall_at_5": metrics["document"]["recall_at_5"],
            "recall_at_10": metrics["document"]["recall_at_10"],
            "status": "VERIFIED_FROM_PERSISTED_TRACE",
        },
        "focus_questions": focus,
    }


def _acceptance(metrics: dict[str, Any], dense: dict[str, Any], purity: dict[str, Any]) -> dict[str, Any]:
    registration = metrics["registration"]["dominance_rate"]
    pure = purity["pure_document_retrieval"]
    assisted = purity["section_assisted_document_retrieval"]
    if pure["recall_at_5"] is not None and pure["recall_at_5"]["rate"] >= 0.8:
        conclusion = "HIERARCHICAL_DOCUMENT_STAGE_VALID"
    elif assisted["recall_at_5"]["rate"] >= 0.8:
        conclusion = "SECTION_ASSISTED_DOCUMENT_STAGE_VALID"
    else:
        conclusion = "HIERARCHICAL_DOCUMENT_STAGE_STILL_WEAK"
    return {
        "schema_version": "hierarchical_retrieval.v1.acceptance_gate_corrected",
        "registration_page_dominance": {
            "observed": registration,
            "comparison_bug": "The original report compared the structured rate object to integer 0 instead of comparing observed.rate to 0.",
            "corrected_predicate": "registration.dominance_rate.rate == 0",
            "result": "PASS" if registration["rate"] == 0 else "FAIL",
        },
        "section_dense": {
            "direct_section_dense_coverage": dense["direct_section_dense_coverage"],
            "effective_section_vector_availability": dense["effective_section_vector_availability"],
            "direct_coverage_is_not_replaced_by_fallback": True,
        },
        "global_rescue": {
            "gold_dependency": metrics["global_rescue"]["gold_dependency"],
            "excluded_from_pure_document_recall": True,
        },
        "document_stage_conclusion": conclusion,
        "conclusion_basis": "Pure Document Recall is not reconstructable from current persisted artifacts without prohibited query embedding. The verified 100% Document Recall@5 is Section-Assisted, not Pure Document Retrieval.",
    }


def _report(audit: dict[str, Any], dense: dict[str, Any], purity: dict[str, Any], acceptance: dict[str, Any]) -> str:
    focus_rows = "\n".join(
        f"| {row['question_id']} | {row['pure_document_rank_status']} | {row['document_bm25_rank']} | {row['document_dense_rank']} | {row['section_assisted_document_rank']} | {row['hierarchical_section_rank']} | {row['evidence_rank']} |"
        for row in purity["focus_questions"]
    )
    return "\n".join([
        "# HIERARCHICAL RETRIEVAL METRIC INTEGRITY AUDIT",
        "",
        "> TASK-020C.1.1。仅读取既有 TASK-020C.1 Shadow 制品；没有调整 Retriever、权重、RRF、Boost、Gold 或知识源，也没有调用 Provider、刷新 Root-002 或扫描 Root-003。",
        "",
        "## 1. Registration 指标校正",
        "",
        f"- 原始值：{acceptance['registration_page_dominance']['observed']}。",
        "- 原报告 FAIL 的原因：将 `{numerator, denominator, rate}` 整个对象与整数 `0` 比较，属于验收代码类型比较错误。",
        f"- 正确判断：`rate == 0`；结果：**{acceptance['registration_page_dominance']['result']}**。",
        "",
        "## 2. Section Dense 覆盖率拆分",
        "",
        f"- Direct Section Dense Count：{dense['direct_section_dense_count']}；Eligible 中 Direct Count：{dense['direct_section_dense_eligible_count']}。",
        f"- Parent Document Vector Fallback Count：{dense['parent_document_vector_fallback_count']}。",
        f"- Excluded Section Count：{dense['excluded_section_count']}；Eligible Section Count：{dense['eligible_section_count']}。",
        f"- Direct Section Dense Coverage：{dense['direct_section_dense_coverage']['rate']}。",
        f"- Effective Section Vector Availability：{dense['effective_section_vector_availability']['rate']}。",
        f"- 1870 个回退原因：{dense['fallback_root_cause']['reason']}",
        "",
        "## 3. Document Stage 纯度",
        "",
        "- A. 是：在 Document TopK 之前，系统已对全库 Section 执行 Query 相关性计算。",
        "- B. 是：全库 Section 的 BM25/Dense 排名被折叠为父 Document 信号，并参与 Document RRF。",
        "- C. 是：Document TopK 已使用 Section Retrieval 结果，因此它不是纯 Document Stage。",
        "- D. 纯 Document 指标当前不可由持久化 Trace 精确还原：Trace 未保存 Query Vector 和全量 Document-only Dense 排名；根据本 TASK 禁止调用 Provider，未重新嵌入 Query。",
        "",
        "## 4. 指标",
        "",
        "| 路径 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | 状态 |",
        "|---|---:|---:|---:|---:|---|",
        "| Pure Document Retrieval | — | — | — | — | NOT_RECONSTRUCTABLE_FROM_PERSISTED_TRACE |",
        f"| Section-Assisted Document Retrieval | {purity['section_assisted_document_retrieval']['recall_at_1']['rate']} | {purity['section_assisted_document_retrieval']['recall_at_3']['rate']} | {purity['section_assisted_document_retrieval']['recall_at_5']['rate']} | {purity['section_assisted_document_retrieval']['recall_at_10']['rate']} | VERIFIED |",
        "",
        "## 5. BA 专项",
        "",
        "| BA | Pure Document Rank | Native BM25 Rank | Native Dense Rank | Section-Assisted Document Rank | Hierarchical Section Rank | Evidence Rank |",
        "|---|---|---:|---:|---:|---:|---:|",
        focus_rows,
        "",
        "## 6. Global Rescue",
        "",
        f"- Gold Dependency：{acceptance['global_rescue']['gold_dependency']['rate']}。它未计入 Pure Document Recall。",
        "",
        "## 7. 最终结论",
        "",
        f"**{acceptance['document_stage_conclusion']}**",
        "",
        "原因：当前可验证的 100% Document Recall@5 来自 Section-Assisted Document Retrieval；不能将它表述为纯 Document Retrieval 成功。",
        "",
        "TASK-020C.1.1 = COMPLETE",
        "",
    ])


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / max(1, denominator), 4)}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
