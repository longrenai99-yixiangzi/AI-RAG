from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
RUNS = V26 / "live_shadow_runs.jsonl"
MODE = "LIVE_REQUEST_BACKGROUND_V2_6_1_DEV_SHADOW"


def main() -> int:
    rows = [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()] if RUNS.exists() else []
    raw = [row for row in rows if row.get("execution_mode") == MODE]
    latest = {}
    for row in raw:
        latest.setdefault(row.get("question_hash"), row)
    records = list(latest.values())
    runtime_errors = sum(bool(row.get("v2_error")) or row.get("v2_status") in {"SHADOW_ERROR", "ANSWER_VALIDATION_FAILED"} for row in records)
    report = {
        "schema_version": "knowledge_os_v2_6_1.live_shadow_status",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "execution_mode": MODE,
        "sample_basis": "Only actual requests received after V2.6.1 dev candidate wiring; historical V2.5 rows are excluded.",
        "raw_record_count": len(raw),
        "sample_size": len(records),
        "minimum_effective_sample": 30,
        "sample_gate": "PASS" if len(records) >= 30 else "SHADOW_INSUFFICIENT_SAMPLE",
        "candidate_revisions": dict(Counter(str(row.get("candidate_revision") or "UNKNOWN") for row in records)),
        "candidate_hashes": sorted({str(row.get("candidate_hash") or "") for row in records if row.get("candidate_hash")}),
        "candidate_delta": {"new_hit_candidates": sum(bool(row.get("new_hit_candidate")) for row in records), "lost_hit_candidates": sum(bool(row.get("lost_hit_candidate")) for row in records)},
        "rescue_usage": {"period_scope": sum(bool((row.get("period_scope_rescue") or {}).get("rescued_evidence_ids")) for row in records), "exact_named_source": sum(bool((row.get("named_source_rescue") or {}).get("rescued_evidence_ids")) for row in records)},
        "runtime_error_count": runtime_errors,
        "status": "LIVE_SHADOW_REVIEW_REQUIRED" if len(records) >= 30 and not runtime_errors else "SHADOW_RUNTIME_ERROR" if runtime_errors else "SHADOW_INSUFFICIENT_SAMPLE",
        "formal_8000_touched": False,
    }
    (V26 / "live_shadow_v2_6_1_dev_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# V2.6.1 开发候选 Live Shadow", "", "> 仅记录真实用户问题；不以自动题、历史 V2.5 记录或离线重放补样本。", "", f"- 有效样本：`{report['sample_size']}/30`", f"- 样本门：`{report['sample_gate']}`", f"- 运行状态：`{report['status']}`", f"- 运行异常：`{report['runtime_error_count']}`", "", "候选达到 30 条真实去重问题后，仍须人工核验 New/Lost Hit 与引用，不能直接解除发布闸门。", ""]
    (ROOT / "docs" / "LIVE_SHADOW_V2_6_1_DEV_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("sample_size", "sample_gate", "status", "runtime_error_count")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
