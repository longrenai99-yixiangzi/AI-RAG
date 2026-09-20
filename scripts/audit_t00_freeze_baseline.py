"""T00 - 冻结当前真实基线（只读审计，不修改运行时）。

输出目录：evaluation/knowledge_os_system_audit/
    baseline/                  配置与索引指纹副本
    baseline_questions.json    当前已记录的真实问题基线
    baseline_answers.json      当前回答/证据/耗时基线
    environment.json           环境、Git、模型、数据计数
    rollback.md                回滚步骤

约束：
    仅读取 8010 内部试用链路，不触碰正式 8000 / 正式 Qdrant / SQLite。
    不修改任何业务数据与运行配置。
"""

from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_system_audit"
BASE = OUT / "baseline"

STATE_PATH = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"
ATOMIC_PATH = ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl"
FROZEN_INDEX_PATH = (
    ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "atomic_evidence.jsonl"
)
CONFIG_PATH = ROOT / "config" / "internal_trial.yaml"
MODEL_DIR = ROOT / "models"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def git(*args: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60
        )
        return r.stdout.strip()
    except Exception as exc:  # pragma: no cover - 环境缺少 git 时降级
        return f"<git unavailable: {exc}>"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def scan_jsonl(path: Path) -> dict:
    """流式统计 jsonl，避免一次性载入大文件。"""
    stats = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "records": 0,
        "unique_document_ids": set(),
        "unique_source_paths": set(),
        "unique_sha256": set(),
        "file_type": Counter(),
        "granularity": Counter(),
        "parse_status": Counter(),
        "text_chars_total": 0,
        "text_chars_min": None,
        "text_chars_max": 0,
        "empty_text": 0,
        "sample_evidence_ids": [],
    }
    if not path.exists():
        return stats
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                stats["records"] += 1
                continue
            stats["records"] += 1
            if stats["records"] <= 5:
                stats["sample_evidence_ids"].append(rec.get("evidence_id"))
            stats["unique_document_ids"].add(rec.get("document_id"))
            stats["unique_source_paths"].add(rec.get("source_path"))
            stats["unique_sha256"].add(rec.get("sha256"))
            stats["file_type"][rec.get("file_type") or "<none>"] += 1
            stats["granularity"][rec.get("granularity") or "<none>"] += 1
            meta = rec.get("metadata") or {}
            stats["parse_status"][meta.get("parse_status") or "<none>"] += 1
            text = rec.get("text") or ""
            n = len(text)
            stats["text_chars_total"] += n
            stats["text_chars_max"] = max(stats["text_chars_max"], n)
            stats["text_chars_min"] = n if stats["text_chars_min"] is None else min(stats["text_chars_min"], n)
            if not text.strip():
                stats["empty_text"] += 1
    for key in ("unique_document_ids", "unique_source_paths", "unique_sha256"):
        stats[key] = len(stats[key])
    for key in ("file_type", "granularity", "parse_status"):
        stats[key] = dict(stats[key].most_common())
    if stats["records"]:
        stats["avg_text_chars"] = round(stats["text_chars_total"] / stats["records"], 2)
    return stats


def probe_service(host: str = "127.0.0.1", port: int = 8010) -> dict:
    info = {"host": host, "port": port, "listening": False, "endpoints": {}, "pid": None}
    try:
        with socket.create_connection((host, port), timeout=3):
            info["listening"] = True
    except OSError:
        return info
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, timeout=30
        ).stdout.decode("utf-8", "replace")
        for line in out.splitlines():
            if f"{host}:{port}" in line and "LISTENING" in line:
                info["pid"] = line.split()[-1]
                break
    except Exception:
        pass
    for path in ("/knowledge-os/api/v2/enabled", "/api/v2/enabled", "/knowledge-os/api/status"):
        url = f"http://{host}:{port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode("utf-8", "replace")
                info["endpoints"][path] = {"http_status": resp.status, "body": body[:500]}
        except Exception as exc:
            info["endpoints"][path] = {"http_status": None, "error": str(exc)[:200]}
    return info


def collect_models() -> dict:
    result = {}
    if not MODEL_DIR.exists():
        return {"model_dir": str(MODEL_DIR), "exists": False}
    for name in sorted(p.name for p in MODEL_DIR.iterdir() if p.is_dir()):
        d = MODEL_DIR / name
        files = []
        total = 0
        for f in sorted(d.rglob("*")):
            if f.is_file():
                size = f.stat().st_size
                total += size
                files.append({"name": str(f.relative_to(d)), "size_bytes": size})
        result[name] = {
            "path": str(d),
            "file_count": len(files),
            "total_size_bytes": total,
            "has_config": (d / "config.json").exists(),
            "has_tokenizer": (d / "tokenizer.json").exists(),
            "weight_file": next(
                (
                    f["name"]
                    for f in files
                    if f["name"].endswith((".bin", ".safetensors", ".pt", ".onnx"))
                ),
                None,
            ),
            "files": files[:40],
        }
    return {"model_dir": str(MODEL_DIR), "exists": True, "models": result}


def collect_sources() -> dict:
    if not STATE_PATH.exists():
        return {"state_path": str(STATE_PATH), "exists": False}
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    sources = state.get("sources", {})
    summary = {
        "state_path": str(STATE_PATH),
        "schema_version": state.get("schema_version"),
        "source_count": len(sources),
        "knowledge_count": len(state.get("knowledge", {})),
        "question_variant_count": len(state.get("question_variants", {})),
        "feedback_count": len(state.get("feedback", {})),
        "change_candidate_count": len(state.get("change_candidates", {})),
        "query_run_count": len(state.get("query_runs", {})),
        "event_count": len(state.get("events", [])),
        "by_index_status": Counter(),
        "by_body_status": Counter(),
        "by_approval_status": Counter(),
        "by_root": Counter(),
        "active_versions": 0,
        "inactive_versions": 0,
        "total_versions": 0,
        "missing_files": [],
        "sources": [],
    }
    for sid, src in sources.items():
        summary["by_index_status"][src.get("index_status") or "<none>"] += 1
        summary["by_body_status"][src.get("body_status") or "<none>"] += 1
        summary["by_approval_status"][src.get("approval_status") or "<none>"] += 1
        summary["by_root"][src.get("knowledge_root_id") or "<none>"] += 1
        versions = src.get("versions", [])
        summary["total_versions"] += len(versions)
        summary["active_versions"] += sum(1 for v in versions if v.get("active"))
        summary["inactive_versions"] += sum(1 for v in versions if not v.get("active"))
        if src.get("exists") is False:
            summary["missing_files"].append(sid)
        summary["sources"].append(
            {
                "source_id": sid,
                "file_name": src.get("file_name"),
                "file_type": src.get("file_type"),
                "source_path": src.get("source_path"),
                "knowledge_root_id": src.get("knowledge_root_id"),
                "approval_status": src.get("approval_status"),
                "exists": src.get("exists"),
                "body_status": src.get("body_status"),
                "index_status": src.get("index_status"),
                "version_count": len(versions),
                "chunk_count": sum(v.get("chunk_count") or 0 for v in versions),
                "current_hash": (src.get("current_hash") or "")[:16],
            }
        )
    for key in ("by_index_status", "by_body_status", "by_approval_status", "by_root"):
        summary[key] = dict(summary[key].most_common())
    return summary


def collect_query_runs() -> tuple[list, list]:
    """从真实 query_runs 抽取问题基线与回答基线。"""
    if not STATE_PATH.exists():
        return [], []
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    runs = state.get("query_runs", {})
    questions, answers = [], []
    for rid, run in (runs.items() if isinstance(runs, dict) else enumerate(runs)):
        questions.append(
            {
                "query_run_id": run.get("query_run_id") or rid,
                "question": run.get("question"),
                "resolved_question": run.get("resolved_question"),
                "conversation_id": run.get("conversation_id"),
                "node_id": run.get("node_id"),
                "pipeline_version": run.get("pipeline_version"),
                "timestamp": run.get("timestamp"),
            }
        )
        answers.append(
            {
                "query_run_id": run.get("query_run_id") or rid,
                "question": run.get("question"),
                "answer_status": run.get("answer_status"),
                "bundle_status": run.get("bundle_status"),
                "document_id_count": len(run.get("document_ids") or []),
                "evidence_id_count": len(run.get("evidence_ids") or []),
                "citation_ids": run.get("citation_ids"),
                "evidence_ids": run.get("evidence_ids"),
                "latency_ms": (run.get("latency") or {}).get("total_ms"),
                "latency_breakdown": run.get("latency"),
                "gold_runtime_injection": run.get("gold_runtime_injection"),
                "feedback": run.get("feedback"),
            }
        )
    questions.sort(key=lambda x: x.get("timestamp") or "")
    answers.sort(key=lambda x: x.get("query_run_id") or "")
    return questions, answers


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    BASE.mkdir(parents=True, exist_ok=True)

    print("[T00] 采集 Git 状态 ...")
    git_info = {
        "head": git("rev-parse", "HEAD"),
        "head_short": git("rev-parse", "--short", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "describe": git("describe", "--always", "--dirty"),
        "last_commit_subject": git("log", "-1", "--pretty=%s"),
        "last_commit_date": git("log", "-1", "--pretty=%cI"),
        "status_porcelain": git("status", "--porcelain").splitlines(),
        "diff_stat": git("diff", "--stat"),
    }
    git_info["dirty_file_count"] = len(git_info["status_porcelain"])

    print("[T00] 采集运行环境 ...")
    env_info = {
        "captured_at": now_iso(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cwd": str(ROOT),
        "workspace": str(ROOT),
    }

    print("[T00] 采集运行时服务状态 ...")
    service = probe_service()

    print("[T00] 采集模型 ...")
    models = collect_models()

    print("[T00] 采集来源与状态库 ...")
    sources = collect_sources()

    print("[T00] 统计 Atomic Evidence（正式路径）...")
    atomic = scan_jsonl(ATOMIC_PATH)

    print("[T00] 统计冻结索引（较慢，需计算哈希）...")
    frozen = scan_jsonl(FROZEN_INDEX_PATH)
    frozen["sha256"] = sha256_file(FROZEN_INDEX_PATH)

    print("[T00] 采集问题与回答基线 ...")
    questions, answers = collect_query_runs()

    config_text = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else ""
    (BASE / "internal_trial.yaml").write_text(config_text, encoding="utf-8")
    (BASE / "git_status.txt").write_text("\n".join(git_info["status_porcelain"]), encoding="utf-8")
    (BASE / "git_diff_stat.txt").write_text(git_info["diff_stat"], encoding="utf-8")

    environment = {
        "task": "T00_FREEZE_BASELINE",
        "captured_at": now_iso(),
        "scope": "8010 内部试用链路（只读审计）",
        "git": git_info,
        "environment": env_info,
        "service_8010": service,
        "models": models,
        "sources": sources,
        "atomic_evidence": atomic,
        "frozen_index": frozen,
        "config": {
            "path": str(CONFIG_PATH),
            "content_sha256": sha256_file(CONFIG_PATH),
            "trial_mode": "trial_mode: true" in config_text,
            "read_only": "read_only: true" in config_text,
            "formal_cutover": "formal_cutover: false" in config_text,
        },
        "counts_summary": {
            "source_count": sources.get("source_count"),
            "document_count": atomic.get("unique_document_ids"),
            "atomic_evidence_count": atomic.get("records"),
            "frozen_index_record_count": frozen.get("records"),
            "knowledge_count": sources.get("knowledge_count"),
            "query_run_count": sources.get("query_run_count"),
        },
    }

    write_json(OUT / "environment.json", environment)
    write_json(OUT / "baseline_questions.json", questions)
    write_json(OUT / "baseline_answers.json", answers)

    status_counter = Counter(a.get("answer_status") for a in answers)
    print("\n[T00] 基线概览")
    print(f"  Git HEAD      : {git_info['head_short']} ({git_info['branch']}) dirty={git_info['dirty_file_count']}")
    print(f"  8010 监听     : {service['listening']}  pid={service['pid']}")
    print(f"  Source 数量   : {sources.get('source_count')}")
    print(f"  Document 数量 : {atomic.get('unique_document_ids')}")
    print(f"  Chunk/证据数  : {atomic.get('records')} (冻结索引 {frozen.get('records')})")
    print(f"  Knowledge     : {sources.get('knowledge_count')}")
    print(f"  历史 query_run: {sources.get('query_run_count')}  状态分布={dict(status_counter)}")
    print(f"  输出目录      : {OUT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
