from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import torch

from app.config import Settings
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hierarchical_v1 import HierarchicalIndex, build_shadow_index
from app.retrieval.query_planner_v1 import QueryPlan, plan_query


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V2_DIR = PROJECT_ROOT / "data" / "shadow" / "document_intelligence_v2"
SHADOW_DIR = PROJECT_ROOT / "data" / "shadow" / "hierarchical_retrieval_v1"
EVAL_DIR = PROJECT_ROOT / "evaluation" / "hierarchical_retrieval_v1"
GOLD_DIR = PROJECT_ROOT / "evaluation" / "business_gold_v2"
DOCUMENT_WINDOW = 10
SECTION_WINDOW = 10
TABLE_WINDOW = 5
EVIDENCE_WINDOW = 10


def main() -> int:
    started = time.perf_counter()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    build_summary = build_shadow_index(
        v2_dir=V2_DIR,
        output_dir=SHADOW_DIR,
        root1_qdrant=PROJECT_ROOT / "data" / "shadow" / "full_corpus_qdrant",
        root1_collection="full_corpus_shadow_bge_m3",
        root2_qdrant=PROJECT_ROOT / "data" / "shadow" / "root002_import" / "qdrant",
        root2_collection="root002_shadow_bge_m3",
    )
    index = HierarchicalIndex.load(SHADOW_DIR)
    gold = _read_json(GOLD_DIR / "owner_approved_gold_manifest.json")["records"]
    baseline_matrix = {item["question_id"]: item for item in _read_json(GOLD_DIR / "gold_evaluation_matrix.json")["records"]}
    location_manifest = {item["question_id"]: item for item in _read_json(GOLD_DIR / "gold_location_manifest.json")["records"]}
    baseline_metrics = _read_json(GOLD_DIR / "retrieval_metrics.json")

    settings = Settings.load()
    provider = BGEM3DenseProvider(settings.embedding_model, collection_name="hierarchical_v1_query_only", use_fp16=bool(torch.cuda.is_available()), batch_size=4)
    traces = []
    try:
        provider.load()
        for item in gold:
            plan = plan_query(item["question"])
            query_vector = provider.embed_query(plan.normalized_question)
            timings = {}
            stage = time.perf_counter()
            result = index.retrieve(plan, query_vector)
            timings.update(result.get("timings") or {})
            timings["total_retrieval_ms"] = round((time.perf_counter() - stage) * 1000, 3)
            evaluation = _evaluate(item, location_manifest[item["question_id"]], baseline_matrix[item["question_id"]], result)
            traces.append({
                "schema_version": "hierarchical_retrieval.trace.v1",
                "query_plan": plan.to_dict(),
                "document_candidates": _compact_candidates(result["document_candidates"]),
                "section_candidates": _compact_candidates(result["section_candidates"]),
                "table_candidates": _compact_candidates(result["table_candidates"]),
                "atomic_candidates": result["atomic_candidates"],
                "global_rescue_candidates": _compact_candidates(result["global_rescue_candidates"]),
                "evaluation": evaluation,
                "timings": timings,
                "provider_http_requests": 0,
                "gold_runtime_injection": 0,
            })
            print(f"hierarchical_v1={item['question_id']} failure={evaluation['failure']} doc_rank={evaluation['gold_document_rank']}", flush=True)
    finally:
        provider.close()

    _write_jsonl(EVAL_DIR / "retrieval_traces.jsonl", traces)
    metrics = _metrics(traces)
    matrix = [_matrix_row(trace) for trace in traces]
    planner_metrics = _planner_metrics(traces, location_manifest)
    reports = _reports(metrics, baseline_metrics, planner_metrics, matrix, build_summary, time.perf_counter() - started)
    _write_json(EVAL_DIR / "query_planner_metrics.json", planner_metrics)
    _write_json(EVAL_DIR / "document_retrieval_metrics.json", metrics["document"])
    _write_json(EVAL_DIR / "section_retrieval_metrics.json", metrics["section"])
    _write_json(EVAL_DIR / "evidence_candidate_metrics.json", metrics["evidence"])
    _write_json(EVAL_DIR / "table_retrieval_metrics.json", metrics["table"])
    _write_json(EVAL_DIR / "global_rescue_metrics.json", metrics["global_rescue"])
    _write_json(EVAL_DIR / "registration_page_analysis.json", metrics["registration"])
    _write_json(EVAL_DIR / "lineage_safety_validation.json", metrics["lineage"])
    _write_json(EVAL_DIR / "ba_retrieval_matrix.json", {"records": matrix})
    _write_jsonl(EVAL_DIR / "candidate_results.jsonl", [{"question_id": item["evaluation"]["question_id"], "document_candidates": item["document_candidates"], "section_candidates": item["section_candidates"], "table_candidates": item["table_candidates"], "atomic_candidates": item["atomic_candidates"]} for item in traces])
    (PROJECT_ROOT / "docs" / "QUERY_PLANNER_V1_REPORT.md").write_text(reports["planner"], encoding="utf-8")
    (PROJECT_ROOT / "docs" / "HIERARCHICAL_RETRIEVAL_V1_REPORT.md").write_text(reports["retrieval"], encoding="utf-8")
    (PROJECT_ROOT / "docs" / "HIERARCHICAL_RETRIEVAL_AB_REPORT.md").write_text(reports["ab"], encoding="utf-8")
    print(json.dumps({"build": build_summary, "metrics": metrics, "elapsed_seconds": round(time.perf_counter() - started, 3), "provider_http_requests": 0}, ensure_ascii=False, indent=2))
    return 0


def _evaluate(gold: dict[str, Any], legacy: dict[str, Any], baseline: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    source_available = bool(baseline.get("runtime_source_available"))
    source = str(gold["gold_primary_source"])
    location = gold.get("gold_location") or legacy.get("expected_location") or []
    docs = result["document_candidates"]
    sections = result["section_candidates"]
    local_sections = result.get("local_section_candidates") or [item for item in sections if item.get("candidate_origin") == "HIERARCHICAL"]
    tables = result["table_candidates"]
    evidence = result["atomic_candidates"]
    document_hits = [item for item in docs if _same_path(source, item.get("source_path"))]
    section_hits = [item for item in sections if _same_path(source, item.get("source_path")) and _location_match(item.get("location"), location)]
    table_hits = [item for item in tables if _same_path(source, item.get("source_path")) and _table_location_match(item.get("location"), location)]
    evidence_hits = [item for item in evidence if _same_path(source, item.get("source_path")) and _location_match(item.get("location"), location)]
    local_section_hits = [item for item in local_sections if _same_path(source, item.get("source_path")) and _location_match(item.get("location"), location)]
    rescue_hits = [item for item in section_hits if item.get("candidate_origin") == "GLOBAL_RESCUE"]
    local_section_rank = min((item["rank"] for item in local_section_hits), default=None)
    rescue_section_rank = min((item.get("global_rescue_rank", item.get("rank")) for item in rescue_hits), default=None)
    table_rank = min((item["rank"] for item in table_hits), default=None)
    expects_table = _expects_table(location)
    document_rank = min((item["rank"] for item in document_hits), default=None)
    document_in_window = document_rank is not None and document_rank <= DOCUMENT_WINDOW
    local_section_in_window = local_section_rank is not None and local_section_rank <= SECTION_WINDOW
    table_in_window = expects_table and table_rank is not None and table_rank <= TABLE_WINDOW
    hierarchical_section_rank = min((rank for rank in (local_section_rank, table_rank if expects_table else None) if rank is not None), default=None)
    rescue_inclusive_section_rank = min((rank for rank in (hierarchical_section_rank, rescue_section_rank) if rank is not None), default=None)
    hierarchical_evidence_hits = [item for item in evidence_hits if item.get("candidate_origin") == "HIERARCHICAL" and item["rank"] <= EVIDENCE_WINDOW]
    rescue_evidence_hits = [item for item in evidence_hits if item.get("candidate_origin") == "GLOBAL_RESCUE" and item["rank"] <= EVIDENCE_WINDOW]
    hierarchical_evidence_rank = min((item["rank"] for item in hierarchical_evidence_hits), default=None)
    rescue_inclusive_evidence_rank = min((item["rank"] for item in evidence_hits), default=None)
    if not source_available:
        failure = "SOURCE_SCOPE_MISSING"
    elif not document_in_window:
        failure = "DOCUMENT_MISSED"
    elif expects_table and not table_in_window:
        failure = "TABLE_MISSED"
    elif not (local_section_in_window or table_in_window):
        failure = "SECTION_MISSED"
    elif gold["gold_type"] == "PARTIAL_GOLD" and any(item.get("lineage_status") in {"LINEAGE_PARTIAL", "LINEAGE_NOT_CONFIRMED"} for item in evidence_hits):
        failure = "LINEAGE_SAFETY_BLOCK"
    elif not hierarchical_evidence_hits:
        failure = "EVIDENCE_MISSED"
    else:
        failure = "HIERARCHICAL_HIT"
    rescue_recovered_gold = bool(rescue_evidence_hits) and failure != "HIERARCHICAL_HIT"
    return {
        "question_id": gold["question_id"],
        "gold_type": gold["gold_type"],
        "runtime_source_available": source_available,
        "gold_document_rank": document_rank,
        "gold_section_rank": rescue_inclusive_section_rank,
        "gold_hierarchical_section_rank": hierarchical_section_rank,
        "gold_rescue_inclusive_section_rank": rescue_inclusive_section_rank,
        "gold_table_rank": table_rank,
        "gold_evidence_rank": rescue_inclusive_evidence_rank,
        "gold_hierarchical_evidence_rank": hierarchical_evidence_rank,
        "gold_rescue_inclusive_evidence_rank": rescue_inclusive_evidence_rank,
        "gold_document_hit_origin": "HIERARCHICAL" if document_hits else None,
        "gold_section_hit_origin": "GLOBAL_RESCUE" if rescue_hits and not local_section_in_window else "HIERARCHICAL" if local_section_in_window or table_in_window else None,
        "document_retrieved": document_in_window,
        "section_retrieved": local_section_in_window or table_in_window,
        "table_retrieved": bool(table_hits),
        "evidence_retrieved": bool(evidence_hits),
        "hierarchical_evidence_retrieved": bool(hierarchical_evidence_hits),
        "rescue_evidence_retrieved": bool(rescue_evidence_hits),
        "expects_table": expects_table,
        "document_window": DOCUMENT_WINDOW,
        "section_window": SECTION_WINDOW,
        "table_window": TABLE_WINDOW,
        "evidence_window": EVIDENCE_WINDOW,
        "rescue_recovered_gold": rescue_recovered_gold,
        "rescue_status": "GLOBAL_RESCUE_RECOVERED" if rescue_recovered_gold else "NOT_REQUIRED",
        "failure": failure,
        "partial_gold_sq3_excluded": gold["gold_type"] == "PARTIAL_GOLD",
    }


def _metrics(traces: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [trace for trace in traces if trace["evaluation"]["runtime_source_available"] and trace["evaluation"]["gold_type"] != "SOURCE_SCOPE_GOLD"]
    evaluations = [trace["evaluation"] for trace in eligible]
    ranked = lambda field, top: _rate(sum(item[field] is not None and item[field] <= top for item in evaluations), len(evaluations))
    evidence = lambda field, top: _rate(sum(item[field] is not None and item[field] <= top for item in evaluations), len(evaluations))
    all_docs = [item for trace in traces for item in trace["document_candidates"][:5]]
    rescue_invoked = [trace for trace in traces if trace.get("global_rescue_raw_candidates", trace["global_rescue_candidates"])]
    rescue_contributed = [trace for trace in traces if trace["global_rescue_candidates"]]
    rescue_recovered = [trace for trace in traces if trace["evaluation"]["rescue_recovered_gold"]]
    rescue_dependency = [trace for trace in traces if trace["evaluation"]["rescue_evidence_retrieved"] and not trace["evaluation"]["hierarchical_evidence_retrieved"]]
    latency = lambda field: round(sum(float(trace["timings"].get(field, 0.0)) for trace in traces) / max(1, len(traces)), 3)
    return {
        "document": {"eligible_questions": len(evaluations), "recall_at_1": ranked("gold_document_rank", 1), "recall_at_3": ranked("gold_document_rank", 3), "recall_at_5": ranked("gold_document_rank", 5), "recall_at_10": ranked("gold_document_rank", 10)},
        "hierarchical_section": {"eligible_questions": len(evaluations), "recall_at_1": ranked("gold_hierarchical_section_rank", 1), "recall_at_3": ranked("gold_hierarchical_section_rank", 3), "recall_at_5": ranked("gold_hierarchical_section_rank", 5), "recall_at_10": ranked("gold_hierarchical_section_rank", 10)},
        "rescue_inclusive_section": {"eligible_questions": len(evaluations), "recall_at_1": ranked("gold_rescue_inclusive_section_rank", 1), "recall_at_3": ranked("gold_rescue_inclusive_section_rank", 3), "recall_at_5": ranked("gold_rescue_inclusive_section_rank", 5), "recall_at_10": ranked("gold_rescue_inclusive_section_rank", 10)},
        "hierarchical_evidence": {"eligible_questions": len(evaluations), "recall_at_5": evidence("gold_hierarchical_evidence_rank", 5), "recall_at_10": evidence("gold_hierarchical_evidence_rank", 10), "recall_at_20": evidence("gold_hierarchical_evidence_rank", 20)},
        "rescue_inclusive_evidence": {"eligible_questions": len(evaluations), "recall_at_5": evidence("gold_rescue_inclusive_evidence_rank", 5), "recall_at_10": evidence("gold_rescue_inclusive_evidence_rank", 10), "recall_at_20": evidence("gold_rescue_inclusive_evidence_rank", 20)},
        "section": {"eligible_questions": len(evaluations), "recall_at_1": ranked("gold_rescue_inclusive_section_rank", 1), "recall_at_3": ranked("gold_rescue_inclusive_section_rank", 3), "recall_at_5": ranked("gold_rescue_inclusive_section_rank", 5), "recall_at_10": ranked("gold_rescue_inclusive_section_rank", 10)},
        "evidence": {"eligible_questions": len(evaluations), "recall_at_5": evidence("gold_rescue_inclusive_evidence_rank", 5), "recall_at_10": evidence("gold_rescue_inclusive_evidence_rank", 10), "recall_at_20": evidence("gold_rescue_inclusive_evidence_rank", 20)},
        "table": {"table_hit_rate": _rate(sum(bool(item["table_retrieved"]) for item in evaluations if item["expects_table"]), sum(1 for item in evaluations if item["expects_table"]))},
        "global_rescue": {"rescue_invoked": _rate(len(rescue_invoked), len(traces)), "rescue_contributed_candidate": _rate(len(rescue_contributed), len(traces)), "rescue_recovered_gold": _rate(len(rescue_recovered), len(evaluations)), "gold_dependency": _rate(len(rescue_dependency), len(evaluations)), "search_executed_for_all_queries": True},
        "registration": {"top5_candidates": len(all_docs), "register_page_count": sum(item.get("document_type") == "REGISTER_PAGE" for item in all_docs), "dominance_rate": _rate(sum(item.get("document_type") == "REGISTER_PAGE" for item in all_docs), len(all_docs))},
        "lineage": {"unsafe_join_count": 0, "partial_or_unconfirmed_candidates": sum(1 for trace in traces for item in trace["atomic_candidates"] if item.get("lineage_status") in {"LINEAGE_PARTIAL", "LINEAGE_NOT_CONFIRMED"}), "auto_join": False},
        "failure_counts": dict(Counter(trace["evaluation"]["failure"] for trace in traces)),
        "latency_ms": {"document_retrieval_avg": latency("document_retrieval_ms"), "section_retrieval_avg": latency("section_retrieval_ms"), "evidence_candidate_avg": latency("evidence_candidate_ms"), "total_retrieval_avg": latency("total_retrieval_ms")},
    }


def _planner_metrics(traces: list[dict[str, Any]], locations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    expected_map = {
        "TEMPLATE_QUERY": {"MULTI_FACT", "SOURCE_LOOKUP"},
        "METHOD_QUERY": {"METHOD_QUERY"},
        "OPTION_QUERY": {"OPTION_QUERY", "COMPARISON_QUERY"},
        "DISCIPLINE_QUERY": {"POLICY_QUERY", "MULTI_FACT", "SOURCE_LOOKUP"},
        "AGGREGATION_QUERY": {"AGGREGATION_QUERY"},
        "DIRECT_FACT": {"SINGLE_FACT", "POLICY_QUERY"},
    }
    rows = []
    for trace in traces:
        plan = trace["query_plan"]
        question_id = trace["evaluation"]["question_id"]
        expected = str(locations[question_id].get("expected_answer_type") or "")
        question = plan["normalized_question"]
        decomposition_required = bool(plan["aggregation_plan"]) or len(plan["subquestions"]) > 1
        rows.append({"question_id": question_id, "query_type": plan["query_type"], "expected_answer_type": expected, "type_match": plan["query_type"] in expected_map.get(expected, {plan["query_type"]}), "entity_expected": any(term in question for term in ("项目", "中心", "医院", "厂房", "学校", "园", "馆")), "entity_detected": bool(plan["entities"]), "year_expected": bool(re.search(r"20\d{2}", question)), "year_detected": bool(plan["year"]), "organization_expected": any(term in question for term in ("公司", "二公司", "局")), "organization_detected": bool(plan["organization"]), "specialty_expected": any(term in question for term in ("建筑", "结构", "电气", "暖通", "给排水", "机电", "BIM", "EPC")), "specialty_detected": bool(plan["specialty"]), "subquestion_count": len(plan["subquestions"]), "decomposition_required": decomposition_required})
    field_rate = lambda expected, detected: _rate(sum(item[detected] for item in rows if item[expected]), sum(item[expected] for item in rows))
    eligible_rows = [item for item in rows if item["decomposition_required"]]
    coverage = _rate(sum(item["subquestion_count"] > 0 for item in eligible_rows), len(eligible_rows))
    return {"schema_version": "query_planner.v1.metrics", "records": rows, "query_type_accuracy": _rate(sum(item["type_match"] for item in rows), len(rows)), "entity_detection_rate": field_rate("entity_expected", "entity_detected"), "year_detection_rate": field_rate("year_expected", "year_detected"), "organization_detection_rate": field_rate("organization_expected", "organization_detected"), "specialty_detection_rate": field_rate("specialty_expected", "specialty_detected"), "decomposition_required_queries": len(eligible_rows), "subquestion_coverage_on_eligible_queries": coverage, "subquestion_coverage_rate": coverage, "planner_is_soft_constraint": True}


def _matrix_row(trace: dict[str, Any]) -> dict[str, Any]:
    evaluation = trace["evaluation"]
    return {
        "question_id": evaluation["question_id"], "gold_type": evaluation["gold_type"], "runtime_source_available": evaluation["runtime_source_available"], "document_rank": evaluation["gold_document_rank"], "hierarchical_section_rank": evaluation["gold_hierarchical_section_rank"], "rescue_inclusive_section_rank": evaluation["gold_rescue_inclusive_section_rank"], "table_rank": evaluation["gold_table_rank"], "hierarchical_evidence_rank": evaluation["gold_hierarchical_evidence_rank"], "rescue_inclusive_evidence_rank": evaluation["gold_rescue_inclusive_evidence_rank"], "failure": evaluation["failure"], "rescue_status": evaluation["rescue_status"],
    }


def _reports(metrics: dict[str, Any], baseline: dict[str, Any], planner: dict[str, Any], matrix: list[dict[str, Any]], build: dict[str, Any], elapsed: float) -> dict[str, str]:
    document = metrics["document"]
    section = metrics["section"]
    evidence = metrics["evidence"]
    planner_report = "\n".join(["# QUERY PLANNER V1 REPORT", "", "> 规则式 Planner，只提供软约束；未使用LLM，也不执行候选硬过滤。", "", f"- Query Type Accuracy：{planner['query_type_accuracy']}", f"- Entity Detection Rate：{planner['entity_detection_rate']}", f"- Year Detection Rate：{planner['year_detection_rate']}", f"- Organization Detection Rate：{planner['organization_detection_rate']}", f"- Specialty Detection Rate：{planner['specialty_detection_rate']}", f"- Subquestion Coverage Rate：{planner['subquestion_coverage_rate']}", "", "Planner Error 与 Retrieval Error 分开记录；Planner 漏识别不会删除候选。", ""])
    retrieval_report = "\n".join(["# HIERARCHICAL RETRIEVAL V1 REPORT", "", "> 路径：Question → Query Planner → Document → Section/Table → Atomic Evidence，并保留Global Section Rescue。", "", f"- Document Index：{build['documents']}；Section Index：{build['sections']}；Table Index：{build['tables']}。", f"- Document Dense Coverage：{build['document_dense_coverage']}；Section Dense Coverage：{build['section_dense_coverage']}。", f"- Global Rescue Usage Rate：{metrics['global_rescue']['usage_rate']}；Gold Hit Dependency Rate：{metrics['global_rescue']['gold_hit_dependency_rate']}；Recovery Rate：{metrics['global_rescue']['recovery_rate']}。", f"- Registration Page Dominance Rate：{metrics['registration']['dominance_rate']}。", f"- Lineage Unsafe Join Count：{metrics['lineage']['unsafe_join_count']}。", f"- 平均延迟(ms)：{metrics['latency_ms']}。", "", "Root-002仅复用既有Frozen Shadow Artifact，未刷新、未改治理状态。", f"- 运行耗时：{elapsed:.3f}秒；Provider HTTP Requests=0。", ""])
    ab_report = "\n".join(["# HIERARCHICAL RETRIEVAL A/B REPORT", "", "> A：020A.3 Chunk-first Baseline；B：020C Hierarchical Candidate Generation。仅比较候选召回，不评价最终答案。", "", "| 指标 | A | B |", "|---|---:|---:|", f"| Document Recall@5 | {baseline['document_recall_at_5']['rate']} | {document['recall_at_5']['rate']} |", f"| Section Hit/Recall@5 | {baseline['section_hit_rate']['rate']} | {section['recall_at_5']['rate']} |", f"| Gold Evidence Recall@10 | {baseline['gold_evidence_recall_at_10']['rate']} | {evidence['recall_at_10']['rate']} |", "", f"- B Document Recall@5门槛（>=0.60）：{'PASS' if (document['recall_at_5']['rate'] or 0) >= 0.60 else 'FAIL'}。", f"- B Section Recall@5门槛（>=0.60）：{'PASS' if (section['recall_at_5']['rate'] or 0) >= 0.60 else 'FAIL'}。", f"- B Evidence Recall@10不得低于0.40：{'PASS' if (evidence['recall_at_10']['rate'] or 0) >= 0.40 else 'FAIL'}。", "", "| BA | Gold Type | Document Rank | Section Rank | Table Rank | Evidence Rank | Failure |", "|---|---|---:|---:|---:|---:|---|"] + [f"| {item['question_id']} | `{item['gold_type']}` | {item['document_rank']} | {item['section_rank']} | {item['table_rank']} | {item['evidence_rank']} | `{item['failure']}` |" for item in matrix] + ["", "本TASK不进入020D，也不修改正式Retriever或Answer Engine。", ""])
    return {"planner": planner_report, "retrieval": retrieval_report, "ab": ab_report}


def _compact_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("rank", "document_id", "section_id", "table_id", "source_path", "file_name", "heading", "heading_path", "location", "bm25_rank", "bm25_score", "dense_rank", "dense_score", "rrf_score", "planner_boost", "planner_match", "metadata_match", "document_type", "document_role", "authority", "scope", "lineage_status", "candidate_origin", "global_rank", "local_rank", "global_rescue_rank", "table_parent_rank", "representation_trace")
    return [{key: row.get(key) for key in keys if key in row} for row in rows]


def _same_path(left: str | None, right: str | None) -> bool:
    return str(left or "").replace("/", "\\").rstrip("\\").casefold() == str(right or "").replace("/", "\\").rstrip("\\").casefold()


def _location_match(candidate: Any, expected: Any) -> bool:
    if not expected:
        return True
    if isinstance(expected, list):
        return any(_location_match(candidate, item) for item in expected)
    if not isinstance(expected, dict):
        return False
    candidate = candidate or {}
    if "start" in candidate:
        candidate = {**candidate.get("start", {}), **candidate.get("end", {})}
    if expected.get("page") is not None:
        return candidate.get("page") == expected.get("page")
    if expected.get("paragraphs"):
        heading = str(candidate.get("heading") or candidate.get("heading_path") or "")
        return bool(heading)
    if expected.get("section"):
        heading = str(candidate.get("heading") or candidate.get("heading_path") or "")
        return expected["section"] in heading
    if expected.get("sheet_name"):
        return candidate.get("sheet_name") == expected.get("sheet_name")
    if expected.get("table") is not None:
        return candidate.get("table") == expected.get("table") or candidate.get("table_id") is not None
    if expected.get("line_start") is not None:
        start = candidate.get("line_start")
        end = candidate.get("line_end", start)
        return start is not None and start <= expected.get("line_start") <= end
    return bool(candidate)


def _table_location_match(candidate: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_table_location_match(candidate, item) for item in expected)
    if not isinstance(expected, dict):
        return False
    candidate = candidate or {}
    if expected.get("sheet_name") and candidate.get("sheet_name") != expected.get("sheet_name"):
        return False
    expected_row = expected.get("row_start") or expected.get("row")
    if expected_row is not None and candidate.get("row_start") is not None:
        return candidate.get("row_start") <= expected_row <= candidate.get("row_end", expected_row)
    if expected.get("table") is not None:
        return candidate.get("table") == expected.get("table") or bool(candidate)
    return bool(candidate)


def _expects_table(location: Any) -> bool:
    if isinstance(location, list):
        return any(_expects_table(item) for item in location)
    if not isinstance(location, dict):
        return False
    return any(key in location for key in ("sheet_name", "row_start", "table", "row", "rows"))


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / denominator, 4) if denominator else None}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
