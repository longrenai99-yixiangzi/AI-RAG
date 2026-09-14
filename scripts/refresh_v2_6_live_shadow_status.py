from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
RUNS = V26 / "live_shadow_runs.jsonl"


def main() -> int:
    rows = [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()] if RUNS.exists() else []
    live_raw = [row for row in rows if row.get("execution_mode") == "LIVE_REQUEST_BACKGROUND_V2_5_SHADOW"]
    live_by_question = {}
    for row in live_raw:
        live_by_question.setdefault(row.get("question_hash"), row)
    live = list(live_by_question.values())
    now = datetime.now(timezone.utc).astimezone().isoformat()
    comparable = [row for row in live if row.get("source_agreement") is not None]
    v1_latencies = [float(row["v1_latency_ms"]) for row in live if row.get("v1_latency_ms") is not None]
    v2_latencies = [float(row["v2_latency_ms"]) for row in live if row.get("v2_latency_ms") is not None]
    v1_error_count = sum(bool(row.get("v1_error")) or row.get("v1_status") in {"ERROR", "ANSWER_VALIDATION_FAILED"} for row in live)
    v2_error_count = sum(bool(row.get("v2_error")) or row.get("v2_status") in {"SHADOW_ERROR", "ANSWER_VALIDATION_FAILED"} for row in live)
    critical_failures = v2_error_count
    if len(live) < 30:
        shadow_gate, stop_reason = "SHADOW_INSUFFICIENT_SAMPLE", "已接入 V2.5 后的 Live Shadow 唯一问题样本尚不足30。"
    elif critical_failures:
        shadow_gate, stop_reason = "SHADOW_GATE_FAIL", f"接入后唯一样本达到 {len(live)}，但发现 {critical_failures} 条 V2.5 Shadow 异常，需先修复并复核。"
    else:
        shadow_gate, stop_reason = "LIVE_SHADOW_REVIEW_REQUIRED", "样本达到30且无运行异常，但 New/Lost Hit 与 Citation 仍需人工核验。"
    report = {"schema_version": "knowledge_os_v2_6.live_shadow_report", "captured_at": now, "execution_mode": "LIVE_REQUEST_BACKGROUND_V2_5_SHADOW", "live_runtime_branching": True, "branch_status": "WIRED", "raw_record_count": len(live_raw), "duplicate_record_count": len(live_raw) - len(live), "sample_size": len(live), "sample_target": 100, "minimum_effective_sample": 30, "sample_basis": "only requests received after V2.5 background branch wiring; pre-wiring real requests remain historical baseline and are not relabeled", "sample_gate": "SHADOW_INSUFFICIENT_SAMPLE" if len(live) < 30 else "PASS", "v2_candidate_execution": "V2_5_DENSE_RRF_AND_ANSWER_SHADOW", "agreement": {"source_comparable_count": len(comparable), "source_agreement_count": sum(bool(row.get("source_agreement")) for row in comparable), "source_agreement_rate": round(sum(bool(row.get("source_agreement")) for row in comparable) / len(comparable), 4) if comparable else None, "section_agreement_count": sum(bool(row.get("section_agreement")) for row in live), "section_agreement_rate": None}, "new_hits": {"candidate_count": sum(bool(row.get("new_hit_candidate")) for row in live), "verified_count": 0, "verification": "REVIEW_REQUIRED"}, "lost_hits": {"candidate_count": sum(bool(row.get("lost_hit_candidate")) for row in live), "verified_count": 0, "verification": "REVIEW_REQUIRED"}, "critical_failures": critical_failures, "answer_rates": {"v1_answered_rate": round(sum(row.get("v1_answer_status") == "ANSWERED" or row.get("v1_status") == "ANSWERED" for row in live) / len(live), 4) if live else None, "v2_answered_rate": round(sum(row.get("v2_answer_status") == "ANSWERED" or row.get("v2_status") == "ANSWERED" for row in live) / len(live), 4) if live else None}, "latency": {"v1_p50_ms": round(statistics.median(v1_latencies), 3) if v1_latencies else None, "v1_p95_ms": round(sorted(v1_latencies)[max(0, int(len(v1_latencies) * 0.95) - 1)], 3) if v1_latencies else None, "v2_p50_ms": round(statistics.median(v2_latencies), 3) if v2_latencies else None, "v2_p95_ms": round(sorted(v2_latencies)[max(0, int(len(v2_latencies) * 0.95) - 1)], 3) if v2_latencies else None}, "errors": {"v1_error_count": v1_error_count, "v2_runtime_error_count": v2_error_count, "v2_branch_not_run_count": 0, "v1_error_rate": round(v1_error_count / len(live), 4) if live else None, "v2_error_rate": round(v2_error_count / len(live), 4) if live else None}, "shadow_gate": shadow_gate, "stop_reason": stop_reason, "formal_8000_touched": False, "records_path": str(RUNS)}
    if report["agreement"]["source_comparable_count"]:
        report["agreement"]["source_agreement_rate"] = round(report["agreement"]["source_agreement_count"] / report["agreement"]["source_comparable_count"], 4)
    (V26 / "live_shadow_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs" / "LIVE_SHADOW_REPORT.md").write_text("\n".join(["# V2.6 Live Shadow Report", "", f"- V2.5 后台分支：`{report['branch_status']}`", f"- 接入后有效样本：{report['sample_size']}（目标 100；最低有效样本 30）", f"- 样本门：`{report['sample_gate']}`", f"- Live Shadow Gate：`{report['shadow_gate']}`", "", "## 口径", "", report["sample_basis"], "", "## 当前限制", "", report["stop_reason"], "", "V1 继续给用户返回原有答案；V2.5 仅在后台运行并写入对照记录。New Hit、Lost Hit 和 Citation 变化必须人工审核，不能自动判定。", ""]))
    print(json.dumps({"branch_status": report["branch_status"], "live_sample_size": report["sample_size"], "sample_gate": report["sample_gate"], "shadow_gate": report["shadow_gate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
