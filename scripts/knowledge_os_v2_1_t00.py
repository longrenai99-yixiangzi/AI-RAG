"""Freeze the V2.1 baseline without touching runtime or prior staging artifacts."""

from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2_1" / "baseline"
SOURCE_ROOT = Path(r"[LOCAL_PATH_REDACTED]")
EXTERNAL_ROOT = Path(r"[LOCAL_PATH_REDACTED]�公司技术部")
STATE = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"
V1_INDEX = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "atomic_evidence.jsonl"
V2_INDEX = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "bm25_v2.json"
V2_CHUNKS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl"
V2_MANIFEST = ROOT / "evaluation" / "knowledge_os_v2" / "baseline" / "manifest.json"
V2_AB = ROOT / "evaluation" / "knowledge_os_v2" / "retrieval" / "ab_matrix.json"
GOLD = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"
CONFIGS = (ROOT / "config" / "internal_trial.yaml", ROOT / "config" / "structured_v2_staging.yaml")


def file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            h.update(block)
    return h.hexdigest()


def tree_hash(root: Path) -> dict:
    excluded = {".git", ".obsidian", ".agents", ".copilot", "copilot", ".rag", ".claude", ".claudian", ".opencode", ".ai-growth"}
    if not root.is_dir():
        return {"exists": False, "file_count": 0, "sha256": None}
    rows: list[str] = []
    for current, directories, files in __import__("os").walk(root, topdown=True, followlinks=False):
        directories[:] = [name for name in directories if name.lower() not in excluded]
        for name in files:
            path = Path(current) / name
            digest = file_hash(path)
            if digest:
                rows.append(f"{path.relative_to(root).as_posix()}\t{digest}")
    rows.sort()
    return {"exists": True, "file_count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()}


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    return result.stdout.strip()


def listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def aggregate_hash(paths: list[Path]) -> str:
    rows = [f"{path.relative_to(ROOT).as_posix()}\t{file_hash(path)}" for path in paths if path.exists()]
    return hashlib.sha256("\n".join(sorted(rows)).encode("utf-8")).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dirty = git("status", "--porcelain").splitlines()
    old_manifest = json.loads(V2_MANIFEST.read_text(encoding="utf-8")) if V2_MANIFEST.exists() else {}
    payload = {
        "schema_version": "knowledge_os_v2_1.t00",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "git": {"head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"), "dirty_files": dirty, "diff_stat": git("diff", "--stat")},
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "cwd": str(ROOT)},
        "ports": {"8000_listening": listening(8000), "8010_listening": listening(8010)},
        "sources": {"root001": tree_hash(SOURCE_ROOT), "external_root_readable": EXTERNAL_ROOT.is_dir()},
        "artifacts": {"legacy_v1_index_sha256": file_hash(V1_INDEX), "structured_layer_sha256": aggregate_hash(sorted((ROOT / "data" / "shadow" / "knowledge_v2_staging").glob("*.jsonl"))), "staging_index_sha256": file_hash(V2_INDEX), "semantic_chunk_sha256": file_hash(V2_CHUNKS), "v2_manifest_sha256": file_hash(V2_MANIFEST), "v2_ab_sha256": file_hash(V2_AB), "benchmark_sha256": file_hash(GOLD), "runtime_config_sha256": aggregate_hash(list(CONFIGS))},
        "runtime_config": {str(path.relative_to(ROOT)): path.read_text(encoding="utf-8") if path.exists() else None for path in CONFIGS},
        "previous_v2_baseline": old_manifest,
        "gate": {"legacy_index_touched": False, "v2_staging_isolated": True, "formal_port_8000_touched": False, "runtime_switch_authorized": False},
    }
    (OUT / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "git_status.txt").write_text("\n".join(dirty), encoding="utf-8")
    print(json.dumps({"head": payload["git"]["head"], "dirty_files": len(dirty), "8000": payload["ports"]["8000_listening"], "8010": payload["ports"]["8010_listening"], "source_files": payload["sources"]["root001"]["file_count"], "output": str(OUT)}, ensure_ascii=False, indent=2))
    return 2 if payload["ports"]["8000_listening"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
