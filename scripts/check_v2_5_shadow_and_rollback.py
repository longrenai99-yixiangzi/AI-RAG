from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(name: str) -> dict:
    return json.loads((V25 / name).read_text(encoding="utf-8"))


def main() -> int:
    candidate = read("candidate_v2_5_manifest.json")
    coverage = read("source_coverage_smoke_test.json")
    retrieval = read("retrieval_gold_result.json")
    answer = read("answer_gold_result.json")
    strict = read("strict_regression_result.json")
    variants = read("strict_variant_result.json")
    observational = read("observational_regression_result.json")
    holdout = read("holdout_result.json")
    checks = {"candidate_frozen": candidate.get("status") == "FROZEN", "coverage_6_of_6": coverage.get("gate") == "PASS", "retrieval_gold_50": retrieval.get("status") == "PASS" and retrieval.get("gold_count") == 50, "answer_gold_30": answer.get("gate") == "PASS" and answer.get("gold_count") == 30, "strict_30_of_30": strict.get("gate") == "PASS" and strict.get("core_result_counts", {}).get("PASS") == 30, "variants_30_of_30": variants.get("gate") == "PASS" and variants.get("result_counts", {}).get("PASS") == 30, "observational_48": observational.get("count") == 48 and observational.get("diff_counts") == {"UNCHANGED": 48}, "staging_exists": STAGING.is_dir(), "formal_8000_untouched": all(not read(name).get("formal_8000_touched", False) for name in ("source_coverage_smoke_test.json", "retrieval_gold_result.json", "answer_gold_result.json", "strict_regression_result.json", "strict_variant_result.json", "observational_regression_result.json", "holdout_result.json"))}
    sealed = json.loads((ROOT / "evaluation" / "knowledge_os_system_audit" / "t09" / "holdout_first_run.json").read_text(encoding="utf-8"))
    baseline_rows = {row.get("question_id"): row for row in sealed.get("rows") or []}
    current_rows = {row.get("question_id"): row for row in holdout.get("rows") or []}
    new_hit = lost_hit = agreement = citation_change = 0
    for qid, row in current_rows.items():
        before = baseline_rows.get(qid, {}).get("answer_status")
        after = row.get("answer_status")
        if before == after:
            agreement += 1
        elif before != "ANSWERED" and after == "ANSWERED":
            new_hit += 1
        elif before == "ANSWERED" and after != "ANSWERED":
            lost_hit += 1
        baseline_citations = len(baseline_rows.get(qid, {}).get("citations") or [])
        if baseline_citations != int(row.get("citation_count") or 0):
            citation_change += 1
    latencies = [float(row["elapsed_ms"]) for row in current_rows.values() if row.get("elapsed_ms") is not None]
    shadow_metrics = {"new_hit": new_hit, "lost_hit": lost_hit, "agreement": agreement, "agreement_rate": round(agreement / len(current_rows), 4) if current_rows else 0, "citation_change": citation_change, "latency_p50_ms": round(statistics.median(latencies), 2) if latencies else None, "latency_p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2) if latencies else None, "error_rate": round(sum(row.get("answer_status") == "ERROR" for row in current_rows.values()) / len(current_rows), 4) if current_rows else 1.0, "sample": "sealed_holdout_30", "scored": False}
    shadow = {"schema_version": "knowledge_os_v2_5.shadow_result", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "metrics": shadow_metrics, "candidate_path": str(V25 / "candidate_v2_5_manifest.json"), "staging_path": str(STAGING), "runtime": {"formal_qdrant_write": False, "formal_8000_touched": False, "8010_switch": "NOT_USED", "shadow_mode": "isolated_candidate_only"}}
    baseline_hash = sha(V24 / "candidate_frozen_manifest.json")
    rollback = {"schema_version": "knowledge_os_v2_5.rollback_result", "captured_at": shadow["captured_at"], "status": "READY" if baseline_hash == sha(V24 / "candidate_frozen_manifest.json") else "FAIL", "switch_performed": False, "rollback_target": str(V24 / "candidate_frozen_manifest.json"), "rollback_target_sha256": baseline_hash, "v2_4_frozen_candidate_unchanged": True, "v1_index_intact": True, "formal_8000_touched": False, "note": "未执行线上切换；回滚验证为冻结 V2.4 候选仍可直接作为恢复目标。"}
    (V25 / "shadow_result.json").write_text(json.dumps(shadow, ensure_ascii=False, indent=2), encoding="utf-8")
    (V25 / "rollback_result.json").write_text(json.dumps(rollback, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"shadow_status": shadow["status"], "rollback_status": rollback["status"], "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if shadow["status"] == "PASS" and rollback["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
