from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
T09 = ROOT / "evaluation" / "knowledge_os_system_audit" / "t09"


def main() -> int:
    questions = json.loads((T09 / "holdout.json").read_text(encoding="utf-8"))
    sealed = json.loads((T09 / "holdout_first_run.json").read_text(encoding="utf-8")) if (T09 / "holdout_first_run.json").exists() else {}
    rows = []
    with httpx.Client(timeout=180, trust_env=False) as client:
        for item in questions:
            try:
                started = time.perf_counter()
                response = client.post("http://127.0.0.1:8010/api/v2/query", json={"question": item["question"], "trial_user": "reviewer-001", "conversation_id": f"v25-holdout-{item['question_id']}"})
                response.raise_for_status()
                result = response.json()
                rows.append({"question_id": item["question_id"], "question": item["question"], "answer_status": result.get("answer_status"), "answer_mode": result.get("answer_mode"), "query_run_id": result.get("query_run_id"), "citation_count": len(result.get("citations") or []), "provider_http_requests": result.get("provider_http_requests", 0), "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "error": ""})
            except Exception as error:
                rows.append({"question_id": item["question_id"], "question": item["question"], "answer_status": "ERROR", "answer_mode": None, "query_run_id": None, "citation_count": 0, "provider_http_requests": 0, "elapsed_ms": None, "error": f"{type(error).__name__}: {error}"})
            print(f"holdout={len(rows)}/{len(questions)} status={rows[-1]['answer_status']}", flush=True)
    errors = sum(row["answer_status"] == "ERROR" for row in rows)
    payload = {"schema_version": "knowledge_os_v2_5.holdout_result", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "questions": len(rows), "scored": False, "sealed_baseline_path": str(T09 / "holdout_first_run.json"), "sealed_baseline_questions": sealed.get("questions"), "reason": "Holdout 仅保留原始运行结果，不用于调整检索或答案规则；待内容负责人盲审。", "error_count": errors, "gate": "PASS" if len(rows) == len(questions) and errors == 0 else "FAIL", "formal_8000_touched": False, "runtime_endpoint": "http://127.0.0.1:8010/api/v2/query", "rows": rows}
    (V25 / "holdout_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("questions", "error_count", "scored", "gate")}, ensure_ascii=False, indent=2))
    return 0 if payload["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
