from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"
CHUNKS = ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl"
OUT = ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "replacement_candidates.jsonl"


def main() -> int:
    data = yaml.safe_load(GOLD.read_text(encoding="utf-8")) or {}
    wanted = {"C017", "C019", "C023", "C033", "C051", "C056", "C059", "C071", "C073", "C078", "C088", "C093", "C097", "C099", "C109", "C115", "C116", "C020", "C024", "C029", "C042", "C058", "C074", "C081", "C087", "C104"}
    rows = [row for row in data.get("questions") or [] if str(row.get("id")) in {f"FCQ-{number:03d}" for number in range(71, 91)}]
    chunks = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    docs = {str(row.get("document_id")): row for row in []}
    candidates: list[dict] = []
    for row in rows:
        expected = [str(value) for value in row.get("expected_files") or []]
        snippets = []
        for chunk in chunks:
            file_name = str(chunk.get("file_name") or "")
            if expected and not any(name.casefold() in file_name.casefold() or file_name.casefold() in name.casefold() for name in expected):
                continue
            snippets.append({"chunk_id": chunk.get("chunk_id"), "file_name": file_name, "section_path": chunk.get("section_path"), "snippet": str(chunk.get("raw_text") or "")[:800]})
            if len(snippets) >= 3:
                break
        candidates.append({"question_id": row.get("id"), "question": row.get("question"), "acceptable_sources": [], "acceptable_sections": [], "unacceptable_sources": [], "candidate_source": {"files": expected, "topic": row.get("topic"), "source": "POLICY_TEMPLATE_REPLACEMENT_CANDIDATE"}, "review_candidates": snippets, "business_domain": "设计管理", "question_type": row.get("topic") or "制度模板", "verification_status": "PENDING_HUMAN_CONFIRM", "verified_by": None, "verified_at": None, "created_at": datetime.now(timezone.utc).astimezone().isoformat()})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in candidates), encoding="utf-8")
    print(json.dumps({"count": len(candidates), "ids": [row["question_id"] for row in candidates], "output": str(OUT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
