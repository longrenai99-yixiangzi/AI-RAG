from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"


def main() -> int:
    report = json.loads((V26 / "live_shadow_report.json").read_text(encoding="utf-8"))
    gate_path = V26 / "final_release_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).astimezone().isoformat()
    gate.update({"captured_at": now, "status": "BLOCKED", "final_status": "BLOCKED", "stop_after": "T03_LIVE_SHADOW_GATE", "gates": {**(gate.get("gates") or {}), "owner_source_version": "PASS", "live_shadow": report.get("shadow_gate"), "rollback_drill": "NOT_RUN_LIVE_SHADOW_BLOCKED", "candidate_integrity": "NOT_RUN_LIVE_SHADOW_BLOCKED", "8010_switch_authorization": "NOT_REQUESTED", "immediate_smoke": "NOT_RUN", "canary": "NOT_RUN"}, "top_blocking_issues": [f"Live Shadow 有效唯一问题样本为 {report.get('sample_size')}，低于最低门槛 {report.get('minimum_effective_sample')}。", "V2.5 答案引擎尚未接入 8010 Live Runtime；当前仅有 BM25 诊断预览。", "任务书禁止重复刷题、自动造题或以 Offline Shadow 冒充 Live Shadow；T04 及后续切换停止。"], "runtime": {**(gate.get("runtime") or {}), "8010_primary_unchanged": True, "8010_switch_performed": False, "8000_touched": False, "formal_qdrant_write": False, "formal_sqlite_write": False, "formal_index_switch": False, "v1_index_intact": True}, "next_action": "COLLECT_AT_LEAST_30_UNIQUE_REAL_REQUESTS_AND_WIRE_V2_5_LIVE_BRANCH"})
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": gate["status"], "stop_after": gate["stop_after"], "live_shadow": report["shadow_gate"], "sample_size": report["sample_size"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
