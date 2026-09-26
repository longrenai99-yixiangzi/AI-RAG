from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.trial.live_shadow_v25 import RUNTIME_CODE_SHA256

V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
RUNS = V26 / "live_shadow_runs.jsonl"
MODE = "LIVE_REQUEST_BACKGROUND_V2_6_2_DEV_SHADOW"
MANIFEST = V26 / "remediation_candidate_v2_6_2.json"
EXCLUSIONS = V26 / "v2_6_2_owner_exclusions.json"
MANUAL_REVIEW = V26 / "v2_6_2_live_shadow_review_823d.json"


def _known_drill_query_ids(candidate_hash: str, reports: list[Path]) -> set[str]:
    query_ids = set()
    for path in reports:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if report.get("candidate_hash") != candidate_hash:
            continue
        for step in report.get("steps") or []:
            if step.get("step") not in {"V262_SMOKE", "V262_CANARY", "V1_RESTORATION_SMOKE"}:
                continue
            query_ids.update(
                str(row["query_run_id"])
                for row in step.get("results") or []
                if row.get("query_run_id")
            )
    return query_ids


def _exclude_owner_invalid_questions(rows: list[dict], excluded_hashes: set[str]) -> tuple[list[dict], list[dict]]:
    excluded = [row for row in rows if str(row.get("question_hash") or "") in excluded_hashes]
    eligible = [row for row in rows if str(row.get("question_hash") or "") not in excluded_hashes]
    return eligible, excluded


def _runtime_code_counts(rows: list[dict]) -> dict[str, int]:
    return dict(Counter(str(row.get("runtime_code_sha256") or "UNRECORDED") for row in rows))


def _reviewed_hit_query_ids(review: dict, candidate_hash: str, runtime_code_hash: str) -> set[str]:
    if review.get("candidate_hash") != candidate_hash:
        return set()
    reviewed = set()
    for row in review.get("records") or []:
        disposition = row.get("disposition")
        if disposition == "FALSE_LOST_HIT":
            reviewed.add(str(row.get("query_run_id") or ""))
        elif disposition == "FALSE_NEW_HIT_REMEDIATED" and row.get("remediated_runtime_code_sha256") == runtime_code_hash:
            reviewed.add(str(row.get("query_run_id") or ""))
    return reviewed


def main() -> int:
    rows = [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()] if RUNS.exists() else []
    candidate_hash = json.loads(MANIFEST.read_text(encoding="utf-8")).get("candidate_hash")
    raw = [row for row in rows if row.get("execution_mode") == MODE and row.get("candidate_hash") == candidate_hash]
    drill_ids = _known_drill_query_ids(candidate_hash, list(V26.glob("v2_6_2_8010_rollback_drill*.json")))
    excluded_tests = [row for row in raw if str(row.get("query_run_id") or "") in drill_ids]
    after_drill = [row for row in raw if str(row.get("query_run_id") or "") not in drill_ids]
    exclusion_doc = json.loads(EXCLUSIONS.read_text(encoding="utf-8")) if EXCLUSIONS.exists() else {}
    owner_excluded_hashes = {str(item.get("question_hash") or "") for item in exclusion_doc.get("records") or []}
    eligible, excluded_owner_invalid = _exclude_owner_invalid_questions(after_drill, owner_excluded_hashes)
    current_runtime_code = RUNTIME_CODE_SHA256
    latest = {}
    for row in eligible:
        question_hash = row.get("question_hash")
        previous = latest.get(question_hash)
        if previous is None or str(row.get("timestamp") or "") >= str(previous.get("timestamp") or ""):
            latest[question_hash] = row
    records = list(latest.values())
    errors = sum(bool(row.get("v2_error")) or row.get("v2_status") in {"SHADOW_ERROR", "ANSWER_VALIDATION_FAILED"} for row in records)
    manual_review = json.loads(MANUAL_REVIEW.read_text(encoding="utf-8")) if MANUAL_REVIEW.exists() else {}
    reviewed_ids = _reviewed_hit_query_ids(manual_review, candidate_hash, current_runtime_code)
    reviewed_new_hits = sum(bool(row.get("new_hit_candidate")) and str(row.get("query_run_id") or "") in reviewed_ids for row in records)
    reviewed_lost_hits = sum(bool(row.get("lost_hit_candidate")) and str(row.get("query_run_id") or "") in reviewed_ids for row in records)
    unreviewed_new_hits = sum(bool(row.get("new_hit_candidate")) and str(row.get("query_run_id") or "") not in reviewed_ids for row in records)
    unreviewed_lost_hits = sum(bool(row.get("lost_hit_candidate")) and str(row.get("query_run_id") or "") not in reviewed_ids for row in records)
    if errors:
        status = "SHADOW_RUNTIME_ERROR"
    elif len(records) < 30:
        status = "SHADOW_INSUFFICIENT_SAMPLE"
    elif unreviewed_new_hits or unreviewed_lost_hits:
        status = "LIVE_SHADOW_REVIEW_REQUIRED"
    else:
        status = "LIVE_SHADOW_REVIEWED_WITH_REMEDIATION"
    report = {
        "schema_version": "knowledge_os_v2_6_2.live_shadow_status",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "execution_mode": MODE,
        "current_candidate_hash": candidate_hash,
        "current_runtime_code_sha256": current_runtime_code,
        "sample_basis": "Count distinct real background-shadow requests for the current candidate hash; runtime code SHA is retained as lineage but does not reset the sample-volume gate. Rollback-drill Smoke/Canary and Owner-invalid question hashes are excluded.",
        "raw_record_count": len(raw),
        "excluded_drill_test_record_count": len(excluded_tests),
        "excluded_owner_invalid_record_count": len(excluded_owner_invalid),
        "excluded_owner_invalid_question_count": len({str(row.get("question_hash") or "") for row in excluded_owner_invalid}),
        "effective_raw_record_count": len(eligible),
        "sample_size": len(records),
        "minimum_effective_sample": 30,
        "sample_gate": "PASS" if len(records) >= 30 else "SHADOW_INSUFFICIENT_SAMPLE",
        "runtime_code_record_counts": _runtime_code_counts(records),
        "current_runtime_code_record_count": sum(row.get("runtime_code_sha256") == current_runtime_code for row in records),
        "manual_review_artifact": str(MANUAL_REVIEW.relative_to(ROOT)) if MANUAL_REVIEW.exists() else None,
        "candidate_revisions": dict(Counter(str(row.get("candidate_revision") or "UNKNOWN") for row in records)),
        "candidate_hashes": sorted({str(row.get("candidate_hash") or "") for row in records if row.get("candidate_hash")}),
        "new_hit_candidates": sum(bool(row.get("new_hit_candidate")) for row in records),
        "lost_hit_candidates": sum(bool(row.get("lost_hit_candidate")) for row in records),
        "reviewed_new_hit_candidates": reviewed_new_hits,
        "reviewed_lost_hit_candidates": reviewed_lost_hits,
        "unreviewed_new_hit_candidates": unreviewed_new_hits,
        "unreviewed_lost_hit_candidates": unreviewed_lost_hits,
        "runtime_error_count": errors,
        "status": status,
        "formal_8000_touched": False,
    }
    (V26 / "live_shadow_v2_6_2_dev_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs" / "LIVE_SHADOW_V2_6_2_DEV_REPORT.md").write_text("\n".join([
        "# V2.6.2 开发候选 Live Shadow",
        "",
        "> 仅统计当前候选 hash 下的后台 Shadow 真实问题；不混入历史 hash、回滚演练 Smoke/Canary、Owner 已排除问题或离线回放。",
        "",
        f"- 有效样本：{report["sample_size"]}/30",
        f"- 回滚演练测试记录（已排除）：{report["excluded_drill_test_record_count"]}",
        f"- Owner 无效题记录（已排除）：{report["excluded_owner_invalid_record_count"]}（{report["excluded_owner_invalid_question_count"]} 个题目）",
        f"- 当前运行时代码 SHA-256：`{report["current_runtime_code_sha256"]}`",
        f"- 样本运行代码指纹分布（仅追溯，不改变计数）：`{report["runtime_code_record_counts"]}`",
        f"- New/Lost Hit：{report["new_hit_candidates"]}/{report["lost_hit_candidates"]}；已复核：{report["reviewed_new_hit_candidates"]}/{report["reviewed_lost_hit_candidates"]}",
        f"- 样本门：{report["sample_gate"]}",
        f"- 运行异常：{report["runtime_error_count"]}",
        f"- 状态：{report["status"]}",
        "",
    ]), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("sample_size", "excluded_drill_test_record_count", "excluded_owner_invalid_record_count", "excluded_owner_invalid_question_count", "runtime_code_record_counts", "current_runtime_code_sha256", "new_hit_candidates", "lost_hit_candidates", "reviewed_new_hit_candidates", "reviewed_lost_hit_candidates", "unreviewed_new_hit_candidates", "unreviewed_lost_hit_candidates", "sample_gate", "status", "runtime_error_count")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
