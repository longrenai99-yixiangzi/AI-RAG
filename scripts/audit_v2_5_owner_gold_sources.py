from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V24 = ROOT / "evaluation" / "knowledge_os_v2_4"
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
OWNER = ROOT / "evaluation" / "business_gold_v2" / "owner_approved_gold_manifest.json"
DOCS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "documents.jsonl"
V2_DOCS = ROOT / "data" / "shadow" / "document_intelligence_v2" / "documents.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    strict = json.loads((V24 / "strict_regression_result.json").read_text(encoding="utf-8"))
    ids = [row["source_answer_gold_id"] for row in strict["records"] if row.get("set") == "core" and row.get("result") == "NOT_EVALUABLE"]
    owners = {str(row.get("question_id")): row for row in (json.loads(OWNER.read_text(encoding="utf-8")).get("records") or [])}
    docs = read_jsonl(DOCS) + read_jsonl(V2_DOCS)
    records = []
    for regression_id in [row["question_id"] for row in strict["records"] if row.get("set") == "core" and row.get("result") == "NOT_EVALUABLE"]:
        gold_id = next(row["source_answer_gold_id"] for row in strict["records"] if row.get("question_id") == regression_id)
        owner = owners.get(gold_id) or {}
        path = Path(str(owner.get("gold_primary_source") or ""))
        file_name = path.name
        exact_registered = [row for row in docs if str(row.get("source_path") or "").casefold() == str(path).casefold()]
        mirrors = [row for row in docs if str(row.get("file_name") or "").casefold() == file_name.casefold()]
        exists = path.is_file()
        current_status = "SOURCE_NOT_REGISTERED" if exists and not exact_registered else "REGISTERED" if exact_registered else "SOURCE_MISSING"
        reason = "SOURCE_NOT_IN_SHADOW_SCOPE" if exists and not exact_registered else "SOURCE_PARSE_MISSING" if exact_registered and not any(row.get("parse_status") == "parsed" for row in exact_registered) else "SOURCE_NOT_REGISTERED"
        location = owner.get("gold_location")
        records.append({"regression_id": regression_id, "question": owner.get("question"), "owner_gold_source": str(path), "owner_gold_source_version": owner.get("source_version") or owner.get("source_hash") or "[待核实：Owner Gold 清单未提供 source_version]", "owner_gold_section": location, "source_expected_path": str(path), "source_current_status": current_status, "reason_not_evaluable": reason, "physical_exists": exists, "file_name": file_name, "file_size_bytes": path.stat().st_size if exists else None, "file_sha256": sha(path), "file_type": path.suffix.lower(), "owner_manifest_status": owner.get("owner_approval_status"), "owner_confirmation": owner.get("owner_confirmation"), "exact_registered_count": len(exact_registered), "same_name_registration_count": len(mirrors), "same_name_registration_paths": [row.get("source_path") for row in mirrors[:10]], "knowledge_scope": "OUTSIDE_V2_4_FROZEN_SHADOW_SCOPE" if exists and not exact_registered else "IN_SCOPE"})
    V25.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone().isoformat()
    (V25 / "not_evaluable_6.json").write_text(json.dumps({"schema_version": "knowledge_os_v2_5.not_evaluable_6", "captured_at": now, "count": len(records), "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    (V25 / "owner_gold_source_audit.json").write_text(json.dumps({"schema_version": "knowledge_os_v2_5.owner_gold_source_audit", "captured_at": now, "count": len(records), "admission_summary": {"SOURCE_ADMISSION_APPROVED": 0, "GOLD_REVIEW_REQUIRED": len(records)}, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(records), "ids": [row["regression_id"] for row in records], "physical_exists": sum(row["physical_exists"] for row in records), "source_not_in_scope": sum(row["reason_not_evaluable"] == "SOURCE_NOT_IN_SHADOW_SCOPE" for row in records)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
