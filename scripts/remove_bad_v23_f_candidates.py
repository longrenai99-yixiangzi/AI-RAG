from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "replacement_candidates.jsonl"
AUDIO = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "rejected_candidates.jsonl"


def main() -> int:
    rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    bad = [row for row in rows if str(row.get("question_id", "")).startswith("V23-F")]
    keep = [row for row in rows if not str(row.get("question_id", "")).startswith("V23-F")]
    GOLD.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in keep), encoding="utf-8")
    with AUDIO.open("a", encoding="utf-8") as handle:
        for row in bad:
            handle.write(json.dumps({"question_id": row.get("question_id"), "status": "REJECTED_GENERATOR_QUALITY", "reason": "table_header_row_not_data", "recorded_at": datetime.now(timezone.utc).astimezone().isoformat()}, ensure_ascii=False) + "\n")
    print(json.dumps({"removed_from_review": len(bad), "remaining_candidates": len(keep)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
