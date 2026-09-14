from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"


def main() -> int:
    path = V26 / "live_shadow_manual_review.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).astimezone().isoformat()
    for row in payload.get("records") or []:
        if row.get("manual_decision") == "NOT_VERIFIED":
            row.update({"not_verified_semantics": "BOTH_REPLAY_ANSWERS_AND_SOURCE_LOCATIONS_INCORRECT", "review_note": "用户确认：两份重放答案的事实、来源定位等都不对。"})
    payload["not_verified_semantics"] = "USER_CONFIRMED_BOTH_ANSWERS_AND_SOURCE_LOCATIONS_INCORRECT"
    payload["semantics_recorded_at"] = now
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (V26 / "live_shadow_manual_review.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in payload.get("records") or []), encoding="utf-8")
    report_path = V26 / "live_shadow_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["manual_review"]["not_verified_semantics"] = "用户确认：16 条 NOT_VERIFIED 的两份重放答案及其来源定位均不正确。"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    gate_path = V26 / "final_release_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["top_blocking_issues"] = ["人工核验确认 VERIFIED_LOST_HIT=2，说明 V2.5 在两条真实问题上退化。", "人工核验确认 NOT_VERIFIED=16：两份重放答案的事实、来源定位等均不正确。", "历史 Shadow 异常=2，虽已修复代码，仍须保留审计并完成干净窗口验证。", "T04 Rollback Drill 及后续 8010 切换停止。"]
    gate["manual_review_semantics"] = "NOT_VERIFIED means both replay answers and source locations were user-confirmed incorrect."
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"not_verified_count": sum(row.get("manual_decision") == "NOT_VERIFIED" for row in payload.get("records") or []), "semantics": payload["not_verified_semantics"], "release_status": gate["status"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
