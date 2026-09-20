from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"


def main() -> int:
    matrix = json.loads((V23 / "retrieval_matrix.json").read_text(encoding="utf-8"))
    version = str(matrix.get("best_post_reranker") or matrix.get("best_pre_reranker") or "")
    rows = matrix.get("per_question", {}).get(version) or []
    chunks = [json.loads(line) for line in (ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    documents = {json.loads(line).get("document_id"): json.loads(line) for line in (ROOT / "data" / "shadow" / "knowledge_v2_staging" / "documents.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    in_scope_files = {str(documents.get(row.get("document_id"), {}).get("file_name") or row.get("file_name") or "").casefold() for row in chunks}
    records = []
    for row in rows:
        file_rank = int(row.get("file_rank") or 0)
        section_rank = int(row.get("section_rank") or 0)
        expected_files = [str(value) for value in row.get("expected_files") or []]
        in_scope = any(str(value).replace("/", "\\").rsplit("\\", 1)[-1].casefold() in in_scope_files for value in expected_files)
        if not in_scope:
            status = "SOURCE_SCOPE_MISSING"
        elif file_rank == 0:
            status = "INSUFFICIENT"
        elif not row.get("expected_sections"):
            status = "PASS"
        elif section_rank == 0 or section_rank > 10:
            status = "SECTION_MISS"
        else:
            status = "PASS"
        records.append({"question_id": row.get("question_id"), "file_rank": file_rank, "section_rank": section_rank, "row_rank": int(row.get("row_rank") or 0), "status": status})
    evaluated_records = [item for item in records if item["status"] != "SOURCE_SCOPE_MISSING"]
    total = len(evaluated_records)
    passed = sum(item["status"] == "PASS" for item in evaluated_records)
    false_reject_rate = round((total - passed) / total, 4) if total else None
    payload = {
        "schema_version": "knowledge_os_v2_3.validator_report",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "PASS" if false_reject_rate is not None and false_reject_rate <= 0.10 else "FAIL",
        "candidate_version": version,
        "evaluated": total,
        "passed": passed,
        "source_scope_missing": sum(item["status"] == "SOURCE_SCOPE_MISSING" for item in records),
        "insufficient": sum(item["status"] == "INSUFFICIENT" for item in records),
        "section_miss": sum(item["status"] == "SECTION_MISS" for item in records),
        "false_reject_rate": false_reject_rate,
        "target_false_reject_rate": 0.10,
        "scope": "retrieval evidence candidate only; answer claims and citations are not evaluated until Answer Gold is available",
        "records": records,
        "runtime": {"formal_qdrant_write": False, "formal_8000_touched": False, "provider_http_requests": 0},
    }
    (V23 / "validator_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "candidate_version", "evaluated", "passed", "false_reject_rate", "target_false_reject_rate")}, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
