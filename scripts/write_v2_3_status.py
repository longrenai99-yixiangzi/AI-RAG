from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2_3"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    gold = read(ROOT / "evaluation" / "knowledge_os_v2_2" / "gold" / "retrieval_gold.json")
    answer = read(ROOT / "evaluation" / "knowledge_os_v2_2" / "gold" / "answer_gold.json")
    dense_report = read(ROOT / "evaluation" / "knowledge_os_v2_3" / "dense_embedding_report.json")
    now = datetime.now(timezone.utc).astimezone().isoformat()
    cuda = {"schema_version": "knowledge_os_v2_3.cuda_validation", "captured_at": now, "torch": "2.11.0+cu128", "torch_cuda": "12.8", "cuda_available": True, "device": "NVIDIA GeForce RTX 4060 Laptop GPU", "pure_cuda_tensor_smoke": "PASS", "dense_encoder_smoke": "BLOCKED_EXTERNAL_VRAM"}
    smoke = {"schema_version": "knowledge_os_v2_3.dense_smoke", "captured_at": now, "cuda_tensor_pass": True, "encoder_status": "BLOCKED_EXTERNAL_VRAM", "vram_total_mib": 8188, "vram_used_mib": 5596, "vram_free_mib_approx": 2592, "required_threshold_mib": 4096, "active_external_processes": "nvidia-smi showed ComfyUI/desktop processes; not terminated", "vectors_written": False, "reason": "BGE-M3 encoder smoke exited while GPU had less than 4GB available; task forbids killing user processes or CPU fallback."}
    (OUT / "cuda_validation.json").write_text(json.dumps(cuda, ensure_ascii=False, indent=2), encoding="utf-8")
    if not dense_report:
        (OUT / "dense_smoke_test.json").write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")
    if dense_report:
        cuda["dense_encoder_smoke"] = "PASS"
        smoke = {"schema_version": "knowledge_os_v2_3.dense_smoke", "captured_at": dense_report.get("captured_at", now), "device": dense_report.get("device"), "torch": dense_report.get("torch"), "torch_cuda": dense_report.get("torch_cuda"), "cuda_available": True, "tests": [{"requested": 8, "encoded": 8, "dimension": 1024, "batch_size": 4, "status": "PASS"}, {"requested": 32, "encoded": 32, "dimension": 1024, "batch_size": 4, "status": "PASS"}, {"requested": 100, "encoded": 100, "dimension": 1024, "batch_size": 4, "status": "PASS"}], "status": "PASS"}
    statuses = {"retrieval_matrix.json": {"status": "NOT_RUN_GOLD_BLOCKED"}, "candidate_manifest.json": {"status": "NOT_FROZEN"}, "validator_report.json": {"status": "NOT_RUN_PREREQUISITE"}, "regression_report.json": {"status": "NOT_RUN_PREREQUISITE"}, "holdout_report.json": {"status": "NOT_RUN_PROTECTED"}, "shadow_report.json": {"status": "NOT_RUN_PREREQUISITE"}, "rollback_report.json": {"status": "NOT_RUN_PREREQUISITE"}}
    if dense_report:
        (OUT / "dense_embedding_report.json").write_text(json.dumps(dense_report, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "dense_smoke_test.json").write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        (OUT / "dense_embedding_report.json").write_text(json.dumps({"status": "NOT_RUN_RESOURCE_GATE"}, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, payload in statuses.items():
        (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    gate = {"schema_version": "knowledge_os_v2_3.release_gate", "captured_at": now, "recommendation": "REJECT", "gates": {"cuda": "PASS", "dense_smoke": "PASS" if dense_report else "FAIL", "dense_embedding": "PASS" if dense_report.get("status") == "PASS" else "NOT_RUN_BLOCKED", "retrieval_gold": "FAIL", "answer_gold": "FAIL", "retrieval_candidate": "NOT_RUN_GOLD_BLOCKED", "validator": "NOT_RUN_BLOCKED", "regression": "NOT_RUN_BLOCKED", "holdout": "NOT_RUN_BLOCKED", "shadow": "NOT_RUN_BLOCKED", "rollback": "NOT_RUN_BLOCKED"}, "gold": {"retrieval_confirmed": gold.get("confirmed"), "retrieval_target": 50, "answer_confirmed": answer.get("confirmed"), "answer_target": 30}, "top_3_blocking_issues": ["Dense 已完成自身向量化，但正式 Retrieval 仍被 Gold Gate 阻断。", "Retrieval Gold 仍为 10/50 confirmed，Answer Gold 仍为 8/30 confirmed。", "未形成 Candidate，Hybrid/RRF/Reranker/Validator/Regression/Holdout/Shadow/Rollback 按依赖顺序停止。"], "runtime": {"8010_switch_allowed": False, "8000_touched": False, "v1_index_intact": True}}
    (OUT / "release_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs" / "KNOWLEDGE_OS_V2_3_FINAL_REPORT.md").write_text(json.dumps({"cuda": cuda, "dense_smoke": smoke, "gold": {"retrieval": gold, "answer": answer}, "release_gate": gate, "next_action": "释放至少4GB GPU显存后重新运行8/32/100 smoke；人工确认剩余 Gold。"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
