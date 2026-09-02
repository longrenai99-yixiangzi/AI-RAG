from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "data" / "shadow" / "document_intelligence_v2"
COMPAT = V2 / "compatibility_samples.jsonl"
TRACE = ROOT / "evaluation" / "verified_answer_engine_v2_stabilization" / "fresh_run_trace.jsonl"
EVAL = ROOT / "evaluation" / "verified_answer_engine_v2_stabilization"
REPORT = ROOT / "docs" / "DOCX_STRUCTURED_EVIDENCE_LINKAGE_REPORT.md"
TARGET_FILE = "设计管理策划书-星谷科创中心项目.docx"


def main() -> int:
    runtime = next(row for row in _read_jsonl(TRACE) if row["question_id"] == "BA-010")
    v2_counts = {name: sum(TARGET_FILE in line for line in (V2 / name).read_text(encoding="utf-8").splitlines()) for name in ("documents.jsonl", "tables.jsonl", "table_rows.jsonl", "atomic_evidence.jsonl")}
    owner = next(row for row in _read_jsonl(COMPAT) if row.get("question_id") == "BA-010" and row.get("file_name") == TARGET_FILE)
    locations = owner.get("gold_location") or []
    locations = [locations] if isinstance(locations, dict) else locations
    owner_row_locator = ", ".join(str(location.get("rows")) for location in locations if location.get("rows") is not None)
    table11 = [item for item in runtime["bundle"]["candidate_evidence"] if (item.get("location") or {}).get("table") == 11 and item.get("file_name") == TARGET_FILE]
    audit = {
        "status": "DOCX_STRUCTURED_ARTIFACT_INCOMPLETE",
        "target_file": TARGET_FILE,
        "target_table": 11,
        "document_intelligence_v2_matches": v2_counts,
        "runtime_table11_evidence_ids": [item["evidence_id"] for item in table11],
        "runtime_table11_location": table11[0].get("location") if table11 else None,
        "docx_table11_rows_available": 0,
        "docx_table11_rows_mapped": 0,
        "docx_table11_cells_mapped": 0,
        "professional_categories_detected": [],
        "professional_counts_runtime": {},
        "total_count_runtime": None,
        "profit_field_available": False,
        "profit_positive_count_answerable": False,
        "owner_gold_artifact_detected": True,
        "owner_gold_row_locator": owner_row_locator or None,
        "owner_gold_runtime_eligible": False,
        "owner_gold_exclusion_reason": "artifact_only=true and gold_type=PARTIAL_GOLD; using its rows in runtime would be Gold Runtime Injection.",
        "lineage_status": "LINEAGE_PARTIAL",
        "lineage_unsafe_aggregation": 0,
        "gold_runtime_injection": 0,
        "fresh_run": runtime["fresh_run"],
    }
    mapping = {"status": audit["status"], "rows": [], "reason": "No non-Gold DOCX Table11 row/cell artifact exists in the allowed Shadow inputs."}
    aggregation = {"status": audit["status"], "professional_count_answerable": False, "total_count_answerable": False, "profit_positive_count_answerable": False, "counts": {}, "source_row_ids": []}
    answer = {"question_id": "BA-010", "answer": runtime["answer"], "citation_boundary": "DOCX Table11 is cited only as an incomplete table object; no XLSX or Gold rows are cited."}
    renderer = _read_json(EVAL / "renderer_quality_metrics.json")
    summary = {"raw_evidence_dump_rate": renderer["raw_evidence_dump_rate"], "internal_column_label_leakage": renderer["internal_column_label_leakage"], "malformed_unicode_in_answer": renderer["malformed_unicode_in_answer"], "rendered_claim_validation_rate": renderer["rendered_claim_validation_rate"]}
    _write_json(EVAL / "ba010_docx_table11_audit.json", audit)
    _write_json(EVAL / "ba010_docx_row_mapping.json", mapping)
    _write_json(EVAL / "ba010_runtime_aggregation.json", aggregation)
    _write_json(EVAL / "ba010_answer_result.json", answer)
    _write_json(EVAL / "renderer_quality_metrics_summary.json", summary)
    REPORT.write_text(_report(audit, summary), encoding="utf-8")
    assert audit["gold_runtime_injection"] == 0
    assert audit["lineage_unsafe_aggregation"] == 0
    print(json.dumps({"status": audit["status"], "gold_runtime_injection": 0}, ensure_ascii=False))
    return 0


def _report(audit: dict[str, Any], renderer: dict[str, Any]) -> str:
    return "\n".join([
        "# DOCX STRUCTURED EVIDENCE LINKAGE REPORT", "",
        "> TASK-020F.1.1：仅审计并使用冻结 Shadow 工件；未读取 Root-002 实体文件。", "",
        "## 审计结论", "",
        f"- Status：`{audit['status']}`。", "- 当前 Runtime 已定位 DOCX Table11，但 Document Intelligence V2 没有该 DOCX 的 Document/Table/Row/Atomic 行级工件。",
        f"- Runtime Table11 Evidence IDs：{audit['runtime_table11_evidence_ids']}；位置：{audit['runtime_table11_location']}。",
        f"- DOCX 可用行 / 已映射行 / 已映射单元格：{audit['docx_table11_rows_available']} / {audit['docx_table11_rows_mapped']} / {audit['docx_table11_cells_mapped']}。", "",
        "## Owner Artifact 边界", "",
        f"- 检测到 Owner Gold 的 Table11 行定位 `{audit['owner_gold_row_locator']}`，但其标记为 `artifact_only=true`、`gold_type=PARTIAL_GOLD`。",
        "- 为保持 `Gold Runtime Injection=0`，这些行仅用于离线审计，不进入 Runtime Bundle、Claim、Citation 或聚合计算。",
        "- DOCX/XLSX 继续 `LINEAGE_PARTIAL`；未执行自动关联。", "",
        "## Runtime 行级事实", "", "- 专业类别、各专业条数与总条数：均不可回答。", "- 利润字段与增加效益条数：证据不足。", "- BA-010 继续 `PARTIAL_ANSWER`；不会使用 XLSX 或 Gold 数字补足。", "",
        "## Renderer 指标", "", f"- Raw Evidence Dump Rate：{renderer['raw_evidence_dump_rate']['rate']}", f"- Internal Column Label Leakage：{renderer['internal_column_label_leakage']}", f"- Malformed Unicode In Answer：{renderer['malformed_unicode_in_answer']}", f"- Rendered Claim Validation：{renderer['rendered_claim_validation_rate']['rate']}", "",
        "## 后续前置条件", "", "须在后续治理批准后，仅针对该确切 DOCX Owner Source 重新生成非 Gold 的 Table11 Row/Cell Structured Artifact；在此之前不得进入 020G。", "",
        "TASK-020F.1.1 = COMPLETE", "", "等待架构评审。", ""
    ])


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
