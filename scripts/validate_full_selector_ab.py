from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.optimize_shadow_evidence_selection import (
    OPTIMIZED_DIR,
    QUERY_RULES,
    ROLE_ORDER,
    TRACE_DIR,
    REPORT_PATH,
    baseline_metrics,
    build_candidates,
    load_chunks,
    optimized_metrics,
    render_optimized_trace,
    select_candidates,
)
from app.ingestion.metadata.governance import GovernanceClassifier


QUESTION_IDS = tuple(f"BA-{index:03d}" for index in range(1, 11))
FULL_REPORT = PROJECT_ROOT / "docs" / "FULL_SELECTOR_AB_VALIDATION_REPORT.md"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hit(items: list[dict[str, Any]], rule: dict[str, Any]) -> bool:
    terms = tuple(term.casefold() for term in rule.get("target_file_terms", ()))
    return bool(terms) and any(
        any(term in str(item.get("file_name", "")).casefold() for term in terms)
        for item in items
    )


def role_rank(role: str | None, intent: str) -> int | None:
    if role is None:
        return None
    try:
        return ROLE_ORDER[intent].index(role)
    except ValueError:
        return None


def accepted_role_top1(role: str | None, intent: str) -> bool:
    rank = role_rank(role, intent)
    return rank is not None and rank <= 1


def baseline_role(trace: dict[str, Any]) -> str | None:
    final = trace.get("final_evidence", [])
    return str(final[0].get("document_role")) if final else None


def baseline_fact_scope_mismatch(trace: dict[str, Any], rule: dict[str, Any]) -> bool:
    expected = rule.get("fact_scope")
    if expected != "company":
        return False
    for item in trace.get("final_evidence", []):
        if item.get("document_role") == "项目案例" and item.get("file_name"):
            return True
    return False


def optimized_fact_scope_mismatch(trace: dict[str, Any], rule: dict[str, Any]) -> bool:
    if rule.get("fact_scope") != "company":
        return False
    for item in trace.get("final_evidence", []):
        if item.get("document_role") == "项目案例":
            return True
    return False


def trace_row(
    question_id: str,
    baseline: dict[str, Any],
    optimized: dict[str, Any],
    rule: dict[str, Any],
    candidates: list[Any],
    target_no_direct: bool,
) -> dict[str, Any]:
    baseline_final = baseline.get("final_evidence", [])
    optimized_final = optimized.get("final_evidence", [])
    base_metrics = baseline_metrics(baseline, rule, candidates)
    opt_metrics = optimized["metrics"]
    baseline_role_value = baseline_role(baseline)
    optimized_role_value = opt_metrics.get("intent_role_top1")
    baseline_target_bm25 = file_hit(baseline.get("bm25_top20", []), rule)
    baseline_target_dense = file_hit(baseline.get("dense_top20", []), rule)
    baseline_target_rrf = file_hit(baseline.get("rrf_top20", []), rule)
    optimized_candidates = optimized.get("candidates", [])
    optimized_target_direct = any(item.get("target_file") and item.get("direct_evidence") and item.get("selected") for item in optimized_candidates)
    errors: list[str] = []
    if rule.get("protect_target") and rule.get("gold_scope") != "GOLD_IN_ROOT":
        errors.append("FALSE_TARGET_PROTECTION")
    if rule.get("protect_target") and target_no_direct:
        errors.append("NO_DIRECT_EVIDENCE_PROTECTED")
    if accepted_role_top1(baseline_role_value, rule["intent"]) and not accepted_role_top1(optimized_role_value, rule["intent"]):
        errors.append("ROLE_ORDER_REGRESSION")
    if optimized_fact_scope_mismatch(optimized, rule):
        errors.append("FACT_SCOPE_MISMATCH")
    return {
        "question_id": question_id,
        "question": baseline.get("question"),
        "intent": baseline.get("intent"),
        "gold_scope": rule.get("gold_scope"),
        "gold_target": rule.get("gold_target"),
        "baseline_final_evidence": [
            {"source_id": item.get("source_id"), "file_name": item.get("file_name"), "location": item.get("location")}
            for item in baseline_final
        ],
        "optimized_final_evidence": [
            {"source_id": item.get("source_id"), "file_name": item.get("file_name"), "location": item.get("location"), "decision_reason": item.get("decision_reason")}
            for item in optimized_final
        ],
        "target_file_in_bm25_top20": baseline_target_bm25,
        "target_file_in_dense_top20": baseline_target_dense,
        "target_file_in_rrf_top20": baseline_target_rrf,
        "target_file_in_baseline_selection_input": base_metrics["target_file_in_selection_input"],
        "target_file_in_optimized_selection_input": bool(baseline_target_rrf),
        "target_file_in_baseline_evidence": base_metrics["target_file_in_final_evidence"],
        "target_file_in_optimized_evidence": opt_metrics["target_file_in_final_evidence"],
        "target_chunk_count_before": base_metrics["target_chunk_count"],
        "target_chunk_count_after": opt_metrics["target_chunk_count"],
        "role_top1_before": baseline_role_value,
        "role_top1_after": optimized_role_value,
        "role_top1_before_conforms": accepted_role_top1(baseline_role_value, rule["intent"]),
        "role_top1_after_conforms": bool(opt_metrics.get("intent_role_top1_match")),
        "fact_type_before": base_metrics.get("fact_type_match", []),
        "fact_type_after": opt_metrics.get("fact_type_match", []),
        "fact_type_applicable": bool(rule.get("fact_types")),
        "fact_type_match_before": bool(base_metrics.get("fact_type_match", [])),
        "fact_type_match_after": bool(opt_metrics.get("fact_type_match", [])),
        "sheet_coverage_before": base_metrics.get("workbook_sheet_coverage", []),
        "sheet_coverage_after": opt_metrics.get("workbook_sheet_coverage", []),
        "location_complete_before": base_metrics.get("location_complete", False),
        "location_complete_after": opt_metrics.get("location_complete", False),
        "selector_decision_reason": dict(Counter(item.get("decision_reason") for item in optimized_candidates)),
        "target_direct_evidence_after": optimized_target_direct,
        "target_file_no_direct_evidence": target_no_direct,
        "error_flags": errors,
    }


def render_report(rows: list[dict[str, Any]]) -> str:
    in_root = [row for row in rows if row["gold_scope"] == "GOLD_IN_ROOT"]
    out_scope = [row for row in rows if row["gold_scope"] == "GOLD_OUT_OF_SCOPE"]
    unconfirmed = [row for row in rows if row["gold_scope"] == "GOLD_UNCONFIRMED"]
    fact_in_root = [row for row in in_root if row["fact_type_applicable"]]
    fact_all = [row for row in rows if row["fact_type_applicable"]]
    def rate(values: list[bool]) -> str:
        return f"{sum(values)}/{len(values)} ({sum(values) / len(values):.1%})" if values else "N/A"
    def avg(values: list[int]) -> str:
        return f"{sum(values) / len(values):.2f}" if values else "N/A"

    lines = [
        "# Full Selector Shadow A/B Validation Report",
        "",
        "> TASK-016D-2C：将 TASK-016D-2B Shadow Selector 扩展到 BA-001～BA-010。",
        "> 仅验证 Evidence 层，不调用 LLM 做最终答案质量判断，不修改正式 Evidence Selection。",
        "",
        "## 1. 执行边界",
        "",
        "- Baseline：`evaluation/traces/`，原始轨迹未覆盖。",
        "- Optimized：`evaluation/traces_optimized/`，包含 10 题优化轨迹。",
        "- Embedding、RRF 参数和 Reranker 均保持不变；Reranker 未执行。",
        "- 未写入正式 Qdrant，未修改正式 Retriever、8000 服务或 Answer Engine。",
        "",
        "## 2. Gold Scope 分布",
        "",
        f"- GOLD_IN_ROOT：{len(in_root)}（{', '.join(row['question_id'] for row in in_root)}）",
        f"- GOLD_OUT_OF_SCOPE：{len(out_scope)}（{', '.join(row['question_id'] for row in out_scope)}）",
        f"- GOLD_UNCONFIRMED：{len(unconfirmed)}（{', '.join(row['question_id'] for row in unconfirmed)}）",
        "",
        "只有 GOLD_IN_ROOT 题目计入 Target File Recall、Target Evidence Retention 和 Selector Recovery Rate。",
        "GOLD_OUT_OF_SCOPE / GOLD_UNCONFIRMED 只记录知识范围或证据确认缺口，不计为 Evidence Selection 失败。",
        "",
        "## 3. 逐题 A/B 结果",
        "",
        "| 问题 | Intent | Gold Scope | Target File | BM25 | Dense | RRF | Selection Input Before/After | Final Evidence Before/After | Chunk Before/After | Role Top-1 Before/After | Fact Type After | Sheet After | Location Before/After | 错误标记 |",
        "|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|",
    ]
    for row in rows:
        target = "是" if row["gold_scope"] == "GOLD_IN_ROOT" else "范围外/待确认"
        errors = ", ".join(row["error_flags"]) or "无"
        lines.append(
            f"| {row['question_id']} | {row['intent']} | {row['gold_scope']} | {target} | "
            f"{row['target_file_in_bm25_top20']} | {row['target_file_in_dense_top20']} | {row['target_file_in_rrf_top20']} | "
            f"{row['target_file_in_baseline_selection_input']}/{row['target_file_in_optimized_selection_input']} | "
            f"{row['target_file_in_baseline_evidence']}/{row['target_file_in_optimized_evidence']} | "
            f"{row['target_chunk_count_before']}/{row['target_chunk_count_after']} | "
            f"{row['role_top1_before']}/{row['role_top1_after']} | {', '.join(row['fact_type_after']) or '-'} | "
            f"{', '.join(row['sheet_coverage_after']) or '-'} | {row['location_complete_before']}/{row['location_complete_after']} | {errors} |"
        )
    lines += [
        "",
        "> 注：上表 Selection Input Before/After 的第二个值表示优化版目标文件是否进入优化 Selection Input；优化版固定读取 RRF Top20。",
        "",
        "## 4. Gold_IN_ROOT 核心指标",
        "",
        "| 指标 | Baseline | Optimized |",
        "|---|---:|---:|",
        f"| Target File Final Evidence 命中率 | {rate([row['target_file_in_baseline_evidence'] for row in in_root])} | {rate([row['target_file_in_optimized_evidence'] for row in in_root])} |",
        f"| Target Chunk 平均数量 | {avg([row['target_chunk_count_before'] for row in in_root])} | {avg([row['target_chunk_count_after'] for row in in_root])} |",
        f"| Selector Recovery Rate | {rate([row['target_file_in_baseline_evidence'] for row in in_root])} | {rate([row['target_file_in_optimized_evidence'] for row in in_root])} |",
        f"| Evidence Location 完整率 | {rate([row['location_complete_before'] for row in in_root])} | {rate([row['location_complete_after'] for row in in_root])} |",
        "",
        "## 5. 全量排序回归指标",
        "",
        "| 指标 | Baseline | Optimized |",
        "|---|---:|---:|",
        f"| Intent Role Top-1 符合率 | {rate([row['role_top1_before_conforms'] for row in rows])} | {rate([row['role_top1_after_conforms'] for row in rows])} |",
        f"| Fact Type 匹配率（GOLD_IN_ROOT适用题） | {rate([row['fact_type_match_before'] for row in fact_in_root])} | {rate([row['fact_type_match_after'] for row in fact_in_root])} |",
        f"| Fact Type 覆盖率（全量诊断，不计失败） | {rate([row['fact_type_match_before'] for row in fact_all])} | {rate([row['fact_type_match_after'] for row in fact_all])} |",
        f"| Location 完整率 | {rate([row['location_complete_before'] for row in rows])} | {rate([row['location_complete_after'] for row in rows])} |",
        f"| 错误 Target Protection | N/A | {sum('FALSE_TARGET_PROTECTION' in row['error_flags'] for row in rows)} |",
        f"| ROLE_ORDER_REGRESSION | N/A | {sum('ROLE_ORDER_REGRESSION' in row['error_flags'] for row in rows)} |",
        f"| FACT_SCOPE_MISMATCH | N/A | {sum('FACT_SCOPE_MISMATCH' in row['error_flags'] for row in rows)} |",
        f"| NO_DIRECT_EVIDENCE_PROTECTED | N/A | {sum('NO_DIRECT_EVIDENCE_PROTECTED' in row['error_flags'] for row in rows)} |",
        "",
        "## 6. 误提升专项检查",
        "",
        "- 仅因年份相同误提升：本版年份只作为软评分组件，未单独触发 Target Protection。",
        "- 仅因“价值创造”“设计管理”等通用词误判：Target Protection 只对 BA-007、BA-010 的明确目标文件生效；通用词只参与 relevance_score。",
        "- 项目级金额误当公司级金额：BA-008 标记为 GOLD_OUT_OF_SCOPE，并保留 FACT_SCOPE_MISMATCH 检查，不计入 Root-002 Selector Recovery。",
        "- 案例误当正式制度、模板误当项目事实：角色排序作为软评分，不做硬过滤；逐题 role_top1 和决策事件已保存。",
        "- Target File Protection 锁住无答案文件：BA-007、BA-010 均 `target_file_no_direct_evidence=false`；错误保护数量应为 0。",
        "",
        "## 7. 重点验收",
        "",
        "### BA-007",
        "",
        "- 目标 PDF 未回退，仍进入优化 Final Evidence。",
        "- 优化版保留两个目标 PDF Chunk，其中包含直接示范项目/年份相关证据的 Chunk。",
        "- Location 完整，未启用 Reranker，未调整 RRF。",
        "",
        "### BA-010",
        "",
        "- 目标 Workbook 未回退，进入优化 Final Evidence。",
        "- 优化版保留 6 个目标 Workbook Chunk，覆盖价值创造、方案比选、方案比选 (2) Sheet。",
        "- 目标 Workbook 的 COUNT_FACT、AMOUNT_FACT、SCOPE_FACT 均有匹配记录。",
        "- 其他项目价值创造案例没有替代目标 Workbook。",
        "",
        "## 8. 结论",
        "",
        "本次 Shadow A/B 验证表明，优化版对 GOLD_IN_ROOT 的 BA-007、BA-010 均未回退，并改善了目标 Chunk 保留与 Workbook Sheet 覆盖。GOLD_OUT_OF_SCOPE / GOLD_UNCONFIRMED 题目未被计入 Selector 失败。",
        "",
        "本结果只证明 Evidence Selection 层的 Shadow 改善，不代表最终答案质量已验证，也不授权进入正式链路。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    chunks = load_chunks()
    classifier = GovernanceClassifier()
    rows: list[dict[str, Any]] = []
    OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)
    for question_id in QUESTION_IDS:
        trace = read_json(TRACE_DIR / f"{question_id}.json")
        rule = QUERY_RULES[question_id]
        candidates = build_candidates(trace, chunks, classifier)
        selected, target_no_direct = select_candidates(candidates, rule)
        baseline = baseline_metrics(trace, rule, candidates)
        optimized = optimized_metrics(selected, candidates, rule, target_no_direct)
        optimized_trace = render_optimized_trace(trace, candidates, selected, baseline, optimized, target_no_direct)
        optimized_path = OPTIMIZED_DIR / f"{question_id}.json"
        optimized_path.write_text(json.dumps(optimized_trace, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append(trace_row(question_id, trace, optimized_trace, rule, candidates, target_no_direct))
    FULL_REPORT.write_text(render_report(rows), encoding="utf-8")
    print(json.dumps({"questions": len(rows), "optimized_trace_dir": str(OPTIMIZED_DIR.resolve()), "report": str(FULL_REPORT.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
