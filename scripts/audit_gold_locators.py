from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.ingestion.atomic_search import query_facets, search_atomic_evidence


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Shadow Gold file and location candidates without changing Gold data.")
    parser.add_argument(
        "--records",
        type=Path,
        default=PROJECT_ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "v1_business_acceptance",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "atomic_evidence" / "gold_locator_audit.jsonl",
    )
    args = parser.parse_args()

    records = [json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines() if line.strip()]
    results: list[dict[str, Any]] = []
    for question_path in sorted(args.questions.glob("BA-*.json")):
        case = json.loads(question_path.read_text(encoding="utf-8"))
        question = str(case.get("question") or "")
        expected_files = [str(value) for value in case.get("expected_files") or []]
        hits = search_atomic_evidence(question, records, limit=20)
        candidates = [_candidate(hit) for hit in hits]
        gold_scope = "GOLD_UNCONFIRMED" if not expected_files else "GOLD_IN_ROOT"
        if expected_files and not any(item["file_name"] in expected_files for item in candidates):
            gold_scope = "GOLD_OUT_OF_SCOPE"
        results.append(
            {
                "question_id": case.get("question_id") or question_path.stem,
                "question": question,
                "gold_scope": gold_scope,
                "expected_files": expected_files,
                "query_facets": query_facets(question),
                "candidate_count": len(candidates),
                "candidates": candidates,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(value, ensure_ascii=False) for value in results) + "\n",
        encoding="utf-8",
    )
    report_path = PROJECT_ROOT / "docs" / "GOLD_LOCATOR_AUDIT.md"
    report_path.write_text(render_report(args.records, args.output, results), encoding="utf-8")
    summary = Counter(item["gold_scope"] for item in results)
    print(
        json.dumps(
            {
                "questions": len(results),
                "gold_scope": dict(summary),
                "candidate_questions": sum(bool(item["candidates"]) for item in results),
                "output": str(args.output.resolve()),
                "report": str(report_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _candidate(hit: dict[str, Any]) -> dict[str, Any]:
    record = hit["record"]
    text = str(record.get("text") or "")
    return {
        "score": hit["score"],
        "evidence_id": record.get("evidence_id"),
        "file_name": record.get("file_name"),
        "source_path": record.get("source_path"),
        "file_type": record.get("file_type"),
        "location": record.get("location") or {},
        "facet_reasons": hit.get("facet_reasons", []),
        "year_matches": hit.get("year_matches", []),
        "metric_matches": hit.get("metric_matches", []),
        "text_metric_matches": hit.get("text_metric_matches", []),
        "entity_matches": hit.get("entity_matches", []),
        "text_entity_matches": hit.get("text_entity_matches", []),
        "field_matches": hit.get("field_matches", []),
        "registration_only": _is_registration(record),
        "text": text[:900],
    }


def _is_registration(record: dict[str, Any]) -> bool:
    if record.get("file_type") != ".md":
        return False
    text = str(record.get("text") or "")
    path = str(record.get("source_path") or "").lower()
    return any(marker in text for marker in ("file://", "[[", "原始资料", "原库业务目录")) or (
        "关联内容" in text and not any(char.isdigit() for char in text)
    ) or "\\wiki\\entities\\" in path


def render_report(records_path: Path, output_path: Path, results: list[dict[str, Any]]) -> str:
    lines = [
        "# Shadow Gold 文件与定位审计",
        "",
        "> 本报告只读扫描 Root-001 原子证据，生成候选文件、候选行/段/页/Sheet 和查询约束；不修改 Gold 数据，不把候选命中当作正确答案。",
        "",
        f"- 原子证据：`{records_path.resolve()}`",
        f"- 审计结果：`{output_path.resolve()}`",
        "- 目标范围：BA-001～BA-010",
        "",
        "## 1. 结论",
        "",
        "当前 BA-001～BA-010 的 `expected_files` 均为空，10 题均为 `GOLD_UNCONFIRMED`。因此当前只能确认检索定位候选，不能计算业务 Recall，也不能据此确认回答正确。",
        "",
        "## 2. 汇总",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| 问题数 | {len(results)} |",
        f"| 有候选的问题 | {sum(bool(item['candidates']) for item in results)} |",
        f"| 无候选的问题 | {sum(not item['candidates'] for item in results)} |",
        f"| GOLD_UNCONFIRMED | {sum(item['gold_scope'] == 'GOLD_UNCONFIRMED' for item in results)} |",
        f"| 登记页首候选 | {sum(bool(item['candidates']) and item['candidates'][0]['registration_only'] for item in results)} |",
        "",
        "## 3. 逐题候选",
        "",
        "| 问题 | 约束 | 首选文件 | 首选位置 | 首选解释 |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        candidate = (result.get("candidates") or [{}])[0]
        facets = result.get("query_facets") or {}
        constraints = "; ".join(
            f"{key}={','.join(value) if isinstance(value, list) else value}"
            for key, value in facets.items()
            if value
        ) or "无显式约束"
        lines.append(
            f"| {result['question_id']} | `{constraints}` | {candidate.get('file_name') or '-'} | `{candidate.get('location') or {}}` | {', '.join(candidate.get('facet_reasons') or []) or '-'} |"
        )
    lines.extend(["", "## 4. 使用规则", ""])
    for result in results:
        lines.extend([f"### {result['question_id']}：{result['question']}", ""])
        if not result["candidates"]:
            lines.append("- 没有 Root-001 原子候选；不能据此断言知识库不存在答案。")
            lines.append("")
            continue
        for index, candidate in enumerate(result["candidates"][:5], start=1):
            label = "登记页/链接候选" if candidate["registration_only"] else "正文候选"
            lines.append(
                f"{index}. **{label}** `{candidate['file_name']}`，score={candidate['score']}，location=`{candidate['location']}`，facet=`{candidate['facet_reasons']}`"
            )
            lines.append(f"   - `{candidate['text'][:300]}`")
        lines.append("")
    lines.extend(
        [
            "## 5. 下一步",
            "",
            "1. 由业务负责人确认每题的正确文件和原文位置；",
            "2. 对 Root-002 资料单独建立同格式的 Shadow Gold 定位，不与 Root-001 混淆；",
            "3. 确认 `expected_files` 与 `expected_locations` 后，再计算 Recall@K、MRR 和 Evidence 命中率。",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
