from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import PROJECT_ROOT


router = APIRouter(prefix="/api/v2/gold-review", tags=["V2.2 Gold Review"])
ROOT = PROJECT_ROOT / "evaluation" / "knowledge_os_v2_2" / "gold"
SOURCE = PROJECT_ROOT / "evaluation" / "knowledge_os_v2_1" / "gold" / "retrieval_gold.jsonl"
REPLACEMENTS = PROJECT_ROOT / "evaluation" / "knowledge_os_v2_3" / "gold" / "replacement_candidates.jsonl"
CHUNKS = PROJECT_ROOT / "data" / "shadow" / "knowledge_v2_staging" / "semantic_chunks.jsonl"
DECISIONS = ROOT / "review_decisions.jsonl"


class GoldReviewDecision(BaseModel):
    reviewer: str = "reviewer-001"
    status: str = Field(pattern="^(CONFIRMED|PENDING|REJECTED|NO_VALID_EVIDENCE)$")
    acceptable_sources: list[str] = Field(default_factory=list)
    acceptable_sections: list[dict[str, Any]] = Field(default_factory=list)
    unacceptable_sources: list[str] = Field(default_factory=list)
    comment: str = ""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def _items() -> list[dict[str, Any]]:
    rows = _read_jsonl(SOURCE) + _read_jsonl(REPLACEMENTS)
    chunks = _read_jsonl(CHUNKS)
    decisions = {str(row.get("question_id")): row for row in _read_jsonl(DECISIONS)}
    for index, row in enumerate(rows):
        qid = str(row.get("question_id"))
        if qid in decisions:
            row = {**row, **decisions[qid]}
        elif row.get("verification_status") == "OWNER_CONFIRMED":
            row = {**row, "verification_status": "CONFIRMED"}
        rows[index] = row
        sources = row.get("acceptable_sources") or ((row.get("candidate_source") or {}).get("files") or [(row.get("candidate_source") or {}).get("file")])
        sections = row.get("acceptable_sections") or ([{"section_path": (row.get("candidate_source") or {}).get("section")}] if (row.get("candidate_source") or {}).get("section") else [])
        candidates = []
        for chunk in chunks:
            name = str(chunk.get("file_name") or "")
            if sources and not any(str(source or "") and str(source).casefold() in name.casefold() for source in sources):
                continue
            if sections and not any(str(section.get("section_path") or section.get("section") or "").casefold() in str(chunk.get("section_path") or "").casefold() for section in sections):
                continue
            candidates.append({"chunk_id": chunk.get("chunk_id"), "file_name": name, "section_path": chunk.get("section_path"), "snippet": str(chunk.get("raw_text") or "")[:800]})
            if len(candidates) >= 3:
                break
        row["review_candidates"] = candidates
        row.setdefault("verification_status", "PENDING_HUMAN_CONFIRM")
        row.setdefault("acceptable_sources", [])
        row.setdefault("acceptable_sections", [])
    return rows


@router.get("/summary")
def summary() -> dict[str, Any]:
    rows = _items()
    return {"total": len(rows), "confirmed": sum(row.get("verification_status") == "CONFIRMED" for row in rows), "pending": sum(row.get("verification_status") == "PENDING" or row.get("verification_status") == "PENDING_HUMAN_CONFIRM" for row in rows), "rejected": sum(row.get("verification_status") == "REJECTED" for row in rows), "no_valid_evidence": sum(row.get("verification_status") == "NO_VALID_EVIDENCE" for row in rows)}


@router.get("/items")
def items(status: str = "PENDING", offset: int = 0, limit: int = 20) -> dict[str, Any]:
    rows = _items()
    if status:
        pending = {"PENDING", "PENDING_HUMAN_CONFIRM"}
        rows = [row for row in rows if (row.get("verification_status") in pending if status == "PENDING" else row.get("verification_status") == status)]
    start, size = max(0, offset), max(1, min(limit, 100))
    return {"items": rows[start : start + size], "total": len(rows), "offset": start, "limit": size}


@router.post("/items/{question_id}/review")
def review(question_id: str, decision: GoldReviewDecision) -> dict[str, Any]:
    rows = _items()
    if not any(str(row.get("question_id")) == question_id for row in rows):
        raise HTTPException(status_code=404, detail="GOLD_QUESTION_NOT_FOUND")
    record = {"question_id": question_id, **decision.model_dump(), "reviewed_at": datetime.now(timezone.utc).astimezone().isoformat(), "verification_status": decision.status}
    DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    with DECISIONS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"saved": True, "decision": record, "formal_knowledge_publish": 0}
