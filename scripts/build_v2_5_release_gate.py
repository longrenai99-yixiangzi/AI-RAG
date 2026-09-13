from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"


def read(name: str) -> dict:
    return json.loads((V25 / name).read_text(encoding="utf-8"))


def main() -> int:
    now = datetime.now(timezone.utc).astimezone().isoformat()
    embedding = read("embedding_increment_report.json")
    retrieval = read("retrieval_gold_result.json")
    retrieval_cmp = read("retrieval_v2_4_vs_v2_5.json")
    answer = read("answer_gold_result.json")
    strict = read("strict_regression_result.json")
    variants = read("strict_variant_result.json")
    coverage = read("source_coverage_smoke_test.json")
    observational = read("observational_regression_result.json")
    holdout = read("holdout_result.json")
    shadow = read("shadow_result.json")
    rollback = read("rollback_result.json")
    v24_strict = json.loads((V24 / "strict_regression_result.json").read_text(encoding="utf-8"))
    original_ids = {"SRG-001", "SRG-002", "SRG-004", "SRG-005", "SRG-006", "SRG-008"}
    old_rows = {row["question_id"]: row for row in v24_strict.get("records", []) if row.get("question_id") in original_ids}
    new_rows = {row["question_id"]: row for row in strict.get("records", []) if row.get("question_id") in original_ids}
    source_audit = json.loads((V25 / "owner_gold_source_audit.json").read_text(encoding="utf-8"))
    resolution = []
    for record in source_audit.get("records") or []:
        rid = record["regression_id"]
        resolution.append({"regression_id": rid, "source_answer_gold_id": next((row.get("source_answer_gold_id") for row in new_rows.values() if row.get("question_id") == rid), None), "source": record.get("owner_gold_source"), "section": record.get("owner_gold_section"), "v2_4_result": old_rows.get(rid, {}).get("result", "NOT_EVALUABLE"), "v2_5_result": new_rows.get(rid, {}).get("result"), "v2_5_missing_claims": new_rows.get(rid, {}).get("missing_claims", []), "v2_5_citation_valid": new_rows.get(rid, {}).get("citation_valid", False), "v2_5_actual_sections": new_rows.get(rid, {}).get("actual_sections", [])})
    gates = {"cuda": "PASS" if embedding.get("status") == "PASS" else "FAIL", "dense": "PASS" if embedding.get("status") == "PASS" and embedding.get("new_vectors_pending") == 0 and embedding.get("old_vectors_equal") is True else "FAIL", "retrieval_gold": "PASS" if retrieval.get("status") == "PASS" and retrieval.get("gold_count") == 50 else "FAIL", "retrieval_regression": retrieval_cmp.get("gate", "FAIL"), "answer_gold": "PASS" if answer.get("gate") == "PASS" and answer.get("gold_count") == 30 else "FAIL", "owner_gold_coverage": coverage.get("gate", "FAIL"), "strict_regression": "PASS" if strict.get("gate") == "PASS" and strict.get("core_result_counts", {}).get("NOT_EVALUABLE") == 0 and strict.get("core_result_counts", {}).get("FAIL") == 0 and strict.get("unsupported_claims") == 0 and strict.get("wrong_scope") == 0 else "FAIL", "variant_stability": "PASS" if variants.get("gate") == "PASS" and variants.get("result_counts", {}).get("PASS") == 30 else "FAIL", "observational_regression": "OBSERVED" if observational.get("count") == 48 and observational.get("diff_counts") == {"UNCHANGED": 48} else "FAIL", "holdout": "PASS" if holdout.get("gate") == "PASS" and holdout.get("questions") == 30 and holdout.get("error_count") == 0 else "FAIL", "shadow": "PASS" if shadow.get("status") == "PASS" and shadow.get("metrics", {}).get("lost_hit") == 0 and shadow.get("metrics", {}).get("error_rate") == 0 else "FAIL", "rollback": "PASS" if rollback.get("status") == "READY" else "FAIL"}
    objective_pass = all(value in {"PASS", "OBSERVED"} for value in gates.values())
    payload = {"schema_version": "knowledge_os_v2_5.release_gate", "captured_at": now, "recommendation": "CONDITIONAL_APPROVE" if objective_pass else "REJECT", "gate_status": "PASS_WITH_CONDITIONS" if objective_pass else "REJECTED", "gates": gates, "strict_regression": {key: strict.get(key) for key in ("core_count", "core_result_counts", "core_pass_rate", "variant_count", "variant_result_counts", "variant_stability_rate", "critical_failures", "unsupported_claims", "wrong_scope")}, "retrieval": {"gold_count": retrieval.get("gold_count"), "v2_4_rrf_k60": retrieval.get("baseline_v2_4_rrf_k60"), "v2_5_rrf_k60": retrieval.get("v2_5_rrf_k60"), "delta": retrieval.get("delta_v2_5_minus_v2_4")}, "observational": {key: observational.get(key) for key in ("count", "v2_4_status_counts", "v2_5_status_counts", "diff_counts", "accuracy_gate")}, "holdout": {"questions": holdout.get("questions"), "error_count": holdout.get("error_count"), "scored": holdout.get("scored")}, "shadow": shadow.get("metrics"), "rollback": {key: rollback.get(key) for key in ("status", "switch_performed", "v2_4_frozen_candidate_unchanged", "v1_index_intact")}, "not_evaluable_resolution": resolution, "conditions": ["Owner Gold 清单未提供原始 source_version；V2.5 以文件 SHA-256 作为可追溯 source_version，正式切换前需内容负责人确认该版本口径。", "8010 仍保持 V1 Runtime；本次只批准候选进入受控 Shadow/待授权切换，不自动切换。", "8000 保持 OFF，未写正式 Qdrant、SQLite 或正式 Index。"] if objective_pass else ["至少一项 Release Gate 未通过，停止切换。"], "runtime": {"8010_switch_allowed": False, "8010_switch_authorization": "REQUIRED", "8000_touched": False, "formal_qdrant_write": False, "formal_sqlite_write": False, "formal_index_switch": False, "v1_index_intact": True, "candidate_manifest": str(V25 / "candidate_v2_5_manifest.json")}, "formal_8000_touched": False}
    (V25 / "release_gate.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"recommendation": payload["recommendation"], "gate_status": payload["gate_status"], "gates": gates, "conditions": payload["conditions"]}, ensure_ascii=False, indent=2))
    return 0 if objective_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
