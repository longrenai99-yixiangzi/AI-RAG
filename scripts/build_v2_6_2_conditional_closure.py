from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"


def read(name: str) -> dict:
    return json.loads((V26 / name).read_text(encoding="utf-8"))


def main() -> int:
    candidate = read("remediation_candidate_v2_6_2.json")
    integrity = read("v2_6_2_candidate_integrity.json")
    compatibility = read("v2_6_2_compatibility_replay.json")
    manual = read("v2_6_2_manual_review_summary.json")
    shadow = read("live_shadow_v2_6_2_dev_report.json")
    owner_decision = read("v2_6_2_owner_release_decision_823d.json")
    t6 = read("v2_6_2_8010_rollback_drill.json")
    deployment_authorized = bool(owner_decision.get("deployment_authorized"))
    deployment_blockers = []
    if integrity.get("status") != "PASS":
        deployment_blockers.append("当前候选完整性检查尚未通过。")
    if shadow.get("current_candidate_hash") != candidate["candidate_hash"]:
        deployment_blockers.append("Live Shadow 报告与当前候选哈希不一致。")
    if shadow.get("sample_gate") != "PASS":
        deployment_blockers.append("当前候选的 Live Shadow 样本门尚未通过。")
    if compatibility.get("current_candidate_hash") != candidate["candidate_hash"]:
        deployment_blockers.append("T5离线诊断报告与当前候选哈希不一致。")
    if t6.get("status") != "PASS" or t6.get("candidate_hash") != candidate["candidate_hash"]:
        deployment_blockers.append("当前候选哈希下的 8010 回滚验证尚未通过。")
    if owner_decision.get("candidate_hash") != candidate["candidate_hash"]:
        deployment_blockers.append("Owner 决定与当前候选哈希不一致。")
    if not deployment_authorized:
        deployment_blockers.append("Owner 已批准候选版本，但尚未授权启动、写入或切换 8000。")
    version_approved = owner_decision.get("decision") == "APPROVED_VERSION_NOT_DEPLOYED"
    payload = {
        "schema_version": "knowledge_os_v2_6_2.conditional_closure",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "APPROVED_VERSION_NOT_DEPLOYED" if version_approved else "CONDITIONAL_CLOSURE_NOT_RELEASE_APPROVED",
        "candidate_hash": candidate["candidate_hash"],
        "owner_release_decision": owner_decision.get("decision"),
        "deployment_authorized": deployment_authorized,
        "evidence": {
            "owner_review_decision_counts": manual["decision_counts"],
            "candidate_integrity": integrity["status"],
            "compatibility_questions": compatibility["historical_question_count"],
            "compatibility_status_counts": compatibility["current_status_counts"],
            "current_live_shadow": {
                "sample_size": shadow["sample_size"],
                "minimum_effective_sample": shadow["minimum_effective_sample"],
                "sample_gate": shadow["sample_gate"],
            },
        },
        "deployment_blockers": deployment_blockers,
        "allowed_next_steps": [
            "保留823d版本批准结果和未部署状态；不写入、启动或切换8000。",
            "如需正式部署，先准备明确的部署与恢复方案，再单独取得8000操作授权。",
        ],
        "runtime": {
            "8010_switch_performed": False,
            "8010_switch_authorized": False,
            "formal_8000_touched": False,
        },
    }
    out = V26 / "v2_6_2_conditional_closure.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ROOT / "docs" / "V2_6_2_CONDITIONAL_CLOSURE.md"
    report.write_text("\n".join([
        "# V2.6.2 已批准候选部署状态",
        "",
        "> 候选版本823d已获批准，但当前未部署。此摘要不授权8000启动、写入或切换。",
        "",
        f"- 候选哈希：{payload['candidate_hash']}",
        f"- Owner版本决定：{payload['owner_release_decision']}；部署授权：{payload['deployment_authorized']}",
        f"- Owner复核台账决策分布（不等于当前Gold重放条数）：`{payload['evidence']['owner_review_decision_counts']}`",
        f"- 候选完整性：`{payload['evidence']['candidate_integrity']}`",
        f"- 历史真实问题兼容性重放：`{payload['evidence']['compatibility_questions']}` 条",
        f"- 当前候选 Live Shadow：`{payload['evidence']['current_live_shadow']['sample_size']}/{payload['evidence']['current_live_shadow']['minimum_effective_sample']}`",
        "",
        "## 部署限制",
        "",
        *[f"- {item}" for item in payload["deployment_blockers"]],
        "",
    ]), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "candidate_hash": payload["candidate_hash"], "out": str(out), "report": str(report)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
