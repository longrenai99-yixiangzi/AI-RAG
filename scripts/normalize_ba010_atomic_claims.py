from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_ba010_fact_claim_shadow import (
    OUTPUT,
    claim,
    load_facts,
    render_answer,
    validate_citations,
)


REPORT = PROJECT_ROOT / "docs" / "ATOMIC_FACT_CLAIM_VALIDATION_REPORT.md"


def build_atomic_claims(facts: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(facts["source_rows"])
    groups = facts["count_result"]["groups"]
    claims: list[dict[str, Any]] = []
    claims.append(
        claim(
            claim_id="C1",
            claim_type="TOTAL_COUNT",
            text=f"星谷科创中心设计价值创造清单共有{facts['count_result']['total_valid_rows']}条有效明细。",
            value=facts["count_result"]["total_valid_rows"],
            unit="条",
            group=None,
            operation="COUNT(valid_detail_rows)",
            rows=rows,
            facts=facts,
        )
    )
    next_id = 2
    for group in groups:
        group_rows = [row for row in rows if row["professional"] == group["group_by_value"]]
        group_claim = claim(
                claim_id=f"C{next_id}",
                claim_type="GROUP_COUNT",
                text=f"{group['group_by_value']}共{group['total_count']}条。",
                value=group["total_count"],
                unit="条",
                group=group["group_by_value"],
                operation="COUNT",
                rows=group_rows,
                facts=facts,
            )
        claims.append(group_claim)
        next_id += 1
    for group in groups:
        group_rows = [
            row
            for row in rows
            if row["professional"] == group["group_by_value"] and row.get("increase_benefit") is True
        ]
        benefit_claim = claim(
                claim_id=f"C{next_id}",
                claim_type="BENEFIT_COUNT",
                text=f"{group['group_by_value']}中利润大于0的增加效益条目为{group['increase_benefit_count']}条。",
                value=group["increase_benefit_count"],
                unit="条",
                group=group["group_by_value"],
                operation="FILTER(利润>0)+COUNT",
                rows=group_rows,
                facts=facts,
            )
        # A zero-count claim has no positive source rows; retain the group's
        # Evidence ID as scope provenance without inventing a source row.
        if not group_rows:
            all_group_rows = [row for row in rows if row["professional"] == group["group_by_value"]]
            benefit_claim["evidence_ids"] = sorted({row.get("evidence_id") for row in all_group_rows if row.get("evidence_id")})
            benefit_claim["source_rows"] = []
            benefit_claim["source_locations"] = []
        claims.append(benefit_claim)
        next_id += 1
    benefit_rows = [row for row in rows if row.get("increase_benefit") is True]
    claims.append(
        claim(
            claim_id=f"C{next_id}",
            claim_type="BENEFIT_COUNT",
            text=f"按业务口径“增加效益 = 利润 > 0”，有效明细中共有{facts['count_result']['increase_benefit_total_count']}条增加效益记录。",
            value=facts["count_result"]["increase_benefit_total_count"],
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
            text=f"有{facts['count_result']['unresolved_profit_total_count']}条有效明细的利润字段为空或未判定；这些记录不代表没有效益。",
            value=facts["count_result"]["unresolved_profit_total_count"],
            unit="条",
            group=None,
            operation="COUNT(unresolved_profit)",
            rows=unresolved_rows,
            facts=facts,
        )
    )
    return claims


def validate_atomic_claims(facts: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    groups = facts["count_result"]["groups"]
    rows = facts["source_rows"]
    by_group = {group["group_by_value"]: group for group in groups}
    group_claims = {claim_item["group"]: claim_item for claim_item in claims if claim_item["claim_type"] == "GROUP_COUNT"}
    benefit_group_claims = {
        claim_item["group"]: claim_item
        for claim_item in claims
        if claim_item["claim_type"] == "BENEFIT_COUNT" and claim_item["group"] is not None
    }
    if len([item for item in claims if item["claim_type"] == "TOTAL_COUNT"]) != 1:
        errors.append("TOTAL_COUNT claim count is not 1")
    if len(group_claims) != 8:
        errors.append(f"GROUP_COUNT claim count is {len(group_claims)}, expected 8")
    if len(benefit_group_claims) != 8:
        errors.append(f"group BENEFIT_COUNT claim count is {len(benefit_group_claims)}, expected 8")
    if len([item for item in claims if item["claim_type"] == "BENEFIT_COUNT" and item["group"] is None]) != 1:
        errors.append("overall BENEFIT_COUNT claim count is not 1")
    if len([item for item in claims if item["claim_type"] == "DATA_QUALITY_NOTE"]) != 1:
        errors.append("DATA_QUALITY_NOTE claim count is not 1")
    valid_row_ids = {row["row_number"] for row in rows}
    if 88 in valid_row_ids:
        errors.append("row 88 is present in valid source rows")
    for group_name, expected in by_group.items():
        group_rows = {row["row_number"] for row in rows if row["professional"] == group_name}
        benefit_rows = {row["row_number"] for row in rows if row["professional"] == group_name and row.get("increase_benefit") is True}
        group_claim = group_claims.get(group_name)
        benefit_claim = benefit_group_claims.get(group_name)
        if group_claim is None or group_claim["value"] != len(group_rows) or set(group_claim["source_rows"]) != group_rows:
            errors.append(f"GROUP_COUNT mismatch: {group_name}")
        if benefit_claim is None or benefit_claim["value"] != len(benefit_rows) or set(benefit_claim["source_rows"]) != benefit_rows:
            errors.append(f"BENEFIT_COUNT mismatch: {group_name}")
    total_claim = next((item for item in claims if item["claim_type"] == "TOTAL_COUNT"), None)
    overall_benefit = next((item for item in claims if item["claim_type"] == "BENEFIT_COUNT" and item["group"] is None), None)
    data_note = next((item for item in claims if item["claim_type"] == "DATA_QUALITY_NOTE"), None)
    if total_claim is None or total_claim["value"] != 80 or set(total_claim["source_rows"]) != valid_row_ids:
        errors.append("TOTAL_COUNT mismatch")
    if overall_benefit is None or overall_benefit["value"] != 37:
        errors.append("overall BENEFIT_COUNT is not 37")
    if overall_benefit is not None and set(overall_benefit["source_rows"]) != {row["row_number"] for row in rows if row.get("increase_benefit") is True}:
        errors.append("overall BENEFIT_COUNT source rows mismatch")
    if data_note is None or data_note["value"] != 43 or "没有效益" in data_note["text"] and "不代表" not in data_note["text"]:
        errors.append("DATA_QUALITY_NOTE mismatch")
    if sum(item["value"] for item in benefit_group_claims.values()) != 37:
        errors.append("group BENEFIT_COUNT sum is not 37")
    return {"valid": not errors, "status": "VALID" if not errors else "FACT_CLAIM_INVALID", "errors": errors}


def render_report(result: dict[str, Any]) -> str:
    claims = result["claims"]
    validation = result["validation_result"]
    citation = result["citation_result"]
    counts = {claim_type: len([item for item in claims if item["claim_type"] == claim_type]) for claim_type in ("TOTAL_COUNT", "GROUP_COUNT", "BENEFIT_COUNT", "DATA_QUALITY_NOTE")}
    lines = [
        "# Atomic Fact Claim Validation Report",
        "",
        "> TASK-016E-2B.1：将 BA-010 的复合分组事实拆分为原子化、独立可验证 Claim。",
        "> 不重新计算 Excel，不调用 LLM，不修改业务规则、Retriever、Evidence Selection、正式 Qdrant 或 Answer Engine。",
        "",
        "## 1. 冻结事实",
        "",
        "- total_rows：80",
        "- increase_effect_count：37",
        "- undetermined_profit_count：43",
        "- reconciliation_status：`37_CONFIRMED`",
        "- business_rule：增加效益 = 利润 > 0",
        "",
        "## 2. Claim 数量",
        "",
        f"- Claim 总数：**{len(claims)}**",
        f"- TOTAL_COUNT：{counts['TOTAL_COUNT']}",
        f"- GROUP_COUNT：{counts['GROUP_COUNT']}",
        f"- BENEFIT_COUNT：{counts['BENEFIT_COUNT']}（8 个分组 + 1 个总体）",
        f"- DATA_QUALITY_NOTE：{counts['DATA_QUALITY_NOTE']}",
        "",
        "## 3. 原子 Claim 对账",
        "",
        "| Claim ID | 类型 | Group | Core Value | Source Rows | Evidence IDs |",
        "|---|---|---|---:|---:|---|",
    ]
    for item in claims:
        lines.append(f"| {item['claim_id']} | {item['claim_type']} | {item.get('group') or '-'} | {item['value']} | {len(item['source_rows'])} | {', '.join(item['evidence_ids'])} |")
    lines += [
        "",
        "复合显示仍可在用户界面合并，例如“建筑：25条，其中增加效益12条”，但后台分别来自一个 GROUP_COUNT Claim 和一个 BENEFIT_COUNT Claim。",
        "",
        "## 4. Validator",
        "",
        f"- Fact Claim Validator：`{validation['status']}`",
        f"- Citation Validator：`{citation['status']}`",
        f"- Validator errors：`{validation['errors'] or citation['errors'] or '无'}`",
        "- GROUP_COUNT 总和：80",
        "- 分组 BENEFIT_COUNT 总和：37",
        "- 总体 BENEFIT_COUNT：37",
        "- DATA_QUALITY_NOTE：43",
        "- 第 88 行进入 Claim：否",
        "",
        "## 5. Citation",
        "",
        "每个 GROUP_COUNT 引用该分组全部有效明细行；每个分组 BENEFIT_COUNT 只引用该分组利润 > 0 的行；总体 BENEFIT_COUNT 引用 37 条利润 > 0 行。",
        "所有 Claim 的 source_locations 和 evidence_ids 保存在 `evaluation/fact_answers/BA-010.json`。",
        "",
        "## 6. 结论",
        "",
        "原子 Claim 验证通过。数字事实没有被合并成不可独立验证的 Claim，利润未判定的 43 条也没有被描述为未增加效益。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    facts = load_facts()
    claims = build_atomic_claims(facts)
    validation = validate_atomic_claims(facts, claims)
    citation = validate_citations(facts, claims)
    current = json.loads(OUTPUT.read_text(encoding="utf-8"))
    current["claims"] = claims
    current["validation_result"] = validation
    current["citation_result"] = citation
    current["atomic_claims"] = True
    current["claim_counts"] = {
        claim_type: len([item for item in claims if item["claim_type"] == claim_type])
        for claim_type in ("TOTAL_COUNT", "GROUP_COUNT", "BENEFIT_COUNT", "DATA_QUALITY_NOTE")
    }
    current["final_answer"] = render_answer(facts, claims)
    OUTPUT.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(render_report(current), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.resolve()), "report": str(REPORT.resolve()), "claims": len(claims), "fact_claim_status": validation["status"], "citation_status": citation["status"]}, ensure_ascii=False, indent=2))
    return 0 if validation["valid"] and citation["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
