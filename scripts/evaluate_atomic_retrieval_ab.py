from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.ingestion.atomic_search import query_facets, search_atomic_evidence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BODY_TYPES = {".pdf", ".docx", ".pptx", ".xlsx"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare legacy Shadow evidence with atomic Shadow candidates.")
    parser.add_argument("--records", type=Path, default=PROJECT_ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl")
    parser.add_argument("--baseline", type=Path, default=PROJECT_ROOT / "evaluation" / "v1_business_acceptance")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "evaluation" / "atomic_evidence")
    args = parser.parse_args()

    records = [json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines() if line.strip()]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(args.baseline.glob("BA-*.json")):
        baseline = json.loads(path.read_text(encoding="utf-8"))
        baseline_evidence = baseline.get("top_evidence") or []
        question = baseline.get("question", "")
        atomic_hits = search_atomic_evidence(question, records, limit=5)
        atomic_candidates = [_candidate(item) for item in atomic_hits]
        baseline_files = {str(item.get("file_name") or "") for item in baseline_evidence}
        atomic_files = {str(item.get("file_name") or "") for item in atomic_candidates}
        results.append(
            {
                "question_id": baseline.get("question_id") or path.stem,
                "question": baseline.get("question"),
                "query_facets": query_facets(question),
                "gold_scope": "GOLD_UNCONFIRMED" if not baseline.get("expected_files") else "GOLD_IN_ROOT",
                "expected_files": baseline.get("expected_files") or [],
                "baseline_status": baseline.get("final_status"),
                "baseline_evidence": [_baseline_candidate(item) for item in baseline_evidence],
                "atomic_candidates": atomic_candidates,
                "baseline_atomic_file_overlap": sorted(baseline_files & atomic_files),
                "atomic_candidate_count": len(atomic_candidates),
                "baseline_has_exact_locator": any(_exact_locator(item.get("location") or {}) for item in baseline_evidence),
                "atomic_has_exact_locator": any(_exact_locator(item.get("location") or {}) for item in atomic_candidates),
                "atomic_top_registration_only": bool(atomic_candidates and atomic_candidates[0]["registration_only"]),
            }
        )

    output_path = args.output_dir / "retrieval_ab.jsonl"
    output_path.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in results) + "\n", encoding="utf-8")
    report_path = PROJECT_ROOT / "docs" / "ATOMIC_RETRIEVAL_AB_REPORT.md"
    report_path.write_text(render_report(args.records, results, output_path), encoding="utf-8")
    print(json.dumps(_summary(results, output_path, report_path), ensure_ascii=False, indent=2))
    return 0


def _baseline_candidate(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_name": value.get("file_name"),
        "source_path": value.get("source_path"),
        "location": value.get("location"),
        "excerpt": str(value.get("excerpt") or "")[:500],
    }


def _candidate(value: dict[str, Any]) -> dict[str, Any]:
    record = value["record"]
    return {
        "score": value["score"],
        "matched_terms": value["matched_terms"],
        "identity_match_terms": value.get("identity_match_terms", []),
        "phrase_matches": value.get("phrase_matches", []),
        "year_matches": value.get("year_matches", []),
        "metric_matches": value.get("metric_matches", []),
        "text_metric_matches": value.get("text_metric_matches", []),
        "entity_matches": value.get("entity_matches", []),
        "text_entity_matches": value.get("text_entity_matches", []),
        "field_matches": value.get("field_matches", []),
        "facet_reasons": value.get("facet_reasons", []),
        "evidence_id": record.get("evidence_id"),
        "file_name": record.get("file_name"),
        "source_path": record.get("source_path"),
        "location": record.get("location"),
        "granularity": record.get("granularity"),
        "registration_only": _is_registration(record),
        "text": str(record.get("text") or "")[:900],
    }


def _is_registration(record: dict[str, Any]) -> bool:
    text = str(record.get("text") or "")
    path = str(record.get("source_path") or "").lower()
    return record.get("file_type") == ".md" and (
        any(marker in text for marker in ("file://", "[[", "原始资料", "原库业务目录"))
        or ("\u5173\u8054\u5185\u5bb9" in text and not any(char.isdigit() for char in text))
        or "\\wiki\\entities\\" in path
    )


def _exact_locator(location: dict[str, Any]) -> bool:
    if "row_start" in location and "row_end" in location:
        return location.get("row_start") == location.get("row_end")
    if "line_start" in location and "line_end" in location:
        return location.get("line_start") == location.get("line_end")
    return any(key in location for key in ("text_line_start", "text_index", "paragraph_start"))


def _summary(results: list[dict[str, Any]], output_path: Path, report_path: Path) -> dict[str, Any]:
    return {
        "questions": len(results),
        "gold_scope": {scope: sum(item["gold_scope"] == scope for item in results) for scope in sorted({item["gold_scope"] for item in results})},
        "baseline_exact_locator": sum(item["baseline_has_exact_locator"] for item in results),
        "atomic_exact_locator": sum(item["atomic_has_exact_locator"] for item in results),
        "registration_only_top": sum(item["atomic_top_registration_only"] for item in results),
        "baseline_atomic_file_overlap": sum(bool(item["baseline_atomic_file_overlap"]) for item in results),
        "output": str(output_path.resolve()),
        "report": str(report_path.resolve()),
    }


def render_report(records_path: Path, results: list[dict[str, Any]], output_path: Path) -> str:
    lines = [
        "# Shadow 原子证据 Retrieval A/B 验证报告",
        "",
        "> 本报告只比较既有 Shadow Chunk 证据和原子证据候选，不调用 LLM，不写 Qdrant，不把候选命中当作 Gold 真值。",
        "",
        f"- 原子证据：`{records_path.resolve()}`",
        f"- 逐题结果：`{output_path.resolve()}`",
        "- 当前 BA Gold 的 `expected_files` 为空，因此本报告不计算 Recall，不宣称检索准确率提升。",
        "",
        "## 1. A/B 结果",
        "",
        "| 问题 | Gold Scope | 基线状态 | 基线首条来源 | 原子首条候选 | 原子定位 | 原子与基线文件重合 |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        baseline = (result.get("baseline_evidence") or [{}])[0]
        atomic = (result.get("atomic_candidates") or [{}])[0]
        lines.append(
            f"| {result['question_id']} | {result['gold_scope']} | {result.get('baseline_status') or '-'} | {baseline.get('file_name') or '-'} | {atomic.get('file_name') or '-'} | `{atomic.get('location') or {}}` | {', '.join(result['baseline_atomic_file_overlap']) or '-'} |"
        )
    lines.extend(["", "## 2. 可解释统计", "", "| 指标 | 数量 |", "|---|---:|"])
    summary = _summary(results, output_path, output_path)
    lines.extend(
        [
            f"| 题目数 | {summary['questions']} |",
            f"| `GOLD_UNCONFIRMED` | {summary['gold_scope'].get('GOLD_UNCONFIRMED', 0)} |",
            f"| 基线存在精确定位 | {summary['baseline_exact_locator']} |",
            f"| 原子候选存在精确定位 | {summary['atomic_exact_locator']} |",
            f"| 原子首条候选为登记页 | {summary['registration_only_top']} |",
            f"| 原子候选与基线文件有重合 | {summary['baseline_atomic_file_overlap']} |",
            "",
            "## 3. 结论",
            "",
            "1. 原子层已经能够把证据细化到 Markdown 行、XLSX 行、PDF 页内行、DOCX 段落/表格行和 PPTX 文本行。",
            "2. 原子层仍会被年度总结等通用文本干扰；因此必须继续加入实体、年份、指标字段和来源角色约束。",
            "3. BA-003、BA-010 等问题只能命中登记页时，说明 Source Closure 仍未完成，不能把登记页当正文。",
            "4. 在 `expected_files` 补齐前，本报告只能作为定位能力诊断，不能作为 Recall 评价。",
            "",
            "## 4. 下一步",
            "",
            "将原子证据搜索与文档实体、年份、字段和 authority 进行 Shadow 融合，先做 A/B，再考虑接入正式 Retriever。",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
