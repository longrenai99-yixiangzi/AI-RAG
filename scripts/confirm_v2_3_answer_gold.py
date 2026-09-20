from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "evaluation" / "knowledge_os_v2_3"
BASE = ROOT / "evaluation" / "knowledge_os_v2_1" / "gold" / "answer_gold.jsonl"
CANDIDATES = V23 / "gold" / "answer_gold_candidates.jsonl"
OUT = V23 / "gold" / "answer_gold.jsonl"
DECISIONS = V23 / "gold" / "answer_review_decisions.jsonl"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def main() -> int:
    now = datetime.now(timezone.utc).astimezone().isoformat()
    base = [row for row in read(BASE) if str(row.get("verification_status")) in {"OWNER_CONFIRMED", "CONFIRMED"}]
    candidates = [row for row in read(CANDIDATES) if str(row.get("question_id", "")).startswith("V23-A")]
    if len(candidates) != 22:
        raise RuntimeError(f"expected 22 answer candidates, got {len(candidates)}")
    for row in candidates:
        row.update({"verification_status": "OWNER_CONFIRMED", "verified_by": "USER_CONFIRMED_A001_A022", "verified_at": now})
    rows = base + candidates
    if len(rows) != 30 or len({str(row.get("question_id")) for row in rows}) != 30:
        raise RuntimeError("Answer Gold must contain 30 unique records")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    decisions = [{"question_id": row["question_id"], "status": "CONFIRMED", "reviewer": "USER", "comment": "用户明确确认 A001-A022 全部作为 Answer Gold", "reviewed_at": now} for row in candidates]
    DECISIONS.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in decisions), encoding="utf-8")
    snapshot = {"schema_version": "knowledge_os_v2_3.answer_gold_snapshot", "captured_at": now, "source": str(OUT), "confirmed": len(rows), "target": 30, "pending": 0, "candidate_ids": [row["question_id"] for row in candidates], "status": "PASS"}
    (V23 / "answer_gold_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
