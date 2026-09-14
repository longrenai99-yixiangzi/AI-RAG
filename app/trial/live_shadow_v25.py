from __future__ import annotations

import json
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from app.bm25 import tokenize
from app.retrieval.query_planner_v1 import plan_query
from app.verified_answer_engine_v2 import render, validate
from scripts.run_verified_answer_engine_v2 import _runtime_bundle


ROOT = Path(__file__).resolve().parents[2]
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"
RUNS = ROOT / "evaluation" / "knowledge_os_v2_6" / "live_shadow_runs.jsonl"

_write_lock = threading.Lock()
_shadow_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="v25-live-shadow")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _append(row: dict[str, Any]) -> None:
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with RUNS.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _location(section_path: str, table_id: str | None) -> dict[str, Any]:
    location: dict[str, Any] = {}
    if section_path.casefold().startswith("page "):
        try:
            location["page"] = int(section_path.split()[-1])
        except ValueError:
            pass
    elif section_path.casefold().startswith("sheet"):
        location["sheet_name"] = section_path
    elif section_path:
        location["section_path"] = section_path
    if table_id:
        location["table_id"] = table_id
    return location


class V25LiveShadow:
    """Read-only V2.5 candidate branch used behind the V1 response path."""

    def __init__(self) -> None:
        manifest = json.loads((V25 / "candidate_v2_5_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "FROZEN":
            raise RuntimeError("V2_5_CANDIDATE_NOT_FROZEN")
        self.manifest = manifest
        self.docs = {str(row.get("document_id")): row for row in _read_jsonl(STAGING / "documents.jsonl")}
        self.chunks = _read_jsonl(STAGING / "semantic_chunks.jsonl")
        for chunk in self.chunks:
            document = self.docs.get(str(chunk.get("document_id")), {})
            chunk["file_name"] = chunk.get("file_name") or document.get("file_name")
            chunk["source_path"] = chunk.get("source_path") or document.get("source_path")
            chunk["source_version"] = chunk.get("source_version") or document.get("source_version")
        self.atomic = {
            str(chunk.get("chunk_id")): {
                "evidence_id": str(chunk.get("chunk_id")),
                "source_id": chunk.get("source_id") or chunk.get("document_id"),
                "source_version": chunk.get("source_version"),
                "document_id": chunk.get("document_id"),
                "section_id": chunk.get("section_id"),
                "table_id": chunk.get("table_id"),
                "source_path": chunk.get("source_path"),
                "file_name": chunk.get("file_name"),
                "file_type": chunk.get("file_type"),
                "heading_path": chunk.get("section_path") or "",
                "location": _location(str(chunk.get("section_path") or ""), chunk.get("table_id")),
                "text": chunk.get("raw_text") or chunk.get("retrieval_text") or "",
                "raw_text": chunk.get("raw_text") or chunk.get("retrieval_text") or "",
                "search_context": chunk.get("retrieval_text") or "",
                "lineage_status": "LINEAGE_CONFIRMED",
            }
            for chunk in self.chunks
            if chunk.get("chunk_id")
        }
        tables = {str(row.get("table_id")): row for row in _read_jsonl(STAGING / "tables.jsonl")}
        self.structured_rows = []
        for row in _read_jsonl(STAGING / "table_rows.jsonl"):
            table = tables.get(str(row.get("table_id")), {})
            document = self.docs.get(str(row.get("document_id")), {})
            row = {
                **row,
                "row_id": row.get("row_id") or row.get("table_row_id"),
                "source_path": document.get("source_path"),
                "file_name": document.get("file_name"),
                "sheet_name": table.get("sheet_name"),
                "source_location": {"table": table.get("table_number"), "sheet_name": table.get("sheet_name"), "table_id": row.get("table_id")},
                "bundle_evidence_id": "V25-STRUCTURED-" + str(row.get("table_id")),
            }
            self.structured_rows.append(row)
        self.vectors = np.load(STAGING / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
        if self.vectors.shape[0] != len(self.chunks):
            raise RuntimeError("V2_5_DENSE_CHUNK_MISMATCH")
        weighted = [
            " ".join(
                [str(row.get("section_path") or "")] * 5
                + [str(row.get("file_name") or "")] * 3
                + [str((row.get("knowledge_type") or {}).get("value") or "")] * 2
                + [str(row.get("raw_text") or "")]
            )
            for row in self.chunks
        ]
        self.bm25 = BM25Okapi([tokenize(text) or ["_empty_"] for text in weighted])

    def run(self, question: str, primary: dict[str, Any], *, query_vector: list[float] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        plan = plan_query(question)
        vector = np.asarray(query_vector if query_vector is not None else primary.get("query_vector") or [], dtype=np.float32)
        if vector.size != self.vectors.shape[1]:
            raise RuntimeError("V2_5_QUERY_VECTOR_MISSING")
        bm = np.asarray(self.bm25.get_scores(tokenize(question) or ["_empty_"]), dtype=np.float32)
        dense = np.asarray(self.vectors @ vector, dtype=np.float32)
        scores: dict[int, float] = {}
        for rank, index in enumerate(np.argsort(-bm).tolist(), start=1):
            scores[index] = scores.get(index, 0.0) + 1.0 / (60 + rank)
        for rank, index in enumerate(np.argsort(-dense).tolist(), start=1):
            scores[index] = scores.get(index, 0.0) + 1.0 / (60 + rank)
        order = [index for index, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
        candidate_rows = []
        for rank, index in enumerate(order[:20], start=1):
            chunk = self.chunks[index]
            candidate_rows.append({
                "evidence_id": str(chunk.get("chunk_id")),
                "document_id": chunk.get("document_id"),
                "source_path": chunk.get("source_path"),
                "file_name": chunk.get("file_name"),
                "source_version": chunk.get("source_version"),
                "heading_path": chunk.get("section_path") or "",
                "location": _location(str(chunk.get("section_path") or ""), chunk.get("table_id")),
                "text": chunk.get("raw_text") or "",
                "raw_text": chunk.get("raw_text") or "",
                "rank": rank,
                "lineage_status": "LINEAGE_CONFIRMED",
            })
        documents = {str(key): dict(value) for key, value in self.docs.items()}
        for document in documents.values():
            document.setdefault("scope", {})
            document.setdefault("document_role", document.get("document_type"))
            document.setdefault("authority_level", "UNKNOWN")
        result = {"atomic_candidates": candidate_rows}
        bundle = _runtime_bundle(question, plan.to_dict(), result, documents, self.atomic, self.structured_rows)
        answer = render(bundle)
        validation = validate(answer, bundle)
        citations = answer.get("citations") or []
        primary_citations = primary.get("citations") or []
        primary_source = (primary_citations[0] or {}).get("file_name") if primary_citations else None
        shadow_source = (citations[0] or {}).get("file_name") if citations else None
        primary_status = str(primary.get("answer_status") or "UNKNOWN")
        shadow_status = str(answer.get("answer_status") or "UNKNOWN")
        return {
            "v2_status": shadow_status,
            "v2_answer_status": shadow_status,
            "v2_bundle_status": bundle.get("bundle_status"),
            "v2_answer": answer.get("answer_text") or answer.get("answer"),
            "v2_citations": citations,
            "v2_top_source": shadow_source,
            "v2_top_section": (citations[0] or {}).get("display_location") if citations else (candidate_rows[0].get("heading_path") if candidate_rows else None),
            "source_agreement": primary_source == shadow_source if primary_source and shadow_source else None,
            "section_agreement": None,
            "new_hit_candidate": primary_status not in {"ANSWERED", "FACT_RESULT"} and shadow_status == "ANSWERED",
            "lost_hit_candidate": primary_status in {"ANSWERED", "FACT_RESULT"} and shadow_status not in {"ANSWERED", "FACT_RESULT"},
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "validation": validation,
            "candidate_hash": self.manifest.get("candidate_hash"),
        }


_engine: V25LiveShadow | None = None
_engine_lock = threading.Lock()


def _get_engine() -> V25LiveShadow:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = V25LiveShadow()
    return _engine


def run_async(*, question: str, query_run_id: str, conversation_id: str, primary: dict[str, Any], query_vector: list[float] | None = None, query_encoder: Any = None) -> None:
    def worker() -> None:
        started = time.perf_counter()
        base = {
            "shadow_run_id": "LS26-" + uuid.uuid4().hex[:20],
            "timestamp": _now(),
            "query_run_id": query_run_id,
            "session_id_hash": uuid.uuid5(uuid.NAMESPACE_URL, conversation_id or query_run_id).hex,
            "question_hash": uuid.uuid5(uuid.NAMESPACE_URL, question).hex,
            "question": question,
            "v1_status": primary.get("answer_status"),
            "v1_answer": primary.get("answer"),
            "v1_top_source": (primary.get("citations") or [{}])[0].get("file_name"),
            "v1_top_section": (primary.get("citations") or [{}])[0].get("display_location"),
            "v1_citation": primary.get("citations") or [],
            "v1_latency_ms": (primary.get("latency") or {}).get("total_ms"),
            "v1_error": None,
            "execution_mode": "LIVE_REQUEST_BACKGROUND_V2_5_SHADOW",
        }
        try:
            vector = query_vector
            if vector is None and query_encoder is not None:
                vector = query_encoder(question)
            shadow = _get_engine().run(question, primary, query_vector=vector)
            base.update({
                "v2_status": shadow["v2_status"],
                "v2_answer_status": shadow["v2_answer_status"],
                "v2_answer": shadow["v2_answer"],
                "v2_bundle_status": shadow["v2_bundle_status"],
                "v2_top_source": shadow["v2_top_source"],
                "v2_top_section": shadow["v2_top_section"],
                "v2_citation": shadow["v2_citations"],
                "source_agreement": shadow["source_agreement"],
                "section_agreement": shadow["section_agreement"],
                "new_hit_candidate": shadow["new_hit_candidate"],
                "lost_hit_candidate": shadow["lost_hit_candidate"],
                "new_hit_verification": "REVIEW_REQUIRED" if shadow["new_hit_candidate"] else "NOT_A_CANDIDATE",
                "lost_hit_verification": "REVIEW_REQUIRED" if shadow["lost_hit_candidate"] else "NOT_A_CANDIDATE",
                "v2_latency_ms": shadow["latency_ms"],
                "v2_error": None if shadow["validation"].get("valid") else "V2_5_SHADOW_ANSWER_VALIDATION_FAILED",
                "v2_validation": shadow["validation"],
                "candidate_hash": shadow["candidate_hash"],
            })
        except Exception as error:
            base.update({"v2_status": "SHADOW_ERROR", "v2_answer_status": None, "v2_top_source": None, "v2_top_section": None, "v2_citation": [], "source_agreement": None, "section_agreement": None, "new_hit_candidate": None, "lost_hit_candidate": None, "new_hit_verification": "NOT_ASSESSED", "lost_hit_verification": "NOT_ASSESSED", "v2_latency_ms": round((time.perf_counter() - started) * 1000, 3), "v2_error": f"{type(error).__name__}: {error}"})
        _append(base)

    _shadow_executor.submit(worker)
