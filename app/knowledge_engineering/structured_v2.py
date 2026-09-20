from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from typing import Any, Iterable


SCHEMA_VERSION = "structured_knowledge.v2"
MIN_CHARS = 40
TARGET_CHARS = 600
MAX_CHARS = 900


def stable_id(kind: str, *parts: object) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "|".join([SCHEMA_VERSION, kind, *(str(part) for part in parts)])))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def section_number(title: str) -> str | None:
    match = re.match(r"^\s*((?:第[一二三四五六七八九十百千万\d]+[章节]|\d+(?:\.\d+){0,8}))", title or "")
    return match.group(1) if match else None


def infer_knowledge_type(text: str) -> str:
    rules = (
        ("表格", ("表", "工作表：")), ("职责", ("职责", "负责", "责任")),
        ("流程", ("流程", "步骤", "程序")), ("清单", ("清单", "检查项")),
        ("风险", ("风险", "隐患")), ("措施", ("措施", "应当", "应")),
        ("指标", ("指标", "率", "数量", "金额")), ("案例", ("案例", "复盘", "经验总结")),
        ("制度", ("制度", "规定", "办法", "细则")), ("模板", ("模板", "范本")),
        ("定义", ("是指", "定义")),
    )
    return next((kind for kind, terms in rules if any(term in text for term in terms)), "其他")


def chunk_units(units: Iterable[str], *, target: int = TARGET_CHARS, maximum: int = MAX_CHARS) -> list[str]:
    """Keep each parsed paragraph/list unit intact; length balances but never cuts a unit."""
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for unit in (item.strip() for item in units):
        if not unit:
            continue
        projected = current_size + len(unit) + (1 if current else 0)
        if current and projected > target and current_size >= MIN_CHARS:
            chunks.append("\n".join(current))
            current, current_size = [], 0
        current.append(unit)
        current_size += len(unit) + (1 if current_size else 0)
        if current_size >= maximum:
            chunks.append("\n".join(current))
            current, current_size = [], 0
    if current:
        chunks.append("\n".join(current))
    return chunks


def quality_for(raw_text: str, *, has_context: bool, is_table: bool = False) -> tuple[int, list[str]]:
    reasons: list[str] = []
    compact = normalize_text(raw_text)
    score = 100
    if len(compact) < MIN_CHARS:
        score -= 45; reasons.append("TOO_SHORT")
    if not has_context:
        score -= 25; reasons.append("MISSING_SECTION_CONTEXT")
    if re.fullmatch(r"[\d.、:：;；()（）\-—]+", compact or " "):
        score -= 55; reasons.append("NUMBERING_ONLY")
    if is_table and ("表头：" not in raw_text or "行：" not in raw_text):
        score -= 35; reasons.append("TABLE_CONTEXT_MISSING")
    return max(score, 0), reasons


def retrieval_text(*, domain: str | None, document_title: str, section_path: str, raw_text: str, project: Any = None, organization: Any = None, specialty: Any = None) -> str:
    values = (("知识域", domain), ("组织", organization), ("项目", project), ("专业", specialty), ("文档", document_title), ("章节", section_path), ("正文", raw_text))
    return "\n\n".join(f"[{label}]\n{value}" for label, value in values if value not in (None, "", []))


def exact_duplicates(chunks: list[dict[str, Any]]) -> None:
    first_by_text: dict[str, str] = {}
    for chunk in chunks:
        key = normalize_text(str(chunk["raw_text"]))
        if not key:
            continue
        first = first_by_text.setdefault(key, str(chunk["chunk_id"]))
        if first != chunk["chunk_id"]:
            chunk["duplicate_of"] = first
            chunk["quality_reasons"].append("EXACT_DUPLICATE")
            chunk["chunk_quality_score"] = max(0, int(chunk["chunk_quality_score"]) - 20)


def build_structured_layer(documents: list[dict[str, Any]], sections: list[dict[str, Any]], paragraphs: list[dict[str, Any]], tables: list[dict[str, Any]], table_rows: list[dict[str, Any]], atomic_evidence: list[dict[str, Any]], source_registry: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build staging-only V2 records from the existing document structure; legacy evidence remains unchanged."""
    docs_by_id = {str(row["document_id"]): row for row in documents}
    sections_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    paragraphs_by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tables_by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence_by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sections: sections_by_doc[str(row["document_id"])].append(row)
    for row in paragraphs: paragraphs_by_section[str(row.get("section_id") or "")].append(row)
    for row in tables: tables_by_section[str(row.get("section_id") or "")].append(row)
    for row in table_rows: rows_by_table[str(row.get("table_id") or "")].append(row)
    for row in atomic_evidence:
        if row.get("section_id"): evidence_by_section[str(row["section_id"])].append(row)

    sources: list[dict[str, Any]] = []
    staged_docs: list[dict[str, Any]] = []
    staged_sections: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for document_id, doc in docs_by_id.items():
        path = str(doc.get("source_path") or "")
        registered = source_registry.get(path.casefold())
        source_id = str((registered or {}).get("source_id") or stable_id("source", path))
        source_version = str((registered or {}).get("current_hash") or doc.get("content_hash") or "")
        profile = doc.get("document_profile") or {}
        domain = profile.get("business_domain", {}).get("value") or "设计管理"
        metadata = {"strong_fact": {"source_id": source_id, "source_version": source_version, "source_hash": str(doc.get("content_hash") or ""), "document_type": profile.get("document_type", {}).get("value"), "effective_status": (registered or {}).get("body_status") or "UNVERIFIED"}, "inferred": {key: profile.get(key, {}) for key in ("organization", "project", "year", "specialty", "business_domain")}}
        if source_id not in seen_sources:
            seen_sources.add(source_id)
            sources.append({"schema_version": SCHEMA_VERSION, "source_id": source_id, "source_version": source_version, "source_hash": str(doc.get("content_hash") or ""), "title": doc.get("file_name"), "file_path": path, "file_type": doc.get("file_type"), "status": (registered or {}).get("index_status") or "STAGING_ONLY", "parse_status": doc.get("parse_status"), "effective_status": (registered or {}).get("body_status") or "UNVERIFIED"})
        staged_docs.append({"schema_version": SCHEMA_VERSION, "document_id": document_id, "source_id": source_id, "source_version": source_version, "source_path": path, "source_hash": doc.get("content_hash"), "title": doc.get("structure", {}).get("title") or doc.get("file_name"), "file_name": doc.get("file_name"), "file_type": doc.get("file_type"), "parse_status": doc.get("parse_status"), "document_type": profile.get("document_type", {}).get("value"), "knowledge_domain": domain, "knowledge_nodes": ["design-management"], "effective_status": metadata["strong_fact"]["effective_status"], "metadata": metadata})
        bindings.append({"schema_version": SCHEMA_VERSION, "object_type": "DOCUMENT", "object_id": document_id, "knowledge_node_id": "design-management", "status": "BOUND", "method": "EXISTING_FRAMEWORK_ROOT", "evidence": "[LOCAL_PATH_REDACTED]"})
        for section in sorted(sections_by_doc[document_id], key=lambda row: int(row.get("section_order") or 0)):
            section_id = str(section["section_id"])
            path_value = str(section.get("heading_path") or section.get("heading") or "")
            title = str(section.get("heading") or "")
            staged_sections.append({"schema_version": SCHEMA_VERSION, "section_id": section_id, "document_id": document_id, "section_title": title, "section_level": int(section.get("depth") or 0) + 1, "section_number": section_number(title), "parent_section_id": section.get("parent_section_id"), "section_path": path_value, "page_start": (section.get("location_start") or {}).get("page"), "page_end": (section.get("location_end") or {}).get("page")})
            bindings.append({"schema_version": SCHEMA_VERSION, "object_type": "SECTION", "object_id": section_id, "knowledge_node_id": "design-management", "status": "BOUND", "method": "INHERITED_FROM_DOCUMENT", "evidence": document_id})
            units = [str(row.get("text") or "") for row in sorted(paragraphs_by_section[section_id], key=lambda row: (int(row.get("order") or 0), str(row.get("paragraph_id") or "")))]
            for index, raw in enumerate(chunk_units(units), start=1):
                _append_chunk(chunks, bindings, doc, source_id, source_version, section, path_value, raw, index, evidence_by_section[section_id], is_table=False)
            for table in tables_by_section[section_id]:
                header = " | ".join(str(item) for item in table.get("header") or [])
                table_name = str(table.get("table_title") or table.get("title") or table.get("table_id") or "表格")
                for row in rows_by_table[str(table.get("table_id") or "")]:
                    values = " | ".join(str(item.get("value") or "") for item in row.get("cells") or [])
                    raw = f"表名：{table_name}\n表头：{header}\n行：{values}"
                    _append_chunk(chunks, bindings, doc, source_id, source_version, section, path_value, raw, int(row.get("row_number") or 0), evidence_by_section[section_id], is_table=True, table_id=str(table.get("table_id") or ""))
    exact_duplicates(chunks)
    for chunk in chunks: chunk["index_status"] = "QUARANTINED" if int(chunk["chunk_quality_score"]) < 70 else "STAGING_CANDIDATE"
    return {"sources": sources, "documents": staged_docs, "sections": staged_sections, "semantic_chunks": chunks, "knowledge_node_bindings": bindings}


def _append_chunk(chunks: list[dict[str, Any]], bindings: list[dict[str, Any]], doc: dict[str, Any], source_id: str, source_version: str, section: dict[str, Any], section_path: str, raw_text: str, ordinal: int, evidence: list[dict[str, Any]], *, is_table: bool, table_id: str = "") -> None:
    score, reasons = quality_for(raw_text, has_context=bool(section_path), is_table=is_table)
    document_id, section_id = str(doc["document_id"]), str(section["section_id"])
    chunk_id = stable_id("semantic-chunk", document_id, section_id, table_id or "paragraph", ordinal, hashlib.sha256(raw_text.encode("utf-8")).hexdigest())
    normalized = normalize_text(raw_text)
    evidence_ids = [str(item.get("evidence_id")) for item in evidence if normalize_text(str(item.get("text") or "")) and normalize_text(str(item.get("text") or "")) in normalized]
    profile = doc.get("document_profile") or {}
    domain = profile.get("business_domain", {}).get("value") or "设计管理"
    token_count = len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", raw_text))
    chunks.append({"schema_version": SCHEMA_VERSION, "chunk_id": chunk_id, "source_id": source_id, "source_version": source_version, "document_id": document_id, "section_id": section_id, "knowledge_domain": domain, "knowledge_nodes": ["design-management"], "section_path": section_path, "knowledge_type": {"value": infer_knowledge_type(raw_text), "classification": "RULE_INFERRED", "verified": False}, "raw_text": raw_text, "retrieval_text": retrieval_text(domain=domain, document_title=str(doc.get("structure", {}).get("title") or doc.get("file_name") or ""), section_path=section_path, raw_text=raw_text, project=profile.get("project", {}).get("value"), organization=profile.get("organization", {}).get("value"), specialty=profile.get("specialty", {}).get("value")), "parent_chunk_id": None, "atomic_evidence_ids": evidence_ids, "char_count": len(raw_text), "token_count": token_count, "structure_quality": {"score": score, "reasons": reasons}, "metadata_quality": doc.get("metadata_quality"), "chunk_quality_score": score, "quality_reasons": reasons, "table_id": table_id or None})
    bindings.append({"schema_version": SCHEMA_VERSION, "object_type": "SEMANTIC_CHUNK", "object_id": chunk_id, "knowledge_node_id": "design-management", "status": "BOUND", "method": "INHERITED_FROM_DOCUMENT", "evidence": document_id})
