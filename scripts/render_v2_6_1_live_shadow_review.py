from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
RUNS = V26 / "live_shadow_runs.jsonl"
MODE = "LIVE_REQUEST_BACKGROUND_V2_6_1_DEV_SHADOW"


def main() -> int:
    rows = [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = {}
    for row in rows:
        if row.get("execution_mode") == MODE:
            latest.setdefault(row.get("question_hash"), row)
    candidates = [row for row in latest.values() if row.get("new_hit_candidate") or row.get("lost_hit_candidate")]
    candidates.sort(key=lambda row: (0 if row.get("new_hit_candidate") else 1, str(row.get("timestamp") or "")))
    now = datetime.now(timezone.utc).astimezone().isoformat()
    records = []
    for index, row in enumerate(candidates, start=1):
        records.append({
            "review_id": f"V261-LSR-{index:03d}",
            "candidate_type": "NEW_HIT" if row.get("new_hit_candidate") else "LOST_HIT",
            "question": row.get("question"),
            "v1": {"status": row.get("v1_status"), "answer": row.get("v1_answer"), "citations": row.get("v1_citation") or []},
            "v2_6_1": {"status": row.get("v2_status"), "answer": row.get("v2_answer"), "citations": row.get("v2_citation") or [], "candidate_hash": row.get("candidate_hash"), "candidate_revision": row.get("candidate_revision"), "period_scope_rescue": row.get("period_scope_rescue") or {}, "named_source_rescue": row.get("named_source_rescue") or {}},
            "historical_shadow_run_id": row.get("shadow_run_id"),
            "manual_decision": None,
            "review_note": "核对两份答案的事实、问题范围和引用定位；不得只按回答状态判断。",
        })
    payload = {"schema_version": "knowledge_os_v2_6_1.live_shadow_manual_review", "captured_at": now, "execution_mode": MODE, "review_count": len(records), "new_hit_count": sum(row["candidate_type"] == "NEW_HIT" for row in records), "lost_hit_count": sum(row["candidate_type"] == "LOST_HIT" for row in records), "status": "PENDING_OWNER_REVIEW", "records": records}
    (V26 / "live_shadow_v2_6_1_manual_review.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.1 Live Shadow 人工核验", "", "> 仅列出状态发生变化的真实问题；人工判断以事实、范围和引用是否正确为准。", ""]
    for row in records:
        lines += [f"## {row['review_id']} · {row['candidate_type']}", "", f"**问题**：{row['question']}", "", f"**当前 Primary（{row['v1']['status']}）**", "", row["v1"]["answer"] or "（无正文）", "", f"**V2.6.1（{row['v2_6_1']['status']}）**", "", row["v2_6_1"]["answer"] or "（无正文）", "", "请填写：`VERIFIED_NEW_HIT`、`VERIFIED_LOST_HIT` 或 `NOT_VERIFIED`。", ""]
    (ROOT / "docs" / "LIVE_SHADOW_V2_6_1_MANUAL_REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"review_count": len(records), "new_hit_count": payload["new_hit_count"], "lost_hit_count": payload["lost_hit_count"], "status": payload["status"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
