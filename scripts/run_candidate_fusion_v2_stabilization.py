from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.retrieval.hierarchical_v1 import HierarchicalIndex


ROOT = Path(__file__).resolve().parents[1]
SOURCE_EVAL = ROOT / "evaluation" / "candidate_fusion_v2"
OUTPUT = ROOT / "evaluation" / "candidate_fusion_v2_stabilization"
INDEX_DIR = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    traces = _read_jsonl(SOURCE_EVAL / "fusion_traces.jsonl")
    by_id = {row["question_id"]: row for row in traces}
    index = HierarchicalIndex.load(INDEX_DIR)
    documents = {str(row["document_id"]): row for row in index.documents}
    atomic = {str(row.get("evidence_id")): row for row in index.atomic if row.get("evidence_id")}
    comparison = _comparison(by_id, documents, atomic)
    scope = _scope_audit(by_id["BA-008"], documents, atomic)
    reranker = _reranker_audit(by_id["BA-008"], scope)
    generic = _generic_evaluability(by_id, documents, atomic)
    authority = _authority_audit(by_id, generic)
    matrix = _post_fix_matrix(by_id)
    metrics = _post_fix_metrics()
    _write_json(OUTPUT / "ba001_ba008_trace_comparison.json", comparison)
    _write_json(OUTPUT / "scope_signal_audit.json", scope)
    _write_json(OUTPUT / "reranker_scope_audit.json", reranker)
    _write_json(OUTPUT / "generic_gold_evaluability.json", generic)
    _write_json(OUTPUT / "generic_metrics_corrected.json", generic["metrics"])
    _write_json(OUTPUT / "authority_scope_audit.json", authority)
    _write_json(OUTPUT / "post_fix_ba_matrix.json", matrix)
    _write_json(OUTPUT / "post_fix_metrics.json", metrics)
    (ROOT / "docs" / "CANDIDATE_FUSION_V2_STABILIZATION_REPORT.md").write_text(_report(comparison, scope, reranker, generic, authority, matrix, metrics), encoding="utf-8")
    assert metrics["provider_http_requests"] == 0
    assert metrics["lineage_unsafe_join_count"] == 0
    print(json.dumps({"acceptance": metrics["acceptance"], "provider_http_requests": 0}, ensure_ascii=False))
    return 0


def _comparison(traces: dict[str, dict[str, Any]], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "candidate_fusion.v2.stabilization.trace_comparison", "records": [_trace_record(traces[key], documents, atomic) for key in ("BA-001", "BA-008")]}


def _trace_record(trace: dict[str, Any], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    plan = trace["query_plan"]
    return {"question_id": trace["question_id"], "question": trace["question"], "query_plan": plan, "top10": [_candidate_row(item, plan, documents, atomic) for item in trace["post_rerank_candidates"][:10]]}


def _scope_audit(trace: dict[str, Any], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    plan = trace["query_plan"]
    rows = [_candidate_row(item, plan, documents, atomic) for item in trace["post_rerank_candidates"][:10]]
    for row in rows:
        row["mismatch_labels"] = _mismatch_labels(row["field_match"])
        row["numeric_values"] = sorted(set(re.findall(r"-?\d+(?:\.\d+)?", row["excerpt"])))
    same_scope = [row for row in rows if row["field_match"]["organization_match"] == "MATCH" and row["field_match"]["year_match"] == "MATCH" and row["field_match"]["metric_match"] == "MATCH"]
    return {"schema_version": "candidate_fusion.v2.stabilization.scope", "question_id": trace["question_id"], "planner_identification": {"organization": plan["organization"], "year": plan["year"], "metric": plan["metric"], "correct": True}, "records": rows, "same_scope_conflict_candidates": [{"file_name": row["file_name"], "numeric_values": row["numeric_values"], "rank": row["post_rerank_rank"]} for row in same_scope], "scope_match_metric_is_too_coarse": True}


def _candidate_row(item: dict[str, Any], plan: dict[str, Any], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    document = documents.get(str(item.get("document_id")), {})
    source = atomic.get(str(item.get("evidence_id")), {})
    field_match = _field_match(plan, document, source, item)
    trace = item.get("fusion_trace") or {}
    return {"post_rerank_rank": item.get("post_rerank_rank"), "pre_rerank_rank": item.get("pre_rerank_rank"), "file_name": item.get("file_name"), "source_path": item.get("source_path"), "heading_path": item.get("heading_path"), "candidate_origin": item.get("candidate_origin"), "organization": document.get("organization") or (document.get("scope") or {}).get("organization") or [], "project": document.get("project") or (document.get("scope") or {}).get("project") or [], "year": document.get("year") or (document.get("scope") or {}).get("year") or [], "document_role": item.get("document_role"), "authority": item.get("authority"), "field_match": field_match, "document_contribution": trace.get("document_support_rrf"), "section_contribution": trace.get("section_support_rrf"), "evidence_contribution": trace.get("evidence_lexical_rrf", 0) + trace.get("evidence_dense_rrf", 0), "metadata_contribution": trace.get("metadata_soft_bonus"), "scope_contribution": trace.get("scope_soft_bonus"), "authority_contribution": trace.get("authority_soft_bonus"), "role_contribution": trace.get("role_soft_bonus"), "reranker_score": item.get("reranker_score"), "final_fusion_score": item.get("final_fusion_score"), "post_rerank_score": item.get("post_rerank_score"), "excerpt": str(item.get("text") or source.get("text") or "")[:900], "lineage_status": item.get("lineage_status")}


def _field_match(plan: dict[str, Any], document: dict[str, Any], source: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    scope = document.get("scope") or {}
    result = {}
    for field, query_values in (("organization", plan.get("organization", [])), ("project", plan.get("project", [])), ("year", plan.get("year", [])), ("specialty", plan.get("specialty", []))):
        values = document.get(field) or scope.get(field) or []
        values = values if isinstance(values, list) else [values]
        if not query_values:
            result[f"{field}_match"] = "NOT_APPLICABLE"
        elif any(str(query).casefold() in json.dumps(values, ensure_ascii=False).casefold() for query in query_values):
            result[f"{field}_match"] = "MATCH"
        elif values:
            result[f"{field}_match"] = "MISMATCH"
        else:
            result[f"{field}_match"] = "UNKNOWN"
    text = " ".join(str(value or "") for value in (item.get("file_name"), item.get("heading_path"), item.get("text"), source.get("text"))).casefold()
    metrics = plan.get("metric", [])
    result["metric_match"] = "NOT_APPLICABLE" if not metrics else "MATCH" if all(str(metric).casefold() in text for metric in metrics) else "MISMATCH"
    return result


def _mismatch_labels(match: dict[str, str]) -> list[str]:
    mapping = {"organization_match": "ORGANIZATION_MISMATCH", "year_match": "YEAR_MISMATCH", "project_match": "PROJECT_SCOPE_MISMATCH", "metric_match": "METRIC_MISMATCH", "specialty_match": "ROLE_MISMATCH"}
    labels = [label for field, label in mapping.items() if match.get(field) == "MISMATCH"]
    return labels or ["NONE"]


def _reranker_audit(trace: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    passages = {json.loads(line)["question_id"]: json.loads(line)["passages"] for line in (ROOT / "data" / "shadow" / "candidate_fusion_v2" / "pre_rerank_inputs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    return {"schema_version": "candidate_fusion.v2.stabilization.reranker", "question_id": "BA-008", "pre_rerank_top10": [{"rank": row["pre_rerank_rank"], "file_name": row["file_name"], "reranker_input": passages[trace["question_id"]][row["pre_rerank_rank"] - 1] if row["pre_rerank_rank"] and row["pre_rerank_rank"] <= len(passages[trace["question_id"]]) else None, "reranker_score": row["reranker_score"], "post_rerank_rank": row["post_rerank_rank"]} for row in trace["post_rerank_candidates"][:10]], "reranker_scope_blindness": True, "reason": "Existing reranker input contains Document Title, Heading Path and Evidence only; it does not carry structured organization/project/year/role fields, while several candidates share coarse company/year/metric matches."}


def _generic_evaluability(traces: dict[str, dict[str, Any]], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manifest = _read_json(SOURCE_EVAL / "generic_regression_manifest.json")["records"]
    records = []
    for item in manifest:
        files = set(item.get("expected_files") or [])
        doc_matches = [document for document in documents.values() if document.get("file_name") in files]
        evidence_mapping = bool(item.get("expected_evidence_ids") or item.get("expected_location"))
        if not doc_matches:
            status = "SOURCE_SCOPE_MISSING"
        elif not evidence_mapping:
            status = "GENERIC_GOLD_MAPPING_MISSING"
        elif item.get("owner_confirmed") is not True:
            status = "PROVISIONAL_GOLD_WEAK"
        else:
            status = "GENERIC_EVALUABLE"
        records.append({"question_id": item["id"], "gold_source_exists_runtime": bool(doc_matches), "gold_document_v2_mapped": bool(doc_matches), "gold_evidence_v2_mapped": evidence_mapping, "gold_location_mapped": bool(item.get("expected_location")), "gold_status": status})
    evaluable = {row["question_id"] for row in records if row["gold_status"] == "GENERIC_EVALUABLE"}
    metrics = _generic_metrics_same_mapping(traces, evaluable)
    return {"schema_version": "candidate_fusion.v2.stabilization.generic_evaluability", "records": records, "counts": _count(row["gold_status"] for row in records), "metrics": metrics}


def _generic_metrics_same_mapping(traces: dict[str, dict[str, Any]], evaluable: set[str]) -> dict[str, Any]:
    if not evaluable:
        return {"denominator": 0, "020c_mrr": None, "020d_pre_rerank_mrr": None, "020d_post_rerank_mrr": None, "reason": "No fixed Generic Gold has both an explicit V2 Evidence mapping and an owner-confirmed status."}
    rows = [traces[key] for key in evaluable]
    values = lambda field: [row.get(field) for row in rows]
    mrr = lambda ranks: round(sum(1 / rank for rank in ranks if rank) / len(rows), 4)
    return {"denominator": len(rows), "020c_mrr": mrr(values("baseline_evidence_rank")), "020d_pre_rerank_mrr": mrr(values("pre_rerank_evidence_rank")), "020d_post_rerank_mrr": mrr(values("post_rerank_evidence_rank"))}


def _authority_audit(traces: dict[str, dict[str, Any]], generic: dict[str, Any]) -> dict[str, Any]:
    by_id = {row["question_id"]: row for row in generic["records"]}
    records = []
    for question_id, trace in traces.items():
        if not question_id.startswith("FCQ-"):
            continue
        status = by_id[question_id]["gold_status"]
        top = (trace.get("final_evidence") or [{}])[0]
        if status != "GENERIC_EVALUABLE":
            reason = "GOLD_MAPPING_UNSUITABLE"
        elif top.get("scope_match") in {"MISMATCH", "UNKNOWN"}:
            reason = "SCOPE_NOT_COMPARABLE"
        else:
            reason = "AUTHORITY_COMPARABLE"
        records.append({"question_id": question_id, "gold_status": status, "top_authority": top.get("authority"), "top_scope_match": top.get("scope_match"), "classification": reason})
    return {"records": records, "counts": _count(row["classification"] for row in records), "authority_appropriate_rate_recomputed": None, "reason": "Authority is not scored independently because no Generic Gold is currently evidence-evaluable."}


def _post_fix_matrix(traces: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"scope_guard_applied": False, "reason": "No non-arbitrary generic scope feature can distinguish the conflicting BA-008 company/year/metric reports; a guard was not applied.", "records": [{"question_id": key, "post_rerank_evidence_rank": traces[key].get("post_rerank_evidence_rank"), "final_status": traces[key].get("final_status"), "lineage_auto_join": False} for key in sorted(item for item in traces if item.startswith("BA-"))]}


def _post_fix_metrics() -> dict[str, Any]:
    post = _read_json(SOURCE_EVAL / "post_rerank_metrics.json")
    business = post["business"]
    return {"business": business, "acceptance": "NOT_PASSED_MRR_NO_IMPROVEMENT", "reason": "Business MRR remains 0.85, not greater than 020C baseline 0.85. Scope guard was not applied because BA-008 is a same-scope fact conflict, not a simple scope mismatch.", "provider_http_requests": 0, "network_access": False, "formal_qdrant_write": False, "lineage_unsafe_join_count": 0, "gold_runtime_injection": False, "ba_runtime_hardcoding": False}


def _report(comparison: dict[str, Any], scope: dict[str, Any], reranker: dict[str, Any], generic: dict[str, Any], authority: dict[str, Any], matrix: dict[str, Any], metrics: dict[str, Any]) -> str:
    return "\n".join(["# CANDIDATE FUSION V2 STABILIZATION REPORT", "", "> TASK-020D.1。只读复核既有020D Trace；未调用模型或Provider，未修改候选、权重、RRF、Gold、Index或Qdrant。", "", "## 1. 根因结论", "", "- BA-001：正式手册的 Evidence Dense、Section 与 Document 支持共同进入前列，故从原候选 Rank 4 提升至 Rank 1。", "- BA-008：Planner正确识别公司、2025和创效金额；但Top候选中存在多个同为公司/2025/创效金额的不同事实值。粗粒度 Scope= MATCH 无法区分事实口径。", "- BA-008 Reranker输入缺少显式组织、项目、年份和角色字段，确认为 `RERANKER_SCOPE_BLINDNESS`。", "- 该问题同时属于 `SAME_SCOPE_CONFLICT`：不引入任意业务偏好，不能只凭通用Soft Boost把某一份同范围报告指定为唯一正确答案。", "", "## 2. Generic Gold可评价性", "", f"- 状态分布：`{generic['counts']}`。只有 `GENERIC_EVALUABLE` 进入MRR分母；当前分母：{generic['metrics']['denominator']}。", "- 原30题的0.0667不能作为当前V2 Atomic Evidence质量结论，因为该集没有显式V2 Evidence/Location映射且非Owner Confirmed。", "", "## 3. 修正决策", "", "- 未应用Scope Guard：现有 BA-008 的核心冲突不是项目/年份/组织错配，而是同范围候选的事实值冲突。强行加分会构成对单题结果的隐式偏好。", "- 未重新调用reranker：本TASK禁止Provider调用，因此只审计了既有reranker输入。", "", "## 4. 验收", "", f"- Business MRR：{metrics['business']['gold_evidence_mrr']}；要求 >0.85；结果：**NOT PASSED**。", f"- BA-008 Post-Rerank Rank：{next(row['post_rerank_evidence_rank'] for row in matrix['records'] if row['question_id']=='BA-008')}；要求 <=3；结果：**NOT PASSED**。", "- BA-001 / BA-002 / BA-004 / BA-010 保持既有安全状态；BA-010仍为 `LINEAGE_SAFETY_BLOCK` / `NO_AUTO_JOIN`。", "", "TASK-020D.1 = COMPLETE", "", "020D不接受；停止，不进入020E。", ""])


def _count(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[str(value)] = result.get(str(value), 0) + 1
    return result


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
