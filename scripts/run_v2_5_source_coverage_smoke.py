from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def basename(value: object) -> str:
    return str(value or "").replace("/", "\\").rsplit("\\", 1)[-1].casefold()


def compact(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def source_rows(record: dict) -> list[dict]:
    names = {basename(record.get("file_name")), basename(record.get("source_expected_path")), basename(record.get("owner_gold_source"))}
    return [row for row in ATOMIC if basename(row.get("file_name") or row.get("source_path")) in names]


def text_rows(rows: list[dict]) -> list[str]:
    return [str(row.get("text") or row.get("raw_text") or "") for row in rows]


def section_check(record: dict, chunks: list[dict], atomic: list[dict]) -> dict:
    rid = record["regression_id"]
    section = record.get("owner_gold_section")
    evidence: list[dict] = []
    if rid == "SRG-001":
        hits = [row for row in chunks if row.get("section_path") == "Page 17" and "设计任务书编制" in str(row.get("raw_text") or "")]
        evidence = [{"section": "Page 17 / 9.1 设计任务书编制", "matches": len(hits), "chunk_ids": [row.get("chunk_id") for row in hits[:3]]}]
        return {"pass": bool(hits), "evidence": evidence}
    if rid == "SRG-002":
        hits = [row for row in chunks if row.get("section_path") == "Page 30" and "17.3.2" in str(row.get("raw_text") or "")]
        evidence = [{"section": "Page 30 / 17.3.2 设计创效计算", "matches": len(hits), "chunk_ids": [row.get("chunk_id") for row in hits[:3]]}]
        return {"pass": bool(hits), "evidence": evidence}
    if rid == "SRG-004":
        rows = source_rows(record)
        found = []
        for item in section or []:
            row = int(item.get("row_start"))
            values = [compact(value) for value in item.get("values") or [] if compact(value)]
            hits = [x for x in rows if f"第{row}行" in str(x.get("text") or "") and all(value in compact(x.get("text")) for value in values)]
            found.append({"row": row, "matches": len(hits), "evidence_ids": [x.get("evidence_id") for x in hits[:2]]})
        return {"pass": bool(found) and all(item["matches"] > 0 for item in found), "evidence": found}
    if rid == "SRG-005":
        rows = source_rows(record)
        hits = [x for x in rows if "不少于40个项目图形文件" in str(x.get("text") or "") and x.get("table_id")]
        return {"pass": bool(hits), "evidence": [{"table": 1, "field": "考核内容", "matches": len(hits), "evidence_ids": [x.get("evidence_id") for x in hits[:3]]}]}
    if rid == "SRG-006":
        rows = source_rows(record)
        hits = [x for x in rows if "一、设计示范工程实施要求" in str(x.get("text") or "")]
        claims = record.get("expected_claims") or []
        claim_hits = [{"claim": claim, "matches": sum(compact(claim_part) in compact(x.get("text")) for x in rows for claim_part in [claim.split("：", 1)[-1]])} for claim in claims]
        return {"pass": bool(hits) and all(item["matches"] > 0 for item in claim_hits), "evidence": [{"section": "一、设计示范工程实施要求", "matches": len(hits), "evidence_ids": [x.get("evidence_id") for x in hits[:3]]}], "claim_evidence": claim_hits}
    if rid == "SRG-008":
        rows = source_rows(record)
        found = []
        for item in section or []:
            row = int(item.get("row_start"))
            values = [compact(value) for value in item.get("values") or [] if compact(value)]
            hits = [x for x in rows if f"第{row}行" in str(x.get("text") or "") and all(value in compact(x.get("text")) for value in values)]
            found.append({"sheet_name": item.get("sheet_name"), "row": row, "matches": len(hits), "evidence_ids": [x.get("evidence_id") for x in hits[:2]]})
        return {"pass": bool(found) and all(item["matches"] > 0 for item in found), "evidence": found}
    return {"pass": False, "evidence": [], "reason": "unsupported_owner_gold_shape"}


def main() -> int:
    global DOCS, CHUNKS, ATOMIC
    records = json.loads((V25 / "not_evaluable_6.json").read_text(encoding="utf-8"))["records"]
    DOCS = read_jsonl(STAGING / "documents.jsonl")
    CHUNKS = read_jsonl(STAGING / "semantic_chunks.jsonl")
    ATOMIC = read_jsonl(STAGING / "atomic_evidence.jsonl")
    doc_by_id = {str(row.get("document_id")): row for row in DOCS}
    for row in CHUNKS:
        doc = doc_by_id.get(str(row.get("document_id")), {})
        row["file_name"] = row.get("file_name") or doc.get("file_name")
        row["source_path"] = row.get("source_path") or doc.get("source_path")
    results = []
    for record in records:
        expected = {basename(record.get("file_name")), basename(record.get("source_expected_path")), basename(record.get("owner_gold_source"))}
        docs = [row for row in DOCS if basename(row.get("file_name") or row.get("source_path")) in expected]
        chunks = [row for row in CHUNKS if basename(row.get("file_name") or row.get("source_path")) in expected]
        atomic = source_rows(record)
        section = section_check(record, chunks, atomic)
        results.append({"regression_id": record["regression_id"], "source_answer_gold_id": record.get("source_answer_gold_id"), "file_name": record.get("file_name"), "expected_source": record.get("source_expected_path"), "physical_exists": bool(record.get("physical_exists")), "staged_document_count": len(docs), "staged_chunk_count": len(chunks), "staged_atomic_evidence_count": len(atomic), "section_evidence": section.get("evidence"), "claim_evidence": section.get("claim_evidence", []), "status": "PASS" if record.get("physical_exists") and docs and chunks and atomic and section.get("pass") else "FAIL", "failure": "" if record.get("physical_exists") and docs and chunks and atomic and section.get("pass") else "SOURCE_OR_SECTION_MISSING"})
    passed = sum(row["status"] == "PASS" for row in results)
    payload = {"schema_version": "knowledge_os_v2_5.source_coverage_smoke_test", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "scope": "six_not_evaluable_owner_gold_sources", "expected_count": len(records), "passed_count": passed, "failed_count": len(records) - passed, "gate": "PASS" if passed == len(records) else "FAIL", "formal_8000_touched": False, "staging_path": str(STAGING), "records": results}
    (V25 / "source_coverage_smoke_test.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("expected_count", "passed_count", "failed_count", "gate")}, ensure_ascii=False, indent=2))
    return 0 if payload["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
