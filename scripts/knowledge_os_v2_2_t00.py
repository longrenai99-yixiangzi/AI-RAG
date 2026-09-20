from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2_2"
V21 = ROOT / "evaluation" / "knowledge_os_v2_1" / "baseline" / "manifest.json"


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            h.update(block)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


def port(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def main() -> int:
    baseline = json.loads(V21.read_text(encoding="utf-8")) if V21.exists() else {}
    paths = {
        "v1_index": ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "atomic_evidence.jsonl",
        "v2_index": ROOT / "data" / "shadow" / "knowledge_v2_staging" / "bm25_v2.json",
        "v2_chunks": ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl",
        "v2_1_gold": ROOT / "evaluation" / "knowledge_os_v2_1" / "gold" / "gold_manifest.json",
        "v2_1_node": ROOT / "evaluation" / "knowledge_os_v2_1" / "node_binding" / "metrics.json",
        "v2_1_chunk": ROOT / "evaluation" / "knowledge_os_v2_1" / "chunk_governance" / "metrics.json",
        "v2_1_dense": ROOT / "evaluation" / "knowledge_os_v2_1" / "retrieval_ab" / "dense_v2_metrics.json",
        "trial_config": ROOT / "config" / "internal_trial.yaml",
    }
    payload = {"schema_version": "knowledge_os_v2_2.t00", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "git": {"head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"), "dirty_files": git("status", "--porcelain").splitlines()}, "ports": {"8000": port(8000), "8010": port(8010)}, "artifacts": {name: {"path": str(path), "sha256": sha(path)} for name, path in paths.items()}, "previous_v2_1_baseline": baseline, "gate": {"v1_index_touched": False, "8000_touched": False, "8010_switched": False, "holdout_run": False}}
    (OUT / "baseline.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"head": payload["git"]["head"], "dirty_files": len(payload["git"]["dirty_files"]), "8000": payload["ports"]["8000"], "8010": payload["ports"]["8010"], "output": str(OUT / 'baseline.json')}, ensure_ascii=False, indent=2))
    return 2 if payload["ports"]["8000"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
