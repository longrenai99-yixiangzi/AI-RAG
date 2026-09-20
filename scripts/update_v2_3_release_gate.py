from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    matrix = read(V23 / "retrieval_matrix.json")
    validator = read(V23 / "validator_report.json")
    answer_validation = read(V23 / "answer_validation_report.json")
    regression = read(V23 / "regression_report.json")
    dense = read(V23 / "dense_embedding_report.json")
    answer = read(V23 / "answer_gold_snapshot.json") or read(ROOT / "evaluation" / "knowledge_os_v2_2" / "gold" / "answer_gold.json")
    now = datetime.now(timezone.utc).astimezone().isoformat()
    validator_pass = validator.get("status") == "PASS"
    answer_pass = answer.get("confirmed") == 30
    answer_validation_pass = answer_validation.get("status") == "PASS"
    top_issues = []
    if not validator_pass:
        top_issues.append(f"Candidate Validator False Reject 为 {validator.get('false_reject_rate')}, 高于 10% 门槛；不得进入 Regression。")
    if not answer_pass:
        top_issues.append(f"Answer Gold 尚未达到 30/30，当前为 {answer.get('confirmed')}；回答层验证未启动。")
    if validator_pass and answer_pass and answer_validation_pass and regression.get("status") != "PASS":
        top_issues.append("Regression 48 仅完成运行观察，缺少逐题 Claim 真值，不能作为 Regression Gate PASS。")
    top_issues.append("Retrieval Candidate 虽已冻结为 RRF(k=60)，但正式运行时仍保持关闭。")
    gate = {
        "schema_version": "knowledge_os_v2_3.release_gate",
        "captured_at": now,
        "recommendation": "REJECT",
        "gates": {"cuda": "PASS", "dense_smoke": "PASS", "dense_embedding": "PASS" if dense.get("status") == "PASS" else "FAIL", "retrieval_gold": "PASS" if matrix.get("gold_count") == 50 else "FAIL", "retrieval_candidate": "PASS" if (V23 / "candidate_manifest.json").exists() else "FAIL", "validator": validator.get("status", "NOT_RUN"), "answer_gold": "PASS" if answer_pass else "FAIL", "answer_validation": "PASS" if answer_validation_pass else "FAIL", "regression": regression.get("status", "NOT_RUN") if validator_pass and answer_pass and answer_validation_pass else "NOT_RUN_ANSWER_GOLD_BLOCKED" if validator_pass and not answer_pass else "NOT_RUN_VALIDATOR_BLOCKED", "holdout": "NOT_RUN_REGRESSION_NOT_PASS" if regression.get("status") != "PASS" else "NOT_RUN_PROTECTED", "shadow": "NOT_RUN_REGRESSION_NOT_PASS" if regression.get("status") != "PASS" else "NOT_RUN_PREREQUISITE", "rollback": "NOT_RUN_REGRESSION_NOT_PASS" if regression.get("status") != "PASS" else "NOT_RUN_PREREQUISITE"},
        "gold": {"retrieval_confirmed": matrix.get("gold_count"), "retrieval_target": 50, "answer_confirmed": answer.get("confirmed"), "answer_target": 30},
        "retrieval": {"best_pre_reranker": matrix.get("best_pre_reranker"), "best_post_reranker": matrix.get("best_post_reranker"), "reranker_enabled": (matrix.get("reranker") or {}).get("enabled"), "file_recall_at_10": (((matrix.get("versions") or {}).get(str(matrix.get("best_pre_reranker")) or {}).get("metrics") or {}).get("file") or {}).get("recall@10")},
        "validator": {"status": validator.get("status"), "false_reject_rate": validator.get("false_reject_rate"), "target_false_reject_rate": validator.get("target_false_reject_rate")},
        "top_3_blocking_issues": top_issues[:3],
        "runtime": {"8010_switch_allowed": False, "8000_touched": False, "formal_qdrant_write": False, "v1_index_intact": True},
    }
    (V23 / "release_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs" / "KNOWLEDGE_OS_V2_3_FINAL_REPORT.md").write_text(json.dumps({"release_gate": gate, "retrieval_matrix": matrix, "validator": validator, "next_action": "修复 Candidate Validator 的证据定位/召回问题；补齐 Answer Gold 30/30 后再重新运行后续 Gate。"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
