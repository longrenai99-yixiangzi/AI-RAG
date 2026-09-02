from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.aggregate_ba010_fact_shadow import (
    OPTIMIZED_TRACE,
    OUTPUT,
    REPORT,
    SOURCE_RECORDS,
    STAGING,
    TARGET_FILE_NAME,
    TARGET_SHEET,
    choose_authoritative_document,
    extract_table_block,
    numeric_value,
    read_jsonl,
    source_record_for,
)


CONFIRMED_REPORT = PROJECT_ROOT / "docs" / "BA010_CONFIRMED_FACT_AGGREGATION_REPORT.md"


def enriched_rows(previous: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = previous.get("source_rows", [])
    headers = previous.get("header", {}).get("values", [])
    if "利润" not in headers:
        raise ValueError("价值创造 Sheet 未找到利润字段")
    profit_index = headers.index("利润")
    result_rows: list[dict[str, Any]] = []
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    unresolved: list[dict[str, Any]] = []
    total_increase = 0
    total_not_increased = 0
    for row in rows:
        values = list(row.get("values") or [])
        raw = values[profit_index] if profit_index < len(values) else ""
        parsed, parse_status = numeric_value(raw)
        if parsed is None:
            increase: bool | None = None
            classification = "UNRESOLVED_PROFIT"
            unresolved.append(
                {
                    "row_number": row["row_number"],
                    "professional": row["professional"],
                    "raw_profit": raw,
                    "reason": parse_status,
                    "evidence_id": row.get("evidence_id"),
                }
            )
        elif parsed > 0:
            increase = True
            classification = "INCREASE_BENEFIT"
            total_increase += 1
        else:
            increase = False
            classification = "NOT_INCREASE_BENEFIT"
            total_not_increased += 1
        enriched = {
            **row,
            "profit_raw": raw,
            "profit_numeric": parsed,
            "profit_parse_status": parse_status,
            "increase_benefit": increase,
            "business_rule": "利润 > 0",
            "classification": classification,
        }
        result_rows.append(enriched)
        group = groups.setdefault(
            row["professional"],
            {
                "group_by_value": row["professional"],
                "total_count": 0,
                "increase_benefit_count": 0,
                "not_increased_count": 0,
                "unresolved_profit_count": 0,
                "increase_benefit_rows": [],
                "not_increased_rows": [],
                "unresolved_profit_rows": [],
                "evidence_ids": [],
            },
        )
        group["total_count"] += 1
        if increase is True:
            group["increase_benefit_count"] += 1
            group["increase_benefit_rows"].append(row["row_number"])
        elif increase is False:
            group["not_increased_count"] += 1
            group["not_increased_rows"].append(row["row_number"])
        else:
            group["unresolved_profit_count"] += 1
            group["unresolved_profit_rows"].append(row["row_number"])
        if row.get("evidence_id") and row["evidence_id"] not in group["evidence_ids"]:
            group["evidence_ids"].append(row["evidence_id"])
    return result_rows, {
        "groups": list(groups.values()),
        "total_valid_rows": len(rows),
        "increase_benefit_total_count": total_increase,
        "not_increased_total_count": total_not_increased,
        "unresolved_profit_total_count": len(unresolved),
        "unresolved_profit_rows": unresolved,
    }


def render_report(result: dict[str, Any]) -> str:
    summary = result["count_result"]
    lines = [
        "# BA-010 Confirmed Fact Aggregation Report",
        "",
        "> TASK-016E-2A.2：基于业务负责人确认的“利润 > 0”口径，对 BA-010 执行 Shadow 确定性聚合。",
        "> 不调用 LLM，不修改原始 Excel、Retriever、Evidence Selection、Answer Engine、8000 服务或正式 Qdrant。",
        "",
        "## 1. 已确认业务规则",
        "",
        "```yaml",
        "benefit_semantics: 增加效益",
        "mapped_field: 利润",
        "operator: '>'",
        "threshold: 0",
        "business_rule_source: business_owner_confirmation",
        "```",
        "",
        "缺失值、`/`、文本或无法解析的利润值不视为 0；它们单独归入“利润未判定”。",
        "",
        "## 2. 目标范围",
        "",
        f"- Workbook：`{result['target_document']}`",
        f"- Sheet：`{result['target_sheet']}`",
        f"- 权威路径：`{result['authoritative_source_path']}`",
        f"- Evidence IDs：`{result['evidence_ids']}`",
        "- 未使用其他 Sheet 的“效益”字段，也未使用其他项目案例。",
        "",
        "## 3. 总体统计",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| 总有效条目数 | {summary['total_valid_rows']} |",
        f"| 增加效益条目数（利润 > 0） | {summary['increase_benefit_total_count']} |",
        f"| 确定未增加效益条目数（利润 <= 0） | {summary['not_increased_total_count']} |",
        f"| 利润未判定条目数 | {summary['unresolved_profit_total_count']} |",
        "",
        "## 4. 按专业/原始分组统计",
        "",
        "| 专业/原始分组值 | 专业总条数 | 增加效益条数 | 确定未增加效益 | 利润未判定 | 增加效益源行号 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for group in summary["groups"]:
        lines.append(
            f"| {group['group_by_value']} | {group['total_count']} | {group['increase_benefit_count']} | {group['not_increased_count']} | {group['unresolved_profit_count']} | {', '.join(map(str, group['increase_benefit_rows'])) or '-'} |"
        )
    lines += [
        "",
        "## 5. 未判定利润行",
        "",
        "| 行号 | 分组 | 原始利润值 | 原因 | Evidence ID |",
        "|---:|---|---|---|---|",
    ]
    for row in summary["unresolved_profit_rows"]:
        lines.append(f"| {row['row_number']} | {row['professional']} | `{row['raw_profit']}` | {row['reason']} | {row.get('evidence_id') or '-'} |")
    if not summary["unresolved_profit_rows"]:
        lines.append("| - | - | - | 无 | - |")
    lines += [
        "",
        "## 6. Provenance",
        "",
        "- 每一条源行均保留 workbook、sheet、row_number、values、source_location、source_id 和 evidence_id。",
        "- 增加效益判断只读取 `利润` 单元格，未读取或替代为“涉及金额”“收入”“效益”。",
        "- 参与计算的原始行号保存在 `evaluation/fact_aggregation/BA-010.json` 的 `source_rows` 和各分组字段中。",
        "",
        "## 7. 聚合状态",
        "",
        f"- aggregation_status：`{result['aggregation_status']}`",
        "- 由于存在利润空值/占位符未判定行，当前状态为 `PARTIAL_AGGREGATION`；这不是计算失败，而是对缺失业务数据的保守标记。",
        "- 如业务负责人进一步确认空利润按 0 处理，才可在后续任务中重新定义未增加效益统计；本次不自行推断。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
    rows, summary = enriched_rows(previous)
    result = {
        **previous,
        "benefit_semantics": "增加效益",
        "mapped_field": "利润",
        "operator": ">",
        "threshold": 0,
        "business_rule_source": "business_owner_confirmation",
        "source_rows": rows,
        "groups": summary["groups"],
        "filtered_rows": summary["total_valid_rows"],
        "count_result": summary,
        "aggregation_status": "AGGREGATED" if summary["unresolved_profit_total_count"] == 0 else "PARTIAL_AGGREGATION",
        "aggregation_notes": [
            "业务负责人已确认：增加效益 = 利润 > 0。",
            "利润空值/占位符/无法解析值不当作 0，单独列为未判定。",
            "不使用涉及金额、其他 Sheet 的效益、收入或其他项目案例替代利润字段。",
        ],
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    CONFIRMED_REPORT.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.resolve()), "report": str(CONFIRMED_REPORT.resolve()), "status": result["aggregation_status"], "total_valid_rows": summary["total_valid_rows"], "increase_benefit": summary["increase_benefit_total_count"], "not_increased": summary["not_increased_total_count"], "unresolved_profit": summary["unresolved_profit_total_count"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
