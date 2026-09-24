"""Build a non-authoritative d6bc Owner fact/source review queue."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_6_remediation" / "v2_6_2_sources"
REPLAY = V26 / "v2_6_2_compatibility_replay.json"
OUT = V26 / "v2_6_2_owner_review_precheck_d6bc.json"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def precheck(question: str, answer: str) -> list[str]:
    reasons: list[str] = []
    if "未检索到可直接支撑结论" in answer:
        reasons.append("ANSWER_DECLARES_INSUFFICIENT_EVIDENCE")
    if re.search(r"关键文件：|\[\[raw/", answer) and re.search(r"多少|几项|几个|哪些|哪几个|分别|各", question):
        reasons.append("ANSWER_IS_FILE_POINTER_FOR_FACT_QUERY")
    if len(question) >= 16 and len(answer) < 45:
        reasons.append("COMPOUND_QUERY_WITH_VERY_SHORT_ANSWER")
    if re.search(r"分别|各|与|和|及", question) and not re.search(r"分别|各|和|及|、|；|,|，", answer):
        reasons.append("COMPOUND_QUERY_NOT_OBVIOUSLY_EXPANDED")
    return reasons


def main() -> int:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    docs = read_jsonl(STAGING / "documents.jsonl")
    evidence = read_jsonl(STAGING / "atomic_evidence.jsonl")
    doc_ids = {row.get("document_id") for row in docs}
    evidence_ids = {row.get("evidence_id") for row in evidence}
    by_doc = {row.get("document_id"): row for row in docs}

    records: list[dict] = []
    reason_counts: Counter[str] = Counter()
    citation_count = 0
    document_matches = 0
    evidence_matches = 0
    locator_matches = 0

    for row in replay["records"]:
        reasons = precheck(row.get("question", ""), row.get("current_answer", ""))
        for reason in reasons:
            reason_counts[reason] += 1
        citations = []
        for citation in row.get("current_citations") or []:
            citation_count += 1
            document_id = citation.get("document_id")
            if document_id in doc_ids:
                document_matches += 1
            if citation.get("evidence_id") in evidence_ids:
                evidence_matches += 1
            doc = by_doc.get(document_id)
            locator_match = bool(doc and citation.get("source_path") == doc.get("source_path"))
            locator_matches += int(locator_match)
            citations.append(
                {
                    "citation_id": citation.get("citation_id"),
                    "evidence_id": citation.get("evidence_id"),
                    "source_id": citation.get("source_id"),
                    "document_id": document_id,
                    "source_path": citation.get("source_path"),
                    "file_name": citation.get("file_name"),
                    "location": citation.get("location"),
                    "staging_document_match": document_id in doc_ids,
                    "staging_evidence_match": citation.get("evidence_id") in evidence_ids,
                    "staging_source_path_match": locator_match,
                }
            )
        records.append(
            {
                "question_hash": row.get("question_hash"),
                "question": row.get("question"),
                "current_candidate_hash": row.get("current_candidate_hash"),
                "current_status": row.get("current_status"),
                "current_bundle_status": row.get("current_bundle_status"),
                "current_answer": row.get("current_answer"),
                "current_validation": row.get("current_validation"),
                "citations": citations,
                "agent_precheck": "REVIEW_REQUIRED" if reasons else "NO_STRUCTURAL_PRECHECK_FLAG",
                "precheck_reasons": reasons,
                "owner_decision": None,
            }
        )

    payload = {
        "schema_version": "knowledge_os_v2_6_2.owner_review_precheck",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "PRECHECK_ONLY_NOT_OWNER_DECISION",
        "candidate_hash": replay["current_candidate_hash"],
        "review_scope": "368 d6bc offline compatibility replay records",
        "decision_semantics": "owner_decision remains null; this artifact does not create ANSWER_GOLD_MATCH or NOT_VERIFIED",
        "summary": {
            "total": len(records),
            "precheck_flagged": sum(bool(row["precheck_reasons"]) for row in records),
            "reason_counts": dict(reason_counts),
            "citation_count": citation_count,
            "staging_evidence_id_matches": evidence_matches,
            "staging_document_id_matches": document_matches,
            "staging_source_path_matches": locator_matches,
        },
        "runtime_boundaries": {
            "formal_8000_touched": False,
            "formal_qdrant_write": False,
            "formal_sqlite_write": False,
            "formal_index_switch": False,
            "source_root_read_only": True,
        },
        "records": records,
    }
    assert len(records) == replay["historical_question_count"]
    assert payload["candidate_hash"] == "d6bc010ac8c06057e79c6c8ae6c0a82083d78b2f88125a769f10033a5c2061f9"
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "out": str(OUT), **payload["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
