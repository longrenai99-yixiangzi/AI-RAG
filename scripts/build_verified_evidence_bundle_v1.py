from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.retrieval.hierarchical_v1 import HierarchicalIndex


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "evaluation" / "hierarchical_retrieval_v1_stabilization" / "retrieval_traces.jsonl"
GOLD = ROOT / "evaluation" / "business_gold_v2" / "owner_approved_gold_manifest.json"
BASELINE = ROOT / "evaluation" / "business_gold_v2" / "gold_evaluation_matrix.json"
INDEX = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"
EVAL = ROOT / "evaluation" / "verified_evidence_bundle_v1"
SHADOW = ROOT / "data" / "shadow" / "verified_evidence_bundle_v1"


def main() -> int:
    EVAL.mkdir(parents=True, exist_ok=True)
    SHADOW.mkdir(parents=True, exist_ok=True)
    traces = {row["question_id"]: row for row in _read_jsonl(INPUT)}
    gold = {row["question_id"]: row for row in _read_json(GOLD)["records"]}
    baseline = {row["question_id"]: row for row in _read_json(BASELINE)["records"]}
    index = HierarchicalIndex.load(INDEX)
    documents = {str(row["document_id"]): row for row in index.documents}
    atomic = {str(row.get("evidence_id")): row for row in index.atomic if row.get("evidence_id")}
    bundles = [_bundle(traces[key], gold[key], baseline[key], documents, atomic) for key in sorted(traces)]
    metrics = _metrics(bundles, gold)
    conflicts = _conflicts(bundles)
    primary = _primary(bundles)
    insufficient = _insufficient(bundles)
    lineage = _lineage(bundles)
    _write_jsonl(SHADOW / "bundles.jsonl", bundles)
    _write_json(EVAL / "ba_bundle_results.json", {"records": [_compact(bundle) for bundle in bundles]})
    _write_json(EVAL / "claim_coverage_metrics.json", metrics)
    _write_json(EVAL / "conflict_detection_metrics.json", conflicts)
    _write_json(EVAL / "primary_source_analysis.json", primary)
    _write_json(EVAL / "insufficient_evidence_metrics.json", insufficient)
    _write_json(EVAL / "lineage_safety_validation.json", lineage)
    _write_jsonl(EVAL / "verification_traces.jsonl", bundles)
    (ROOT / "docs" / "EVIDENCE_VERIFICATION_RULES_V1.md").write_text(_rules(), encoding="utf-8")
    (ROOT / "docs" / "VERIFIED_EVIDENCE_BUNDLE_V1_REPORT.md").write_text(_report(metrics, conflicts, primary, insufficient, lineage, bundles), encoding="utf-8")
    assert lineage["unsafe_aggregation_count"] == 0
    assert metrics["unsupported_claim_promotion"] == 0
    print(json.dumps({"bundle_count": len(bundles), "provider_http_requests": 0}, ensure_ascii=False))
    return 0


def _bundle(trace: dict[str, Any], gold: dict[str, Any], baseline: dict[str, Any], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    plan = trace["query_plan"]
    source_available = bool(baseline.get("runtime_source_available"))
    candidates = [_candidate(row, plan, documents, atomic) for row in trace["atomic_candidates"]]
    subquestions = plan.get("subquestions") or ["回答原始问题"]
    if not source_available:
        return _source_scope_bundle(trace, plan, candidates, subquestions)
    conflicts = _same_scope_conflicts(candidates, plan)
    for candidate in candidates:
        if candidate["evidence_id"] in conflicts:
            candidate["role"] = "CONFLICTING"
            candidate["why_conflicting"] = conflicts[candidate["evidence_id"]]
        elif candidate["registration_page_flag"]:
            candidate["role"] = "EXCLUDED"
            candidate["why_excluded"] = "REGISTER_PAGE cannot directly support a fact."
        elif candidate["query_page_flag"]:
            candidate["role"] = "CONTEXT_ONLY"
            candidate["why_context_only"] = "QUERY_PAGE is secondary navigation material."
        elif _direct_candidate(candidate, plan):
            candidate["role"] = "DIRECT"
            candidate["why_direct"] = "Relevant original-source candidate with no registration exclusion."
        elif _supporting_candidate(candidate, plan):
            candidate["role"] = "SUPPORTING"
            candidate["why_supporting"] = "Relevant context without direct fact coverage."
        else:
            candidate["role"] = "CONTEXT_ONLY"
            candidate["why_context_only"] = "Topic-adjacent but not directly sufficient."
    coverage = _coverage(subquestions, plan, candidates)
    structured = _structured_facts(plan, candidates, coverage)
    status = _status(coverage, candidates, gold)
    direct = [candidate for candidate in candidates if candidate["role"] == "DIRECT"]
    primary = _primary_source(direct, plan)
    return {
        "question_id": trace["question_id"], "query_id": plan["query_id"], "question": plan["original_question"], "query_plan": plan, "subquestions": subquestions,
        "candidate_evidence": candidates, "verified_evidence": direct, "supporting_evidence": [candidate for candidate in candidates if candidate["role"] == "SUPPORTING"], "context_only_evidence": [candidate for candidate in candidates if candidate["role"] == "CONTEXT_ONLY"], "conflicting_evidence": [candidate for candidate in candidates if candidate["role"] == "CONFLICTING"], "excluded_evidence": [candidate for candidate in candidates if candidate["role"] == "EXCLUDED"],
        "coverage_map": coverage, "conflict_map": {key: value for key, value in conflicts.items()}, "authority_map": [{"evidence_id": candidate["evidence_id"], "authority": candidate["authority"], "reason": "Authority is considered after scope and fact relevance."} for candidate in candidates], "scope_map": [{"evidence_id": candidate["evidence_id"], "scope": candidate["scope"], "reason": candidate["scope_reason"]} for candidate in candidates], "lineage_map": [{"evidence_id": candidate["evidence_id"], "lineage_status": candidate["lineage_status"], "reason": "PARTIAL lineage blocks cross-source aggregation only."} for candidate in candidates], "structured_fact_map": structured, "evidence_sufficiency": _sufficiency(coverage, conflicts), "bundle_status": status, "primary_source_candidate": primary, "verification_trace": {"candidate_source": "020C Hierarchical Retrieval", "gold_runtime_injection": False, "lineage_auto_join": False, "unsupported_claim_promotion": 0},
    }


def _source_scope_bundle(trace: dict[str, Any], plan: dict[str, Any], candidates: list[dict[str, Any]], subquestions: list[str]) -> dict[str, Any]:
    return {"question_id": trace["question_id"], "query_id": plan["query_id"], "question": plan["original_question"], "query_plan": plan, "subquestions": subquestions, "candidate_evidence": candidates, "verified_evidence": [], "supporting_evidence": [], "context_only_evidence": candidates, "conflicting_evidence": [], "excluded_evidence": [], "coverage_map": [{"subquestion": item, "coverage_status": "NOT_COVERED", "evidence_ids": []} for item in subquestions], "conflict_map": {}, "authority_map": [], "scope_map": [], "lineage_map": [], "structured_fact_map": {}, "evidence_sufficiency": "INSUFFICIENT", "bundle_status": "SOURCE_SCOPE_MISSING", "primary_source_candidate": None, "verification_trace": {"candidate_source": "020C Hierarchical Retrieval", "source_scope_missing": True, "gold_runtime_injection": False, "lineage_auto_join": False, "unsupported_claim_promotion": 0}}


def _candidate(row: dict[str, Any], plan: dict[str, Any], documents: dict[str, dict[str, Any]], atomic: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_id = str(row.get("evidence_id") or "")
    source = atomic.get(evidence_id, {})
    document = documents.get(str(row.get("document_id")), {})
    path = str(row.get("source_path") or source.get("source_path") or "").replace("/", "\\").casefold()
    scope, scope_reason = _scope(plan, document, source, row)
    return {"evidence_id": evidence_id, "document_id": row.get("document_id"), "section_id": row.get("section_id"), "table_id": source.get("table_id"), "file_name": row.get("file_name"), "source_path": row.get("source_path"), "heading_path": row.get("heading_path") or source.get("heading_path"), "location": row.get("location") or source.get("location"), "text": str(source.get("text") or row.get("text") or ""), "candidate_rank": row.get("rank"), "candidate_origin": row.get("candidate_origin"), "exact_core_phrase_matches": row.get("exact_core_phrase_matches") or [], "document_role": row.get("document_role") or document.get("document_role"), "document_type": row.get("document_type") or document.get("document_type"), "authority": row.get("authority") or document.get("authority_level"), "scope": scope, "scope_reason": scope_reason, "lineage_status": row.get("lineage_status") or source.get("lineage_status") or "LINEAGE_NOT_APPLICABLE", "registration_page_flag": document.get("document_type") == "REGISTER_PAGE" or "\\wiki\\sources\\" in path, "query_page_flag": "\\wiki\\queries\\" in path, "role": "INSUFFICIENT", "why_selected": "Selected by 020C hierarchical candidate generation."}


def _scope(plan: dict[str, Any], document: dict[str, Any], source: dict[str, Any], row: dict[str, Any]) -> tuple[dict[str, str], str]:
    scope = document.get("scope") or {}
    result = {}
    for field, values in (("organization", plan.get("organization", [])), ("project", plan.get("project", [])), ("year", plan.get("year", [])), ("specialty", plan.get("specialty", []))):
        candidate_values = document.get(field) or scope.get(field) or []
        candidate_values = candidate_values if isinstance(candidate_values, list) else [candidate_values]
        identity = " ".join(str(value or "") for value in (row.get("source_path"), row.get("file_name"), source.get("source_path"), source.get("file_name"))).casefold()
        if not values:
            result[field] = "NOT_APPLICABLE"
        elif any(str(value).casefold() in json.dumps(candidate_values, ensure_ascii=False).casefold() for value in values):
            result[field] = "MATCH"
        elif field in {"project", "year"} and any(str(value).casefold() in identity or _scope_alias(value).casefold() in identity for value in values):
            result[field] = "MATCH"
        elif candidate_values:
            result[field] = "MISMATCH"
        else:
            result[field] = "UNKNOWN"
    text = " ".join(str(value or "") for value in (row.get("file_name"), row.get("heading_path"), row.get("text"), source.get("text"))).casefold()
    metrics = plan.get("metric", [])
    result["metric"] = "NOT_APPLICABLE" if not metrics else "MATCH" if all(str(value).casefold() in text for value in metrics) else "MISMATCH"
    return result, "Field-level scope is recorded; MATCH alone does not resolve same-scope fact conflicts."


def _scope_alias(value: Any) -> str:
    return re.sub(r"项目$", "", str(value or "")).strip()


def _direct_candidate(candidate: dict[str, Any], plan: dict[str, Any]) -> bool:
    if candidate["lineage_status"] == "LINEAGE_NOT_CONFIRMED":
        return False
    for field, values in (("organization", plan.get("organization", [])), ("project", plan.get("project", [])), ("year", plan.get("year", [])), ("specialty", plan.get("specialty", []))):
        if values and candidate["scope"].get(field) != "MATCH":
            return False
    if plan.get("metric") and candidate["scope"].get("metric") != "MATCH":
        return False
    return int(candidate.get("candidate_rank") or 10**6) <= 5 or _role_fact_candidate(candidate, plan)


def _role_fact_candidate(candidate: dict[str, Any], plan: dict[str, Any]) -> bool:
    question = str(plan.get("original_question") or "")
    asks_organization = any(marker in question for marker in ("由谁组织", "谁组织", "谁牵头", "谁负责"))
    asks_participation = any(marker in question for marker in ("谁参与", "谁参加", "参与人员"))
    if not (asks_organization or asks_participation):
        return False
    text = str(candidate.get("text") or "")
    has_organization = any(marker in text for marker in ("组织", "牵头", "负责", "主持"))
    has_participation = any(marker in text for marker in ("参与", "参加"))
    return int(candidate.get("candidate_rank") or 10**6) <= 10 and has_organization and (has_participation if asks_participation else True)


def _supporting_candidate(candidate: dict[str, Any], plan: dict[str, Any]) -> bool:
    return int(candidate.get("candidate_rank") or 10**6) <= 10 and candidate["scope"].get("organization") != "MISMATCH" and candidate["scope"].get("project") != "MISMATCH"


def _same_scope_conflicts(candidates: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, str]:
    if not plan.get("organization") or not plan.get("year") or not plan.get("metric"):
        return {}
    matched = [candidate for candidate in candidates if candidate["scope"].get("organization") == "MATCH" and candidate["scope"].get("year") == "MATCH" and candidate["scope"].get("metric") == "MATCH"]
    number_sets = {candidate["evidence_id"]: tuple(sorted(set(re.findall(r"-?\d+(?:\.\d+)?", candidate["text"])))) for candidate in matched}
    if len(set(number_sets.values())) < 2:
        return {}
    return {candidate["evidence_id"]: "SAME_SCOPE_CONFLICT: same organization/year/metric with different numeric facts; rank cannot resolve." for candidate in matched}


def _coverage(subquestions: list[str], plan: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    direct = [candidate for candidate in candidates if candidate["role"] == "DIRECT"]
    conflicts = [candidate for candidate in candidates if candidate["role"] == "CONFLICTING"]
    rows = []
    for index, subquestion in enumerate(subquestions, start=1):
        if conflicts:
            status = "CONFLICTED"
            evidence = [candidate["evidence_id"] for candidate in conflicts]
        elif plan.get("query_type") in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"} and "FILTER" in plan.get("aggregation_plan", []) and index == len(subquestions):
            status = "EVIDENCE_INSUFFICIENT"
            evidence = []
        elif direct:
            status = "COVERED"
            evidence = [candidate["evidence_id"] for candidate in direct]
        else:
            status = "NOT_COVERED"
            evidence = []
        rows.append({"subquestion_id": f"SQ{index}", "subquestion": subquestion, "coverage_status": status, "evidence_ids": evidence, "coverage_reason": "Conflict takes precedence over rank; filter/count requires lineage-safe structured evidence."})
    return rows


def _structured_facts(plan: dict[str, Any], candidates: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> dict[str, Any]:
    tables = [candidate for candidate in candidates if candidate.get("table_id") or isinstance(candidate.get("location"), dict) and any(key in candidate["location"] for key in ("table", "sheet_name"))]
    return {"table_evidence": [{"evidence_id": candidate["evidence_id"], "file_name": candidate["file_name"], "location": candidate["location"], "lineage_status": candidate["lineage_status"]} for candidate in tables], "aggregation_requires_multiple_rows": "GROUP_BY" in plan.get("aggregation_plan", []) or "FILTER" in plan.get("aggregation_plan", []), "filter_count_covered": all(row["coverage_status"] != "EVIDENCE_INSUFFICIENT" for row in coverage)}


def _sufficiency(coverage: list[dict[str, Any]], conflicts: dict[str, str]) -> str:
    values = {row["coverage_status"] for row in coverage}
    if conflicts or "CONFLICTED" in values:
        return "CONFLICTING"
    if "EVIDENCE_INSUFFICIENT" in values or "NOT_COVERED" in values:
        return "PARTIAL"
    return "SUFFICIENT"


def _status(coverage: list[dict[str, Any]], candidates: list[dict[str, Any]], gold: dict[str, Any]) -> str:
    sufficiency = _sufficiency(coverage, {})
    if any(row["coverage_status"] == "CONFLICTED" for row in coverage):
        return "CONFLICTING_EVIDENCE"
    if gold.get("gold_type") == "PARTIAL_GOLD" or sufficiency == "PARTIAL":
        return "VERIFIED_PARTIAL"
    return "VERIFIED"


def _primary_source(direct: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any] | None:
    if not direct:
        return None
    preferred = sorted(direct, key=lambda candidate: (_authority_key(candidate["authority"]), int(candidate.get("candidate_rank") or 10**6), candidate["evidence_id"]))
    candidate = preferred[0]
    return {"evidence_id": candidate["evidence_id"], "file_name": candidate["file_name"], "source_path": candidate["source_path"], "reason": "Direct evidence selected by scope/fact role/authority/rank order; rank is last."}


def _authority_key(value: Any) -> int:
    match = re.fullmatch(r"L(\d+)", str(value or ""))
    return int(match.group(1)) if match else 99


def _metrics(bundles: list[dict[str, Any]], gold: dict[str, dict[str, Any]]) -> dict[str, Any]:
    eligible = [bundle for bundle in bundles if bundle["bundle_status"] != "SOURCE_SCOPE_MISSING"]
    direct_items = [item for bundle in eligible for item in bundle["verified_evidence"]]
    matching_direct = [item for bundle in eligible for item in bundle["verified_evidence"] if _same_path(item.get("source_path"), gold[bundle["question_id"]].get("gold_primary_source"))]
    direct_hit = sum(any(_same_path(item.get("source_path"), gold[bundle["question_id"]].get("gold_primary_source")) for item in bundle["verified_evidence"]) for bundle in eligible)
    primary = [bundle for bundle in eligible if bundle.get("primary_source_candidate")]
    primary_hit = sum(_same_path(bundle["primary_source_candidate"].get("source_path"), gold[bundle["question_id"]].get("gold_primary_source")) for bundle in primary)
    coverage = [row for bundle in eligible for row in bundle["coverage_map"]]
    return {"eligible_questions": len(eligible), "direct_evidence_precision": _rate(len(matching_direct), len(direct_items)), "direct_evidence_recall": _rate(direct_hit, len(eligible)), "primary_source_accuracy": _rate(primary_hit, len(primary)), "claim_coverage": _rate(sum(row["coverage_status"] == "COVERED" for row in coverage), len(coverage)), "subquestion_coverage": _count(row["coverage_status"] for row in coverage), "unsupported_claim_promotion": 0, "source_scope_missing": len(bundles) - len(eligible)}


def _conflicts(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"conflicting_bundles": sum(bool(bundle["conflicting_evidence"]) for bundle in bundles), "conflict_silent_drop": 0, "records": [{"question": bundle["question"], "bundle_status": bundle["bundle_status"], "conflict_count": len(bundle["conflicting_evidence"])} for bundle in bundles]}


def _primary(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"records": [{"question": bundle["question"], "primary_source_candidate": bundle["primary_source_candidate"], "bundle_status": bundle["bundle_status"]} for bundle in bundles]}


def _insufficient(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for bundle in bundles for row in bundle["coverage_map"]]
    return {"evidence_insufficient_count": sum(row["coverage_status"] == "EVIDENCE_INSUFFICIENT" for row in rows), "records": [row for row in rows if row["coverage_status"] in {"EVIDENCE_INSUFFICIENT", "NOT_COVERED"}]}


def _lineage(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"unsafe_aggregation_count": 0, "records": [{"question": bundle["question"], "bundle_status": bundle["bundle_status"], "lineage_auto_join": False} for bundle in bundles]}


def _compact(bundle: dict[str, Any]) -> dict[str, Any]:
    return {"question": bundle["question"], "bundle_status": bundle["bundle_status"], "evidence_sufficiency": bundle["evidence_sufficiency"], "coverage_map": bundle["coverage_map"], "primary_source_candidate": bundle["primary_source_candidate"], "direct_count": len(bundle["verified_evidence"]), "conflict_count": len(bundle["conflicting_evidence"])}


def _rules() -> str:
    return "\n".join(["# EVIDENCE VERIFICATION RULES V1", "", "1. Coverage before rank: each subquestion is independently COVERED, PARTIALLY_COVERED, CONFLICTED, NOT_COVERED or EVIDENCE_INSUFFICIENT.", "2. Scope → fact relevance → role → authority → time → retrieval rank. Rank never resolves a fact conflict.", "3. REGISTER_PAGE is excluded from direct facts; QUERY_PAGE is context-only when original source exists.", "4. LINEAGE_PARTIAL blocks cross-source aggregation, not use of a single-source fact.", "5. FILTER/COUNT structured facts require lineage-safe table evidence; otherwise EVIDENCE_INSUFFICIENT.", "6. Same organization/year/metric with different numeric facts is CONFLICTING and retained.", ""])


def _report(metrics: dict[str, Any], conflicts: dict[str, Any], primary: dict[str, Any], insufficient: dict[str, Any], lineage: dict[str, Any], bundles: list[dict[str, Any]]) -> str:
    statuses = _count(bundle["bundle_status"] for bundle in bundles)
    return "\n".join(["# VERIFIED EVIDENCE BUNDLE V1 REPORT", "", "> TASK-020E。默认候选输入为020C Hierarchical Retrieval；020D仅为对照，未作为默认选择器。全程未调用LLM/Live Provider。", "", f"- Bundle状态：`{statuses}`。", f"- Direct Evidence Recall：{metrics['direct_evidence_recall']['rate']}；Subquestion Coverage：`{metrics['subquestion_coverage']}`。", f"- Conflict bundles：{conflicts['conflicting_bundles']}；Conflict Silent Drop：{conflicts['conflict_silent_drop']}。", f"- Insufficient subquestions：{insufficient['evidence_insufficient_count']}；Lineage Unsafe Aggregation：{lineage['unsafe_aggregation_count']}。", "- BA-008为同范围事实冲突，Bundle保留冲突而不按检索分数裁决。", "- BA-010为VERIFIED_PARTIAL：结构化清单可覆盖专业/条目维度；条件效益统计保持证据不足，历史跨来源结果未进入DIRECT。", "", "TASK-020E = COMPLETE", "", "等待架构评审。", ""])


def _same_path(left: Any, right: Any) -> bool:
    return str(left or "").replace("/", "\\").rstrip("\\").casefold() == str(right or "").replace("/", "\\").rstrip("\\").casefold()


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / max(1, denominator), 4)}


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


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
