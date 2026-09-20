from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V22 = ROOT / "evaluation" / "knowledge_os_v2_2"
V21 = ROOT / "evaluation" / "knowledge_os_v2_1"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    node = read(V22 / "node_binding" / "metrics.json")
    repair = read(V22 / "quarantine_repair" / "quarantine_repair_report.json")
    gold = read(V21 / "gold" / "gold_manifest.json")
    dense = read(V22 / "retrieval_ab" / "dense_gpu_report.json")
    lexical = read(V21 / "retrieval_ab" / "lexical_matrix.json")
    V22.joinpath("gold").mkdir(parents=True, exist_ok=True)
    V22.joinpath("retrieval_ab").mkdir(parents=True, exist_ok=True)
    (V22 / "gold" / "retrieval_gold.json").write_text(json.dumps({"source": str(V21 / 'gold' / 'retrieval_gold.jsonl'), "total": gold.get("retrieval_gold_total"), "confirmed": gold.get("retrieval_gold_confirmed"), "pending": gold.get("retrieval_gold_pending"), "review_endpoint": "/knowledge-os/gold-review", "gate": "FAIL"}, ensure_ascii=False, indent=2), encoding="utf-8")
    (V22 / "gold" / "answer_gold.json").write_text(json.dumps({"source": str(V21 / 'gold' / 'answer_gold.jsonl'), "confirmed": gold.get("answer_gold_confirmed"), "target": 30, "gate": "FAIL"}, ensure_ascii=False, indent=2), encoding="utf-8")
    (V22 / "retrieval_ab" / "retrieval_ab_matrix.json").write_text(json.dumps({"lexical": lexical, "dense": {"status": "NOT_RUN_CUDA_FAILURE"}, "weighted_hybrid": {"status": "NOT_RUN_DENSE_BLOCKED"}, "rrf": {"status": "NOT_RUN_DENSE_BLOCKED"}, "reranker": {"status": "NOT_RUN_DENSE_BLOCKED"}}, ensure_ascii=False, indent=2), encoding="utf-8")
    reports = {
        "validator_report.json": {"status": "NOT_RUN_PREREQUISITE", "old_v1_provisional_false_reject_rate": 0.3023, "reason": "Gold and Dense candidate not ready"},
        "regression_report.json": {"status": "NOT_RUN_PREREQUISITE", "regression_count": 48, "reason": "Candidate freeze and Validator not ready"},
        "holdout_report.json": {"status": "NOT_RUN_PROTECTED", "holdout_count": 30, "reason": "Regression not passed; holdout untouched"},
        "shadow_report.json": {"status": "NOT_RUN_PREREQUISITE", "reason": "Holdout not passed"},
        "rollback_report.json": {"status": "NOT_RUN_PREREQUISITE", "reason": "No release candidate"},
    }
    for name, payload in reports.items():
        (V22 / ("validator" if name.startswith("validator") else "regression" if name.startswith("regression") else "holdout" if name.startswith("holdout") else "shadow" if name.startswith("shadow") else "release_gate") / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    gate = {"schema_version": "knowledge_os_v2_2.release_gate", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "recommendation": "REJECT", "gates": {"node_binding": "PASS" if (node.get("semantic_chunk", {}).get("detail_node_coverage") or 0) >= 0.85 and (node.get("root_only_chunk_rate") or 1) <= 0.15 else "FAIL", "quarantine_repair": "PASS" if repair.get("quarantine_gate_pass") else "FAIL", "retrieval_gold": "PASS" if gold.get("retrieval_gold_confirmed", 0) >= 50 else "FAIL", "answer_gold": "PASS" if gold.get("answer_gold_confirmed", 0) >= 30 else "FAIL", "dense_gpu": "PASS" if dense.get("cuda_available") is True else "FAIL", "retrieval_matrix": "NOT_RUN_BLOCKED", "validator": "NOT_RUN_BLOCKED", "regression": "NOT_RUN_BLOCKED", "holdout": "NOT_RUN_BLOCKED", "shadow": "NOT_RUN_BLOCKED", "rollback": "NOT_RUN_BLOCKED"}, "top_3_blocking_issues": ["CUDA_GATE_FAIL：RTX 4060 硬件存在，但 Python 使用 torch 2.13.0+cpu，Dense 未生成。", "Retrieval Gold 仅 10/50 confirmed，40 道仍需人工在 /knowledge-os/gold-review 确认；Answer Gold 仅 8/30。", "Dense Candidate 未冻结，Weighted Hybrid/RRF/Reranker、Validator、Regression、Holdout、Shadow、Rollback 均按依赖顺序停止。"], "runtime": {"8010_switch_allowed": False, "8000_touched": False, "v1_index_intact": True}}
    (V22 / "release_gate" / "release_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs" / "KNOWLEDGE_OS_V2_2_FINAL_REPORT.md").write_text(json.dumps({"release_gate": gate, "node": node, "quarantine_repair": repair, "gold": gold, "dense": dense, "next_action": "在 CUDA-enabled PyTorch 环境完成 GPU Dense；人工确认 40 道 Retrieval Gold 和 22 道 Answer Gold 后再恢复后续依赖阶段。"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
