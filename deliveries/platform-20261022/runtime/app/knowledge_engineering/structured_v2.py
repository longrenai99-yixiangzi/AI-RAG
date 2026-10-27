from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter, defaultdict
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
    """Keep parsed units intact and PDF page content together when it fits the limit."""
    grouped: list[str] = []
    page: list[str] | None = None
    for raw in units:
        unit = raw.strip()
        if not unit:
            continue
        if re.fullmatch(r"---\s*Page\s+\d+\s*---", unit, re.IGNORECASE):
            if page:
                grouped.append("\n".join(page))
            page = [unit]
        elif page is None:
            grouped.append(unit)
        else:
            page.append(unit)
    if page:
        grouped.append("\n".join(page))

    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for unit in grouped:
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
    if is_table and len(raw_text) > MAX_CHARS:
        score -= 35; reasons.append("TABLE_ROW_TOO_LONG")
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
        bindings.append({"schema_version": SCHEMA_VERSION, "object_type": "DOCUMENT", "object_id": document_id, "knowledge_node_id": "design-management", "status": "BOUND", "method": "EXISTING_FRAMEWORK_ROOT", "evidence": "D:\\example-vault\\00_AI系统\\设计管理知识体系.md"})
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
                if doc.get("file_type") == ".xlsx" and table.get("sheet_state", "visible") != "visible":
                    continue
                header = " | ".join(str(item) for item in table.get("header") or [])
                table_name = str(table.get("table_title") or table.get("title") or table.get("table_id") or "表格")
                structure_review = False
                if doc.get("file_type") == ".xlsx":
                    # shortcut: unresolved columns quarantine the parsed region; split or review its headers before retrieval.
                    for native_row in rows_by_table[str(table.get("table_id") or "")]:
                        if native_row.get("is_header"):
                            continue
                        native_cells = native_row.get("cells") or []
                        _, omitted = _xlsx_answer_cells(native_cells, table.get("header") or [])
                        if any(field["reason"] in {"UNNAMED_HEADER", "AMBIGUOUS_HEADER"} for field in omitted):
                            structure_review = True
                            break
                for row in rows_by_table[str(table.get("table_id") or "")]:
                    if row.get("is_header"):
                        continue
                    cells = row.get("cells") or []
                    excluded = []
                    row_header = header
                    if doc.get("file_type") == ".xlsx":
                        cells, excluded = _xlsx_answer_cells(cells, table.get("header") or [])
                        if not cells:
                            continue
                        row_header = " | ".join(str(cell["header"]) for cell in cells)
                    values = " | ".join(str(item.get("display_text", item["value"])) if item.get("value") is not None else "" for item in cells)
                    raw = f"表名：{table_name}\n表头：{row_header}\n行：{values}"
                    context = row.get("row_context") or []
                    if context:
                        raw += "\n行标识（原文）：" + " | ".join(f"{cell['cell_reference']}={cell.get('display_text',cell['value'])}" for cell in context if cell.get('value_status')=='NATIVE_VALUE' and (not cell.get('display_required') or cell.get('display_text')))
                    _append_chunk(chunks, bindings, doc, source_id, source_version, section, path_value, raw, int(row.get("record_number", row.get("row_number")) or 0), evidence_by_section[section_id], is_table=True, table_id=str(table.get("table_id") or ""), row_location=row.get("source_location") or {})
                    if doc.get("file_type") == ".xlsx":
                        chunks[-1].update(source_cells=cells, excluded_fields=excluded, row_kind="SUMMARY_CANDIDATE" if row.get("is_summary") else "DATA_CANDIDATE")
                        if table.get("context_id"):
                            chunks[-1].update(parent_chunk_id=table['context_id'], context_evidence_ids=row.get('context_evidence_ids') or [], row_context=context)
                        if table.get('source_table_id'):
                            chunks[-1].update(source_table_id=table['source_table_id'],source_table_row_id=row['source_table_row_id'],field_group_index=table['field_group_index'],field_group_count=table['field_group_count'],requires_column_scope=table['requires_column_scope'])
                        if any(cell.get('value_status')!='NATIVE_VALUE' or (cell.get('display_required') and not cell.get('display_text')) for cell in context):
                            chunks[-1]["quality_reasons"].append("ROW_CONTEXT_UNRESOLVED")
                            chunks[-1]["chunk_quality_score"] = 0
                            chunks[-1]["structure_quality"]["score"] = 0
                        if structure_review:
                            chunks[-1]["quality_reasons"].append("XLSX_STRUCTURE_REVIEW_REQUIRED")
                            chunks[-1]["chunk_quality_score"] = 0
                            chunks[-1]["structure_quality"]["score"] = 0
    exact_duplicates(chunks)
    for chunk in chunks: chunk["index_status"] = "QUARANTINED" if int(chunk["chunk_quality_score"]) < 70 else "STAGING_CANDIDATE"
    return {"sources": sources, "documents": staged_docs, "sections": staged_sections, "semantic_chunks": chunks, "knowledge_node_bindings": bindings}


def _xlsx_answer_cells(cells: list[dict[str, Any]], headers: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    counts = Counter(headers)
    selected, excluded = [], []
    for cell in cells:
        label = str(cell.get("header") or "")
        reason = None
        if not label or re.fullmatch(r"列\d+", label) or re.fullmatch(r"[\d.,%]+", label):
            reason = "UNNAMED_HEADER"
        elif counts[label] > 1:
            reason = "AMBIGUOUS_HEADER"
        elif any(term in label for term in ("身份证", "手机号", "联系电话")):
            reason = "PERSONAL_IDENTIFIER"
        elif cell.get("value_status") in {"FORMULA_CACHE_MISSING", "CELL_ERROR", "BODY_MERGE_CROSSES_FIELDS"}:
            reason = cell["value_status"]
        elif cell.get('display_required') and not cell.get('display_text'):
            reason = 'DISPLAY_FORMAT_REVIEW_REQUIRED'
        elif str(cell.get("formula") or "").startswith("=") and cell.get("cached_value") is None:
            reason = "FORMULA_CACHE_MISSING"
        elif str(cell.get("value") or "") in {"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#SPILL!", "#CALC!"}:
            reason = "CELL_ERROR"
        if reason:
            if cell.get("value") not in (None, ""):
                excluded.append({"column": cell.get("column"), "header": label, "reason": reason})
        elif cell.get("value") not in (None, ""):
            selected.append(cell)
    return selected, excluded


def _append_chunk(chunks: list[dict[str, Any]], bindings: list[dict[str, Any]], doc: dict[str, Any], source_id: str, source_version: str, section: dict[str, Any], section_path: str, raw_text: str, ordinal: int, evidence: list[dict[str, Any]], *, is_table: bool, table_id: str = "", row_location: dict[str, Any] | None = None) -> None:
    score, reasons = quality_for(raw_text, has_context=bool(section_path), is_table=is_table)
    document_id, section_id = str(doc["document_id"]), str(section["section_id"])
    chunk_id = stable_id("semantic-chunk", document_id, section_id, table_id or "paragraph", ordinal, hashlib.sha256(raw_text.encode("utf-8")).hexdigest())
    normalized = normalize_text(raw_text)
    row_location = row_location or {}
    row_key = next((key for key in ("row_start", "line_start", "row") if row_location.get(key) is not None), None)
    row_index = row_location.get(row_key) if row_key else None
    row_evidence = []
    if is_table and table_id and row_index is not None:
        for item in evidence:
            if item.get("table_id") != table_id:
                continue
            item_location = item.get("location") or {}
            if any(row_location.get(key) is not None and item_location.get(key) != row_location[key] for key in ("sheet_name", "table", "slide", "column_start", "column_end")):
                continue
            item_index = next((item_location.get(key) for key in ("row_start", "line_start", "row") if item_location.get(key) is not None), None)
            if item_index == row_index:
                row_evidence.append(item)
    matching_evidence = row_evidence or [item for item in evidence if normalize_text(str(item.get("text") or "")) and normalize_text(str(item.get("text") or "")) in normalized]
    evidence_ids = [str(item.get("evidence_id")) for item in matching_evidence]
    profile = doc.get("document_profile") or {}
    domain = profile.get("business_domain", {}).get("value") or "设计管理"
    token_count = len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", raw_text))
    chunks.append({"schema_version": SCHEMA_VERSION, "chunk_id": chunk_id, "source_id": source_id, "source_version": source_version, "document_id": document_id, "section_id": section_id, "knowledge_domain": domain, "knowledge_nodes": ["design-management"], "section_path": section_path, "knowledge_type": {"value": infer_knowledge_type(raw_text), "classification": "RULE_INFERRED", "verified": False}, "raw_text": raw_text, "retrieval_text": retrieval_text(domain=domain, document_title=str(doc.get("structure", {}).get("title") or doc.get("file_name") or ""), section_path=section_path, raw_text=raw_text, project=profile.get("project", {}).get("value"), organization=profile.get("organization", {}).get("value"), specialty=profile.get("specialty", {}).get("value")), "parent_chunk_id": None, "atomic_evidence_ids": evidence_ids, "char_count": len(raw_text), "token_count": token_count, "structure_quality": {"score": score, "reasons": reasons}, "metadata_quality": doc.get("metadata_quality"), "chunk_quality_score": score, "quality_reasons": reasons, "table_id": table_id or None})
    chunks[-1].update(file_name=doc.get("file_name"), source_path=doc.get("source_path"), source_location=row_location)
    bindings.append({"schema_version": SCHEMA_VERSION, "object_type": "SEMANTIC_CHUNK", "object_id": chunk_id, "knowledge_node_id": "design-management", "status": "BOUND", "method": "INHERITED_FROM_DOCUMENT", "evidence": document_id})
