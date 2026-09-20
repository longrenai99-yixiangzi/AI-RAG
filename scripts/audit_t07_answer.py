"""Audit answer construction with validated business cases and provisional FCQ labels."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t07"
ENDPOINT = "http://127.0.0.1:8010/api/v2/query"

from scripts.evaluate_knowledge_os_optimization import CASES


def main() -> int:
    rows = []
    with httpx.Client(timeout=180, trust_env=False) as client:
        for case in CASES:
            response = client.post(ENDPOINT, json={"question": case["question"], "trial_user": "reviewer-001", "conversation_id": f"system-audit-t07-{case['id']}"})
            response.raise_for_status()
            result = response.json()
            bundle = (result.get("debug") or {}).get("evidence_bundle") or {}
            answer = str(result.get("answer") or "")
            citation_text = "\n".join(str(item.get("excerpt") or "") for item in result.get("citations", []))
            missing = [term for term in case.get("answer_terms", []) if _compact(term) not in _compact(answer)]
            unsupported = [term for term in case.get("source_terms", []) if _compact(term) not in _compact(citation_text)]
            source_hit = any(str(case.get("source") or "") in str(item.get("file_name") or "") for item in result.get("citations", []))
            location_hit = not case.get("location") or any(case["location"] == str(item.get("display_location") or "") for item in result.get("citations", []))
            status_hit = result.get("answer_status") in case.get("statuses", [])
            passed = status_hit and source_hit and location_hit and not missing and not unsupported
            rows.append({
                "question_id": case["id"], "question": case["question"], "passed": passed,
                "answer_status": result.get("answer_status"), "answer_mode": result.get("answer_mode"), "query_run_id": result.get("query_run_id"),
                "evidence_input": [{"evidence_id": item.get("evidence_id"), "source_id": item.get("source_id"), "source_version": item.get("source_version"), "file_name": item.get("file_name"), "location": item.get("location"), "role": item.get("role")} for item in bundle.get("verified_evidence", [])],
                "expected_claims": case.get("answer_terms", []),
                "generated_claims": [{"claim_id": item.get("claim_id"), "claim_text": item.get("rendered_claim_text"), "evidence_ids": item.get("evidence_ids"), "citation_ids": item.get("citation_ids")} for item in result.get("claims", [])],
                "claim_evidence_map": result.get("claim_evidence_map", []),
                "citation_map": [{"citation_id": item.get("citation_id"), "evidence_id": item.get("evidence_id"), "source_id": item.get("source_id"), "file_name": item.get("file_name"), "location": item.get("display_location")} for item in result.get("citations", [])],
                "missing_claims": missing, "unsupported_claim_checks": unsupported,
                "error_codes": [] if passed else _answer_errors(status_hit, source_hit, location_hit, missing, unsupported),
                "answer": answer,
            })

    t06 = _read_json(ROOT / "evaluation" / "knowledge_os_system_audit" / "t06" / "validator_audit.json")
    payload = {
        "task": "T07_ANSWER_ENGINE_AUDIT", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "RUN_VALIDATED_BUSINESS_SUBSET",
        "validated_questions": len(rows), "answer_correct_rate": _rate(sum(row["passed"] for row in rows), len(rows)),
        "unsupported_claim_rate": _rate(sum(bool(row["unsupported_claim_checks"]) for row in rows), len(rows)),
        "citation_correctness": _rate(sum(not row["error_codes"] or "ANSWER_CITATION_MISMATCH" not in row["error_codes"] for row in rows), len(rows)),
        "provisional_fcq100": {
            "questions": t06.get("questions"),
            "final_expected_source_hit_rate": t06.get("final_expected_source_hit_rate"),
            "note": "FCQ-100 没有逐项业务 Claim 真值，只用于来源/主题层审计，不能计入 Answer Correct。",
        },
        "coverage": ["单事实", "多事实", "数量", "列举", "表格", "制度关系", "项目关系", "版本边界", "无答案"],
        "not_yet_business_labeled": ["多来源归纳", "冲突资料的最终业务裁决"],
        "rows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (OUT / f"answer_audit_{stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "answer_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    first = OUT / "answer_first_run.json"
    if not first.exists():
        first.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("validated_questions", "answer_correct_rate", "unsupported_claim_rate", "citation_correctness")}, ensure_ascii=False))
    return 0


def _answer_errors(status: bool, source: bool, location: bool, missing: list[str], unsupported: list[str]) -> list[str]:
    errors = []
    if not status: errors.append("ANSWER_WRONG_FACT")
    if missing: errors.append("ANSWER_MISSING_FACT")
    if unsupported: errors.append("ANSWER_UNSUPPORTED_CLAIM")
    if not source or not location: errors.append("ANSWER_CITATION_MISMATCH")
    return errors


def _compact(value: object) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _rate(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator, "rate": round(numerator / denominator, 4) if denominator else None}


def _read_json(path: Path) -> dict:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}


if __name__ == "__main__":
    raise SystemExit(main())
