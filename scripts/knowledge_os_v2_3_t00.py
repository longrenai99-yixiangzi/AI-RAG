from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2_3" / "environment_before.json"


def run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        return (result.stdout or result.stderr).strip()
    except Exception as error:
        return f"{type(error).__name__}: {error}"


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    files = {"v1_index": ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "atomic_evidence.jsonl", "v2_index": ROOT / "data" / "shadow" / "knowledge_v2_staging" / "bm25_v2.json", "v2_chunks": ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl", "retrieval_gold": ROOT / "evaluation" / "knowledge_os_v2_1" / "gold" / "gold_manifest.json", "holdout": ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"}
    payload = {"schema_version": "knowledge_os_v2_3.environment_before", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "platform": platform.platform(), "cwd": str(ROOT), "executables": {"where_python": run(["where.exe", "python"]), "where_pip": run(["where.exe", "pip"]), "py_launcher": run(["py", "--version"]), "python_executable": sys.executable, "python_version": sys.version, "pip_version": run([sys.executable, "-m", "pip", "--version"])}, "nvidia_smi": run(["nvidia-smi"]), "git": {"head": run(["git", "rev-parse", "HEAD"]), "branch": run(["git", "branch", "--show-current"]), "dirty_files": run(["git", "status", "--porcelain"]).splitlines()}, "artifacts": {name: {"path": str(path), "sha256": sha(path)} for name, path in files.items()}, "runtime": {"8000_touched": False, "8010_switched": False, "holdout_run": False}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"python": payload["executables"]["python_executable"], "torch_check_pending": True, "output": str(OUT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
