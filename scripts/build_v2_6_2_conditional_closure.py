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
    payload = {
        "schema_version": "knowledge_os_v2_6_2.conditional_closure",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "CONDITIONAL_CLOSURE_NOT_FORMAL_RELEASE",
        "candidate_hash": candidate["candidate_hash"],
        "evidence": {
            "manual_answer_gold": manual["decision_counts"],
            "candidate_integrity": integrity["status"],
            "compatibility_questions": compatibility["historical_question_count"],
            "compatibility_status_counts": compatibility["current_status_counts"],
            "current_live_shadow": {
                "sample_size": shadow["sample_size"],
                "minimum_effective_sample": shadow["minimum_effective_sample"],
                "sample_gate": shadow["sample_gate"],
            },
        },
        "formal_release_blockers": [
            "跨候选兼容性重放是离线诊断，不能替代当前候选的真实 Live Shadow。",
            "当前候选哈希下的有效 Live Shadow 样本尚未达到 30 条。",
            "真实 Rollback Drill 需要明确授权在 8010 执行受控切换；8000 继续禁止写入。",
        ],
        "allowed_next_steps": [
            "保留本条件性收口包作为内部评估结论，不执行切换。",
            "在当前候选下补足真实 Live Shadow 后，申请 8010 受控切换与 Rollback Drill 授权。",
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
        "# V2.6.2 条件性收口结论",
        "",
        "> 该结论可用于内部评估，不等于正式 Release 通过，不授权 8010 切换或 8000 写入。",
        "",
        f"- 候选哈希：`{payload['candidate_hash']}`",
        f"- 人工 Answer Gold：`{payload['evidence']['manual_answer_gold']}`",
        f"- 候选完整性：`{payload['evidence']['candidate_integrity']}`",
        f"- 历史真实问题兼容性重放：`{payload['evidence']['compatibility_questions']}` 条",
        f"- 当前候选 Live Shadow：`{payload['evidence']['current_live_shadow']['sample_size']}/{payload['evidence']['current_live_shadow']['minimum_effective_sample']}`",
        "",
        "## 正式 Release 仍需条件",
        "",
        *[f"- {item}" for item in payload["formal_release_blockers"]],
        "",
    ]), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "candidate_hash": payload["candidate_hash"], "out": str(out), "report": str(report)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
