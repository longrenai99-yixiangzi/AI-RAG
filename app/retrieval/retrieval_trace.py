"""T04 - 全链路 Retrieval Trace。

每次问答生成一个 query_run_id，并把下列阶段完整落盘：

    Query Understanding -> Retrieval Plan -> Lexical -> Dense -> Hybrid
    -> Reranker -> Evidence Validation -> Final Evidence -> Failure

落盘位置：
    evaluation/knowledge_os_system_audit/t04/traces/{query_run_id}.json
    evaluation/knowledge_os_system_audit/t04/traces.jsonl   （聚合索引）

说明：
    当前运行链路使用 RRF 融合，没有独立的 cross-encoder 重排阶段，
    因此 reranker 段如实标记 NOT_PRESENT，不伪造分数。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.retrieval import failure_taxonomy

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / "evaluation" / "knowledge_os_system_audit" / "t04" / "traces"
TRACE_FILE = TRACE_DIR.parent / "traces.jsonl"
MAX_CANDIDATES = 50

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _safe_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _query_understanding(plan: dict[str, Any], question: str, resolved: str) -> dict[str, Any]:
    return {
        "original_query": question,
        "normalized_query": resolved,
        "intent": plan.get("query_type"),
        "organization": _safe_list(plan.get("organization")),
        "project": _safe_list(plan.get("project")),
        "year": _safe_list(plan.get("year")),
        "professional": _safe_list(plan.get("specialty")),
        "metric": _safe_list(plan.get("metric")),
        "aggregation": _safe_list(plan.get("aggregation_plan")),
        "comparison": _safe_list(plan.get("comparison_plan")),
        "enumeration": "LIST_DISTINCT" in _safe_list(plan.get("aggregation_plan")),
        "entities": _safe_list(plan.get("entities")),
        "subquestions": _safe_list(plan.get("subquestions")),
        "planner_confidence": plan.get("planner_confidence"),
    }


def _retrieval_plan(plan: dict[str, Any]) -> dict[str, Any]:
    scope = plan.get("scope_constraints") or {}
    return {
        "lexical_queries": [plan.get("normalized_question") or ""],
        "dense_queries": [plan.get("normalized_question") or ""],
        "aliases": _safe_list(plan.get("entities")),
        "metadata_hints": {
            "document_type_hint": _safe_list(plan.get("document_type_hint")),
            "document_role_hint": _safe_list(plan.get("document_role_hint")),
            "authority_requirement": plan.get("authority_requirement"),
        },
        "hard_filters": scope,
        "soft_filters": {
            "document_type_hint": _safe_list(plan.get("document_type_hint")),
            "document_role_hint": _safe_list(plan.get("document_role_hint")),
        },
        "filter_note": "project/year 等明确范围会在 Evidence Validation 阶段阻断 MISMATCH；文档召回阶段只参与排序",
        "structured_query_hint": plan.get("structured_query_hint"),
    }


def _lexical(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in candidates[:MAX_CANDIDATES]:
        rows.append(
            {
                "chunk_id": item.get("document_id"),
                "rank": item.get("bm25_rank"),
                "score": item.get("bm25_score"),
                "matched_terms": (item.get("planner_match") or {}).get("metadata_match", []),
            }
        )
    return rows


def _dense(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in candidates[:MAX_CANDIDATES]:
        rows.append(
            {
                "chunk_id": item.get("document_id"),
                "rank": item.get("dense_rank"),
                "score": item.get("dense_score"),
            }
        )
    return rows


def _hybrid(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in candidates[:MAX_CANDIDATES]:
        rows.append(
            {
                "chunk_id": item.get("document_id"),
                "lexical_rank": item.get("bm25_rank"),
                "dense_rank": item.get("dense_rank"),
                "hybrid_rank": item.get("rank"),
                "hybrid_score": item.get("rrf_score"),
                "planner_boost": item.get("planner_boost"),
                "candidate_origin": item.get("candidate_origin"),
            }
        )
    return rows


def _reranker() -> dict[str, Any]:
    return {
        "status": "NOT_PRESENT",
        "note": "当前链路采用 RRF 融合，未部署独立 cross-encoder 重排阶段",
        "items": [],
    }


def _evidence_validation(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in (bundle.get("candidate_evidence") or [])[:MAX_CANDIDATES]:
        scope = item.get("scope") or {}
        mismatched = [key for key, value in scope.items() if value == "MISMATCH"]
        unknown = [key for key, value in scope.items() if value == "UNKNOWN"]
        scope_result = "MISMATCH" if mismatched else "UNKNOWN" if unknown else "MATCH_OR_NOT_APPLICABLE"
        reject_reason = item.get("why_excluded") or item.get("why_context_only") or item.get("why_conflicting")
        if not reject_reason and item.get("role") not in {"DIRECT", "SUPPORTING"}:
            reject_reason = f"ROLE_{item.get('role') or 'UNKNOWN'}"
        rows.append(
            {
                "chunk_id": item.get("evidence_id"),
                "document_id": item.get("document_id"),
                "source_id": item.get("source_id"),
                "file_name": item.get("file_name"),
                "display_location": item.get("display_location"),
                "rank": item.get("candidate_rank") or item.get("rank"),
                "score": item.get("score"),
                "role": item.get("role"),
                "candidate_origin": item.get("candidate_origin"),
                "scope_result": scope_result,
                "scope_fields": scope,
                "scope_reason": item.get("scope_reason"),
                "scope_matched": [key for key, value in scope.items() if value == "MATCH"],
                "scope_mismatched": mismatched,
                "scope_unknown": unknown,
                "evidence_result": item.get("verification_status") or item.get("status"),
                "reject_reason": reject_reason,
            }
        )
    return rows


def _final_evidence(answer: dict[str, Any], citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    evidence_by_citation = {item.get("citation_id"): item for item in citations}
    for claim in answer.get("claims") or []:
        for cid in claim.get("citation_ids") or []:
            citation = evidence_by_citation.get(cid) or {}
            rows.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "claim_text": claim.get("claim_text"),
                    "evidence_id": citation.get("evidence_id"),
                    "source_id": citation.get("source_id"),
                    "citation": cid,
                    "source_path": citation.get("source_path"),
                    "file_name": citation.get("file_name"),
                    "location": citation.get("location"),
                }
            )
    return rows


def build_trace(
    *,
    query_run_id: str,
    question: str,
    resolved_question: str,
    conversation_id: str = "",
    result: dict[str, Any],
) -> dict[str, Any]:
    """把一次问答的完整运行过程组装为可回溯 trace。"""
    debug = result.get("debug") or {}
    plan = debug.get("query_plan") or {}
    bundle = debug.get("evidence_bundle") or {}
    answer_status = result.get("answer_status")
    citations = result.get("citations") or []

    document_candidates = debug.get("document_candidates") or []
    section_candidates = debug.get("section_candidates") or []
    table_candidates = debug.get("table_candidates") or []
    candidate_evidence = bundle.get("candidate_evidence") or []
    verified_evidence = bundle.get("verified_evidence") or []

    validation_rows = _evidence_validation(bundle)
    scope_mismatch_in_top = any(
        str(row.get("scope_result") or "").upper() == "MISMATCH" for row in validation_rows[:10]
    )

    failure = failure_taxonomy.classify(
        answer_status=answer_status,
        bundle_status=bundle.get("bundle_status"),
        failure_reason=bundle.get("failure_reason"),
        candidate_count=len(candidate_evidence),
        verified_evidence_count=len(verified_evidence),
        claim_count=len(result.get("claims") or []),
        citation_count=len(citations),
        validation_errors=(result.get("answer_trace") or {}).get("validation_errors")
        if isinstance(result.get("answer_trace"), dict)
        else None,
        scope_mismatch_in_top=scope_mismatch_in_top,
    )

    return {
        "query_run_id": query_run_id,
        "timestamp": _now(),
        "question": question,
        "resolved_question": resolved_question,
        "conversation_id": conversation_id,
        "pipeline_version": result.get("pipeline_version"),
        "answer_status": answer_status,
        "answer_mode": result.get("answer_mode"),
        "dense_runtime": result.get("dense_runtime"),
        "stages": {
            "query_understanding": _query_understanding(plan, question, resolved_question),
            "retrieval_plan": _retrieval_plan(plan),
            "lexical_retrieval": _lexical(document_candidates),
            "dense_retrieval": _dense(document_candidates),
            "hybrid": _hybrid(document_candidates),
            "reranker": _reranker(),
            "section_retrieval": [
                {
                    "chunk_id": item.get("section_id"),
                    "document_id": item.get("document_id"),
                    "rank": item.get("rank"),
                    "score": item.get("score"),
                    "candidate_origin": item.get("candidate_origin"),
                }
                for item in section_candidates[:MAX_CANDIDATES]
            ],
            "table_retrieval": [
                {
                    "chunk_id": item.get("table_id"),
                    "document_id": item.get("document_id"),
                    "rank": item.get("rank"),
                    "score": item.get("score"),
                }
                for item in table_candidates[:MAX_CANDIDATES]
            ],
            "evidence_validation": validation_rows,
            "final_evidence": _final_evidence(result, citations),
        },
        "counts": {
            "document_candidates": len(document_candidates),
            "section_candidates": len(section_candidates),
            "table_candidates": len(table_candidates),
            "candidate_evidence": len(candidate_evidence),
            "verified_evidence": len(verified_evidence),
            "claims": len(result.get("claims") or []),
            "citations": len(citations),
        },
        "bundle_status": bundle.get("bundle_status"),
        "failure_reason_raw": bundle.get("failure_reason"),
        "failure": failure,
        "latency": result.get("latency") or {},
    }


def persist_trace(trace: dict[str, Any]) -> Path | None:
    """落盘单个 trace，并追加到聚合索引。失败不影响主流程。"""
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        path = TRACE_DIR / f"{trace.get('query_run_id')}.json"
        with _LOCK:
            path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
            with TRACE_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(trace, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None
