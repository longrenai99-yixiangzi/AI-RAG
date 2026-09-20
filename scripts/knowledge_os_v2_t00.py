"""Freeze T00 without touching V1 data, 8010 configuration, or 8000."""

from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2" / "baseline"
STATE = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"
CONFIG = ROOT / "config" / "internal_trial.yaml"
V2_CONFIG = ROOT / "config" / "structured_v2_staging.yaml"
V1_INDEX = ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "atomic_evidence.jsonl"
LEGACY_ATOMIC = ROOT / "data" / "shadow" / "atomic_evidence" / "records.jsonl"


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    return result.stdout.strip()


def probe(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def http_json(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8010{path}", timeout=5) as response:
            return {"status": response.status, "body": json.loads(response.read().decode("utf-8"))}
    except Exception as error:
        return {"status": None, "error": f"{type(error).__name__}: {error}"}


def jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(bool(line.strip()) for line in handle)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    sources = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    now = datetime.now(timezone.utc).astimezone().isoformat()
    status = git("status", "--porcelain").splitlines()
    manifest = {
        "schema_version": "knowledge_os_v2.t00",
        "captured_at": now,
        "scope": "8010 internal trial staging; V1 and formal 8000 untouched",
        "git": {"head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"), "dirty_files": status, "diff_stat": git("diff", "--stat")},
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "cwd": str(ROOT)},
        "ports": {"8010_listening": probe(8010), "8000_listening": probe(8000)},
        "8010_observed": {"health": http_json("/api/health"), "v2_enabled": http_json("/api/v2/enabled")},
        "files": {str(path.relative_to(ROOT)): {"exists": path.exists(), "bytes": path.stat().st_size if path.exists() else 0, "sha256": sha256(path)} for path in (CONFIG, V2_CONFIG, STATE, LEGACY_ATOMIC, V1_INDEX)},
        "counts": {"source_registry": len(sources), "legacy_atomic_evidence": jsonl_count(LEGACY_ATOMIC), "v1_frozen_index": jsonl_count(V1_INDEX), "knowledge": len(state.get("knowledge") or {}), "query_runs": len(state.get("query_runs") or {})},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "internal_trial.yaml").write_text(CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else "", encoding="utf-8")
    (OUT / "structured_v2_staging.yaml").write_text(V2_CONFIG.read_text(encoding="utf-8") if V2_CONFIG.exists() else "", encoding="utf-8")
    (OUT / "git_status.txt").write_text("\n".join(status), encoding="utf-8")
    print(json.dumps({"head": manifest["git"]["head"], "dirty_files": len(status), "8010": manifest["ports"]["8010_listening"], "8000": manifest["ports"]["8000_listening"], "legacy_atomic": manifest["counts"]["legacy_atomic_evidence"], "v1_frozen": manifest["counts"]["v1_frozen_index"], "output": str(OUT)}, ensure_ascii=False, indent=2))
    return 2 if manifest["ports"]["8000_listening"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
