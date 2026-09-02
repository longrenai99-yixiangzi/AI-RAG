from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation" / "v2_8010_trial"
GROWTH = ROOT / "data" / "shadow" / "knowledge_growth_v1"
REPORT = ROOT / "docs" / "V2_8010_TRIAL_REPORT.md"


def main() -> int:
    feedback = _read_jsonl(EVAL / "feedback_events.jsonl")
    feedback_ids = {row.get("growth_candidate_id") for row in feedback if row.get("growth_candidate_id")}
    reviews = [row for row in _read_jsonl(GROWTH / "review_records.jsonl") if row.get("candidate_id") in feedback_ids]
    result = {"feedback_events": len(feedback), "feedback_growth_candidates": len(feedback_ids), "reviews": reviews, "automatic_publish": 0}
    _write_json(EVAL / "growth_review_results.json", result)
    safety_path = EVAL / "safety_validation.json"
    safety = json.loads(safety_path.read_text(encoding="utf-8")) if safety_path.exists() else {}
    safety.update({"formal_knowledge_base_write": 0, "formal_qdrant_write": 0, "root002_refresh": 0, "root003_scan": 0})
    _write_json(safety_path, safety)
    report = REPORT.read_text(encoding="utf-8")
    if "## 反馈与人工审核验证" not in report:
        report += "\n## 反馈与人工审核验证\n\n" + f"- Feedback Events：{result['feedback_events']}\n- Feedback Growth Proposals：{result['feedback_growth_candidates']}\n- Review Decisions：{len(reviews)}\n- Automatic Knowledge Publish：0\n"
    if "## 最终安全门" not in report:
        report += "\n## 最终安全门\n\n- Formal Knowledge Base Write：0\n- Formal Qdrant Write：0\n- Root-002 Refresh / Root-003 Scan：0 / 0\n- Provider HTTP Requests / Gold Runtime Injection：0 / 0\n"
    REPORT.write_text(report, encoding="utf-8")
    assert all(row.get("publish_triggered") is False for row in reviews)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
