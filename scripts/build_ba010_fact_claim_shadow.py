from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FACT_PATH = PROJECT_ROOT / "evaluation" / "fact_aggregation" / "BA-010.json"
RECONCILIATION_REPORT = PROJECT_ROOT / "docs" / "BA010_PROFIT_COUNT_RECONCILIATION.md"
OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "fact_answers"
OUTPUT = OUTPUT_DIR / "BA-010.json"
REPORT = PROJECT_ROOT / "docs" / "FACT_CLAIM_CITATION_SHADOW_REPORT.md"


def load_facts() -> dict[str, Any]:
    facts = json.loads(FACT_PATH.read_text(encoding="utf-8"))
    reconciliation = RECONCILIATION_REPORT.read_text(encoding="utf-8")
    if "37_CONFIRMED" not in reconciliation:
        raise ValueError("E-2A.3 reconciliation is not 37_CONFIRMED")
    if facts.get("mapped_field") != "利润" or facts.get("operator") != ">" or facts.get("threshold") != 0:
        raise ValueError("Confirmed benefit rule is not 利润 > 0")
    return facts


def row_locations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "row_number": row["row_number"],
            "source_location": row["source_location"],
            "evidence_id": row.get("evidence_id"),
        }
        for row in rows
    ]


def claim(
    *,
    claim_id: str,
    claim_type: str,
    text: str,
    value: Any,
    unit: str,
    group: str | None,
    operation: str,
    rows: list[dict[str, Any]],
    facts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "claim_type": claim_type,
        "text": text,
        "value": value,
        "unit": unit,
        "group": group,
        "operation": operation,
        "business_rule": {
            "benefit_semantics": facts["benefit_semantics"],
            "mapped_field": facts["mapped_field"],
            "operator": facts["operator"],
            "threshold": facts["threshold"],
            "source": facts["business_rule_source"],
        },
        "evidence_ids": sorted({row.get("evidence_id") for row in rows if row.get("evidence_id")}),
        "source_rows": [row["row_number"] for row in rows],
        "source_locations": row_locations(rows),
    }


def build_claims(facts: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(facts["source_rows"])
    groups = facts["count_result"]["groups"]
    total = facts["count_result"]["total_valid_rows"]
    benefit_total = facts["count_result"]["increase_benefit_total_count"]
    unresolved_total = facts["count_result"]["unresolved_profit_total_count"]
    claims = [
        claim(
            claim_id="C1",
            claim_type="TOTAL_COUNT",
            text=f"星谷科创中心设计价值创造清单共有{total}条有效明细。",
            value=total,
            unit="条",
            group=None,
            operation="COUNT(valid_detail_rows)",
            rows=rows,
            facts=facts,
        )
    ]
    next_id = 2
    for group in groups:
        group_rows = [row for row in rows if row["professional"] == group["group_by_value"]]
        claims.append(
            claim(
                claim_id=f"C{next_id}",
                claim_type="GROUP_COUNT",
                text=f"{group['group_by_value']}共{group['total_count']}条，其中利润大于0的增加效益条目为{group['increase_benefit_count']}条。",
                value={
                    "total_count": group["total_count"],
                    "increase_benefit_count": group["increase_benefit_count"],
                    "not_increased_count": group["not_increased_count"],
                    "unresolved_profit_count": group["unresolved_profit_count"],
                },
                unit="条",
                group=group["group_by_value"],
                operation="GROUP_BY(专业类别)+COUNT+COUNT(profit>0)",
                rows=group_rows,
                facts=facts,
            )
        )
        next_id += 1
    benefit_rows = [row for row in rows if row.get("increase_benefit") is True]
    claims.append(
        claim(
            claim_id=f"C{next_id}",
            claim_type="BENEFIT_COUNT",
            text=f"按已确认业务口径“增加效益 = 利润 > 0”，有效明细中共有{benefit_total}条增加效益记录。",
            value=benefit_total,
            unit="条",
            group=None,
            operation="FILTER(利润>0)+COUNT",
            rows=benefit_rows,
            facts=facts,
        )
    )
    next_id += 1
    unresolved_rows = [row for row in rows if row.get("increase_benefit") is None]
    claims.append(
        claim(
            claim_id=f"C{next_id}",
            claim_type="DATA_QUALITY_NOTE",
            text=f"有{unresolved_total}条有效明细的利润字段为空或未判定；这些记录不能直接解释为没有效益。",
            value=unresolved_total,
            unit="条",
            group=None,
            operation="COUNT(unresolved_profit)",
            rows=unresolved_rows,
            facts=facts,
        )
    )
    return claims


def validate_claims(facts: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    valid_rows = {row["row_number"] for row in facts["source_rows"]}
    benefit_rows = {row["row_number"] for row in facts["source_rows"] if row.get("increase_benefit") is True}
    unresolved_rows = {row["row_number"] for row in facts["source_rows"] if row.get("increase_benefit") is None}
    total = facts["count_result"]["total_valid_rows"]
    benefit_total = facts["count_result"]["increase_benefit_total_count"]
    if sum(group["total_count"] for group in facts["count_result"]["groups"]) != total:
        errors.append("group totals do not equal total_valid_rows")
    if sum(group["increase_benefit_count"] for group in facts["count_result"]["groups"]) != benefit_total:
        errors.append("group benefit totals do not equal increase_benefit_total_count")
    for item in claims:
        rows = set(item["source_rows"])
        if len(rows) != len(item["source_rows"]):
            errors.append(f"{item['claim_id']} contains duplicate source rows")
        if not rows.issubset(valid_rows):
            errors.append(f"{item['claim_id']} contains row outside valid detail rows")
        if 88 in rows:
            errors.append(f"{item['claim_id']} includes excluded summary row 88")
        if len(rows) != int(item["value"] if item["claim_type"] in {"TOTAL_COUNT", "BENEFIT_COUNT", "DATA_QUALITY_NOTE"} else item["value"]["total_count"]):
            errors.append(f"{item['claim_id']} source row count does not equal claim count")
        if item["claim_type"] == "BENEFIT_COUNT" and rows != benefit_rows:
            errors.append("benefit claim source rows do not equal profit-positive rows")
        if item["claim_type"] == "DATA_QUALITY_NOTE":
            if rows != unresolved_rows:
                errors.append("data quality claim source rows do not equal unresolved profit rows")
            if ("没有效益" in item["text"] or "无效益" in item["text"]) and not any(
                marker in item["text"] for marker in ("不能直接解释", "不代表", "不得据此", "未判定")
            ):
                errors.append("data quality claim incorrectly describes unresolved rows as no benefit")
    return {"valid": not errors, "status": "VALID" if not errors else "FACT_CLAIM_INVALID", "errors": errors}


def validate_citations(facts: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    allowed_evidence = set(facts.get("evidence_ids", []))
    valid_rows = {row["row_number"] for row in facts["source_rows"]}
    for item in claims:
        if not item["evidence_ids"]:
            errors.append(f"{item['claim_id']} has no evidence_id")
        if not set(item["evidence_ids"]).issubset(allowed_evidence):
            errors.append(f"{item['claim_id']} references unknown evidence_id")
        if not set(item["source_rows"]).issubset(valid_rows):
            errors.append(f"{item['claim_id']} references invalid source row")
        if len(item["source_locations"]) != len(item["source_rows"]):
            errors.append(f"{item['claim_id']} source location count mismatch")
        for location in item["source_locations"]:
            if not location.get("source_location", {}).get("row_number"):
                errors.append(f"{item['claim_id']} has missing row provenance")
    return {"valid": not errors, "status": "VALID" if not errors else "CITATION_INVALID", "errors": errors}


def render_answer(facts: dict[str, Any], claims: list[dict[str, Any]]) -> str:
    groups = facts["count_result"]["groups"]
    total = facts["count_result"]["total_valid_rows"]
    benefit = facts["count_result"]["increase_benefit_total_count"]
    unresolved = facts["count_result"]["unresolved_profit_total_count"]
    lines = [
        "### 结论",
        "",
        f"星谷科创中心设计价值创造清单共有 **{total} 条有效明细**。按业务负责人确认口径“增加效益 = 利润 > 0”，其中有 **{benefit} 条增加效益记录**。",
        "",
        "### 专业/原始分组统计",
        "",
        "| 专业/原始分组 | 总条数 | 其中增加效益条数（利润 > 0） |",
        "|---|---:|---:|",
    ]
    for group in groups:
        lines.append(f"| {group['group_by_value']} | {group['total_count']} | {group['increase_benefit_count']} |")
    lines += [
        "",
        "### 口径说明",
        "",
        "- 增加效益字段：`利润`；判断规则：`利润 > 0`。",
        f"- 有效明细中利润为空或未判定的记录：**{unresolved} 条**。这些记录不能直接解释为没有效益。",
        "- 第 88 行是公式汇总行，不属于有效明细，未计入上述统计。",
    ]
    return "\n".join(lines)


def render_report(result: dict[str, Any]) -> str:
    validation = result["validation_result"]
    citation = result["citation_result"]
    lines = [
        "# Fact Claim Citation Shadow Report",
        "",
        "> TASK-016E-2B：将已确认的 BA-010 Structured Fact Result 转换为确定性 Claims、Citation 和最终回答。",
        "> 本任务不调用 LLM，不接入正式 Answer Engine，不修改正式 Retriever、Evidence Selection 或正式 Qdrant。",
        "",
        "## 1. FactAggregationResult",
        "",
        f"- query_id：`{result['fact_aggregation']['query_id']}`",
        f"- target_project：`{result['fact_aggregation'].get('target_project')}`",
        f"- target_document：`{result['fact_aggregation']['target_document']}`",
        f"- target_sheet：`{result['fact_aggregation']['target_sheet']}`",
        f"- business_rule：`{json.dumps(result['fact_aggregation']['business_rule'], ensure_ascii=False)}`",
        f"- total_rows：`{result['fact_aggregation']['total_rows']}`",
        f"- increase_effect_count：`{result['fact_aggregation']['increase_effect_count']}`",
        f"- undetermined_profit_count：`{result['fact_aggregation']['undetermined_profit_count']}`",
        f"- aggregation_status：`{result['fact_aggregation']['aggregation_status']}`",
        f"- reconciliation_status：`{result['fact_aggregation']['reconciliation_status']}`",
        f"- evidence_ids：`{result['fact_aggregation']['evidence_ids']}`",
        "",
        "## 2. Claims",
        "",
        "| Claim ID | 类型 | 分组 | 数值 | 单位 | Source Rows | Evidence IDs |",
        "|---|---|---|---:|---|---:|---|",
    ]
    for item in result["claims"]:
        value = item["value"] if isinstance(item["value"], (int, float)) else item["value"].get("total_count", "-")
        lines.append(f"| {item['claim_id']} | {item['claim_type']} | {item.get('group') or '-'} | {value} | {item['unit']} | {len(item['source_rows'])} | {', '.join(item['evidence_ids'])} |")
    lines += [
        "",
        "### Claim 文本",
        "",
    ]
    lines.extend(f"- **{item['claim_id']}**：{item['text']}" for item in result["claims"])
    lines += [
        "",
        "## 3. Validator",
        "",
        f"- Fact Claim Validator：`{validation['status']}`",
        f"- Citation Validator：`{citation['status']}`",
        f"- Fact Claim errors：`{validation['errors'] or '无'}`",
        f"- Citation errors：`{citation['errors'] or '无'}`",
        "- 第 88 行是否进入 Claim：否。",
        "- 利润未判定记录是否被描述为无效益：否。",
        "",
        "## 4. Final Answer",
        "",
        result["final_answer"],
        "",
        "## 5. Citation / Provenance",
        "",
        "每个 Claim 的 `source_rows`、`source_locations` 和 `evidence_ids` 均保存在 `evaluation/fact_answers/BA-010.json`；统计 Claim 不只引用整个 Workbook。",
        "",
        "## 6. 边界",
        "",
        "- LLM 未参与统计或语言改写。",
        "- 未将利润空值自动当成 0。",
        "- 未执行 SUM，不输出总金额。",
        "- 未接入正式 Answer Engine。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    facts = load_facts()
    rows = list(facts["source_rows"])
    source_locations = [
        {
            "row_number": row["row_number"],
            "source_location": row["source_location"],
            "evidence_id": row.get("evidence_id"),
        }
        for row in rows
    ]
    final_facts = {
        "query_id": "BA-010",
        "target_project": facts.get("target_project", "星谷科创中心"),
        "target_document": facts["target_document"],
        "target_sheet": facts["target_sheet"],
        "business_rule": {
            "benefit_semantics": facts["benefit_semantics"],
            "mapped_field": facts["mapped_field"],
            "operator": facts["operator"],
            "threshold": facts["threshold"],
            "source": facts["business_rule_source"],
        },
        "total_rows": facts["count_result"]["total_valid_rows"],
        "groups": facts["count_result"]["groups"],
        "increase_effect_count": facts["count_result"]["increase_benefit_total_count"],
        "undetermined_profit_count": facts["count_result"]["unresolved_profit_total_count"],
        "source_rows": [row["row_number"] for row in rows],
        "source_locations": source_locations,
        "evidence_ids": facts["evidence_ids"],
        "aggregation_status": facts["aggregation_status"],
        "reconciliation_status": "37_CONFIRMED",
    }
    claims = build_claims(facts)
    validation = validate_claims(facts, claims)
    citation = validate_citations(facts, claims)
    result = {
        "fact_aggregation": final_facts,
        "claims": claims,
        "validation_result": validation,
        "citation_result": citation,
        "final_answer": render_answer(facts, claims),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.resolve()), "report": str(REPORT.resolve()), "fact_claim_status": validation["status"], "citation_status": citation["status"], "claims": len(claims)}, ensure_ascii=False, indent=2))
    return 0 if validation["valid"] and citation["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
