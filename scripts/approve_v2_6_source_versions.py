from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"


def main() -> int:
    approval_path = V26 / "owner_source_version_approval.json"
    policy_path = V26 / "source_version_policy.json"
    gate_path = V26 / "final_release_gate.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).astimezone().isoformat()
    for row in approval.get("records") or []:
        row.update({"semantic_version": None, "semantic_version_available": False, "version_policy": "CONTENT_HASH", "effective_status": "APPROVED", "reviewer": "USER_CONFIRMED", "reviewed_at": now, "approval_status": "APPROVED", "review_note": "用户明确确认：当前物理文件 SHA-256 作为 CONTENT_HASH effective_version；该确认不等于授权切换 8010。"})
    approval.update({"source_version_gate": "PASS", "approved_count": len(approval.get("records") or []), "pending_count": 0, "rejected_count": 0, "approved_by": "USER_CONFIRMED", "approved_at": now})
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["effective_version"].update({"current_status": "OWNER_APPROVED_CONTENT_HASH", "approved_at": now})
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate.update({"status": "IN_PROGRESS", "final_status": "IN_PROGRESS", "stop_after": None, "gates": {**(gate.get("gates") or {}), "owner_source_version": "PASS", "live_shadow": "NOT_RUN", "rollback_drill": "NOT_RUN", "candidate_integrity": "NOT_RUN", "8010_switch_authorization": "NOT_REQUESTED", "immediate_smoke": "NOT_RUN", "canary": "NOT_RUN"}, "top_blocking_issues": ["Source Version Gate 已通过；待执行 T02 Live Shadow 与 T04 Rollback Drill。", "8010 切换仍未授权，继续保持 V1 Primary。"], "next_action": "RUN_T02_LIVE_SHADOW"})
    approval_path.write_text(json.dumps(approval, ensure_ascii=False, indent=2), encoding="utf-8")
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_version_gate": approval["source_version_gate"], "approved_count": approval["approved_count"], "pending_count": approval["pending_count"], "next_action": gate["next_action"]}, ensure_ascii=False, indent=2))
    return 0 if approval["source_version_gate"] == "PASS" and approval["approved_count"] == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
