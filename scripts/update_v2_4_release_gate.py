from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    strict = read(V24 / "strict_regression_result.json")
    obs = read(V24 / "observational_regression_result.json")
    candidate = read(V24 / "candidate_frozen_manifest.json")
    validator = read(V23 / "validator_report.json")
    answer = read(V23 / "answer_gold_snapshot.json")
    dense = read(V23 / "dense_embedding_report.json")
    strict_pass = strict.get("gate") == "PASS"
    variant_pass = float(strict.get("variant_stability_rate") or 0) >= 0.90
    now = datetime.now(timezone.utc).astimezone().isoformat()
    issues = []
    if not strict_pass:
        issues.append(f"Strict Regression Gate 未通过：核心 PASS {strict.get('core_result_counts', {}).get('PASS', 0)}/30，NOT_EVALUABLE {strict.get('core_result_counts', {}).get('NOT_EVALUABLE', 0)}，通过率 {strict.get('core_pass_rate')}。")
    if not variant_pass:
        issues.append(f"Variant Stability Rate 为 {strict.get('variant_stability_rate')}，低于建议门槛 0.90。")
    if obs.get("diff_counts") != {"UNCHANGED": 48}:
        issues.append(f"Observational Regression 出现行为变化：{obs.get('diff_counts')}。")
    issues.append("Holdout、Shadow、Rollback 因 Strict Regression 未通过而未运行。")
    gate = {
        "schema_version": "knowledge_os_v2_4.release_gate",
        "captured_at": now,
        "recommendation": "REJECT",
        "gates": {"cuda": "PASS", "dense": "PASS" if dense.get("status") == "PASS" else "FAIL", "retrieval_gold": "PASS" if (V23 / "retrieval_gold_snapshot.json").exists() else "FAIL", "answer_gold": "PASS" if answer.get("confirmed") == 30 else "FAIL", "retrieval_candidate": "PASS" if candidate.get("status") == "FROZEN" else "FAIL", "validator": validator.get("status", "NOT_RUN"), "strict_regression": "PASS" if strict_pass else "FAIL", "variant_stability": "PASS" if variant_pass else "FAIL", "observational_regression": obs.get("status", "NOT_RUN"), "holdout": "NOT_RUN_STRICT_REGRESSION_BLOCKED", "shadow": "NOT_RUN_STRICT_REGRESSION_BLOCKED", "rollback": "NOT_RUN_STRICT_REGRESSION_BLOCKED"},
        "strict_regression": {"core_count": strict.get("core_count"), "core_result_counts": strict.get("core_result_counts"), "core_pass_rate": strict.get("core_pass_rate"), "variant_count": strict.get("variant_count"), "variant_result_counts": strict.get("variant_result_counts"), "variant_stability_rate": strict.get("variant_stability_rate"), "critical_failures": strict.get("critical_failures"), "unsupported_claims": strict.get("unsupported_claims")},
        "observational_regression": {"count": obs.get("count"), "v2_3_status_counts": obs.get("v2_3_status_counts"), "v2_4_status_counts": obs.get("v2_4_status_counts"), "diff_counts": obs.get("diff_counts"), "accuracy_gate": "NOT_APPLICABLE"},
        "top_3_blocking_issues": issues[:3],
        "runtime": {"8010_switch_allowed": False, "8000_touched": False, "formal_qdrant_write": False, "candidate_parameter_changes": False, "v1_index_intact": True},
    }
    V24.mkdir(parents=True, exist_ok=True)
    (V24 / "release_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"release_gate": gate, "candidate_frozen_manifest": candidate, "strict_regression": strict, "observational_regression": obs, "next_action": "补齐或替换 6 条当前范围外的 Strict Gold 证据，建立可评估的 30/30 严格回归集；在此之前不运行 Holdout。"}
    (ROOT / "docs" / "KNOWLEDGE_OS_V2_4_FINAL_REPORT.md").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
