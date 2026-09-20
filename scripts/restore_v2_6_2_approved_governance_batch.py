from __future__ import annotations

import json
from pathlib import Path

from scripts.build_v2_6_2_remediation_candidate import APPROVED, SOURCE_PATH_OVERRIDES, SOURCES


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
OUT = V26 / "v2_6_2_remaining_governance_proposal_approved_17.json"


def norm(value: str) -> str:
    return str(Path(value).resolve()).casefold()


def main() -> int:
    manifest = json.loads((V26 / "remediation_source_approval_v2_6_2.json").read_text(encoding="utf-8"))
    known = {
        norm(str(SOURCE_PATH_OVERRIDES.get(name, APPROVED / name)))
        for name in SOURCES
    }
    for filename in (
        "v2_6_2_missing_content_source_proposal.json",
        "v2_6_2_remaining_source_proposal.json",
        "v2_6_2_source_role_approval_batch.json",
        "v2_6_2_remaining_governance_proposal.json",
    ):
        payload = json.loads((V26 / filename).read_text(encoding="utf-8"))
        known.update(norm(str(item.get("source_path") or item.get("path"))) for item in payload.get("records") or [] if item.get("source_path") or item.get("path"))
    records = [item for item in manifest.get("records") or [] if norm(item["source_path"]) not in known]
    if len(records) != 17:
        raise RuntimeError(f"APPROVED_BATCH_RESTORE_EXPECTED_17_GOT_{len(records)}")
    output = {
        "schema_version": "knowledge_os_v2_6_2.remaining_governance_proposal",
        "captured_at": manifest.get("captured_at"),
        "candidate_hash": json.loads((V26 / "v2_6_2_compatibility_replay.json").read_text(encoding="utf-8")).get("current_candidate_hash"),
        "source_gap_question_count": 42,
        "multi_fact_gap_question_count": 11,
        "source_gap_questions_with_physical_body_match": 31,
        "source_count": 17,
        "approval_status": "APPROVED",
        "approved_by": "USER_CONFIRMED",
        "owner_confirmation_text": "确认：批准《V2.6.2剩余治理提案》中的17个物理文件按当前 SHA-256 作为 missing-content remediation 有效内容版本；不授权写入或启动8000。",
        "records": records,
        "formal_8000_touched": False,
        "8010_switch_authorized": False,
        "note": "Restored immutable approval record for the 17-file batch already integrated into the 31dc89 candidate.",
    }
    for item in output["records"]:
        item["approval_status"] = "APPROVED"
        item["approved_by"] = "USER_CONFIRMED"
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "APPROVED", "source_count": len(records), "out": str(OUT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
