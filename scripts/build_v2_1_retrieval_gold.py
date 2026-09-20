"""T04: assemble a Retrieval Gold review package without upgrading provisional labels."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2_1" / "gold"
OWNER = ROOT / "evaluation" / "business_gold_v2" / "owner_approved_gold_manifest.json"
RECOMMENDED = ROOT / "evaluation" / "knowledge_os_system_audit" / "t09" / "recommended_22.json"
PROVISIONAL = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    owner_records = load_json(OWNER).get("records", [])
    confirmed_ids = {str(row.get("question_id")) for row in owner_records}
    retrieval: list[dict] = []
    answer: list[dict] = []
    for row in owner_records:
        locations = row.get("gold_location") or []
        record = {"question_id": row.get("question_id"), "question": row.get("question"), "acceptable_sources": [row.get("gold_primary_source")] if row.get("gold_primary_source") else [], "acceptable_sections": locations, "unacceptable_sources": [], "business_domain": "设计管理", "question_type": "OWNER_APPROVED_GOLD", "verification_status": "OWNER_CONFIRMED", "verified_by": row.get("owner_confirmation"), "verified_at": None, "gold_type": row.get("gold_type"), "candidate_source": None}
        retrieval.append(record)
        if row.get("gold_type") == "FULL_GOLD":
            answer.append({"question_id": row.get("question_id"), "question": row.get("question"), "expected_claims": row.get("gold_claims") or [], "required_evidence": locations, "acceptable_answer_boundary": "仅限 owner approved claims and cited locations", "verification_status": "OWNER_CONFIRMED", "verified_by": row.get("owner_confirmation"), "verified_at": None})

    recommended = load_json(RECOMMENDED).get("questions", [])
    for row in recommended:
        qid = str(row.get("candidate_id"))
        if qid in confirmed_ids:
            continue
        retrieval.append({"question_id": qid, "question": row.get("question"), "acceptable_sources": [], "acceptable_sections": [], "unacceptable_sources": [], "candidate_source": {"file": row.get("source_file"), "section": row.get("source_heading")}, "business_domain": "设计管理", "question_type": (row.get("types") or ["待分类"])[0], "verification_status": "PENDING_HUMAN_CONFIRM", "verified_by": None, "verified_at": None})
    import yaml
    provisional_rows = yaml.safe_load(PROVISIONAL.read_text(encoding="utf-8")).get("questions", []) if PROVISIONAL.exists() else []
    for row in provisional_rows:
        if len(retrieval) >= 50:
            break
        qid = str(row.get("id"))
        if any(str(item.get("question_id")) == qid for item in retrieval):
            continue
        retrieval.append({"question_id": qid, "question": row.get("question"), "acceptable_sources": [], "acceptable_sections": [], "unacceptable_sources": [], "candidate_source": {"files": row.get("expected_files") or []}, "business_domain": "设计管理", "question_type": row.get("topic") or "待分类", "verification_status": "PENDING_HUMAN_CONFIRM", "verified_by": None, "verified_at": None})
    def write_jsonl(path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    write_jsonl(OUT / "retrieval_gold.jsonl", retrieval[:50])
    write_jsonl(OUT / "answer_gold.jsonl", answer)
    manifest = {"schema_version": "knowledge_os_v2_1.gold", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "retrieval_gold_target": 50, "retrieval_gold_total": min(50, len(retrieval)), "retrieval_gold_confirmed": sum(row["verification_status"] == "OWNER_CONFIRMED" for row in retrieval[:50]), "retrieval_gold_pending": sum(row["verification_status"] == "PENDING_HUMAN_CONFIRM" for row in retrieval[:50]), "answer_gold_target": 30, "answer_gold_confirmed": len(answer), "source_manifests": {"owner_approved": str(OWNER), "recommended_candidates": str(RECOMMENDED), "provisional_questions": str(PROVISIONAL)}, "gate": {"retrieval_gold_pass": sum(row["verification_status"] == "OWNER_CONFIRMED" for row in retrieval[:50]) >= 50, "answer_gold_pass": len(answer) >= 30}, "note": "题目适合评估不等于 acceptable Source/Section 已确认；pending 记录不进入 Gold 指标。"}
    (OUT / "gold_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
