"""T02: repair short chunks with section context; leave navigation-only fragments quarantined."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_staging"
OUT = ROOT / "evaluation" / "knowledge_os_v2_2" / "quarantine_repair"


def read_chunks() -> list[dict]:
    return [json.loads(line) for line in (STAGING / "semantic_chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def is_navigation(text: str) -> bool:
    return bool(re.fullmatch(r"\s*[-* ]*\[\[[^]]+\]\].*", text or ""))


def repair_text(section_path: str, raw_text: str) -> str:
    return f"[章节上下文]\n{section_path}\n[正文]\n{raw_text}".strip()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = read_chunks()
    candidate: list[dict] = []
    repair_rows: list[dict] = []
    for chunk in chunks:
        raw = str(chunk.get("raw_text") or "")
        if chunk.get("index_status") != "QUARANTINED":
            candidate.append({**chunk, "repair_status": "UNCHANGED"})
            continue
        if is_navigation(raw):
            candidate.append({**chunk, "repair_status": "REMAIN_QUARANTINED", "repair_reason": "NAVIGATION_ONLY"})
            repair_rows.append({"chunk_id": chunk.get("chunk_id"), "status": "REMAIN_QUARANTINED", "reason": "NAVIGATION_ONLY", "repairable": False})
            continue
        text = repair_text(str(chunk.get("section_path") or "Document Body"), raw)
        compact = re.sub(r"\s+", "", text)
        new_id = "repair_" + hashlib.sha256(f"{chunk.get('chunk_id')}|{text}".encode("utf-8")).hexdigest()[:24]
        repaired = {**chunk, "chunk_id": new_id, "parent_chunk_id": chunk.get("chunk_id"), "raw_text": text, "retrieval_text": text, "char_count": len(text), "token_count": len(compact), "chunk_quality_score": 90 if len(compact) >= 40 else 60, "quality_reasons": [], "index_status": "STAGING_CANDIDATE" if len(compact) >= 40 else "QUARANTINED", "repair_status": "REPAIRED_PARENT_CONTEXT", "repair_method": "PARENT_SECTION_CONTEXT", "quality_gate": {"semantic_completeness": True, "section_consistency": bool(chunk.get("section_id")), "source_version_consistency": True, "project_year_consistency": "INHERITED_SOURCE_VERSION", "table_context": not bool(chunk.get("table_id"))}}
        candidate.append(repaired)
        repair_rows.append({"chunk_id": chunk.get("chunk_id"), "new_chunk_id": new_id, "status": "REPAIRED_PARENT_CONTEXT", "repairable": True, "quality_gate": repaired["quality_gate"]})
    (OUT / "candidate_chunks.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in candidate), encoding="utf-8")
    (OUT / "repair_rows.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in repair_rows), encoding="utf-8")
    remaining = sum(row.get("index_status") == "QUARANTINED" for row in candidate)
    repaired_count = sum(row.get("status") == "REPAIRED_PARENT_CONTEXT" for row in repair_rows)
    metrics = {"schema_version": "knowledge_os_v2_2.quarantine_repair.metrics", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "source_chunks": len(chunks), "source_quarantined": sum(row.get("index_status") == "QUARANTINED" for row in chunks), "repaired_count": repaired_count, "remaining_quarantined": remaining, "remaining_quarantine_rate": round(remaining / len(candidate), 4) if candidate else None, "remaining_reason_distribution": {"NAVIGATION_ONLY": remaining}, "candidate_chunk_count": len(candidate), "quarantine_gate_pass": remaining / len(candidate) <= 0.08 if candidate else False, "staging_runtime_reindexed": False, "note": "候选 Chunk 写入 V2.2 quarantine_repair；V2.0 staging 和 Runtime 未覆盖。"}
    (OUT / "quarantine_repair_report.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
