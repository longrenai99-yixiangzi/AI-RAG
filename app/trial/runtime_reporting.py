"""Read-only reporting for the currently selected runtime and its local records."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

TRAFFIC_KINDS = {"REAL", "TECHNICAL", "UNCLASSIFIED"}


def traffic_kind(row: dict[str, Any]) -> str:
    explicit = str(row.get("traffic_kind") or "").upper()
    if explicit in TRAFFIC_KINDS:
        return explicit
    conversation = str(row.get("conversation_id") or "").upper()
    comment = str(row.get("comment") or "")
    if re.search(r"(?:^|[_\s-])(?:TECH|TECHNICAL|REGRESSION|SMOKE|CANARY|ROLLBACK|PROBE)(?:$|[_\s-])", conversation) or "TECH_BROWSER" in comment:
        return "TECHNICAL"
    if "Owner真实" in comment:
        return "REAL"
    # Historical UUIDs and ANSWERED status do not prove natural business use.
    return "UNCLASSIFIED"


def source_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    indexed = sum(
        row.get("index_status") == "INDEXED"
        and not row.get("withdrawn")
        and bool(row.get("runtime_source_version") or row.get("source_version"))
        for row in rows
    )
    return {
        "sources": len(rows),
        "indexed_sources": indexed,
        "unavailable_sources": len(rows) - indexed,
        "source_count_scope": "CURRENT_RUNTIME_CATALOG_SOURCE_VERSIONS",
    }


def feedback_fingerprint(row: dict[str, Any]) -> str:
    fields = {key: row.get(key) for key in ("feedback_id", "query_run_id", "question", "comment", "source_path", "expected_answer")}
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def feedback_view(rows: list[dict[str, Any]], annotations: dict[str, Any], candidate_hash: str) -> list[dict[str, Any]]:
    records = annotations.get("records") or {}
    same_candidate = annotations.get("candidate_hash") == candidate_hash
    result = []
    for original in rows:
        row = {**original, "traffic_kind": traffic_kind(original), "original_status": original.get("status")}
        annotation = records.get(str(row.get("feedback_id") or ""), {}) if same_candidate else {}
        if annotation.get("feedback_fingerprint") == feedback_fingerprint(original):
            row.update({key: value for key, value in annotation.items() if key != "feedback_fingerprint"})
        if row["traffic_kind"] == "TECHNICAL":
            row["processing_status"] = "TECHNICAL_RECORD"
        elif row.get("technical_fix_verified") and row.get("published_package_sha256") and row.get("business_review_status") == "PENDING":
            row["processing_status"] = "PUBLISHED_PENDING_BUSINESS_REVIEW"
        elif row.get("business_review_status") == "ACCEPTED" and row.get("technical_fix_verified"):
            row["processing_status"] = "CLOSED"
        elif row.get("status") in {"REJECTED", "DEFERRED", "WITHDRAWN"}:
            row["processing_status"] = str(row["status"])
        else:
            row["processing_status"] = "PENDING_REVIEW"
        result.append(row)
    return result


def feedback_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = Counter(row["traffic_kind"] for row in rows)
    open_statuses = {"PENDING_REVIEW", "PUBLISHED_PENDING_BUSINESS_REVIEW"}
    return {
        "total": len(rows), "real": kinds["REAL"], "technical": kinds["TECHNICAL"],
        "unclassified": kinds["UNCLASSIFIED"],
        "pending": sum(row["traffic_kind"] != "TECHNICAL" and row["processing_status"] in open_statuses for row in rows),
        "pending_business_review": sum(row["processing_status"] == "PUBLISHED_PENDING_BUSINESS_REVIEW" for row in rows),
        "requires_review_or_fix": sum(row["traffic_kind"] != "TECHNICAL" and row["processing_status"] == "PENDING_REVIEW" for row in rows),
        "closed": sum(row["processing_status"] == "CLOSED" for row in rows),
    }


def knowledge_view(items: list[dict[str, Any]], annotations: dict[str, Any], candidate_hash: str) -> list[dict[str, Any]]:
    records = (annotations.get("records") or {}) if annotations.get("candidate_hash") == candidate_hash else {}
    result = []
    for item in items:
        overlay = records.get(item["knowledge_id"], {})
        body_hash = hashlib.sha256(item["content"].encode("utf-8")).hexdigest()
        if overlay.get("source_version") == item.get("source_version") and overlay.get("content_sha256") == body_hash:
            changes = {key: overlay[key] for key in ("node_id", "title", "applicability", "context_question", "context_text", "context_status", "context_source") if key in overlay}
            result.append({**item, "original_node_id": item["node_id"], "original_title": item["title"], **changes})
        else:
            result.append(item)
    return result
