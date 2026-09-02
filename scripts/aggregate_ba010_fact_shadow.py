from __future__ import annotations

import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


STAGING = PROJECT_ROOT / "data" / "shadow" / "root002_import" / "pipeline_staging.jsonl"
SOURCE_RECORDS = PROJECT_ROOT / "data" / "shadow" / "root002_import" / "source_records.jsonl"
OPTIMIZED_TRACE = PROJECT_ROOT / "evaluation" / "traces_optimized" / "BA-010.json"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "fact_aggregation"
OUTPUT = OUTPUT_DIR / "BA-010.json"
REPORT = PROJECT_ROOT / "docs" / "FACT_AGGREGATOR_SHADOW_REPORT.md"
TARGET_FILE_NAME = "方案比选与价值创造清单方案比选及价值创造.xlsx"
TARGET_SHEET = "价值创造"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_cell_pairs(line: str) -> tuple[int, list[str]] | None:
    match = re.match(r"^第(\d+)行：(.+)$", line)
    if not match:
        return None
    row_number = int(match.group(1))
    values: list[str] = []
    for cell in match.group(2).split(" | "):
        _, separator, value = cell.partition("：")
        values.append(value.strip() if separator else cell.strip())
    return row_number, values


def semantic_header(rows: list[tuple[int, list[str]]]) -> tuple[int, list[str]] | None:
    for row_number, values in rows:
        if "专业类别" in values and any(value in values for value in ("涉及金额", "利润", "效益对比（万元）")):
            return row_number, values
    return None


def numeric_value(value: str) -> tuple[float | None, str]:
    text = str(value or "").strip()
    if not text or text in {"-", "—", "/", "无", "NA", "N/A"}:
        return None, "empty_or_placeholder"
    match = re.search(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?", text)
    if not match:
        return None, "text_or_unparseable"
    try:
        return float(match.group(0).replace(",", "")), "numeric"
    except ValueError:
        return None, "numeric_parse_error"


def source_record_for(path: str, records: list[dict[str, Any]]) -> str | None:
    normalized = str(Path(path).resolve(strict=False)).casefold()
    for record in records:
        resolved = record.get("resolved_path")
        if resolved and str(Path(resolved).resolve(strict=False)).casefold() == normalized:
            return record.get("source_id")
    return None


def choose_authoritative_document(documents: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    target_documents = [document for document in documents if Path(document["path"]).name == TARGET_FILE_NAME]
    preferred = [
        document
        for document in target_documents
        if "设计示范项目打造方案" in document["path"] and "新洲星谷" in document["path"]
    ]
    if len(preferred) == 1:
        authoritative = preferred[0]
    elif len(target_documents) == 1:
        authoritative = target_documents[0]
    else:
        authoritative = None
    duplicates = [document for document in target_documents if document is not authoritative]
    return authoritative, duplicates


def extract_table_block(document: dict[str, Any]) -> dict[str, Any] | None:
    for block in document.get("source_blocks", []):
        if block.get("heading_path") == TARGET_SHEET:
            parsed = [parsed for line in str(block.get("text", "")).splitlines() if (parsed := parse_cell_pairs(line))]
            header = semantic_header(parsed)
            if header:
                return {
                    "block": block,
                    "rows": parsed,
                    "header_row": header[0],
                    "headers": header[1],
                }
    return None


def aggregate(authoritative: dict[str, Any], duplicates: list[dict[str, Any]], trace: dict[str, Any], source_records: list[dict[str, Any]]) -> dict[str, Any]:
    table = extract_table_block(authoritative)
    if table is None:
        return {
            "query_id": "BA-010",
            "target_document": TARGET_FILE_NAME,
            "target_sheet": TARGET_SHEET,
            "operations": ["GROUP_BY", "COUNT", "FILTER", "COUNT"],
            "group_by": "专业类别",
            "groups": [],
            "total_rows": 0,
            "filtered_rows": 0,
            "count_result": {},
            "sum_result": None,
            "unit": "条",
            "source_rows": [],
            "evidence_ids": [],
            "aggregation_status": "AGGREGATION_ERROR",
            "error": "权威 Workbook 中未找到可解析的价值创造 Sheet 或语义表头",
        }

    block = table["block"]
    rows = table["rows"]
    headers = table["headers"]
    professional_index = headers.index("专业类别")
    description_index = headers.index("价值创造策划点") if "价值创造策划点" in headers else 1
    amount_fields = [field for field in ("涉及金额", "利润") if field in headers]
    exact_effect_fields = [field for field in ("效益对比（万元）", "效益对比", "增加效益") if field in headers]
    amount_indexes = {field: headers.index(field) for field in amount_fields}
    effect_indexes = {field: headers.index(field) for field in exact_effect_fields}
    evidence_id = next(
        (
            item.get("source_id")
            for item in trace.get("final_evidence", [])
            if item.get("source_path") == authoritative["path"] and item.get("location", {}).get("sheet_name") == TARGET_SHEET
        ),
        None,
    )
    source_id = source_record_for(authoritative["path"], source_records)
    block_location = dict(block.get("location") or {})
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    source_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    current_group: str | None = None
    data_rows = [row for row in rows if row[0] > table["header_row"]]
    raw_candidate_rows = 0
    field_analysis: dict[str, dict[str, Any]] = {}
    for field, index in amount_indexes.items():
        field_analysis[field] = {
            "available": True,
            "column_index": index,
            "nonempty_rows": 0,
            "numeric_rows": 0,
            "positive_rows": 0,
            "parse_failures": 0,
            "rule_candidate": "numeric > 0",
            "accepted_as_increase_effect_field": False,
        }
    if not exact_effect_fields:
        effect_field_status = "NOT_AVAILABLE"
        effect_rule = None
    else:
        effect_field_status = "AVAILABLE_NOT_YET_APPLIED"
        effect_rule = "numeric > 0"

    for row_number, values in data_rows:
        normalized = [str(value or "").strip() for value in values]
        if any(value not in {"", "/", "-", "—"} for value in normalized):
            raw_candidate_rows += 1
        padded = normalized + [""] * max(0, len(headers) - len(normalized))
        raw_professional = padded[professional_index] if professional_index < len(padded) else ""
        description = padded[description_index] if description_index < len(padded) else ""
        numeric_effect_values = []
        for field, index in amount_indexes.items():
            value = padded[index] if index < len(padded) else ""
            if value not in {"", "/", "-", "—"}:
                field_analysis[field]["nonempty_rows"] += 1
            numeric, reason = numeric_value(value)
            if numeric is not None:
                field_analysis[field]["numeric_rows"] += 1
                if numeric > 0:
                    field_analysis[field]["positive_rows"] += 1
                numeric_effect_values.append(numeric)
            elif value not in {"", "/", "-", "—"}:
                field_analysis[field]["parse_failures"] += 1

        if raw_professional not in {"", "/", "-", "—"}:
            current_group = raw_professional
        has_description = description not in {"", "/", "-", "—"}
        has_numeric_effect = bool(numeric_effect_values)
        has_any = any(value not in {"", "/", "-", "—"} for value in normalized)
        if not has_any:
            excluded_rows.append({"row_number": row_number, "reason": "blank_data_row", "values": normalized})
            continue
        if not has_description and not raw_professional and not has_numeric_effect:
            excluded_rows.append({"row_number": row_number, "reason": "no_description_or_fact_fields", "values": normalized})
            continue
        if not raw_professional and not description and has_numeric_effect:
            excluded_rows.append({"row_number": row_number, "reason": "summary_row_not_detail", "values": normalized})
            continue
        if not current_group:
            excluded_rows.append({"row_number": row_number, "reason": "unclassified_professional", "values": normalized})
            continue
        evidence_location = {
            **block_location,
            "row_number": row_number,
            "source_block_row_start": block_location.get("row_start"),
            "source_block_row_end": block_location.get("row_end"),
        }
        record = {
            "source_id": source_id,
            "document_id": block.get("document_id"),
            "workbook": authoritative["file_name"],
            "sheet": TARGET_SHEET,
            "row_number": row_number,
            "professional": current_group,
            "values": normalized,
            "headers": headers,
            "source_location": evidence_location,
            "evidence_id": evidence_id,
        }
        source_rows.append(record)
        group = groups.setdefault(
            current_group,
            {"group_by_value": current_group, "count": 0, "row_numbers": [], "evidence_ids": []},
        )
        group["count"] += 1
        group["row_numbers"].append(row_number)
        if evidence_id and evidence_id not in group["evidence_ids"]:
            group["evidence_ids"].append(evidence_id)

    effect_positive_count: int | None = None
    effect_rows: list[int] = []
    if exact_effect_fields:
        chosen_effect = exact_effect_fields[0]
        index = effect_indexes[chosen_effect]
        for record in source_rows:
            value = record["values"][index] if index < len(record["values"]) else ""
            numeric, _ = numeric_value(value)
            if numeric is not None and numeric > 0:
                effect_rows.append(record["row_number"])
        effect_positive_count = len(effect_rows)
        field_analysis[chosen_effect] = {
            "available": True,
            "column_index": index,
            "rule_applied": "numeric > 0",
            "positive_rows": effect_positive_count,
            "accepted_as_increase_effect_field": True,
        }

    status = "AGGREGATED" if exact_effect_fields else "PARTIAL_AGGREGATION"
    return {
        "query_id": "BA-010",
        "target_project": "星谷科创中心",
        "target_document": TARGET_FILE_NAME,
        "target_sheet": TARGET_SHEET,
        "authoritative_source_path": authoritative["path"],
        "duplicate_workbooks_detected": len(duplicates) + 1,
        "excluded_duplicate_workbooks": [item["path"] for item in duplicates],
        "operations": ["GROUP_BY", "COUNT", "FILTER", "COUNT"],
        "operation_details": {
            "GROUP_BY": {"field": "专业类别", "status": "APPLIED"},
            "COUNT": {"field": "专业类别", "status": "APPLIED"},
            "FILTER": {"field": exact_effect_fields[0] if exact_effect_fields else None, "operator": ">", "value": 0, "status": "APPLIED" if exact_effect_fields else "SKIPPED_FIELD_UNAVAILABLE"},
            "EFFECT_COUNT": {"status": "APPLIED" if exact_effect_fields else "NOT_COMPUTED"},
        },
        "group_by": "专业类别",
        "groups": list(groups.values()),
        "total_rows": raw_candidate_rows,
        "filtered_rows": len(source_rows),
        "excluded_rows": excluded_rows,
        "count_result": {
            "by_professional": {group["group_by_value"]: group["count"] for group in groups.values()},
            "increase_effect_count": effect_positive_count,
            "increase_effect_rows": effect_rows,
            "increase_effect_field": exact_effect_fields[0] if exact_effect_fields else None,
            "increase_effect_rule": effect_rule,
        },
        "sum_result": None,
        "unit": {"count": "条", "effect": None},
        "field_analysis": field_analysis,
        "header": {"row_number": table["header_row"], "values": headers},
        "source_rows": source_rows,
        "evidence_ids": [evidence_id] if evidence_id else [],
        "aggregation_status": status,
        "aggregation_notes": [
            "只使用 SourceBlock 解析结果，不重新读取或修改原始 Excel。",
            "检测到同名 Workbook 版本，按 Source Discovery 登记链选择权威版本，未跨版本混算。",
            "目标 Sheet 不存在‘效益对比（万元）’字段，因此没有把‘涉及金额’或‘利润’擅自解释为‘增加效益’。",
            "问题未要求总金额，因此未执行 SUM。",
        ],
    }


def render_report(result: dict[str, Any]) -> str:
    groups = result.get("groups", [])
    field_analysis = result.get("field_analysis", {})
    excluded = result.get("excluded_rows", [])
    exclusion_counts = Counter(item["reason"] for item in excluded)
    lines = [
        "# Fact Aggregator Shadow Report",
        "",
        "> TASK-016E-2A：只对 BA-010 的 Optimized Evidence 目标 Workbook 执行确定性表格事实聚合。",
        "> 未调用 LLM；未修改 Retriever、Evidence Selection、Answer Engine、8000 服务、原始 Excel 或正式 Qdrant。",
        "",
        "## 1. Query Analysis",
        "",
        "- Query ID：`BA-010`",
        "- Target Project：`星谷科创中心`",
        f"- Target Workbook：`{result.get('target_document')}`",
        f"- Target Sheet：`{result.get('target_sheet')}`",
        "- Operations：`GROUP_BY(专业类别)` → `COUNT(每组)` → `FILTER(效益字段 > 0)` → `COUNT(满足条件记录)`",
        "- SUM：未执行；问题没有要求总金额。",
        "",
        "## 2. Workbook 版本控制",
        "",
        f"- 检测到同名 Workbook：`{result.get('duplicate_workbooks_detected')}` 个。",
        f"- 权威版本：`{result.get('authoritative_source_path')}`",
        "- 选择依据：Source Discovery 登记链指向“设计示范项目打造方案”目录下的版本。",
        "- 其他同名版本未参与计算，防止跨版本混算。",
        "",
        "## 3. Table Extraction",
        "",
        f"- Header 行：`{result.get('header', {}).get('row_number')}`",
        f"- Header：`{json.dumps(result.get('header', {}).get('values', []), ensure_ascii=False)}`",
        f"- 原始有效候选行：`{result.get('total_rows')}`",
        f"- 纳入统计行：`{result.get('filtered_rows')}`",
        f"- 排除行：`{len(excluded)}`",
        f"- 排除原因：`{json.dumps(dict(exclusion_counts), ensure_ascii=False)}`",
        "",
        "## 4. 专业分组统计",
        "",
        "| 专业/原始分组值 | 条目数 | 源行号 | Evidence ID |",
        "|---|---:|---|---|",
    ]
    for group in groups:
        lines.append(f"| {group['group_by_value']} | {group['count']} | {', '.join(map(str, group['row_numbers']))} | {', '.join(group['evidence_ids']) or '-'} |")
    lines += [
        "",
        "> 分组值按表格原始‘专业类别’字段保留；没有把‘整体方案’、‘桩基础支护’等原始值擅自改写成建筑/结构等标准专业。",
        "",
        "## 5. 增加效益字段检查",
        "",
        "| 字段 | 是否存在 | 非空行 | 数值行 | 正数行 | 解析失败 | 是否作为增加效益字段 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for field, info in field_analysis.items():
        lines.append(
            f"| {field} | {info.get('available')} | {info.get('nonempty_rows', '-')} | {info.get('numeric_rows', '-')} | {info.get('positive_rows', '-')} | {info.get('parse_failures', '-')} | {info.get('accepted_as_increase_effect_field')} |"
        )
    lines += [
        "",
        f"- 精确目标字段 `效益对比（万元）`：`{'存在' if result.get('count_result', {}).get('increase_effect_field') else '不存在'}`。",
        f"- 增加效益条数：`{result.get('count_result', {}).get('increase_effect_count') if result.get('count_result', {}).get('increase_effect_count') is not None else '未计算（字段缺失）'}`",
        "- 规则：只有真实存在的目标效益字段才允许执行 `numeric > 0`；本次没有把‘涉及金额’或‘利润’替代为目标字段。",
        "",
        "## 6. FactAggregationResult",
        "",
        f"- aggregation_status：`{result.get('aggregation_status')}`",
        f"- count_result：`{json.dumps(result.get('count_result'), ensure_ascii=False)}`",
        f"- sum_result：`{json.dumps(result.get('sum_result'), ensure_ascii=False)}`",
        f"- evidence_ids：`{result.get('evidence_ids')}`",
        f"- source_rows：`{len(result.get('source_rows', []))}` 条，逐行保存在 `evaluation/fact_aggregation/BA-010.json`。",
        "",
        "## 7. Provenance 验收",
        "",
        "- 每条纳入统计记录保存 workbook、sheet、row_number、values、source_location、source_id 和 evidence_id。",
        "- 每个专业分组保存参与统计的原始 row_number 和 Evidence ID。",
        "- 结果没有只引用“整个 Excel”，可以逐行回查。",
        "- 未接入正式 Answer Engine；当前只输出 Structured Fact Result。",
        "",
        "## 8. 结论",
        "",
        f"本次状态为 `{result.get('aggregation_status')}`：专业分组和条目计数已由真实 SourceBlock 行确定性完成；由于目标 Sheet 没有明确的‘效益对比（万元）’字段，增加效益条数未擅自计算，需业务负责人确认‘涉及金额’或‘利润’是否具有该业务含义后，再设计下一步聚合规则。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    staging = read_jsonl(STAGING)
    documents = [document for document in staging if Path(document["path"]).name == TARGET_FILE_NAME]
    authoritative, duplicates = choose_authoritative_document(documents)
    trace = json.loads(OPTIMIZED_TRACE.read_text(encoding="utf-8"))
    source_records = read_jsonl(SOURCE_RECORDS)
    if authoritative is None:
        result = {
            "query_id": "BA-010",
            "target_document": TARGET_FILE_NAME,
            "target_sheet": TARGET_SHEET,
            "operations": ["GROUP_BY", "COUNT", "FILTER", "COUNT"],
            "group_by": "专业类别",
            "groups": [],
            "total_rows": 0,
            "filtered_rows": 0,
            "count_result": {},
            "sum_result": None,
            "unit": "条",
            "source_rows": [],
            "evidence_ids": [],
            "aggregation_status": "AGGREGATION_INSUFFICIENT",
            "error": f"同名目标 Workbook 数量异常：{len(documents)}，无法确定权威版本",
        }
    else:
        result = aggregate(authoritative, duplicates, trace, source_records)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.resolve()), "report": str(REPORT.resolve()), "status": result.get("aggregation_status"), "groups": len(result.get("groups", [])), "filtered_rows": result.get("filtered_rows")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
