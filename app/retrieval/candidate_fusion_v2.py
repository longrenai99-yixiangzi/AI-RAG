from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Iterable


EVIDENCE_RRF_K = 60
PARENT_RRF_K = 180
SOFT_LIMIT = 0.018


def fuse_evidence_candidates(
    *,
    plan: Any,
    result: dict[str, Any],
    atomic_by_id: dict[str, dict[str, Any]],
    evidence_dense_scores: dict[str, float],
) -> list[dict[str, Any]]:
    """Fuse only candidates emitted by the existing hierarchical retriever."""
    documents = {str(item["document_id"]): item for item in result["document_candidates"]}
    sections = {str(item["section_id"]): item for item in result["section_candidates"]}
    tables_by_parent = _tables_by_parent(result["table_candidates"])
    candidates = _deduplicate(result["atomic_candidates"])
    evidence_dense_ranks = _rank_scores(evidence_dense_scores)
    pre_rows: list[dict[str, Any]] = []
    for evidence in candidates:
        evidence_id = str(evidence.get("evidence_id") or "")
        atomic = atomic_by_id.get(evidence_id, {})
        document = documents.get(str(evidence.get("document_id") or ""), {})
        section = sections.get(str(evidence.get("section_id") or ""), {})
        table = tables_by_parent.get((str(evidence.get("document_id") or ""), str(evidence.get("section_id") or "")))
        scope_match, scope_score, scope_trace = _scope_signal(plan, document, atomic)
        role_score, role_trace = _role_signal(plan, document, atomic)
        authority_score = _authority_signal(document, scope_match)
        metadata_score = _metadata_signal(document, section)
        table_score = 0.006 if table and plan.query_type in {"AGGREGATION_QUERY", "STRUCTURED_QUERY"} else 0.0
        registration = _is_registration_page(document, atomic)
        query_page = _is_query_page(document, atomic)
        navigation_penalty = -0.008 if registration and _is_fact_query(plan) else -0.004 if query_page and _is_fact_query(plan) else 0.0
        evidence_rank = int(evidence.get("rank") or 10**6)
        evidence_dense_rank = evidence_dense_ranks.get(evidence_id)
        document_rank = document.get("rank")
        section_rank = section.get("rank")
        base_evidence_rrf = _rrf(evidence_rank, EVIDENCE_RRF_K) + _rrf(evidence_dense_rank, EVIDENCE_RRF_K)
        section_support = _rrf(section_rank, PARENT_RRF_K)
        document_support = _rrf(document_rank, PARENT_RRF_K)
        soft_score = max(-SOFT_LIMIT, min(SOFT_LIMIT, scope_score + role_score + authority_score + metadata_score + table_score + navigation_penalty))
        final_score = base_evidence_rrf + section_support + document_support + soft_score
        row = {
            "candidate_id": evidence_id or _canonical_key(evidence),
            "canonical_key": _canonical_key(evidence),
            "evidence_id": evidence_id or None,
            "document_id": evidence.get("document_id"),
            "section_id": evidence.get("section_id"),
            "table_id": (atomic or {}).get("table_id") or (table or {}).get("table_id"),
            "source_path": evidence.get("source_path"),
            "file_name": evidence.get("file_name"),
            "heading_path": (section or {}).get("heading_path") or (atomic or {}).get("heading_path"),
            "location": evidence.get("location") or (atomic or {}).get("location"),
            "text": evidence.get("text") or (atomic or {}).get("text") or "",
            "candidate_origin": evidence.get("candidate_origin", "HIERARCHICAL"),
            "document_bm25_rank": document.get("bm25_rank"),
            "document_dense_rank": document.get("dense_rank"),
            "section_bm25_rank": section.get("bm25_rank"),
            "section_dense_rank": section.get("dense_rank"),
            "evidence_bm25_rank": evidence_rank,
            "evidence_dense_rank": evidence_dense_rank,
            "document_rrf_score": document.get("rrf_score"),
            "section_rrf_score": section.get("rrf_score"),
            "evidence_rrf_score": base_evidence_rrf,
            "metadata_match": {"document": document.get("metadata_match", []), "section": section.get("metadata_match", []), "atomic_facets": evidence.get("facet_reasons", [])},
            "planner_match": {"document": document.get("planner_match", {}), "section": section.get("planner_match", {})},
            "scope_match": scope_match,
            "authority": document.get("authority") or document.get("authority_level"),
            "document_role": document.get("document_role"),
            "authority_score": authority_score,
            "document_role_score": role_score,
            "table_match": bool(table),
            "lineage_status": evidence.get("lineage_status") or (atomic or {}).get("lineage_status") or "LINEAGE_NOT_APPLICABLE",
            "registration_page_flag": registration,
            "query_page_flag": query_page,
            "global_rescue_flag": evidence.get("candidate_origin") == "GLOBAL_RESCUE",
            "final_fusion_score": final_score,
            "fusion_trace": {
                "evidence_lexical_rrf": _rrf(evidence_rank, EVIDENCE_RRF_K),
                "evidence_dense_rrf": _rrf(evidence_dense_rank, EVIDENCE_RRF_K),
                "section_support_rrf": section_support,
                "document_support_rrf": document_support,
                "metadata_soft_bonus": metadata_score,
                "scope_soft_bonus": scope_score,
                "scope_trace": scope_trace,
                "authority_soft_bonus": authority_score,
                "role_soft_bonus": role_score,
                "role_trace": role_trace,
                "table_bonus": table_score,
                "navigation_penalty": navigation_penalty,
                "soft_score_capped": soft_score,
                "parent_support_is_bounded": True,
                "lineage_safety_flag": "NO_AUTO_JOIN",
            },
        }
        pre_rows.append(row)
    pre_rows.sort(key=lambda row: (-row["final_fusion_score"], row["candidate_id"]))
    for rank, row in enumerate(pre_rows, start=1):
        row["pre_rerank_rank"] = rank
    _mark_potential_conflicts(pre_rows)
    return pre_rows


def apply_reranker_scores(rows: list[dict[str, Any]], scores: Iterable[float] | None) -> list[dict[str, Any]]:
    values = list(scores or [])
    if len(values) != len(rows):
        values = [0.0] * len(rows)
    for row, score in zip(rows, values, strict=True):
        row["reranker_score"] = float(score)
    reranker_rank = _rank_scores({row["candidate_id"]: row["reranker_score"] for row in rows})
    for row in rows:
        rank = reranker_rank.get(row["candidate_id"])
        row["reranker_rank"] = rank
        row["post_rerank_score"] = _rrf(row.get("pre_rerank_rank"), EVIDENCE_RRF_K) + _rrf(rank, EVIDENCE_RRF_K) + row["fusion_trace"]["soft_score_capped"]
        row["fusion_trace"]["reranker_score"] = row["reranker_score"]
        row["fusion_trace"]["reranker_rrf"] = _rrf(rank, EVIDENCE_RRF_K)
    ordered = sorted(rows, key=lambda row: (-row["post_rerank_score"], row["candidate_id"]))
    for rank, row in enumerate(ordered, start=1):
        row["post_rerank_rank"] = rank
    return ordered


def final_evidence(rows: list[dict[str, Any]], *, limit: int = 10, max_per_section: int = 3) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    counts: dict[tuple[str, str], int] = defaultdict(int)
    seen: set[str] = set()
    for row in rows:
        if row["candidate_id"] in seen:
            continue
        section_key = (str(row.get("document_id") or ""), str(row.get("section_id") or ""))
        if counts[section_key] >= max_per_section:
            continue
        seen.add(row["candidate_id"])
        counts[section_key] += 1
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def reranker_passage(row: dict[str, Any]) -> str:
    return "\n".join([
        f"[Document] {row.get('file_name') or ''}",
        f"[Heading Path] {row.get('heading_path') or ''}",
        f"[Evidence] {str(row.get('text') or '')[:900]}",
    ])


def _tables_by_parent(tables: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for table in tables:
        record = table.get("record") or {}
        key = (str(table.get("document_id") or record.get("document_id") or ""), str(record.get("section_id") or table.get("section_id") or ""))
        if key not in result or int(table.get("rank") or 10**6) < int(result[key].get("rank") or 10**6):
            result[key] = table
    return result


def _deduplicate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("evidence_id") or _canonical_key(row))
        current = selected.get(key)
        if current is None or int(row.get("rank") or 10**6) < int(current.get("rank") or 10**6):
            selected[key] = row
    return sorted(selected.values(), key=lambda row: (int(row.get("rank") or 10**6), str(row.get("evidence_id") or "")))


def _canonical_key(row: dict[str, Any]) -> str:
    return "|".join(str(row.get(field) or "") for field in ("source_path", "section_id", "location", "text"))


def _rank_scores(scores: dict[str, float]) -> dict[str, int]:
    return {key: rank for rank, (key, _) in enumerate(sorted(scores.items(), key=lambda item: (-item[1], item[0])), start=1)}


def _rrf(rank: int | None, constant: int) -> float:
    return 1 / (constant + rank) if rank else 0.0


def _metadata_signal(document: dict[str, Any], section: dict[str, Any]) -> float:
    matches = len(document.get("metadata_match") or []) + len(section.get("metadata_match") or [])
    return min(0.004, matches * 0.001)


def _scope_signal(plan: Any, document: dict[str, Any], atomic: dict[str, Any]) -> tuple[str, float, dict[str, Any]]:
    constraints = getattr(plan, "scope_constraints", {}) or {}
    if not constraints:
        return "UNKNOWN", 0.0, {"matched": [], "mismatched": [], "unknown": True}
    scope = document.get("scope") or {}
    metadata = atomic.get("metadata") or {}
    matched: list[str] = []
    mismatched: list[str] = []
    for field, values in constraints.items():
        candidate_values = scope.get(field) or metadata.get(field) or []
        if isinstance(candidate_values, str):
            candidate_values = [candidate_values]
        candidate_text = json.dumps(candidate_values, ensure_ascii=False).casefold()
        if any(str(value).casefold() in candidate_text for value in values):
            matched.append(field)
        elif candidate_values:
            mismatched.append(field)
    if matched and not mismatched:
        return "MATCH", 0.010, {"matched": matched, "mismatched": []}
    if matched:
        return "PARTIAL", 0.004, {"matched": matched, "mismatched": mismatched}
    if mismatched:
        return "MISMATCH", -0.010, {"matched": [], "mismatched": mismatched}
    return "UNKNOWN", 0.0, {"matched": [], "mismatched": [], "unknown": True}


def _authority_signal(document: dict[str, Any], scope_match: str) -> float:
    if scope_match == "MISMATCH":
        return 0.0
    return {"L1": 0.004, "L2": 0.003, "L3": 0.002}.get(str(document.get("authority") or document.get("authority_level") or ""), 0.0)


def _role_signal(plan: Any, document: dict[str, Any], atomic: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    document_type = str(document.get("document_type") or "")
    document_role = str(document.get("document_role") or "")
    query_type = str(getattr(plan, "query_type", ""))
    preferred = {
        "POLICY_QUERY": {"POLICY", "MANAGEMENT_GUIDE", "RESPONSIBILITY_CONTRACT"},
        "CASE_QUERY": {"PROJECT_CASE", "RETROSPECTIVE"},
        "AGGREGATION_QUERY": {"TABLE_LEDGER", "PROJECT_PLAN"},
        "STRUCTURED_QUERY": {"TABLE_LEDGER", "PROJECT_PLAN"},
        "METHOD_QUERY": {"MANAGEMENT_GUIDE", "WORK_PLAN"},
    }.get(query_type, set())
    score = 0.005 if document_type in preferred else 0.0
    return score, {"query_type": query_type, "document_type": document_type, "document_role": document_role, "preferred": document_type in preferred}


def _is_registration_page(document: dict[str, Any], atomic: dict[str, Any]) -> bool:
    path = str(document.get("source_path") or atomic.get("source_path") or "").replace("/", "\\").casefold()
    return document.get("document_type") == "REGISTER_PAGE" or "\\wiki\\sources\\" in path


def _is_query_page(document: dict[str, Any], atomic: dict[str, Any]) -> bool:
    path = str(document.get("source_path") or atomic.get("source_path") or "").replace("/", "\\").casefold()
    return "\\wiki\\queries\\" in path


def _is_fact_query(plan: Any) -> bool:
    return str(getattr(plan, "query_type", "")) in {"SINGLE_FACT", "POLICY_QUERY", "AGGREGATION_QUERY", "STRUCTURED_QUERY"}


def _mark_potential_conflicts(rows: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("source_path") or ""), str(row.get("heading_path") or ""))].append(row)
    for group in grouped.values():
        values = {tuple(sorted(re.findall(r"-?\d+(?:\.\d+)?", str(row.get("text") or "")))) for row in group}
        conflict = len(values) > 1 and len(group) > 1
        for row in group:
            row["potential_conflict"] = conflict
