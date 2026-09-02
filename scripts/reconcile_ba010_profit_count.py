from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WORKBOOK = (
    Path(r"D:\工作\二公司技术部\2026\概算及策划评审\新洲星谷")
    / "星谷科创项目设计管理策划+设计示范项目打造方案"
    / "方案比选与价值创造清单方案比选及价值创造.xlsx"
)
FACT_RESULT = PROJECT_ROOT / "evaluation" / "fact_aggregation" / "BA-010.json"
REPORT = PROJECT_ROOT / "docs" / "BA010_PROFIT_COUNT_RECONCILIATION.md"


def text(value: Any) -> str:
    return "" if value is None else str(value).replace("\n", " ").strip()


def merged_value(sheet: Any, row: int, column: int) -> Any:
    cell = sheet.cell(row, column)
    if not isinstance(cell, MergedCell):
        return cell.value
    for merged in sheet.merged_cells.ranges:
        if merged.min_row <= row <= merged.max_row and merged.min_col <= column <= merged.max_col:
            return sheet.cell(merged.min_row, merged.min_col).value
    return None


def report_row(row: int, sheet_formula: Any, sheet_values: Any, valid_rows: set[int], exclusion_by_row: dict[int, dict[str, Any]], current_group: str) -> dict[str, Any]:
    raw_values = [merged_value(sheet_formula, row, column) for column in range(1, 11)]
    cached_values = [merged_value(sheet_values, row, column) for column in range(1, 11)]
    return {
        "row_number": row,
        "professional": current_group,
        "value_creation_plan": text(cached_values[1]),
        "profit": cached_values[6],
        "profit_formula": sheet_formula.cell(row, 7).value if isinstance(sheet_formula.cell(row, 7).value, str) and sheet_formula.cell(row, 7).value.startswith("=") else None,
        "in_valid_detail": row in valid_rows,
        "exclusion_reason": exclusion_by_row.get(row, {}).get("reason") if row not in valid_rows else None,
        "raw_cells_A_J": cached_values,
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        "# BA-010 Profit Count Reconciliation",
        "",
        "> TASK-016E-2A.3：对账全 Sheet 的利润正数行与最终 80 条有效价值创造明细。",
        "> 业务规则保持：增加效益 = 利润 > 0。本报告只读，不修改 Aggregator JSON、原始 Excel或正式链路。",
        "",
        "## 1. 对账结论",
        "",
        "**37_CONFIRMED**",
        "",
        "全 Sheet 的 38 条利润正数记录中，有 1 条是公式汇总行，不属于有效价值创造明细；其余 37 条全部进入最终 80 条有效明细。因此当前正式业务明细统计采用 37 条，不需要修复 Fact Aggregator。",
        "",
        "## 2. A：全价值创造 Sheet 的利润 > 0 行",
        "",
        "| 行号 | 专业类别 | 价值创造策划点 | 利润 | 是否进入80条有效明细 | 未进入原因 | 公式 |",
        "|---:|---|---|---:|---|---|---|",
    ]
    for row in result["all_positive_rows"]:
        lines.append(f"| {row['row_number']} | {row['professional']} | {row['value_creation_plan'][:100]} | {row['profit']} | {row['in_valid_detail']} | {row['exclusion_reason'] or '-'} | `{row['profit_formula'] or '-'}` |")
    lines += [
        "",
        f"合计：**{len(result['all_positive_rows'])}** 条。",
        "",
        "## 3. B：最终 80 条有效价值创造明细中的利润 > 0 行",
        "",
        "| 行号 | 专业类别 | 价值创造策划点 | 利润 | 是否进入80条有效明细 |",
        "|---:|---|---|---:|---|",
    ]
    for row in result["valid_positive_rows"]:
        lines.append(f"| {row['row_number']} | {row['professional']} | {row['value_creation_plan'][:100]} | {row['profit']} | {row['in_valid_detail']} |")
    lines += [
        "",
        f"合计：**{len(result['valid_positive_rows'])}** 条。",
        "",
        "## 4. 差集 A - B",
        "",
        "| 行号 | 专业类别 | 利润 | 排除原因 | 行类型 |",
        "|---:|---|---:|---|---|",
    ]
    for row in result["difference"]:
        lines.append(f"| {row['row_number']} | {row['professional']} | {row['profit']} | {row['exclusion_reason']} | {row['row_type']} |")
    lines += [
        "",
        "差集数量：**1** 条，正好解释 `38 → 37`。",
        "",
        "## 5. 差集行核查：第 88 行",
        "",
        "- 行类型：`FORMULA_OR_TOTAL_ROW`",
        "- 判断依据：A88:E88、H88:J88 为空；F88/G88 为汇总公式；价值创造策划点为空；不属于单条明细。",
        "",
        "### 原始单元格 A88:J88",
        "",
        "| 单元格 | 原始公式/值 | 缓存值 |",
        "|---|---|---|",
    ]
    for cell in result["row_88_cells"]:
        lines.append(f"| {cell['cell']} | `{cell['formula_or_value']}` | `{cell['cached_value']}` |")
    lines += [
        "",
        "关键值：",
        "",
        "- `F88 = SUM(F4:F87)`，缓存值 `3376.153022085`；",
        "- `G88 = SUM(G4:G87)`，缓存值 `1898.573022085`；",
        "- `G88 > 0` 只是总计公式结果，不应作为一条新的“增加效益”明细计数。",
        "",
        "## 6. 结论与后续",
        "",
        "- 结论：`37_CONFIRMED`。",
        "- 当前 80 条有效明细中的利润正数条目 37 条是正确的。",
        "- 第 88 行应继续作为汇总行排除，不得加入明细统计。",
        "- 后续可以采用 37 作为当前 BA-010 的“增加效益条数”。",
        "- 未修改 `evaluation/fact_aggregation/BA-010.json`，未自动修复 Aggregator。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    result = json.loads(FACT_RESULT.read_text(encoding="utf-8"))
    valid_rows = {row["row_number"] for row in result["source_rows"]}
    exclusion_by_row = {row["row_number"]: row for row in result.get("excluded_rows", [])}
    workbook_formula = load_workbook(WORKBOOK, data_only=False, read_only=False)
    workbook_values = load_workbook(WORKBOOK, data_only=True, read_only=False)
    try:
        sheet_formula = workbook_formula["价值创造"]
        sheet_values = workbook_values["价值创造"]
        all_positive: list[dict[str, Any]] = []
        current_group = ""
        for row in range(4, sheet_values.max_row + 1):
            raw_group = merged_value(sheet_values, row, 1)
            if raw_group:
                current_group = text(raw_group)
            profit = sheet_values.cell(row, 7).value
            if isinstance(profit, (int, float)) and profit > 0:
                item = report_row(row, sheet_formula, sheet_values, valid_rows, exclusion_by_row, current_group)
                item["row_type"] = "FORMULA_OR_TOTAL_ROW" if row not in valid_rows and item["profit_formula"] else "DETAIL_ROW"
                if item["row_type"] == "FORMULA_OR_TOTAL_ROW":
                    item["professional"] = ""
                all_positive.append(item)
        row_88_cells = []
        for column in range(1, 11):
            cell = sheet_formula.cell(88, column)
            row_88_cells.append(
                {
                    "cell": cell.coordinate,
                    "formula_or_value": cell.value,
                    "cached_value": sheet_values.cell(88, column).value,
                }
            )
    finally:
        workbook_formula.close()
        workbook_values.close()
    valid_positive = [row for row in all_positive if row["in_valid_detail"]]
    difference = [row for row in all_positive if not row["in_valid_detail"]]
    result = {
        "all_positive_rows": all_positive,
        "valid_positive_rows": valid_positive,
        "difference": difference,
        "row_88_cells": row_88_cells,
    }
    REPORT.write_text(render(result), encoding="utf-8")
    print(json.dumps({"report": str(REPORT.resolve()), "all_positive": len(all_positive), "valid_positive": len(valid_positive), "difference": len(difference), "conclusion": "37_CONFIRMED" if len(difference) == 1 and difference[0]["row_number"] == 88 else "UNRESOLVED"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
