from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
CONFIG = ROOT / "config" / "internal_trial.yaml"
V1_INDEX = ROOT / "data" / "shadow" / "full_corpus_qdrant"
PID_FILE = ROOT / "logs" / "trial" / "trial_service.pid"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_sha(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        return "MISSING"
    for item in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(str(item.relative_to(path)).replace("\\", "/").encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def read_json(name: str) -> dict:
    return json.loads((V25 / name).read_text(encoding="utf-8"))


def port_status(port: int) -> dict:
    output = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False).stdout
    rows = [line.strip() for line in output.splitlines() if f":{port} " in line and "LISTENING" in line]
    return {"port": port, "listening": bool(rows), "entries": rows}


def main() -> int:
    V26.mkdir(parents=True, exist_ok=True)
    candidate = read_json("candidate_v2_5_manifest.json")
    admitted = read_json("admitted_sources.json").get("records") or []
    now = datetime.now(timezone.utc).astimezone().isoformat()
    pid = PID_FILE.read_text(encoding="utf-8").strip() if PID_FILE.exists() else None
    v1_port = port_status(8010)
    formal_port = port_status(8000)
    git_head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    baseline = {
        "schema_version": "knowledge_os_v2_6.release_baseline",
        "captured_at": now,
        "git_head": git_head,
        "v1_runtime_config_path": str(CONFIG),
        "v1_runtime_config_hash": sha(CONFIG),
        "v1_index_path": str(V1_INDEX),
        "v1_index_hash": directory_sha(V1_INDEX),
        "v2_5_candidate_hash": candidate.get("candidate_hash"),
        "v2_5_source_hash": candidate.get("staging", {}).get("semantic_chunks_sha256"),
        "v2_5_index_hash": candidate.get("staging", {}).get("semantic_chunks_sha256"),
        "v2_5_embedding_hash": candidate.get("staging", {}).get("dense_vectors_sha256"),
        "candidate_manifest_path": str(V25 / "candidate_v2_5_manifest.json"),
        "candidate_manifest_hash": sha(V25 / "candidate_v2_5_manifest.json"),
        "8010_process": {"pid_file": str(PID_FILE), "pid": pid, "command_observed": "uvicorn app.trial.main:app --host 127.0.0.1 --port 8010", "runtime_role": "V1_PRIMARY"},
        "8010_port_status": v1_port,
        "8000_port_status": formal_port,
        "formal_qdrant_write_status": "OFF",
        "formal_sqlite_write_status": "OFF",
        "formal_index_switch_status": "OFF",
        "candidate_status": candidate.get("status"),
        "formal_8000_touched": False,
    }
    policy = {"schema_version": "knowledge_os_v2_6.source_version_policy", "captured_at": now, "semantic_version": {"meaning": "业务负责人提供的正式版号/发文版号/发布日期版号", "available_for_current_sources": False}, "content_hash_version": {"meaning": "物理文件 SHA-256，用于不可变内容追溯", "available_for_current_sources": True, "algorithm": "SHA-256"}, "effective_version": {"meaning": "经内容负责人确认后可用于内部试用的有效版本", "current_status": "PENDING_OWNER_APPROVAL"}, "codex_boundary": "Codex 只能记录 SOURCE_VERSION_REVIEW_REQUIRED，不能代替内容负责人确认正式版本。"}
    approvals = []
    for source in admitted:
        approvals.append({"source_id": source.get("source_id"), "file_name": source.get("file_name"), "source_path": source.get("source_path"), "sha256": source.get("source_hash") or source.get("source_version"), "semantic_version": None, "semantic_version_available": False, "version_policy": "CONTENT_HASH_PENDING_OWNER_APPROVAL", "effective_status": source.get("effective_status"), "reviewer": "CONTENT_OWNER_REQUIRED", "reviewed_at": None, "approval_status": "PENDING", "review_note": "原始 Owner Gold 清单未提供 semantic_version；Codex 不代确认。请负责人确认该物理文件 SHA-256 是否作为本次有效版本。", "owner_gold_refs": source.get("owner_gold_refs") or []})
    approval_doc = {"schema_version": "knowledge_os_v2_6.owner_source_version_approval", "captured_at": now, "approval_statuses_allowed": ["APPROVED", "REJECTED", "PENDING"], "source_version_gate": "PENDING", "approved_count": 0, "pending_count": len(approvals), "rejected_count": 0, "records": approvals}
    gate = {"schema_version": "knowledge_os_v2_6.final_release_gate", "captured_at": now, "status": "BLOCKED", "final_status": "BLOCKED", "stop_after": "T01_SOURCE_VERSION_GATE", "gates": {"v2_5_candidate_frozen": "PASS" if candidate.get("status") == "FROZEN" else "FAIL", "owner_source_version": "PENDING", "live_shadow": "NOT_RUN_SOURCE_VERSION_BLOCKED", "rollback_drill": "NOT_RUN_SOURCE_VERSION_BLOCKED", "candidate_integrity": "NOT_RUN_SOURCE_VERSION_BLOCKED", "8010_switch_authorization": "NOT_REQUESTED", "immediate_smoke": "NOT_RUN", "canary": "NOT_RUN"}, "top_blocking_issues": ["5/5 Owner Gold Source Version approval 仍为 PENDING，未达到 SOURCE_VERSION_GATE_PASS。", "任务书禁止 Codex 自动把 SHA-256 解释为业务正式版本；需内容负责人逐源确认。", "Live Shadow、Rollback Drill、8010 受控切换在 Source Version Gate 通过前不得执行。"], "runtime": {"8010_primary_unchanged": True, "8010_switch_performed": False, "8000_touched": False, "formal_qdrant_write": False, "formal_sqlite_write": False, "formal_index_switch": False, "v1_index_intact": True}, "next_action": "CONTENT_OWNER_CONFIRM_SOURCE_VERSIONS"}
    (V26 / "release_baseline.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    (V26 / "source_version_policy.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    (V26 / "owner_source_version_approval.json").write_text(json.dumps(approval_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (V26 / "final_release_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": gate["status"], "stop_after": gate["stop_after"], "owner_source_version": approval_doc["source_version_gate"], "8010": v1_port, "8000": formal_port}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
