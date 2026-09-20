"""T03: audit Metadata V2 without inventing values or changing staging records."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
NODE_METRICS = ROOT / "evaluation" / "knowledge_os_v2_1" / "node_binding" / "metrics.json"
OUT = ROOT / "evaluation" / "knowledge_os_v2_1" / "chunk_governance" / "metadata_metrics.json"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def present(value: object) -> bool:
    return value not in (None, "", [], {})


def value_state(field: str, profile: dict, strong: dict) -> str:
    if field in strong and present(strong.get(field)):
        return "STRONG_FACT"
    record = profile.get(field) or {}
    if not present(record.get("value")):
        return "MISSING"
    if record.get("verified") is True:
        return "VERIFIED"
    return "INFERRED"


def main() -> int:
    docs = read_jsonl(STAGING / "documents.jsonl")
    sections = read_jsonl(STAGING / "sections.jsonl")
    chunks = read_jsonl(STAGING / "semantic_chunks.jsonl")
    node_metrics = json.loads(NODE_METRICS.read_text(encoding="utf-8")) if NODE_METRICS.exists() else {}
    fields = ("organization", "project", "year", "specialty", "stage")
    doc_stats: dict[str, dict] = {}
    for field in fields:
        counts = Counter()
        for doc in docs:
            metadata = doc.get("metadata") or {}
            counts[value_state(field, metadata.get("inferred") or {}, metadata.get("strong_fact") or {})] += 1
        total = len(docs)
        doc_stats[field] = {"total": total, "states": dict(counts), "fill_rate_all_documents": round((total - counts["MISSING"]) / total, 4) if total else None, "verified_rate": round(counts["VERIFIED"] / total, 4) if total else None}
    chunk_type = Counter(str((row.get("knowledge_type") or {}).get("classification") or "MISSING") for row in chunks)
    chunk_type_values = Counter(str((row.get("knowledge_type") or {}).get("value") or "MISSING") for row in chunks)
    metrics = {"schema_version": "knowledge_os_v2_1.metadata.metrics", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "applicability_warning": "组织/项目/年份/专业适用性尚未有人工标注；本表先给出全量记录状态，不把推测值伪装成适用字段。", "document_fields": doc_stats, "section_path": {"total": len(sections), "present": sum(present(row.get("section_path")) for row in sections), "fill_rate": round(sum(present(row.get("section_path")) for row in sections) / len(sections), 4) if sections else None, "state": "STRUCTURAL_FACT"}, "knowledge_type": {"total": len(chunks), "classification_states": dict(chunk_type), "values": dict(chunk_type_values), "verified_count": sum((row.get("knowledge_type") or {}).get("verified") is True for row in chunks), "inferred_count": sum((row.get("knowledge_type") or {}).get("classification") == "RULE_INFERRED" for row in chunks)}, "knowledge_node": {"semantic_chunk_any_node_coverage": (node_metrics.get("semantic_chunk") or {}).get("any_node_coverage"), "semantic_chunk_detail_node_coverage": (node_metrics.get("semantic_chunk") or {}).get("detail_node_coverage"), "verified_binding_rate": node_metrics.get("verified_binding_rate"), "root_only_rate": node_metrics.get("root_only_chunk_rate")}, "stage": {"state": "MISSING", "reason": "V2 staging schema has no verified stage field; no stage value was inferred here."}, "hard_filter_policy": "Metadata remains boost/soft-filter only unless explicitly verified by a user/reviewer."}
    OUT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
