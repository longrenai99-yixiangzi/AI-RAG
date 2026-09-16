from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "evaluation" / "knowledge_os_v2_6" / "live_shadow_runs.jsonl"
OUT = ROOT / "evaluation" / "knowledge_os_v2_6" / "historical_live_shadow_questions.md"


def main() -> int:
    rows = [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest: dict[str, dict] = {}
    for row in rows:
        question_hash = str(row.get("question_hash") or "")
        question = str(row.get("question") or "").strip()
        if not question:
            continue
        key = question_hash or question
        latest[key] = row
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in latest.values():
        grouped[str(row.get("candidate_hash") or "UNKNOWN")].append(row)
    lines = [
        "# 历史 Live Shadow 真实问题清单",
        "",
        f"> 导出时间：{datetime.now(timezone.utc).astimezone().isoformat()}",
        f"> 去重问题数：{len(latest)}；仅导出历史记录，不自动重新提交。",
        "",
    ]
    for candidate_hash, items in sorted(grouped.items(), key=lambda pair: pair[0]):
        items.sort(key=lambda row: str(row.get("timestamp") or ""))
        lines += [f"## 候选哈希 `{candidate_hash}`（{len(items)} 条）", ""]
        for index, row in enumerate(items, 1):
            lines.append(f"{index}. {row['question']}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"path": str(OUT), "unique_questions": len(latest), "candidate_groups": len(grouped)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
