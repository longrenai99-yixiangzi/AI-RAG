from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"

DECISIONS = {
    "LSR-001": "NOT_VERIFIED", "LSR-002": "NOT_VERIFIED", "LSR-003": "VERIFIED_NEW_HIT", "LSR-004": "NOT_VERIFIED", "LSR-005": "NOT_VERIFIED", "LSR-006": "NOT_VERIFIED", "LSR-007": "NOT_VERIFIED", "LSR-008": "VERIFIED_NEW_HIT", "LSR-009": "NOT_VERIFIED", "LSR-010": "VERIFIED_NEW_HIT", "LSR-011": "NOT_VERIFIED", "LSR-012": "NOT_VERIFIED", "LSR-013": "NOT_VERIFIED", "LSR-014": "VERIFIED_LOST_HIT", "LSR-015": "NOT_VERIFIED", "LSR-016": "NOT_VERIFIED", "LSR-017": "VERIFIED_LOST_HIT", "LSR-018": "NOT_VERIFIED", "LSR-019": "NOT_VERIFIED", "LSR-020": "NOT_VERIFIED", "LSR-021": "NOT_VERIFIED",
}


def main() -> int:
    path = V26 / "live_shadow_manual_review.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).astimezone().isoformat()
    for row in payload.get("records") or []:
        decision = DECISIONS.get(row.get("review_id"))
        if decision is None:
            raise RuntimeError(f"missing decision: {row.get('review_id')}")
        row.update({"manual_decision": decision, "reviewer": "USER_CONFIRMED", "reviewed_at": now})
    counts = {value: sum(row.get("manual_decision") == value for row in payload.get("records") or []) for value in ("VERIFIED_NEW_HIT", "VERIFIED_LOST_HIT", "NOT_VERIFIED", "PENDING")}
    payload.update({"manual_decision_status": "OWNER_REVIEWED", "reviewed_at": now, "decision_counts": counts, "verified_new_hit_count": counts["VERIFIED_NEW_HIT"], "verified_lost_hit_count": counts["VERIFIED_LOST_HIT"], "gate_impact": "FAIL_VERIFIED_LOST_HIT" if counts["VERIFIED_LOST_HIT"] else "REVIEWED_NO_VERIFIED_LOST_HIT"})
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (V26 / "live_shadow_manual_review.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in payload.get("records") or []), encoding="utf-8")
    report_path = V26 / "live_shadow_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.update({"manual_review": {"review_count": len(payload.get("records") or []), "decision_counts": counts, "verified_new_hit_count": counts["VERIFIED_NEW_HIT"], "verified_lost_hit_count": counts["VERIFIED_LOST_HIT"], "status": "OWNER_REVIEWED"}, "shadow_gate": "SHADOW_GATE_FAIL" if counts["VERIFIED_LOST_HIT"] or report.get("critical_failures", 0) else "LIVE_SHADOW_REVIEWED", "stop_reason": "人工核验确认 2 条 VERIFIED_LOST_HIT，且历史存在 2 条 Shadow 异常；按门禁停止，不进入 Rollback Drill。" if counts["VERIFIED_LOST_HIT"] else report.get("stop_reason")})
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    gate_path = V26 / "final_release_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate.update({"captured_at": now, "status": "BLOCKED", "final_status": "BLOCKED", "stop_after": "T03_LIVE_SHADOW_GATE", "gates": {**(gate.get("gates") or {}), "live_shadow": report["shadow_gate"], "rollback_drill": "NOT_RUN_LIVE_SHADOW_BLOCKED"}, "top_blocking_issues": ["人工核验确认 VERIFIED_LOST_HIT=2，说明 V2.5 在两条真实问题上退化。", "历史 Shadow 异常=2，虽已修复代码，仍须保留审计并完成干净窗口验证。", "T04 Rollback Drill 及后续 8010 切换停止。"], "next_action": "INVESTIGATE_TWO_VERIFIED_LOST_HITS_AND_RUN_CLEAN_SHADOW_WINDOW"})
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reviewed": len(payload.get("records") or []), "decision_counts": counts, "shadow_gate": report["shadow_gate"], "release_status": gate["status"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
