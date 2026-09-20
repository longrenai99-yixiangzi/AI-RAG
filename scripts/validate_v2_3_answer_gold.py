from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
GOLD = V23 / "gold" / "answer_gold.jsonl"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def main() -> int:
    rows = read(GOLD)
    records = []
    for row in rows:
        evidence = row.get("required_evidence")
        evidence = evidence if isinstance(evidence, list) else [evidence] if evidence else []
        source_paths = [str(item.get("source_path") or "") for item in evidence if isinstance(item, dict)]
        claims_ok = bool(row.get("expected_claims")) and all(str(item).strip() for item in row.get("expected_claims") or [])
        evidence_ok = bool(evidence) and all(isinstance(item, dict) and (item.get("source_path") or item.get("section") or item.get("page") or item.get("line_start") or item.get("table") or item.get("table_id") or item.get("sheet_name") or item.get("text") or item.get("location") or item.get("source_location")) for item in evidence)
        source_exists = all(Path(path).is_file() for path in source_paths) if source_paths else False
        status = "PASS" if claims_ok and evidence_ok and source_exists else "SOURCE_SCOPE_MISSING" if claims_ok and evidence_ok else "INVALID"
        records.append({"question_id": row.get("question_id"), "claims_ok": claims_ok, "evidence_ok": evidence_ok, "source_exists": source_exists, "status": status})
    count = len(rows)
    valid = sum(row["status"] == "PASS" for row in records)
    scope_missing = sum(row["status"] == "SOURCE_SCOPE_MISSING" for row in records)
    invalid = sum(row["status"] == "INVALID" for row in records)
    payload = {"schema_version": "knowledge_os_v2_3.answer_validation_report", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "PASS" if count == 30 and invalid == 0 else "FAIL", "evaluated": count, "target": 30, "valid_in_scope": valid, "source_scope_missing": scope_missing, "invalid": invalid, "scope": "package-level Answer Gold validation; generated-answer claim/citation correctness is a later response-level check", "records": records, "runtime": {"llm_calls": 0, "provider_http_requests": 0, "formal_8000_touched": False}}
    (V23 / "answer_validation_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "evaluated", "valid_in_scope", "source_scope_missing", "invalid")}, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
