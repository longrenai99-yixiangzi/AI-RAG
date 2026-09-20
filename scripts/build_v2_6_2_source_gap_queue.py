from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
INPUT = V26 / "v2_6_2_compatibility_replay.json"
OUT = V26 / "v2_6_2_source_gap_queue.json"


def main() -> int:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = [
        row for row in payload.get("records") or []
        if row.get("current_bundle_status") == "INSUFFICIENT_EVIDENCE"
        and (lambda question: len(question) >= 2 and any(char.isalnum() or "\u3400" <= char <= "\u9fff" for char in question))(str(row.get("question") or "").strip())
    ]
    queue = []
    source_counts: Counter[str] = Counter()
    for row in rows:
        citations = row.get("current_citations") or []
        sources = []
        for citation in citations:
            path_text = str(citation.get("source_path") or "")
            path = Path(path_text) if path_text else None
            file_name = str(citation.get("file_name") or (path.name if path else ""))
            key = path_text or file_name or "NO_SOURCE"
            source_counts[key] += 1
            sources.append({
                "file_name": file_name,
                "source_path": path_text,
                "physical_exists": bool(path and path.exists()),
                "location": citation.get("location") or citation.get("display_location"),
                "source_id": citation.get("source_id"),
                "evidence_id": citation.get("evidence_id"),
            })
        queue.append({
            "question_hash": row.get("question_hash"),
            "question": row.get("question"),
            "current_status": row.get("current_status"),
            "current_bundle_status": row.get("current_bundle_status"),
            "sources": sources,
            "action": "VERIFY_SOURCE_BODY_AND_EVIDENCE_ROLE",
        })
    result = {
        "schema_version": "knowledge_os_v2_6_2.source_gap_queue",
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidate_hash": payload.get("current_candidate_hash"),
        "question_count": len(queue),
        "source_reference_counts": source_counts,
        "physical_source_exists_counts": {
            "has_at_least_one_existing_source": sum(any(item["physical_exists"] for item in row["sources"]) for row in queue),
            "no_existing_source": sum(not any(item["physical_exists"] for item in row["sources"]) for row in queue),
        },
        "owner_action": "确认来源正文、版本和定位后，再批量准入候选；禁止以当前错误摘录直接升级为答案。",
        "queue": queue,
        "formal_8000_touched": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("candidate_hash", "question_count", "physical_source_exists_counts", "out") if key in result} | {"out": str(OUT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
