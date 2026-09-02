from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "v2_internal_trial_baseline" / "baseline_fingerprint.json"
REPORT = ROOT / "docs" / "V2_INTERNAL_TRIAL_BASELINE.md"

FILES = [
    "app/document_intelligence/v2.py", "app/ingestion/metadata/schema.py", "app/retrieval/hierarchical_v1.py",
    "app/verified_answer_engine_v2.py", "app/knowledge_growth_v1.py", "app/trial/v2.py", "app/trial/main.py",
    "config/internal_trial.yaml", "config/knowledge_governance_rules.yaml", "scripts/run_verified_answer_engine_v2.py",
    "scripts/run_knowledge_growth_v1.py", "scripts/run_v2_8010_trial.py", "docs/TASK_020F_FINAL_ACCEPTANCE_REPORT.md",
    "docs/KNOWLEDGE_SELF_GROWTH_LOOP_V1_REPORT.md", "docs/V2_8010_TRIAL_REPORT.md",
]
ARTIFACTS = [
    "data/shadow/hierarchical_retrieval_v1_stabilization/document_index/records.jsonl",
    "data/shadow/hierarchical_retrieval_v1_stabilization/document_index/vectors.npy",
    "data/shadow/hierarchical_retrieval_v1_stabilization/section_index/records.jsonl",
    "data/shadow/hierarchical_retrieval_v1_stabilization/section_index/vectors.npy",
    "data/shadow/hierarchical_retrieval_v1_stabilization/table_index/records.jsonl",
    "data/shadow/hierarchical_retrieval_v1_stabilization/atomic_evidence.jsonl",
    "evaluation/verified_answer_engine_v2_final/task_020f_final_acceptance.json",
    "evaluation/knowledge_growth_v1/growth_metrics.json", "evaluation/v2_8010_trial/safety_validation.json",
    "evaluation/v2_8010_trial/ba_ab_results.json",
]


def main() -> int:
    status = _git("status", "--short")
    head = _git("rev-parse", "HEAD").strip()
    fingerprint = {
        "schema_version": "v2_internal_trial_baseline.v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "milestone": "AI设计管理自生长知识库 V2.0 INTERNAL TRIAL BASELINE", "v2_internal_trial": "TRIAL_READY", "production_ready": False,
        "git": {"head_commit": head, "head_subject": _git("log", "-1", "--pretty=%s").strip(), "worktree_clean": not bool(status.strip()), "worktree_status_sha256": _hash_text(status), "commit_freeze_status": "HEAD_RECORDED_NO_NEW_COMMIT_WORKTREE_DIRTY" if status.strip() else "HEAD_RECORDED_WORKTREE_CLEAN"},
        "components": {"document_intelligence_schema": "FROZEN", "hierarchical_retrieval_020c": "FROZEN", "verified_evidence_bundle_020e": "FROZEN", "verified_answer_engine_020f": "FROZEN", "knowledge_growth_loop_020g": "FROZEN", "trial_8010_configuration": "FROZEN"},
        "feature_flags": _feature_flags(), "code_files": _files(FILES), "artifacts": _files(ARTIFACTS),
        "safety": _read_json(ROOT / "evaluation" / "v2_8010_trial" / "safety_validation.json"),
        "acceptance": _read_json(ROOT / "evaluation" / "verified_answer_engine_v2_final" / "task_020f_final_acceptance.json"),
    }
    _write_json(OUT, fingerprint)
    REPORT.write_text(_report(fingerprint), encoding="utf-8")
    print(json.dumps({"head": head, "worktree_clean": fingerprint["git"]["worktree_clean"], "production_ready": False}, ensure_ascii=False))
    return 0


def _feature_flags() -> dict[str, Any]:
    values = _read_yaml(ROOT / "config" / "internal_trial.yaml")
    return {"V2_VERIFIED_RAG_ENABLED": values.get("V2_VERIFIED_RAG_ENABLED"), "v2_verified_rag_8010_only": values.get("v2_verified_rag_8010_only"), "trial_port": values.get("port"), "trial_host": values.get("host"), "formal_port": values.get("formal_port"), "formal_cutover": values.get("formal_cutover"), "root002_governance": values.get("root002_governance"), "root003_enabled": values.get("root003_enabled"), "knowledge_writeback": values.get("knowledge_writeback")}


def _files(items: list[str]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        path = ROOT / item
        rows.append({"path": item, "exists": path.is_file(), "size": path.stat().st_size if path.is_file() else None, "sha256": _sha256(path) if path.is_file() else None})
    return rows


def _report(value: dict[str, Any]) -> str:
    flags = value["feature_flags"]
    return "\n".join([
        "# V2 INTERNAL TRIAL BASELINE", "", "## 状态", "", "- TASK-020A ～ TASK-020H：CLOSED", "- V2_INTERNAL_TRIAL：TRIAL_READY", "- PRODUCTION_READY：FALSE", "",
        "## Git冻结点", "", f"- HEAD：`{value['git']['head_commit']}`", f"- HEAD说明：{value['git']['head_subject']}", f"- 工作区干净：{value['git']['worktree_clean']}", f"- 冻结方式：`{value['git']['commit_freeze_status']}`", "- 未创建新Git提交；当前工作区包含未提交V2工件，基线以HEAD + 文件指纹共同锁定。", "",
        "## 冻结组件", "", "- Document Intelligence Schema", "- 020C Hierarchical Retrieval", "- 020E Verified Evidence Bundle", "- 020F Verified Answer Engine", "- 020G Knowledge Growth Loop", "- 8010 Trial Configuration", "",
        "## 8010配置", "", f"- Host / Port：{flags['trial_host']}:{flags['trial_port']}", f"- V2开关：{flags['V2_VERIFIED_RAG_ENABLED']}；仅8010：{flags['v2_verified_rag_8010_only']}", f"- 8000正式端口：{flags['formal_port']}；正式切换：{flags['formal_cutover']}", f"- Root-002：{flags['root002_governance']}；Root-003启用：{flags['root003_enabled']}", f"- 自动知识回写：{flags['knowledge_writeback']}", "",
        "## 安全冻结", "", "- 禁止切换8000、扩大Root审批、自动发布Growth Candidate。", "- 机器可读文件指纹见 `evaluation/v2_internal_trial_baseline/baseline_fingerprint.json`。", ""
    ])


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> dict[str, Any]:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
