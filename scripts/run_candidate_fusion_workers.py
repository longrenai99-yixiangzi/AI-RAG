from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHADOW_DIR = PROJECT_ROOT / "data" / "shadow" / "candidate_fusion_v2"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("query", "rerank"))
    args = parser.parse_args()
    if args.phase == "query":
        records = _read_json(SHADOW_DIR / "cases.json")["records"]
        result = _run_each("query", [{"id": row["id"], "question": row["question"]} for row in records])
        _write_json(SHADOW_DIR / "query_vectors.json", {"model": "BGE-M3", "precision": "fp16", "vectors": result, "provider_http_requests": 0, "network_access": False})
    else:
        records = _read_jsonl(SHADOW_DIR / "pre_rerank_inputs.jsonl")
        result = _run_each("rerank", records, group_size=3)
        _write_json(SHADOW_DIR / "reranker_scores.json", {"model": "bge-reranker-v2-m3", "precision": "fp16", "scores": result, "provider_http_requests": 0, "network_access": False})
    return 0


def _run_each(phase: str, rows: list[dict[str, Any]], *, group_size: int = 1) -> dict[str, Any]:
    output: dict[str, Any] = {}
    directory = SHADOW_DIR / "workers" / f"{phase}-fp16-single"
    for index, start in enumerate(range(0, len(rows), group_size), start=1):
        group = rows[start : start + group_size]
        input_path = directory / f"input-{index:03d}.json" if phase == "query" else directory / f"input-{index:03d}.jsonl"
        output_path = directory / f"output-{index:03d}.json"
        if phase == "query":
            _write_json(input_path, {"records": group})
        else:
            _write_jsonl(input_path, group)
        if not output_path.is_file():
            detail = "worker failed"
            for attempt in range(3):
                completed = subprocess.run([sys.executable, "-m", "scripts.candidate_fusion_model_worker", phase, str(input_path), str(output_path)], cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8")
                if completed.returncode == 0:
                    break
                detail = (completed.stderr or completed.stdout or detail).strip()
                if attempt < 2:
                    time.sleep(2)
            else:
                raise RuntimeError(f"{phase} worker {index} failed after 3 attempts: {detail[-4000:]}")
        payload = _read_json(output_path)
        output.update(payload["vectors"] if phase == "query" else payload["scores"])
    return output


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
