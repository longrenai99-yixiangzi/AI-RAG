from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "evaluation" / "knowledge_os_system_audit" / "t09" / "regression.json"
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
ENDPOINT = "http://127.0.0.1:8010/api/v2/query"


def run(question: str, index: int) -> dict:
    payload = json.dumps({"question": question, "trial_user": "reviewer-001", "conversation_id": f"v23-regression-{index:02d}"}, ensure_ascii=False).encode("utf-8")
    request = Request(ENDPOINT, data=payload, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    started = time.perf_counter()
    with urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


def main() -> int:
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    rows = []
    for index, case in enumerate(benchmark, start=1):
        try:
            result = run(str(case.get("question") or ""), index)
            status = str(result.get("answer_status") or result.get("final_status") or "UNKNOWN")
            citations = result.get("citations") or result.get("citation") or []
            row = {"question_id": case.get("question_id"), "question": case.get("question"), "source": case.get("source"), "baseline_status_counts": case.get("answer_status_counts") or {}, "current_status": status, "citation_count": len(citations), "elapsed_ms": result.get("elapsed_ms"), "provider_http_requests": result.get("provider_http_requests", 0), "classification": "OBSERVED_ONLY", "strict_evaluable": False}
        except Exception as error:
            row = {"question_id": case.get("question_id"), "question": case.get("question"), "source": case.get("source"), "baseline_status_counts": case.get("answer_status_counts") or {}, "current_status": "ERROR", "citation_count": 0, "elapsed_ms": None, "provider_http_requests": 0, "classification": "NEW_FAILURE", "strict_evaluable": False, "error": f"{type(error).__name__}: {error}"}
        rows.append(row)
        print(f"regression={index}/{len(benchmark)} status={row['current_status']}", flush=True)
    status_counts = Counter(row["current_status"] for row in rows)
    payload = {"schema_version": "knowledge_os_v2_3.regression_report", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "OBSERVED_NOT_RELEASE_GATE", "regression_count": len(rows), "strict_evaluable": sum(row["strict_evaluable"] for row in rows), "classification_counts": dict(Counter(row["classification"] for row in rows)), "runtime_status_counts": dict(status_counts), "reason": "现有 Regression 48 基准来自真实试用问题/变体，未携带逐题答案 Claim 真值；本次只记录运行状态和错误，不计算准确率或宣布 Regression Gate PASS。", "provider_http_requests": sum(int(row.get("provider_http_requests") or 0) for row in rows), "formal_8000_touched": False, "rows": rows}
    (V23 / "regression_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (V23 / "regression_traces.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "regression_count", "strict_evaluable", "classification_counts", "runtime_status_counts", "provider_http_requests")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
