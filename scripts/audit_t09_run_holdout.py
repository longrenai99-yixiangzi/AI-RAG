"""Run and permanently preserve the first Holdout responses without scoring them."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t09"


def main() -> int:
    target = OUT / "holdout_first_run.json"
    if target.exists():
        value = json.loads(target.read_text(encoding="utf-8"))
        print(json.dumps({"status": "PRESERVED_NOT_OVERWRITTEN", "questions": value.get("questions"), "captured_at": value.get("captured_at")}, ensure_ascii=False))
        return 0
    questions = json.loads((OUT / "holdout.json").read_text(encoding="utf-8"))
    rows = []
    with httpx.Client(timeout=180, trust_env=False) as client:
        for item in questions:
            response = client.post("http://127.0.0.1:8010/api/v2/query", json={"question": item["question"], "trial_user": "reviewer-001", "conversation_id": f"sealed-holdout-{item['question_id']}"})
            response.raise_for_status()
            result = response.json()
            rows.append({"question_id": item["question_id"], "question": item["question"], "types": item.get("types", []), "answer_status": result.get("answer_status"), "answer_mode": result.get("answer_mode"), "answer": result.get("answer"), "query_run_id": result.get("query_run_id"), "failure": result.get("diagnostics"), "citations": [{key: citation.get(key) for key in ("file_name", "source_id", "source_version", "display_location")} for citation in result.get("citations", [])]})
    payload = {"task": "T09_HOLDOUT_FIRST_RUN", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "questions": len(rows), "scored": False, "reason": "Holdout尚无业务真值；首次原始结果永久保留，待内容负责人盲审", "rows": rows}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    manifest["holdout_policy"]["sealed"] = True
    manifest["holdout_policy"]["first_run"] = str(target)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "SEALED", "questions": len(rows), "captured_at": payload["captured_at"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
