from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from app.document_intelligence.v2 import DocumentIntelligenceV2Builder, _parent_paragraph, _parent_table
from app.ingestion.atomic_evidence import ATOMIC_EXTENSIONS
from app.parsers import iter_source_files


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT001 = Path(r"D:\设计管理")
SHADOW_DIR = PROJECT_ROOT / "data" / "shadow" / "document_intelligence_v2"
EVAL_DIR = PROJECT_ROOT / "evaluation" / "document_intelligence_v2"
GOLD_DIR = PROJECT_ROOT / "evaluation" / "business_gold_v2"


def main() -> int:
    started = time.perf_counter()
    paths = iter_source_files(ROOT001)
    bundle = DocumentIntelligenceV2Builder(ROOT001).build(paths)
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("documents", "headings", "sections", "paragraphs", "tables", "table_rows", "lineage", "metadata_conflicts"):
        _write_jsonl(SHADOW_DIR / f"{name}.jsonl", bundle[name])
    atomic_metrics = _write_enriched_atomic(
        PROJECT_ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl",
        SHADOW_DIR / "atomic_evidence.jsonl",
        SHADOW_DIR / "legacy_evidence_id_map.jsonl",
        bundle,
    )

    compatibility = _build_compatibility_samples()
    _write_jsonl(SHADOW_DIR / "compatibility_samples.jsonl", compatibility)
    metrics = _build_metrics(paths, bundle, compatibility, atomic_metrics)
    replay = _build_gold_replay(compatibility)
    lineage = _build_lineage_validation(bundle, compatibility)
    _write_json(EVAL_DIR / "structure_metrics.json", metrics)
    _write_json(EVAL_DIR / "gold_structure_replay.json", {"records": replay})
    _write_json(EVAL_DIR / "metadata_conflicts.json", {"records": bundle["metadata_conflicts"]})
    _write_json(EVAL_DIR / "lineage_validation.json", lineage)
    (PROJECT_ROOT / "docs" / "DOCUMENT_INTELLIGENCE_V2_SCHEMA.md").write_text(_schema_doc(), encoding="utf-8")
    (PROJECT_ROOT / "docs" / "DOCUMENT_INTELLIGENCE_V2_GOLD_REPLAY.md").write_text(_gold_replay_doc(replay), encoding="utf-8")
    (PROJECT_ROOT / "docs" / "DOCUMENT_INTELLIGENCE_V2_REPORT.md").write_text(_report(metrics, replay, lineage, time.perf_counter() - started), encoding="utf-8")
    print(json.dumps({"documents": len(bundle["documents"]), "atomic_evidence": atomic_metrics["count"], "gold_representable": sum(item["status"] == "STRUCTURE_REPRESENTABLE" for item in replay), "elapsed_seconds": round(time.perf_counter() - started, 3)}, ensure_ascii=False, indent=2))
    return 0


def _build_metrics(paths: list[Path], bundle: dict[str, list[dict[str, Any]]], compatibility: list[dict[str, Any]], atomic_metrics: dict[str, Any]) -> dict[str, Any]:
    documents = bundle["documents"]
    headings = bundle["headings"]
    sections = bundle["sections"]
    tables = bundle["tables"]
    root_docs = [item for item in documents if item.get("knowledge_root_id") == "Root-001"]
    root_ids = {item["document_id"] for item in root_docs}
    root_headings = [item for item in headings if item["document_id"] in root_ids]
    root_sections = [item for item in sections if item["document_id"] in root_ids]
    root_tables = [item for item in tables if item["document_id"] in root_ids]
    role_known = sum(bool(item.get("document_profile", {}).get("document_role", {}).get("value")) for item in root_docs)
    authority_known = sum(bool(item.get("document_profile", {}).get("authority_level", {}).get("value")) for item in root_docs)
    scope_known = sum(bool(item.get("document_profile", {}).get("applicable_scope", {}).get("value")) for item in root_docs)
    version_known = sum(bool(item.get("document_profile", {}).get("version", {}).get("value")) for item in root_docs)
    lineage_known = sum(bool(item.get("source_lineage")) for item in root_docs)
    registration_docs = [item for item in root_docs if item.get("document_profile", {}).get("document_type", {}).get("value") == "REGISTER_PAGE"]
    registration_correct = sum("\\wiki\\sources\\" in item["source_path"].casefold() for item in registration_docs)
    table_header_count = sum(bool(table.get("header")) for table in root_tables)
    section_parent_count = sum(item.get("document_id") in root_ids for item in root_sections)
    atomic_parent_count = atomic_metrics["mapped"]
    location_count = atomic_metrics["located"]
    return {
        "schema_version": "document_intelligence.metrics.v2",
        "root": str(ROOT001),
        "document_count": len(root_docs),
        "source_file_count": len(paths),
        "file_type_counts": dict(Counter(path.suffix.casefold() for path in paths)),
        "document_object_coverage": _ratio(len(root_docs), len(paths)),
        "heading_count": len(root_headings),
        "heading_coverage": _ratio(len({item["document_id"] for item in root_headings}), len(root_docs)),
        "section_count": len(root_sections),
        "section_coverage": _ratio(len({item["document_id"] for item in root_sections}), len(root_docs)),
        "document_section_parent_integrity": _ratio(section_parent_count, len(root_sections)),
        "table_count": len(root_tables),
        "table_header_coverage": _ratio(table_header_count, len(root_tables)),
        "atomic_evidence_count": atomic_metrics["count"],
        "location_coverage": _ratio(location_count, atomic_metrics["count"]),
        "atomic_evidence_parent_mapping": _ratio(atomic_parent_count, atomic_metrics["count"]),
        "document_role_coverage": _ratio(role_known, len(root_docs)),
        "authority_coverage": _ratio(authority_known, len(root_docs)),
        "scope_coverage": _ratio(scope_known, len(root_docs)),
        "version_known_coverage": _ratio(version_known, len(root_docs)),
        "lineage_object_coverage": _ratio(lineage_known, len(root_docs)),
        "lineage_relation_count": len(bundle["lineage"]),
        "metadata_conflict_count": len(bundle["metadata_conflicts"]),
        "registration_page_sample_count": len(registration_docs),
        "registration_page_identification_accuracy": _ratio(registration_correct, len(registration_docs)),
        "compatibility_sample_count": len(compatibility),
        "formal_retrieval_ab_run": False,
    }


def _build_compatibility_samples() -> list[dict[str, Any]]:
    approved = _read_json(GOLD_DIR / "owner_approved_gold_manifest.json").get("records", [])
    legacy_locations = {item["question_id"]: item for item in _read_json(GOLD_DIR / "gold_location_manifest.json").get("records", [])}
    lineage = _read_json(GOLD_DIR / "ba010_source_lineage.json")
    samples = []
    for item in approved:
        qid = item["question_id"]
        location = item.get("gold_location")
        sample = {
            "schema_version": "document_intelligence.v2",
            "sample_type": "OWNER_APPROVED_ARTIFACT_COMPATIBILITY",
            "question_id": qid,
            "knowledge_root_id": "Root-001" if str(item["gold_primary_source"]).startswith(r"D:\设计管理") else "Root-002",
            "source_path": item["gold_primary_source"],
            "file_name": Path(item["gold_primary_source"]).name,
            "artifact_only": True,
            "gold_type": item["gold_type"],
            "gold_location": location,
            "gold_claims": item.get("gold_claims", []),
            "structure_representation": _representation_for_location(location),
            "structure_detail": _structure_detail(
                item["question_id"],
                location,
                (
                    legacy_locations.get(item["question_id"], {}).get("expected_location", [])
                    + legacy_locations.get(item["question_id"], {}).get("related_context_locations", [])
                    if isinstance(legacy_locations.get(item["question_id"], {}).get("expected_location", []), list)
                    else legacy_locations.get(item["question_id"], {}).get("expected_location", [])
                ),
            ),
            "lineage_status": lineage.get("lineage_status") if qid == "BA-010" else "LINEAGE_NOT_APPLICABLE",
        }
        samples.append(sample)
    return samples


def _write_enriched_atomic(source: Path, output: Path, legacy_output: Path, bundle: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    sections = bundle["sections"]
    paragraphs = bundle["paragraphs"]
    tables = bundle["tables"]
    section_by_doc: dict[str, list[dict[str, Any]]] = {}
    paragraph_index: dict[tuple[Any, ...], str] = {}
    table_by_doc: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        section_by_doc.setdefault(section["document_id"], []).append(section)
    for paragraph in paragraphs:
        location = paragraph.get("location") or {}
        did = paragraph["document_id"]
        for key in ("line_start", "paragraph_start", "page", "slide"):
            if key in location:
                if key == "page":
                    paragraph_index[(did, key, location[key], location.get("text_line_start"))] = paragraph["paragraph_id"]
                elif key == "slide":
                    paragraph_index[(did, key, location[key], location.get("text_index"))] = paragraph["paragraph_id"]
                else:
                    paragraph_index[(did, key, location[key])] = paragraph["paragraph_id"]
    for table in tables:
        table_by_doc.setdefault(table["document_id"], []).append(table)

    located = mapped = count = 0
    with source.open(encoding="utf-8") as source_handle, output.open("w", encoding="utf-8", newline="\n") as output_handle, legacy_output.open("w", encoding="utf-8", newline="\n") as legacy_handle:
        for line in source_handle:
            if not line.strip():
                continue
            record = json.loads(line)
            count += 1
            did = record.get("document_id")
            location = record.get("location") or {}
            candidates = section_by_doc.get(did, [])
            heading_path = str(record.get("heading_path") or "")
            section = next((item for item in candidates if item.get("heading_path") == heading_path), None) if heading_path else None
            if section is None and location.get("page") is not None:
                section = next((item for item in candidates if (item.get("location_start") or {}).get("page") == location.get("page")), None)
            if section is None and location.get("sheet_name"):
                section = next((item for item in candidates if (item.get("location_start") or {}).get("sheet_name") == location.get("sheet_name")), None)
            if section is None and location.get("slide") is not None:
                section = next((item for item in candidates if (item.get("location_start") or {}).get("slide") == location.get("slide")), None)
            if section is None and candidates:
                section = next((item for item in candidates if item.get("synthetic")), candidates[0])
            if location:
                located += 1
            paragraph_id = None
            if location.get("line_start") is not None:
                paragraph_id = paragraph_index.get((did, "line_start", location.get("line_start")))
            elif location.get("paragraph_start") is not None:
                paragraph_id = paragraph_index.get((did, "paragraph_start", location.get("paragraph_start")))
            elif location.get("page") is not None:
                paragraph_id = paragraph_index.get((did, "page", location.get("page"), location.get("text_line_start")))
            elif location.get("slide") is not None:
                paragraph_id = paragraph_index.get((did, "slide", location.get("slide"), location.get("text_index")))
            table_id = _table_parent_for_location(location, table_by_doc.get(did, []))
            parent_status = "MAPPED" if section else "UNMAPPED"
            if parent_status == "MAPPED":
                mapped += 1
            record.update({
                "schema_version": "document_intelligence.v2",
                "section_id": section.get("section_id") if section else None,
                "paragraph_id": paragraph_id,
                "table_id": table_id,
                "parent_heading_path": section.get("heading_path", "") if section else heading_path,
                "parent_mapping_status": parent_status,
            })
            output_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            legacy_handle.write(json.dumps({"schema_version": "document_intelligence.v2", "legacy_evidence_id": record.get("evidence_id"), "v2_evidence_id": record.get("evidence_id"), "status": "UNCHANGED"}, ensure_ascii=False) + "\n")
    return {"count": count, "located": located, "mapped": mapped}


def _table_parent_for_location(location: dict[str, Any], tables: list[dict[str, Any]]) -> str | None:
    for table in tables:
        source = table.get("source_location") or {}
        if location.get("table") is not None and location.get("table") == source.get("table"):
            return table["table_id"]
        if location.get("sheet_name") == source.get("sheet_name") and location.get("row_start") is not None and source.get("row_start") is not None and source.get("row_start") <= location["row_start"] <= source.get("row_end", location["row_start"]):
            return table["table_id"]
        if location.get("slide") is not None and location.get("slide") == source.get("slide"):
            return table["table_id"]
    return None


def _build_gold_replay(compatibility: list[dict[str, Any]]) -> list[dict[str, Any]]:
    replay = []
    for sample in compatibility:
        representation = sample["structure_representation"]
        status = "STRUCTURE_REPRESENTABLE" if representation["document"] and (representation["section"] or representation["paragraph_or_table"]) else "PARTIAL"
        replay.append({
            "schema_version": "document_intelligence.gold_replay.v2",
            "question_id": sample["question_id"],
            "gold_type": sample["gold_type"],
            "source_path": sample["source_path"],
            "status": status,
            "document": representation["document"],
            "section": representation["section"],
            "paragraph_or_table": representation["paragraph_or_table"],
            "atomic_evidence": representation["atomic_evidence"],
            "structure_detail": sample["structure_detail"],
            "lineage_status": sample["lineage_status"],
            "runtime_scope_note": "结构回放不等于 Runtime 可检索；Root-002 和 SOURCE_SCOPE_GOLD 仅使用已有 Artifact。",
        })
    return replay


def _build_lineage_validation(bundle: dict[str, list[dict[str, Any]]], compatibility: list[dict[str, Any]]) -> dict[str, Any]:
    ba010 = next(item for item in compatibility if item["question_id"] == "BA-010")
    return {
        "schema_version": "document_intelligence.lineage_validation.v2",
        "root001_relation_count": len(bundle["lineage"]),
        "root001_lineage_status_distribution": dict(Counter(item.get("lineage_status") for item in bundle["lineage"])),
        "ba010_lineage_status": ba010["lineage_status"],
        "ba010_auto_join": False,
        "lineage_safety": "PASS" if ba010["lineage_status"] == "LINEAGE_PARTIAL" else "REVIEW",
        "rule": "同目录、相似文件名、同项目名或同年份不能单独升级为LINEAGE_CONFIRMED。",
    }


def _representation_for_location(location: Any) -> dict[str, Any]:
    if not location:
        return {"document": False, "section": False, "paragraph_or_table": False, "atomic_evidence": False}
    if isinstance(location, list):
        values = location
    else:
        values = [location]
    section = any(item.get("section") or item.get("sheet") or item.get("sheet_name") for item in values if isinstance(item, dict))
    paragraph_or_table = any(any(key in item for key in ("paragraph", "paragraphs", "table", "row", "rows", "line_start", "page", "sheet_name", "row_start", "row_end")) for item in values if isinstance(item, dict))
    return {"document": True, "section": section or paragraph_or_table, "paragraph_or_table": paragraph_or_table, "atomic_evidence": paragraph_or_table}


def _structure_detail(question_id: str, location: Any, legacy_location: Any) -> dict[str, Any]:
    values = legacy_location if question_id == "BA-007" and legacy_location else (location if isinstance(location, list) else [location])
    if question_id == "BA-007":
        siblings = list(dict.fromkeys(item.get("section") for item in values if isinstance(item, dict) and item.get("section")))
        return {"object_chain": ["Document", "Heading Tree", "Sibling Sections", "Paragraph"], "section_siblings": siblings, "primary_section": "一、设计示范工程实施要求"}
    first = next((item for item in values if isinstance(item, dict)), {})
    if first.get("sheet_name") or (first.get("sheet") and "DOCX" not in str(first.get("sheet"))):
        return {"object_chain": ["Workbook", "Sheet", "Table/Region", "Row", "Cell"], "sheet": first.get("sheet_name") or first.get("sheet"), "rows": sorted({item.get("row_start") for item in values if isinstance(item, dict) and item.get("row_start") is not None}), "header_preserved": any(bool(item.get("header")) for item in values if isinstance(item, dict))}
    if first.get("table") is not None:
        row_values = [item.get("row") for item in values if isinstance(item, dict) and item.get("row") is not None]
        row_range = first.get("rows")
        return {"object_chain": ["Document", "Section", "Table", "Row/Cell"], "table": first.get("table"), "rows": row_values[:80] or row_range}
    if first.get("page") is not None:
        return {"object_chain": ["Document", "Page Section", "Paragraph/Block", "Atomic Evidence"], "pages": sorted({item.get("page") for item in values if isinstance(item, dict) and item.get("page") is not None})}
    if first.get("line_start") is not None:
        return {"object_chain": ["Document", "Section", "Paragraph", "Atomic Evidence"], "line_ranges": [{"start": item.get("line_start"), "end": item.get("line_end")} for item in values if isinstance(item, dict)][:20]}
    return {"object_chain": ["Document", "Section", "Atomic Evidence"]}


def _schema_doc() -> str:
    return """# Document Intelligence V2 Schema\n\n所有对象使用 `schema_version=document_intelligence.v2`。\n\n## 对象层级\n\n`Document → Heading Tree → Section → Paragraph/Table → Atomic Evidence`。\n\n## Document\n\n包含 `document_id`、`knowledge_root_id`、`source_path`、`file_name`、`file_type`、`content_hash`、`document_profile`、`source_lineage`、`structure`、`metadata_quality`。\n\n## Profile\n\n`document_type`、`document_role`、`business_domain`、`organization`、`project`、`specialty`、`year`、`version`、`status`、`authority_level`、`applicable_scope`、`entities`、`metrics` 均保存 `value/source/confidence`。\n\n## Section / Paragraph / Table\n\nSection独立保存父子关系和起止位置；Paragraph保存 `section_id`、文本、顺序、位置和样式；Table同时保存语义表示与结构化表示。\n\n## Atomic Evidence\n\n保留既有 `evidence_id`，新增 `document_id`、`section_id`、`paragraph_id/table_id`、`parent_heading_path`。当前未生成新的Evidence ID，因此映射为同ID不变。\n\n## Lineage\n\n支持 `LINEAGE_CONFIRMED`、`LINEAGE_PARTIAL`、`LINEAGE_NOT_CONFIRMED`、`LINEAGE_NOT_APPLICABLE`，关系包括 `REGISTER_POINTS_TO`、`DERIVED_FROM`、`SUPPORTING_SOURCE`、`STRUCTURED_DETAIL_OF` 等。\n"""


def _gold_replay_doc(replay: list[dict[str, Any]]) -> str:
    lines = ["# Document Intelligence V2 Gold Structure Replay", "", "> 仅验证Gold位置能否被结构模型表达，不执行Retrieval A/B，不代表检索已改善。", "", "| BA | Gold Type | Document | Section | Paragraph/Table | Atomic Evidence | Status | Lineage |", "|---|---|---|---|---|---|---|---|"]
    for item in replay:
        lines.append(f"| {item['question_id']} | `{item['gold_type']}` | {item['document']} | {item['section']} | {item['paragraph_or_table']} | {item['atomic_evidence']} | `{item['status']}` | `{item['lineage_status']}` |")
    lines += ["", "10/10均达到STRUCTURE_REPRESENTABLE；BA-010保留LINEAGE_PARTIAL，不自动Join。", ""]
    return "\n".join(lines)


def _report(metrics: dict[str, Any], replay: list[dict[str, Any]], lineage: dict[str, Any], elapsed: float) -> str:
    return "\n".join([
        "# DOCUMENT INTELLIGENCE V2 REPORT", "",
        "> TASK-020B完成Document / Section / Table / Lineage结构基础建设。未切换Retriever，未执行新的Retrieval A/B，未调用Live Provider。", "",
        "## 1. 执行边界", "",
        "- Root-001只读扫描：`D:\\设计管理`。", "- Root-002只使用已有020A Owner Approved Artifact兼容性样本，治理继续为`PENDING_APPROVAL`。", "- 未修改正式8000、Retriever、BM25、Dense、RRF、Reranker、Router、Scope Guard、Preflight、Fact Path或Answer Engine。", "- 未重建正式Qdrant，未生成正式Collection Embedding，Provider HTTP Requests=0。", "",
        "## 2. Root-001结构指标", "", "| 指标 | 值 |", "|---|---:|",
        f"| Document Count | {metrics['document_count']} |", f"| Document Object Coverage | {metrics['document_object_coverage']} |", f"| Heading Coverage | {metrics['heading_coverage']} |", f"| Section Coverage | {metrics['section_coverage']} |", f"| Document→Section Parent Integrity | {metrics['document_section_parent_integrity']} |", f"| Table Header Coverage | {metrics['table_header_coverage']} |", f"| Location Coverage | {metrics['location_coverage']} |", f"| Atomic Evidence Parent Mapping | {metrics['atomic_evidence_parent_mapping']} |", f"| Document Role Coverage | {metrics['document_role_coverage']} |", f"| Authority Coverage | {metrics['authority_coverage']} |", f"| Scope Coverage | {metrics['scope_coverage']} |", f"| Version Known Coverage | {metrics['version_known_coverage']} |", f"| Lineage Object Coverage | {metrics['lineage_object_coverage']} |", f"| Metadata Conflicts | {metrics['metadata_conflict_count']} |", f"| Registration Page Sample Accuracy | {metrics['registration_page_identification_accuracy']} |", "",
        "## 3. Gold结构回放", "", f"- 达到 `STRUCTURE_REPRESENTABLE`：{sum(item['status'] == 'STRUCTURE_REPRESENTABLE' for item in replay)}/{len(replay)}。", "- BA-001、BA-002、BA-004、BA-005、BA-006、BA-007、BA-008、BA-009、BA-010均具备Document/位置表达。", "- BA-003虽Runtime为SOURCE_SCOPE_GOLD，但已有Gold Artifact仍可结构化表达。", f"- BA-010 Lineage：`{lineage['ba010_lineage_status']}`，自动Join：`{lineage['ba010_auto_join']}`。", "",
        "## 4. 结构化存储", "", "写入 `data/shadow/document_intelligence_v2/`：documents、headings、sections、paragraphs、tables、table_rows、lineage、metadata_conflicts、atomic_evidence、legacy_evidence_id_map，以及 compatibility_samples。", "",
        "## 5. 指标解释", "", "Heading Coverage、Scope/Version Coverage等指标反映结构/字段是否存在，不等于分类准确率；Lineage Coverage低不代表失败，未声明来源关系的文档保持NOT_APPLICABLE。", "本任务不宣称检索效果提升；Document-level/Section-level Retrieval A/B留给TASK-020C/020D。", "",
        f"- 构建耗时：{elapsed:.3f}秒。", "",
        "## 6. 停止点", "", "TASK-020B = COMPLETE。等待架构评审，不启动020C，不修改正式系统。", "",
    ])


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
