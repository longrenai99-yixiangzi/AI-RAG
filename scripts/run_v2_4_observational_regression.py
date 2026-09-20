from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_v2_3_regression_48 import run


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"
BENCHMARK = ROOT / "evaluation" / "knowledge_os_system_audit" / "t09" / "regression.json"


def main() -> int:
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    previous = {row.get("question_id"): row for row in (json.loads(line) for line in (V23 / "regression_traces.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())} if (V23 / "regression_traces.jsonl").exists() else {}
    rows = []
    for index, case in enumerate(benchmark, start=1):
        try:
            result = run(str(case.get("question") or ""), index)
            status = str(result.get("answer_status") or result.get("final_status") or "UNKNOWN")
            citations = result.get("citations") or result.get("citation") or []
            prior = str((previous.get(case.get("question_id")) or {}).get("current_status") or "")
            classification = "UNCHANGED" if prior == status else "IMPROVED" if prior and prior != "ANSWERED" and status == "ANSWERED" else "REGRESSED" if prior == "ANSWERED" and status != "ANSWERED" else "NEW_FAILURE" if status in {"ERROR", "UNKNOWN"} else "OBSERVED"
            rows.append({"question_id": case.get("question_id"), "question": case.get("question"), "v2_3_status": prior, "v2_4_status": status, "classification": classification, "citation_count": len(citations), "elapsed_ms": result.get("elapsed_ms"), "failure_code": result.get("failure_code") or result.get("failure_reason"), "provider_http_requests": result.get("provider_http_requests", 0)})
        except Exception as error:
            rows.append({"question_id": case.get("question_id"), "question": case.get("question"), "v2_3_status": str((previous.get(case.get("question_id")) or {}).get("current_status") or ""), "v2_4_status": "ERROR", "classification": "NEW_FAILURE", "citation_count": 0, "elapsed_ms": None, "failure_code": f"{type(error).__name__}: {error}", "provider_http_requests": 0})
        print(f"observational={index}/{len(benchmark)} status={rows[-1]['v2_4_status']}", flush=True)
    payload = {"schema_version": "knowledge_os_v2_4.observational_regression_result", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "OBSERVED", "count": len(rows), "v2_3_status_counts": dict(Counter(row["v2_3_status"] for row in rows)), "v2_4_status_counts": dict(Counter(row["v2_4_status"] for row in rows)), "diff_counts": dict(Counter(row["classification"] for row in rows)), "accuracy_gate": "NOT_APPLICABLE", "provider_http_requests": sum(int(row.get("provider_http_requests") or 0) for row in rows), "rows": rows}
    V24.mkdir(parents=True, exist_ok=True)
    (V24 / "observational_regression_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "count", "v2_3_status_counts", "v2_4_status_counts", "diff_counts", "accuracy_gate")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
