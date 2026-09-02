from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.ingestion.atomic_search import query_facets, search_atomic_evidence


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay business questions against Shadow atomic evidence.")
    parser.add_argument("--records", type=Path, default=PROJECT_ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl")
    parser.add_argument("--questions", type=Path, default=PROJECT_ROOT / "evaluation" / "v1_business_acceptance")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "evaluation" / "atomic_evidence")
    args = parser.parse_args()
    records = [json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = []
    for path in sorted(args.questions.glob("BA-*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        cases.append({"question_id": value.get("question_id") or path.stem, "question": value.get("question", ""), "baseline_status": value.get("final_status"), "baseline_route": value.get("route")})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        facets = query_facets(case["question"])
        hits = search_atomic_evidence(case["question"], records, limit=5)
        top = []
        for item in hits:
            record = item["record"]
            text = str(record.get("text") or "")
            registration_only = record.get("file_type") == ".md" and any(marker in text for marker in ("file://", "[[", "原始资料", "原库业务目录"))
            top.append({
                "score": item["score"],
                "matched_terms": item["matched_terms"],
                "query_facets": facets,
                "identity_match_terms": item.get("identity_match_terms", []),
                "phrase_matches": item.get("phrase_matches", []),
                "year_matches": item.get("year_matches", []),
                "metric_matches": item.get("metric_matches", []),
                "text_metric_matches": item.get("text_metric_matches", []),
                "entity_matches": item.get("entity_matches", []),
                "text_entity_matches": item.get("text_entity_matches", []),
                "field_matches": item.get("field_matches", []),
                "facet_reasons": item.get("facet_reasons", []),
                "evidence_id": record.get("evidence_id"),
                "file_name": record.get("file_name"),
                "source_path": record.get("source_path"),
                "location": record.get("location"),
                "granularity": record.get("granularity"),
                "registration_only_candidate": registration_only,
                "text": text[:900],
            })
        if not top:
            coverage_status = "NO_ATOMIC_CANDIDATE"
        elif top[0]["registration_only_candidate"]:
            coverage_status = "REGISTRATION_ONLY_CANDIDATE"
        elif not top[0]["identity_match_terms"]:
            coverage_status = "LOW_CONFIDENCE_CONTENT_CANDIDATE"
        else:
            coverage_status = "BODY_ATOMIC_CANDIDATE"
        results.append({**case, "coverage_status": coverage_status, "candidate_count": len(hits), "top_candidates": top})

    output_path = args.output_dir / "real_business_queries.jsonl"
    output_path.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in results) + "\n", encoding="utf-8")
    report_path = PROJECT_ROOT / "docs" / "KNOWLEDGE_ATOMIC_QUERY_REPLAY_REPORT.md"
    report_path.write_text(render_report(args.records, results, output_path), encoding="utf-8")
    print(json.dumps({"questions": len(results), "records": len(records), "coverage_status": _counts(results), "output": str(output_path.resolve()), "report": str(report_path.resolve())}, ensure_ascii=False, indent=2))
    return 0


def _counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        status = result["coverage_status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


def render_report(records_path: Path, results: list[dict[str, Any]], output_path: Path) -> str:
    lines = [
        "# Shadow 原子证据真实业务问题回放报告",
        "",
        "> 本回放只对原子证据 JSONL 做透明关键词匹配，不调用 LLM、不重新运行向量检索，也不把关键词候选直接视为正确答案。",
        "",
        f"- 原子证据：`{records_path.resolve()}`",
        f"- 回放结果：`{output_path.resolve()}`",
        f"- 问题数量：{len(results)}",
        "",
        "## 1. 回放结果",
        "",
        "| 问题 | 基线状态 | 原子层结果 | 候选数 | 最高候选 | 位置 |",
        "|---|---|---|---:|---|---|",
    ]
    for result in results:
        candidate = (result.get("top_candidates") or [{}])[0]
        lines.append(
            f"| {result['question_id']} | {result.get('baseline_status') or '-'} | {result['coverage_status']} | {result['candidate_count']} | {candidate.get('file_name') or '-'} | `{candidate.get('location') or {}}` |"
        )
    lines.extend(["", "## 2. 解释", "", "- `BODY_ATOMIC_CANDIDATE`：目标词也出现在文件名、标题或路径中，原子层找到了正文候选，仍需人工确认是否就是回答问题的证据。", "- `LOW_CONFIDENCE_CONTENT_CANDIDATE`：只命中正文中的通用词，不能据此认定找到了答案。", "- `REGISTRATION_ONLY_CANDIDATE`：只找到登记页、链接或 Wikilink，不能当作外部正文。", "- `NO_ATOMIC_CANDIDATE`：当前 Root-001 的 Markdown/XLSX 原子层没有找到候选，不代表全库绝对没有答案；还可能在未纳入的 PDF/DOCX/PPTX、外部 Root-002 或尚未拆解的内容中。", "", "## 3. 结论", ""])
    counts = _counts(results)
    lines.extend(f"- `{status}`：{count} 题" for status, count in sorted(counts.items()))
    lines.extend(["", "当前回放只能证明原子证据层的覆盖边界，不能替代正式 Retriever 评价。下一阶段应先扩展 PDF/DOCX/PPTX 的细粒度证据，再做 Shadow A/B 检索。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
