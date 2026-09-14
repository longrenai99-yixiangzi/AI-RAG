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
from app.ingestion.atomic_search import search_atomic_evidence
from app.retrieval.query_planner_v1 import plan_query
from app.verified_answer_engine_v2 import render, validate
from scripts.run_verified_answer_engine_v2 import _runtime_bundle


ROOT = Path(__file__).resolve().parents[2]
V25 = ROOT / "evaluation" / "knowledge_os_v2_5"
STAGING = ROOT / "data" / "shadow" / "knowledge_v2_5_staging"
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"
REMEDIATION_MANIFEST = V26 / "remediation_candidate_v2_6_1.json"
RUNS = ROOT / "evaluation" / "knowledge_os_v2_6" / "live_shadow_runs.jsonl"
CANDIDATE_REVISION = "V2.6.1_DEV_PERIOD_SCOPE_RESCUE"

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


def _period_scope_rescue(question: str, plan: Any, atomic: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Rescue only existing, period-matched evidence outside the RRF top-20."""
    period = str(getattr(plan, "period", "") or "")
    metrics = [str(value) for value in getattr(plan, "metric", [])]
    years = [str(value) for value in getattr(plan, "year", [])]
    if period not in {"H1", "FULL_YEAR"} or not metrics:
        return []
    h1_markers = ("\u4e0a\u534a\u5e74", "\u534a\u5e74\u603b\u7ed3")
    annual_markers = ("\u5e74\u5ea6\u603b\u7ed3", "\u5e74\u5ea6\u8ff0\u804c", "\u5e74\u5ea6\u5de5\u4f5c", "\u8ff0\u804c\u62a5\u544a", "\u5168\u5e74\u5de5\u4f5c", "\u5168\u5e74\u521b\u6548")
    matched = []
    for record in atomic.values():
        text = " ".join(str(record.get(key) or "") for key in ("file_name", "source_path", "text")).casefold()
        period_match = any(marker in text for marker in h1_markers) if period == "H1" else any(marker in text for marker in annual_markers)
        year_match = not years or any(year in text for year in years)
        if period_match and year_match and all(metric.casefold() in text for metric in metrics):
            matched.append(record)
    return [item["record"] for item in search_atomic_evidence(question, matched, limit=3)] if matched else []


def _candidate_row(record: dict[str, Any], rank: int, origin: str) -> dict[str, Any]:
    return {
        "evidence_id": str(record.get("evidence_id") or record.get("chunk_id")),
        "document_id": record.get("document_id"),
        "source_path": record.get("source_path"),
        "file_name": record.get("file_name"),
        "source_version": record.get("source_version"),
        "heading_path": record.get("heading_path") or record.get("section_path") or "",
        "location": record.get("location") or _location(str(record.get("section_path") or ""), record.get("table_id")),
        "text": record.get("text") or record.get("raw_text") or "",
        "raw_text": record.get("raw_text") or record.get("text") or "",
        "rank": rank,
        "candidate_origin": origin,
        "lineage_status": "LINEAGE_CONFIRMED",
    }


def _named_source_rescue(question: str, atomic: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    marker = "\u6570\u5b57\u5efa\u9020\u7cfb\u7edf\u89e3\u51b3\u65b9\u6848"
    evidence_markers = ("\u91c7\u7528\u81ea\u4e0b\u800c\u4e0a", "2035\u603b\u4f53\u884c\u52a8\u89c4\u5212", "\u4f9d\u62588\u4e2aBIM", "\u5149\u8c37\u5143\u8457")
    if marker not in question:
        return []
    return [record for record in atomic.values() if marker in str(record.get("file_name") or "") and any(value in str(record.get("text") or "") for value in evidence_markers)]


class V25LiveShadow:
    """Read-only V2.5 data branch with a separately labelled V2.6.1 dev rescue."""

    def __init__(self) -> None:
        manifest = json.loads((V25 / "candidate_v2_5_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "FROZEN":
            raise RuntimeError("V2_5_CANDIDATE_NOT_FROZEN")
        self.manifest = manifest
        self.candidate_hash = manifest.get("candidate_hash")
        self.candidate_revision = CANDIDATE_REVISION
        self.docs = {str(row.get("document_id")): row for row in _read_jsonl(STAGING / "documents.jsonl")}
        self.chunks = _read_jsonl(STAGING / "semantic_chunks.jsonl")
        remediation_vectors: np.ndarray | None = None
        if REMEDIATION_MANIFEST.exists():
            remediation = json.loads(REMEDIATION_MANIFEST.read_text(encoding="utf-8"))
            if remediation.get("status") == "DEV_REMEDIATION_EMBEDDED_NOT_RELEASED" and (remediation.get("source") or {}).get("approval_status") == "APPROVED":
                vector_path = Path(str((remediation.get("dense_embeddings") or {}).get("path") or ""))
                stage = vector_path.parent
                side_docs = _read_jsonl(stage / "documents.jsonl")
                side_chunks = _read_jsonl(stage / "semantic_chunks.jsonl")
                remediation_vectors = np.load(vector_path, mmap_mode="r").astype(np.float32)
                if remediation_vectors.shape[0] != len(side_chunks):
                    raise RuntimeError("V2_6_1_REMEDIATION_VECTOR_CHUNK_MISMATCH")
                self.docs.update({str(row.get("document_id")): row for row in side_docs})
                self.chunks.extend(side_chunks)
                self.candidate_hash = remediation.get("candidate_hash")
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
        base_vectors = np.load(STAGING / "dense_embeddings.npy", mmap_mode="r").astype(np.float32)
        self.vectors = np.concatenate((base_vectors, remediation_vectors), axis=0) if remediation_vectors is not None else base_vectors
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
            candidate_rows.append(_candidate_row(self.atomic[str(self.chunks[index].get("chunk_id"))], rank, "FROZEN_V2_5_RRF"))
        period_rescued = _period_scope_rescue(question, plan, self.atomic)
        named_rescued = _named_source_rescue(question, self.atomic)
        rescue_specs = [("PERIOD_SCOPE_RESCUE", record) for record in period_rescued] + [("EXACT_NAMED_SOURCE_RESCUE", record) for record in named_rescued]
        rescue_rows = []
        rescue_ids = set()
        for origin, record in rescue_specs:
            evidence_id = str(record.get("evidence_id"))
            if evidence_id and evidence_id not in rescue_ids:
                rescue_rows.append(_candidate_row(record, 0, origin))
                rescue_ids.add(evidence_id)
        candidate_rows = [*rescue_rows, *[row for row in candidate_rows if row["evidence_id"] not in rescue_ids]]
        for rank, row in enumerate(candidate_rows, start=1):
            row["rank"] = rank
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
            "candidate_hash": self.candidate_hash,
            "candidate_revision": CANDIDATE_REVISION,
            "period_scope_rescue": {"invoked": bool(getattr(plan, "period", "")), "rescued_evidence_ids": [row["evidence_id"] for row in rescue_rows if row["candidate_origin"] == "PERIOD_SCOPE_RESCUE"]},
            "named_source_rescue": {"invoked": bool(named_rescued), "rescued_evidence_ids": [row["evidence_id"] for row in rescue_rows if row["candidate_origin"] == "EXACT_NAMED_SOURCE_RESCUE"]},
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
            "execution_mode": "LIVE_REQUEST_BACKGROUND_V2_6_1_DEV_SHADOW",
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
                "v2_error": None if shadow["validation"].get("valid") else "V2_6_1_DEV_SHADOW_ANSWER_VALIDATION_FAILED",
                "v2_validation": shadow["validation"],
                "candidate_hash": shadow["candidate_hash"],
                "candidate_revision": shadow["candidate_revision"],
                "period_scope_rescue": shadow["period_scope_rescue"],
                "named_source_rescue": shadow["named_source_rescue"],
            })
        except Exception as error:
            base.update({"v2_status": "SHADOW_ERROR", "v2_answer_status": None, "v2_top_source": None, "v2_top_section": None, "v2_citation": [], "source_agreement": None, "section_agreement": None, "new_hit_candidate": None, "lost_hit_candidate": None, "new_hit_verification": "NOT_ASSESSED", "lost_hit_verification": "NOT_ASSESSED", "v2_latency_ms": round((time.perf_counter() - started) * 1000, 3), "v2_error": f"{type(error).__name__}: {error}"})
        _append(base)

    _shadow_executor.submit(worker)
