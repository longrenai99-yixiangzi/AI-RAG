from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
REVIEW = V26 / "live_shadow_v2_6_1_manual_review.json"
GOLD = ROOT / "evaluation" / "trial_qa_benchmark" / "benchmark_130_questions.jsonl"

ROOT_CAUSES = {
    "V261-LSR-002": ("SOURCE_BODY_MISSING_OR_STRUCTURED_GAP", "V2 returned a topic list instead of the requested count and fields.", "Admit and parse the actual design-option checklist body; bind table headers and rows before answering."),
    "V261-LSR-003": ("QUERY_INTENT_SCOPE_MISMATCH", "V2 confused design-planning review with generic design evaluation.", "Add a design-planning-review intent facet and require participant and follow-up evidence from the same source."),
    "V261-LSR-004": ("SOURCE_BODY_MISSING_OR_REGISTRATION_ONLY", "V2 returned a folder pointer, not the task-book body needed for project and typology counts.", "Parse the task-book compilation source and derive counts and typologies from body evidence."),
    "V261-LSR-005": ("SOURCE_BODY_OR_LOCATION_MISMATCH", "V2 cited an experience index and links but did not provide the requested pool-wall precision fact.", "Parse the Xiaogan PDF and require a numeric page/line evidence window for the precision claim."),
    "V261-LSR-006": ("QUERY_SCOPE_AND_AGGREGATION_MISMATCH", "V2 returned company-wide totals instead of Shenyang Center Tower per-specialty amounts.", "Bind the Shenyang source and use project-scoped table aggregation; reject company-wide fallback."),
    "V261-LSR-007": ("PROJECT_RETRIEVAL_MISMATCH", "V2 answered an unrelated anti-floating question instead of the Hainan Tower crown support-frame fact.", "Add project identity rescue for Hainan Center and require the same-project structural evidence."),
    "V261-LSR-008": ("SOURCE_ROLE_OR_RENDERING_GAP", "V2 had supporting chapter-row excerpts but did not promote the canonical eight-section list to a direct answer.", "Mark the canonical design-planning source as direct for chapter-list queries and preserve section-row evidence."),
    "V261-LSR-010": ("SOURCE_BODY_OR_ROLE_MISMATCH", "V2 returned a general center description and omitted organization and staffing details.", "Use the approved organization-optimization source page and render organization, staffing, and optional-post boundaries separately."),
    "V261-LSR-011": ("QUERY_INTENT_SCOPE_MISMATCH", "V2 returned curtain-wall review timing and unrelated schedule rows, not material-equipment approval timing and overseas variation.", "Add a material-equipment-approval intent and require both domestic and overseas timing evidence."),
    "V261-LSR-012": ("SOURCE_BODY_MISSING_OR_PROJECT_MISMATCH", "V2 returned hospital logistics and transport weights, not the overseas modular data-center module inventory.", "Admit the overseas modular data-center source and bind module, quantity, and maximum-weight fields."),
    "V261-LSR-013": ("METRIC_PERIOD_OR_DEFINITION_CONFLICT", "V2 treated cumulative amount and efficiency as an unresolved conflict instead of two requested 2024 metrics.", "Separate cumulative amount from efficiency and enforce 2024 scope before conflict detection."),
    "V261-LSR-014": ("SOURCE_AND_NARRATIVE_AGGREGATION_GAP", "V2 returned an EPC table excerpt but missed the 100-project and 31-win narrative facts.", "Bind the 2024 annual-summary evidence and keep the two requested facts as separate claims."),
    "V261-LSR-015": ("TIME_SCOPE_SOURCE_MISMATCH", "V2 returned a 2024 project-list row instead of the 2024 H1 review counts 37 and 13.", "Prefer the 2024 H1 summary for this period-specific fact and reject project-list rows as substitutes."),
    "V261-LSR-016": ("TIME_SCOPE_SOURCE_MISMATCH", "V2 returned a 2024 project-list table for a 2025 H1 EPC design-planning completion question.", "Use the 2025 H1 summary and preserve the completion-status evidence window."),
    "V261-LSR-017": ("METRIC_FACET_CONFLICT", "V2 mixed steel-average efficiency and overall efficiency facts from different metric facets.", "Model steel-average efficiency and count-over-16% as separate claims under 2025 scope."),
    "V261-LSR-018": ("TABLE_ROW_SCOPE_MISMATCH", "V2 exposed multiple roof-decoration rows, including an unrelated 742.71万元 value, instead of one project-row answer.", "Select the exact Iron-Investment project row and bind original method, optimized method, and 50万元 result together."),
    "V261-LSR-019": ("SOURCE_BODY_MISSING_OR_REGISTRATION_ONLY", "V2 returned process-folder pointers but not the eight stages and largest-material-volume fact.", "Parse the canonical EPC design-management process body and add a stage-level evidence map."),
    "V261-LSR-020": ("MULTI_SOURCE_PERIOD_GAP", "V2 returned BIM requirements but not the H1 project count plus the same-period forum document.", "Answer as two separately cited claims: 2026 H1 BIM count and forum publication, each with period-scoped evidence."),
}


def main() -> int:
    payload = json.loads(REVIEW.read_text(encoding="utf-8"))
    gold = {}
    if GOLD.exists():
        for line in GOLD.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            gold[row.get("question")] = row
    rows = [row for row in payload.get("records") or [] if row.get("manual_decision") == "NOT_VERIFIED"]
    queue = []
    for row in rows:
        category, finding, action = ROOT_CAUSES.get(row["review_id"], ("UNCLASSIFIED", "No deterministic classification recorded.", "Manual root-cause review required."))
        reference = gold.get(row.get("question")) or {}
        queue.append({"review_id": row["review_id"], "candidate_type": row.get("candidate_type"), "question": row.get("question"), "root_cause_category": category, "finding": finding, "next_action": action, "v1_sources": [item.get("file_name") for item in (row.get("v1") or {}).get("citations", [])[:3]], "v2_sources": [item.get("file_name") for item in (row.get("v2_6_1") or {}).get("citations", [])[:3]], "gold_qid": reference.get("qid") or reference.get("question_id"), "gold_expected_answer": reference.get("expected_answer"), "gold_expected_source": reference.get("expected_source"), "gold_reference_status": "FOUND" if reference else "MISSING", "status": "OPEN_REMEDIATION"})
    result = {"schema_version": "knowledge_os_v2_6_1.not_verified_remediation_queue", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "source_review_status": payload.get("status"), "record_count": len(queue), "categories": {}, "records": queue}
    for row in queue:
        result["categories"][row["root_cause_category"]] = result["categories"].get(row["root_cause_category"], 0) + 1
    out = V26 / "not_verified_remediation_queue.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    live_report_path = V26 / "live_shadow_v2_6_1_dev_report.json"
    if live_report_path.exists():
        live_report = json.loads(live_report_path.read_text(encoding="utf-8"))
        live_report["not_verified_remediation_queue"] = {"status": "OPEN_REMEDIATION", "count": len(queue), "path": str(out), "categories": result["categories"]}
        live_report_path.write_text(json.dumps(live_report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.1 NOT_VERIFIED 修复队列", "", f"- 条数：`{len(queue)}`", f"- 分类：`{result['categories']}`", "- 状态：所有条目保持 `OPEN_REMEDIATION`，未自动改写答案或 Gate。", ""]
    for row in queue:
        lines += [f"## {row['review_id']}", "", f"- 问题：{row['question']}", f"- 根因：`{row['root_cause_category']}`", f"- 证据判断：{row['finding']}", f"- 下一步：{row['next_action']}", f"- V1 来源：`{row['v1_sources']}`", f"- V2.6.1 来源：`{row['v2_sources']}`", f"- Gold：`{row['gold_qid'] or 'MISSING'}`；目标来源：`{row['gold_expected_source'] or 'MISSING'}`", f"- Gold 标准答案：{row['gold_expected_answer'] or '未找到，需人工补齐。'}", ""]
    (ROOT / "docs" / "V2_6_1_NOT_VERIFIED_REMEDIATION_QUEUE.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"record_count": result["record_count"], "categories": result["categories"], "status": "OPEN_REMEDIATION"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
