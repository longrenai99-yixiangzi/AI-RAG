"""Build T00-T05 into the isolated V2 staging layer."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.knowledge_engineering.structured_v2 import build_structured_layer
from app.document_intelligence.v2 import DocumentIntelligenceV2Builder, SUPPORTED_EXTENSIONS


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "shadow" / "document_intelligence_v2"
ROOT001 = Path(r"[LOCAL_PATH_REDACTED]")
LEGACY_ATOMIC = ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl"
STATE = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
EVAL = ROOT / "evaluation" / "knowledge_os_v2"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def ratio(value: int, total: int) -> float | None:
    return round(value / total, 4) if total else None


def main() -> int:
    paths = source_paths(ROOT001)
    bundle = DocumentIntelligenceV2Builder(ROOT001).build(paths, read_jsonl(SOURCE / "atomic_evidence.jsonl") or read_jsonl(LEGACY_ATOMIC))
    documents = bundle["documents"]
    sections = bundle["sections"]
    paragraphs = bundle["paragraphs"]
    tables = bundle["tables"]
    table_rows = bundle["table_rows"]
    legacy = read_jsonl(SOURCE / "atomic_evidence.jsonl") or read_jsonl(LEGACY_ATOMIC)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    registry = {str(row.get("source_path") or "").casefold(): row for row in (state.get("sources") or {}).values() if isinstance(row, dict)}
    layer = build_structured_layer(documents, sections, paragraphs, tables, table_rows, legacy, registry)
    for name, rows in layer.items():
        write_jsonl(STAGING / f"{name}.jsonl", rows)

    evidence_to_chunks: dict[str, list[str]] = defaultdict(list)
    for chunk in layer["semantic_chunks"]:
        for evidence_id in chunk.get("atomic_evidence_ids") or []:
            evidence_to_chunks[evidence_id].append(chunk["chunk_id"])
    links = [{"schema_version": "structured_knowledge.v2", "atomic_evidence_id": row.get("evidence_id"), "legacy_layer": True, "chunk_ids": evidence_to_chunks.get(str(row.get("evidence_id")), []), "source_id": row.get("source_id"), "section_id": row.get("section_id")} for row in legacy]
    write_jsonl(STAGING / "atomic_evidence_links.jsonl", links)

    chunk_rows = layer["semantic_chunks"]
    loaded_paths = {str(row.get("source_path") or "").casefold() for row in documents}
    missing_docs = {str(row.get("document_id")) for row in legacy if row.get("document_id")} - {str(row.get("document_id")) for row in documents}
    unloaded_sources = [row for row in registry.values() if str(row.get("source_path") or "").casefold() not in loaded_paths]
    queue: list[dict] = []
    for doc in documents:
        if doc.get("parse_status") not in {"parsed", "empty"}:
            queue.append({"type": "PARSE_REQUIRED", "status": "OPEN", "document_id": doc.get("document_id"), "source_path": doc.get("source_path"), "reason": doc.get("parse_status")})
        if doc.get("file_type") == ".pdf" and doc.get("parse_status") in {"needs_ocr", "read_error"}:
            queue.append({"type": "OCR_REQUIRED", "status": "OPEN", "document_id": doc.get("document_id"), "source_path": doc.get("source_path")})
        if (doc.get("metadata_quality") or {}).get("review_status") != "AUTO":
            queue.append({"type": "METADATA_REVIEW", "status": "OPEN", "document_id": doc.get("document_id"), "source_path": doc.get("source_path")})
    for chunk in chunk_rows:
        if chunk.get("index_status") == "QUARANTINED":
            queue.append({"type": "CHUNK_REPAIR", "status": "OPEN", "chunk_id": chunk.get("chunk_id"), "source_id": chunk.get("source_id"), "reason": chunk.get("quality_reasons")})
        if chunk.get("duplicate_of"):
            queue.append({"type": "DUPLICATE_REVIEW", "status": "OPEN", "chunk_id": chunk.get("chunk_id"), "duplicate_of": chunk.get("duplicate_of"), "source_id": chunk.get("source_id")})
    for did in sorted(missing_docs):
        queue.append({"type": "SOURCE_VERSION_REVIEW", "status": "OPEN", "document_id": did, "reason": "Legacy evidence has no current Document V2 object in the permitted input"})
    for source in unloaded_sources:
        queue.append({"type": "SOURCE_VERSION_REVIEW", "status": "OPEN", "source_id": source.get("source_id"), "source_path": source.get("source_path"), "reason": "Source registry path was not readable in this run and was not reparsed"})
    write_jsonl(STAGING / "governance_queue.jsonl", queue)

    type_counts = Counter(str(row.get("file_type") or "<none>") for row in documents)
    quarantined = sum(row.get("index_status") == "QUARANTINED" for row in chunk_rows)
    duplicate = sum(bool(row.get("duplicate_of")) for row in chunk_rows)
    table_chunks = [row for row in chunk_rows if row.get("table_id")]
    metrics = {"schema_version": "knowledge_os_v2.phase_a.metrics", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "input_boundary": {"document_intelligence_v2": str(SOURCE), "source_root": "[LOCAL_PATH_REDACTED]", "legacy_evidence_preserved": True, "external_root_readable": False}, "documents": {"count": len(documents), "file_types": dict(type_counts), "parse_status": dict(Counter(str(row.get("parse_status") or "<none>") for row in documents))}, "sections": {"count": len(sections), "with_path": sum(bool(row.get("heading_path") or row.get("heading")) for row in sections), "path_rate": ratio(sum(bool(row.get("heading_path") or row.get("heading")) for row in sections), len(sections))}, "semantic_chunks": {"count": len(chunk_rows), "quarantined": quarantined, "quarantine_rate": ratio(quarantined, len(chunk_rows)), "exact_duplicates_marked": duplicate, "duplicate_rate": ratio(duplicate, len(chunk_rows)), "average_chars": round(sum(int(row.get("char_count") or 0) for row in chunk_rows) / len(chunk_rows), 2) if chunk_rows else 0, "table_chunks": len(table_chunks), "table_context_rate": ratio(sum("表头：" in str(row.get("raw_text")) and "行：" in str(row.get("raw_text")) for row in table_chunks), len(table_chunks))}, "metadata": {"strong_fact_fields": ["source_id", "source_version", "source_hash", "document_type", "effective_status"], "inferred_fields": ["organization", "project", "year", "specialty", "business_domain"], "inferred_verified": False}, "links": {"legacy_evidence_count": len(legacy), "legacy_evidence_with_chunk": sum(bool(row.get("chunk_ids")) for row in links), "legacy_document_ids_without_document_v2": len(missing_docs), "source_registry_paths_not_loaded": len(unloaded_sources)}, "governance_queue": {"count": len(queue), "by_type": dict(Counter(str(row.get("type")) for row in queue))}, "gates": {"legacy_layer_preserved": True, "v2_index_isolated": True, "knowledge_node_root_bound": bool(layer["knowledge_node_bindings"]), "retrieval_runtime_enabled": False, "formal_port_8000_touched": False}}
    (EVAL / "structure" / "metrics.json").parent.mkdir(parents=True, exist_ok=True)
    (EVAL / "structure" / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    report = f"""# Knowledge Structure V2 Report\n\n- Captured: {metrics['captured_at']}\n- Scope: T00-T05, staging only\n- Documents: {len(documents)}; Sections: {len(sections)}; Semantic chunks: {len(chunk_rows)}\n- Quarantined chunks: {quarantined} ({metrics['semantic_chunks']['quarantine_rate'] or 0:.2%})\n- Exact duplicates marked for review: {duplicate} ({metrics['semantic_chunks']['duplicate_rate'] or 0:.2%})\n- Table chunks with table header and row context: {metrics['semantic_chunks']['table_context_rate'] or 0:.2%}\n- Legacy evidence preserved: {len(legacy)} records; no legacy record was deleted\n- Knowledge node binding: root `design-management` inherited from the existing framework file and linked to Document/Section/Semantic Chunk records\n\n## Gate result\n\nThe V2 Structured Knowledge Layer is built as an isolated staging artifact. Runtime retrieval remains disabled and `index_v1_frozen` remains untouched. This is not a claim that the entire enterprise corpus is complete: this run reparsed the readable `[LOCAL_PATH_REDACTED]; the external `[LOCAL_PATH_REDACTED]�公司技术部` root was not readable, and its registered paths are explicitly queued for source/version review.\n\n## Open governance work\n\nSee `data/shadow/knowledge_v2_staging/governance_queue.jsonl` for PARSE_REQUIRED, OCR_REQUIRED, METADATA_REVIEW, CHUNK_REPAIR, DUPLICATE_REVIEW, and SOURCE_VERSION_REVIEW items.\n"""
    (ROOT / "docs" / "KNOWLEDGE_STRUCTURE_V2_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"documents": len(documents), "sections": len(sections), "chunks": len(chunk_rows), "quarantined": quarantined, "duplicates": duplicate, "queue": len(queue), "staging": str(STAGING), "report": str(ROOT / 'docs' / 'KNOWLEDGE_STRUCTURE_V2_REPORT.md')}, ensure_ascii=False, indent=2))
    return 0


def source_paths(root: Path) -> list[Path]:
    excluded = {".agents", ".ai-growth", ".claude", ".claudian", ".copilot", "copilot", ".obsidian", ".opencode", ".rag", ".git"}
    paths: list[Path] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories[:] = [name for name in directories if name.lower() not in excluded]
        for name in files:
            path = Path(current) / name
            if path.suffix.lower() in SUPPORTED_EXTENSIONS and not name.startswith("~$"):
                paths.append(path)
    return sorted(paths, key=lambda item: str(item).casefold())


if __name__ == "__main__":
    raise SystemExit(main())
