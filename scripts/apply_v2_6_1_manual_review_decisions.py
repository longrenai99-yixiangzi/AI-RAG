from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
REVIEW = V26 / "live_shadow_v2_6_1_manual_review.json"
DECISIONS = {
    "V261-LSR-001": "VERIFIED_NEW_HIT",
    "V261-LSR-002": "NOT_VERIFIED",
    "V261-LSR-003": "NOT_VERIFIED",
    "V261-LSR-004": "NOT_VERIFIED",
    "V261-LSR-005": "NOT_VERIFIED",
    "V261-LSR-006": "NOT_VERIFIED",
    "V261-LSR-007": "NOT_VERIFIED",
    "V261-LSR-008": "NOT_VERIFIED",
    "V261-LSR-009": "VERIFIED_NEW_HIT",
    "V261-LSR-010": "NOT_VERIFIED",
    "V261-LSR-011": "NOT_VERIFIED",
    "V261-LSR-012": "NOT_VERIFIED",
    "V261-LSR-013": "NOT_VERIFIED",
    "V261-LSR-014": "NOT_VERIFIED",
    "V261-LSR-015": "NOT_VERIFIED",
    "V261-LSR-016": "NOT_VERIFIED",
    "V261-LSR-017": "NOT_VERIFIED",
    "V261-LSR-018": "NOT_VERIFIED",
    "V261-LSR-019": "NOT_VERIFIED",
    "V261-LSR-020": "NOT_VERIFIED",
    "V261-LSR-021": "NOT_VERIFIED",
}


def main() -> int:
    payload = json.loads(REVIEW.read_text(encoding="utf-8"))
    rows = payload.get("records") or []
    known_ids = {row.get("review_id") for row in rows}
    unknown_ids = sorted(set(DECISIONS) - known_ids)
    now = datetime.now(timezone.utc).astimezone().isoformat()
    for row in rows:
        decision = DECISIONS.get(row.get("review_id"))
        if decision:
            row.update({"manual_decision": decision, "reviewer": "USER_CONFIRMED", "reviewed_at": now})
    counts = Counter(str(row.get("manual_decision") or "PENDING") for row in rows)
    payload.update({"status": "OWNER_REVIEWED", "reviewed_at": now, "decision_counts": dict(counts), "unknown_decision_ids": unknown_ids, "pending_count": counts.get("PENDING", 0), "verified_new_hit_count": counts.get("VERIFIED_NEW_HIT", 0), "verified_lost_hit_count": counts.get("VERIFIED_LOST_HIT", 0), "not_verified_count": counts.get("NOT_VERIFIED", 0), "decision_note": "User supplied decisions applied. V261-LSR-021 was supplied but is not present in the current 20-record candidate list."})
    REVIEW.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REVIEW.with_suffix(".jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    report_path = V26 / "live_shadow_v2_6_1_dev_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["manual_review"] = {"status": "OWNER_REVIEWED", "review_count": len(rows), "decision_counts": dict(counts), "unknown_decision_ids": unknown_ids, "pending_count": counts.get("PENDING", 0), "verified_lost_hit_count": counts.get("VERIFIED_LOST_HIT", 0)}
    report["status"] = "LIVE_SHADOW_REVIEWED_NO_VERIFIED_LOST_HIT" if not unknown_ids and not counts.get("PENDING") and not counts.get("VERIFIED_LOST_HIT") else "LIVE_SHADOW_REVIEW_REQUIRED"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.1 Live Shadow 人工核验结果", "", f"- 状态：`{payload['status']}`", f"- 已核验：`{len(rows)}` 条", f"- 结论计数：`{dict(counts)}`", f"- 未匹配编号：`{unknown_ids or '无'}`", "", "`NOT_VERIFIED` 仍表示该条不能作为正确答案或正确引用使用；不会被提升为 Gate PASS。"]
    (ROOT / "docs" / "LIVE_SHADOW_V2_6_1_MANUAL_REVIEW_RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "review_count": len(rows), "decision_counts": dict(counts), "unknown_decision_ids": unknown_ids}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
