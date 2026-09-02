from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "knowledge_growth.v1"


def candidate_for_trace(trace: dict[str, Any]) -> dict[str, Any] | None:
    answer = trace["answer"]
    bundle = trace["bundle"]
    status = answer["answer_status"]
    if status == "ANSWERED" and bundle["bundle_status"] == "VERIFIED":
        return None
    failure_type, growth_type, priority, reason, action = _classification(trace)
    fingerprint = _fingerprint(trace, failure_type)
    evidence = _evidence_snapshot(trace)
    affected = _affected(bundle)
    return {
        "candidate_id": "GC_" + fingerprint[:16], "candidate_fingerprint": fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(), "source_query_id": trace["question_id"], "question": trace["question"],
        "failure_type": failure_type, "growth_type": growth_type, "priority": priority, "reason": reason,
        "current_answer_status": status, "affected_document_ids": affected["document_ids"], "affected_section_ids": affected["section_ids"], "affected_evidence_ids": affected["evidence_ids"],
        "knowledge_gap": _knowledge_gap(trace, failure_type), "retrieval_gap": _retrieval_gap(trace, failure_type), "answer_gap": _answer_gap(trace, failure_type),
        "recommended_action": action, "suggested_source": _suggested_source(trace, failure_type), "suggested_metadata_fix": None, "suggested_qa": _suggested_qa(trace, failure_type),
        "evidence_snapshot": evidence, "governance_status": _governance_status(failure_type), "review_status": "PROPOSED", "reviewer": None, "review_comment": None,
        "created_by": "AI_PROPOSED", "knowledge_origin": "SOURCE_DERIVED", "schema_version": SCHEMA_VERSION, "occurrence_count": 1, "latest_seen_at": datetime.now(timezone.utc).isoformat(), "related_query_ids": [trace["question_id"]], "regression_question_ids": [trace["question_id"]],
    }


def merge_candidate(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["occurrence_count"] = int(existing.get("occurrence_count", 1)) + 1
    merged["latest_seen_at"] = incoming["latest_seen_at"]
    merged["related_query_ids"] = sorted(set(existing.get("related_query_ids", []) + incoming["related_query_ids"]))
    return merged


def _classification(trace: dict[str, Any]) -> tuple[str, str, str, str, str]:
    answer = trace["answer"]
    bundle = trace["bundle"]
    status = answer["answer_status"]
    if status == "SOURCE_SCOPE_MISSING":
        return "SOURCE_SCOPE_MISSING", "KNOWLEDGE_GROWTH", "P1", "当前允许知识范围内没有可直接支持该问题的来源。", "确认所需正式来源及其知识根；如来源位于未批准范围，提交只读治理审批。"
    if status == "CONFLICTING_ANSWER" or bundle["bundle_status"] == "CONFLICTING_EVIDENCE":
        return "CONFLICTING_EVIDENCE", "CONFLICT_REVIEW_CANDIDATE", "P0", "同范围事实存在冲突，系统不能自动裁决。", "由业务负责人确认正确口径，或补充版本、时间和指标定义。"
    if status == "PARTIAL_ANSWER" or bundle["bundle_status"] in {"VERIFIED_PARTIAL", "INSUFFICIENT_EVIDENCE"}:
        return "INSUFFICIENT_EVIDENCE", "KNOWLEDGE_GROWTH", "P1", "当前问题仅部分被证据覆盖，仍缺少可验证字段或结构化证据。", "补充缺失字段、结构化表格行/列或对应的正式来源；完成后回归原问题。"
    if status == "ANSWER_VALIDATION_FAILED":
        return "ANSWER_VALIDATION_FAILED", "QA_GROWTH", "P0", "答案未通过校验，不能作为可信输出。", "检查 Claim、Citation 和回答模板，不修改正式规则前先完成 Shadow 回归。"
    return "ANSWER_GAP", "QA_GROWTH", "P2", "回答状态异常，需要人工检查表达和 Claim 覆盖。", "审核问答模板与必需证据类型。"


def _knowledge_gap(trace: dict[str, Any], failure_type: str) -> str | None:
    if failure_type == "SOURCE_SCOPE_MISSING":
        return "需要与问题直接对应的正式业务来源；当前治理范围内未发现可用正文。"
    if failure_type == "INSUFFICIENT_EVIDENCE":
        uncovered = [item.get("subquestion") for item in trace["bundle"].get("coverage_map", []) if item.get("coverage_status") == "EVIDENCE_INSUFFICIENT"]
        limitations = [claim.get("rendered_claim_text") for claim in trace["answer"].get("claims", []) if claim.get("claim_type") in {"LIMITATION", "INSUFFICIENT"}]
        return "；".join(filter(None, [*uncovered, *limitations])) or "缺少可验证字段或结构化证据。"
    return None


def _retrieval_gap(trace: dict[str, Any], failure_type: str) -> str | None:
    if failure_type in {"DOCUMENT_MISSED", "SECTION_MISSED", "TABLE_MISSED", "EVIDENCE_MISSED"}:
        return "正确来源存在但未进入对应检索阶段。"
    return None


def _answer_gap(trace: dict[str, Any], failure_type: str) -> str | None:
    if failure_type == "CONFLICTING_EVIDENCE":
        return "需要冲突事实的业务口径确认，不能由答案层自动选择。"
    if failure_type == "INSUFFICIENT_EVIDENCE":
        return "已回答部分事实，但缺失字段不得被补全。"
    return None


def _suggested_source(trace: dict[str, Any], failure_type: str) -> dict[str, Any] | None:
    if failure_type != "SOURCE_SCOPE_MISSING":
        return None
    return {"required_source_type": "正式制度、项目资料或结构化台账", "current_root_status": "NO_APPROVED_SOURCE_IN_CURRENT_SCOPE", "known_owner_source": None, "governance_approval_required": True}


def _suggested_qa(trace: dict[str, Any], failure_type: str) -> dict[str, Any] | None:
    if failure_type != "INSUFFICIENT_EVIDENCE":
        return None
    return {"canonical_question": trace["question"], "expected_answer_type": "FIELD_BACKED_FACT", "required_evidence_type": "STRUCTURED_TABLE_OR_EXPLICIT_FIELD", "ownership": "AI_PROPOSED"}


def _governance_status(failure_type: str) -> str:
    if failure_type == "SOURCE_SCOPE_MISSING":
        return "REQUIRES_SOURCE_GOVERNANCE_REVIEW"
    if failure_type == "CONFLICTING_EVIDENCE":
        return "REQUIRES_BUSINESS_CONFLICT_REVIEW"
    return "REQUIRES_EVIDENCE_COMPLETENESS_REVIEW"


def _affected(bundle: dict[str, Any]) -> dict[str, list[str]]:
    candidates = bundle.get("candidate_evidence", [])
    return {"document_ids": sorted({str(item["document_id"]) for item in candidates if item.get("document_id")}), "section_ids": sorted({str(item["section_id"]) for item in candidates if item.get("section_id")}), "evidence_ids": sorted({str(item["evidence_id"]) for item in candidates if item.get("evidence_id")})}


def _evidence_snapshot(trace: dict[str, Any]) -> dict[str, Any]:
    bundle = trace["bundle"]
    evidence = bundle.get("conflicting_evidence") or bundle.get("verified_evidence") or bundle.get("candidate_evidence", [])[:3]
    return {"bundle_status": bundle["bundle_status"], "query_scope": {"organization": bundle.get("query_plan", {}).get("organization", []), "year": bundle.get("query_plan", {}).get("year", []), "metric": bundle.get("query_plan", {}).get("metric", [])}, "coverage_map": bundle.get("coverage_map", []), "sources": [{"evidence_id": item.get("evidence_id"), "file_name": item.get("file_name"), "source_path": item.get("source_path"), "location": item.get("location"), "document_role": item.get("document_role"), "authority": item.get("authority"), "scope": item.get("scope"), "excerpt": _excerpt(item.get("text") or "")} for item in evidence]}


def _fingerprint(trace: dict[str, Any], failure_type: str) -> str:
    bundle = trace["bundle"]
    target = next((item.get("document_id") for item in bundle.get("verified_evidence", []) if item.get("document_id")), "")
    gap = _knowledge_gap(trace, failure_type) or _retrieval_gap(trace, failure_type) or _answer_gap(trace, failure_type) or ""
    normalized = re.sub(r"\s+", "", trace["question"]).lower()
    return hashlib.sha256("|".join((normalized, failure_type, str(target), gap)).encode("utf-8")).hexdigest()


def _excerpt(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())[:360]
