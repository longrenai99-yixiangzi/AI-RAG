from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
RUNS = V26 / "live_shadow_runs.jsonl"
MODE = "LIVE_REQUEST_BACKGROUND_V2_6_2_DEV_SHADOW"


def main() -> int:
    rows = [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()] if RUNS.exists() else []
    raw = [row for row in rows if row.get("execution_mode") == MODE]
    latest = {}
    for row in raw:
        latest.setdefault(row.get("question_hash"), row)
    records = list(latest.values())
    errors = sum(bool(row.get("v2_error")) or row.get("v2_status") in {"SHADOW_ERROR", "ANSWER_VALIDATION_FAILED"} for row in records)
    report = {"schema_version": "knowledge_os_v2_6_2.live_shadow_status", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "execution_mode": MODE, "sample_basis": "Only actual requests received after V2.6.2 candidate wiring; V2.6.1 and V2.5 rows are excluded.", "raw_record_count": len(raw), "sample_size": len(records), "minimum_effective_sample": 30, "sample_gate": "PASS" if len(records) >= 30 else "SHADOW_INSUFFICIENT_SAMPLE", "candidate_revisions": dict(Counter(str(row.get("candidate_revision") or "UNKNOWN") for row in records)), "candidate_hashes": sorted({str(row.get("candidate_hash") or "") for row in records if row.get("candidate_hash")}), "new_hit_candidates": sum(bool(row.get("new_hit_candidate")) for row in records), "lost_hit_candidates": sum(bool(row.get("lost_hit_candidate")) for row in records), "runtime_error_count": errors, "status": "LIVE_SHADOW_REVIEW_REQUIRED" if len(records) >= 30 and not errors else "SHADOW_RUNTIME_ERROR" if errors else "SHADOW_INSUFFICIENT_SAMPLE", "formal_8000_touched": False}
    (V26 / "live_shadow_v2_6_2_dev_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs" / "LIVE_SHADOW_V2_6_2_DEV_REPORT.md").write_text("\n".join(["# V2.6.2 开发候选 Live Shadow", "", "> 仅统计 V2.6.2 接入后的真实问题；不混入 V2.6.1、V2.5 或离线回放。", "", f"- 有效样本：`{report['sample_size']}/30`", f"- 样本门：`{report['sample_gate']}`", f"- 运行异常：`{report['runtime_error_count']}`", f"- 状态：`{report['status']}`", ""]), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("sample_size", "sample_gate", "status", "runtime_error_count")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
