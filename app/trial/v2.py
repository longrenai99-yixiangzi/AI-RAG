from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from openpyxl import load_workbook
from pydantic import BaseModel, Field

from app.chunker import chunk_blocks
from app.domain import SourceBlock
from app.knowledge_growth_v1 import candidate_for_trace
from app.config import Settings
from app.ingestion.atomic_search import search_atomic_evidence
from app.ingestion.pipeline import run_document_pipeline
from app.ingestion.loaders.pdf_loader import extract_value_creation_rows, extract_value_creation_summary
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hierarchical_v1 import HierarchicalIndex
from app.retrieval.query_planner_v1 import plan_query
from app.verified_answer_engine_v2 import render
from scripts.run_verified_answer_engine_v2 import _load_authorized_docx_rows, _runtime_bundle

from .config import PROJECT_ROOT, TrialConfig, load_users


router = APIRouter(prefix="/api/v2", tags=["V2 Verified Trial"])
CONFIG = TrialConfig.load()
USERS = load_users()
STATIC = Path(__file__).parent / "static" / "v2_trial.html"
INDEX = PROJECT_ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization"
TRIAL = PROJECT_ROOT / "evaluation" / "v2_8010_trial"
GROWTH = PROJECT_ROOT / "data" / "shadow" / "knowledge_growth_v1"
FEEDBACK_CANDIDATES = GROWTH / "feedback_growth_candidates.jsonl"
FEEDBACK_CASES = GROWTH / "feedback_regression_cases.jsonl"
FEEDBACK_RUNS = GROWTH / "feedback_regression_runs.jsonl"
SOURCE_CLOSURE_REGISTER = PROJECT_ROOT / "data" / "shadow" / "trial_cycle_01" / "source_closure_register.jsonl"
TRIAL_FEEDBACK_QUESTIONS = PROJECT_ROOT / "data" / "shadow" / "trial_cycle_01" / "trial_feedback_questions.jsonl"
BATCH_ROOT = PROJECT_ROOT / "data" / "shadow" / "batch_workflow"
BATCH_SOURCE_REGISTER = BATCH_ROOT / "source_registry.jsonl"
BATCH_CASES = BATCH_ROOT / "acceptance_cases.jsonl"
BATCH_RUNS = BATCH_ROOT / "regression_runs.jsonl"
LOADED_SHADOW_PATHS: set[str] = set()


class V2QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    trial_user: str = "reviewer-001"


class V2FeedbackRequest(BaseModel):
    query_id: str
    trial_user: str = "reviewer-001"
    feedback_type: str
    comment: str = ""
    source_path: str = ""
    source_location: str = ""
    expected_answer: str = ""
    required_terms: list[str] = Field(default_factory=list)


class GrowthReviewRequest(BaseModel):
    candidate_id: str
    trial_user: str = "reviewer-001"
    decision: str
    comment: str = ""
    approved_action: str = ""
    confirmed_source_path: str = ""
    confirmed_source_location: str = ""
    required_terms: list[str] = Field(default_factory=list)


class GrowthRegressionRequest(BaseModel):
    candidate_id: str
    trial_user: str = "reviewer-001"


class V2TrialEngine:
    def __init__(self) -> None:
        self.index = HierarchicalIndex.load(INDEX)
        self.documents = {str(row["document_id"]): row for row in self.index.documents}
        self.atomic = {str(row.get("evidence_id")): row for row in self.index.atomic if row.get("evidence_id")}
        self.structured_rows, self.structured_audit = _load_authorized_docx_rows()
        self._load_approved_shadow_sources()
        self.dense = BGEM3DenseProvider(Settings.load().embedding_model, collection_name="v2_8010_query_embeddings", use_fp16=False, batch_size=1)

    def _load_approved_shadow_sources(self) -> None:
        """Overlay explicitly approved files in memory; never writes an index."""
        for source in _approved_shadow_sources():
            path = Path(source["path"])
            if source["approval_status"] != "USER_APPROVED_SHADOW_READ" or not path.is_file():
                continue
            normalized_path = _normalize_source_path(path)
            if normalized_path in LOADED_SHADOW_PATHS:
                continue
            document_id = "trial-approved-" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:24]
            result = self._load_approved_wps_read_only(path, document_id) if path.suffix.lower() == ".wps" else run_document_pipeline(path.parent, files=[path])
            for document in result.documents:
                metadata = dict(document.metadata or {})
                scope = {"organization": [], "project": [], "year": [], "specialty": []}
                if path.suffix.lower() == ".docx":
                    project_name = self._docx_project_name(document.chunks)
                    if project_name:
                        scope["project"] = [project_name]
                self.documents[document_id] = {
                    "document_id": document_id,
                    "knowledge_root_id": "Root-002",
                    "source_path": str(path),
                    "file_name": path.name,
                    "file_type": document.file_type,
                    "document_role": metadata.get("document_role"),
                    "authority_level": metadata.get("authority_level"),
                    "scope": scope,
                }
                for ordinal, chunk in enumerate(document.chunks, start=1):
                    evidence_id = "approved-shadow-" + hashlib.sha256(f"{path}|{chunk.chunk_id}".encode("utf-8")).hexdigest()[:24]
                    self.atomic[evidence_id] = {
                        "evidence_id": evidence_id,
                        "document_id": document_id,
                        "section_id": None,
                        "source_path": str(path),
                        "file_name": path.name,
                        "file_type": document.file_type,
                        "heading_path": chunk.heading_path,
                        "location": chunk.location,
                        "text": chunk.text,
                        "granularity": "chunk",
                        "lineage_status": "LINEAGE_CONFIRMED",
                        "approved_shadow_source": True,
                        "ordinal": ordinal,
                    }
            if path.suffix.lower() == ".xlsx":
                self._load_approved_xlsx_headers(path, document_id)
                self._load_approved_xlsx_review_sections(path, document_id)
            elif path.suffix.lower() == ".docx" and not any(row.get("source_path") == str(path) for row in self.structured_rows):
                self.structured_rows.extend(self._load_approved_docx_value_rows(path, document_id))
            LOADED_SHADOW_PATHS.add(normalized_path)

    def load_approved_sources(self) -> None:
        self._load_approved_shadow_sources()


    @staticmethod
    def _load_approved_wps_read_only(path: Path, document_id: str) -> SimpleNamespace:
        """Read a legacy WPS document through WPS COM without conversion or write-back."""
        app = document = None
        com_initialized = False
        try:
            import pythoncom
            from win32com.client import DispatchEx

            pythoncom.CoInitialize()
            com_initialized = True
            app = DispatchEx("Kwps.Application")
            app.Visible = False
            try:
                app.DisplayAlerts = 0
            except Exception:
                pass
            document = app.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False)
            blocks: list[SourceBlock] = []
            for table_number in range(1, int(document.Tables.Count) + 1):
                table = document.Tables(table_number)
                rows: list[str] = []
                max_columns = 0
                for row in table.Rows:
                    cells = []
                    for cell in row.Cells:
                        text = str(cell.Range.Text or "").replace("\r", " ").replace("\x07", " ").strip()
                        cells.append(text)
                    max_columns = max(max_columns, len(cells))
                    row_text = " | ".join(cells).strip(" |")
                    if row_text:
                        rows.append(row_text)
                if rows:
                    blocks.append(SourceBlock(
                        document_id=document_id,
                        source_path=str(path),
                        file_name=path.name,
                        heading_path="附件1 > 2026年公司设计示范工程计划",
                        text="附件1\n2026年公司设计示范工程计划\n表格：\n" + "\n".join(rows),
                        location={"table": table_number, "rows": len(rows), "columns": max_columns},
                    ))
            if not blocks:
                raise RuntimeError("WPS文档未读取到表格正文")
            return SimpleNamespace(documents=[SimpleNamespace(
                file_type=".wps",
                metadata={"document_role": "工作计划", "authority_level": "L3"},
                chunks=chunk_blocks(blocks),
            )])
        except Exception as error:
            raise RuntimeError(f"WPS只读解析失败：{type(error).__name__}: {error}") from error
        finally:
            if document is not None:
                try:
                    document.Close(SaveChanges=False)
                except Exception:
                    pass
            if app is not None:
                try:
                    app.Quit(SaveChanges=False)
                except Exception:
                    pass
            if com_initialized:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    @staticmethod
    def _docx_project_name(chunks: list[Any]) -> str:
        for chunk in chunks:
            match = re.search(r"项目名称\s*\|\s*([^|\n]+)", str(chunk.text or ""))
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _load_approved_docx_value_rows(path: Path, document_id: str) -> list[dict[str, Any]]:
        from docx import Document

        document = Document(path)
        try:
            for table_number, table in enumerate(document.tables, start=1):
                rows = [[" ".join(cell.text.split()) for cell in row.cells] for row in table.rows]
                header_index = next(
                    (
                        index
                        for index, values in enumerate(rows)
                        if "专业类别" in values and "价值创造策划点" in values and "价值创造分析" in values
                    ),
                    None,
                )
                if header_index is None:
                    continue
                headers = rows[header_index]
                table_id = "approved-shadow-table-" + hashlib.sha256(f"{path}|{table_number}".encode("utf-8")).hexdigest()[:24]
                bundle_id = "SEB_" + hashlib.sha256(f"{document_id}:{table_id}".encode("utf-8")).hexdigest()[:16]
                mapped = []
                for row_number, values in enumerate(rows[header_index + 1 :], start=header_index + 2):
                    if not values or not values[0] or values[0] == "专业类别":
                        continue
                    cells = [
                        {
                            "column_name": header or f"column_{index}",
                            "normalized_column_name": header or f"column_{index}",
                            "raw_value": values[index] if index < len(values) else "",
                            "normalized_value": values[index] if index < len(values) else "",
                            "cell_value": values[index] if index < len(values) else "",
                        }
                        for index, header in enumerate(headers)
                    ]
                    row_id = "SER_" + hashlib.sha256(f"{table_id}:{row_number}".encode("utf-8")).hexdigest()[:16]
                    mapped.append({
                        "document_id": document_id,
                        "table_id": table_id,
                        "section_id": None,
                        "row_id": row_id,
                        "row_number": row_number,
                        "professional": values[0],
                        "profit_numeric": None,
                        "source_path": str(path),
                        "file_name": path.name,
                        "sheet_name": None,
                        "source_location": {"table": table_number, "row_start": row_number, "row_end": row_number, "header_row": header_index + 1},
                        "cells": cells,
                        "bundle_evidence_id": bundle_id,
                        "lineage_status": "LINEAGE_CONFIRMED",
                        "source_artifact": "approved-shadow-docx-table",
                    })
                return mapped
        finally:
            document = None
        return []

    def _load_approved_xlsx_headers(self, path: Path, document_id: str) -> None:
        """Create precise in-memory evidence for multi-row XLSX professional headers."""
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            for worksheet in workbook.worksheets:
                rows = [
                    [str(value).strip() if value is not None else "" for value in row]
                    for row in worksheet.iter_rows(values_only=True)
                ]
                for group_row_index, values in enumerate(rows):
                    groups = [
                        (column, value)
                        for column, value in enumerate(values, start=1)
                        if re.fullmatch(r"[\u3400-\u9fff]{1,8}专业设计参数", value)
                    ]
                    if not groups:
                        continue
                    header_row_index = next(
                        (
                            index
                            for index in range(group_row_index, min(len(rows), group_row_index + 3))
                            if sum(bool(item) for item in rows[index]) >= len(groups)
                            and not any("专业设计参数" in item for item in rows[index] if item)
                        ),
                        None,
                    )
                    if header_row_index is None:
                        continue
                    for group_index, (start_column, group) in enumerate(groups):
                        end_column = groups[group_index + 1][0] if group_index + 1 < len(groups) else len(rows[header_row_index]) + 1
                        fields = [
                            value
                            for value in rows[header_row_index][start_column - 1 : end_column - 1]
                            if value
                        ]
                        if len(fields) < 2:
                            continue
                        evidence_id = "approved-shadow-header-" + hashlib.sha256(
                            f"{path}|{worksheet.title}|{group}".encode("utf-8")
                        ).hexdigest()[:24]
                        self.atomic[evidence_id] = {
                            "evidence_id": evidence_id,
                            "document_id": document_id,
                            "section_id": None,
                            "source_path": str(path),
                            "file_name": path.name,
                            "file_type": ".xlsx",
                            "heading_path": f"{worksheet.title} > {group}",
                            "location": {
                                "sheet_name": worksheet.title,
                                "row_start": header_row_index + 1,
                                "row_end": header_row_index + 1,
                                "column_start": start_column,
                                "column_end": end_column - 1,
                                "header_row": header_row_index + 1,
                            },
                            "text": f"工作表：{worksheet.title}\n{group}包括：{'、'.join(fields)}。",
                            "granularity": "xlsx_header",
                            "lineage_status": "LINEAGE_CONFIRMED",
                            "approved_shadow_source": True,
                        }
        finally:
            workbook.close()

    def _load_approved_xlsx_review_sections(self, path: Path, document_id: str) -> None:
        """Create row-preserving evidence for numbered review-point sections."""
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            for worksheet in workbook.worksheets:
                rows = [
                    [str(value).strip() if value is not None else "" for value in row]
                    for row in worksheet.iter_rows(values_only=True)
                ]
                section_starts = []
                for index, values in enumerate(rows):
                    first = next((value.replace("\n", "") for value in values if value), "")
                    match = re.match(r"^(\d+)[.、]\s*(.+)$", first)
                    if match and not re.match(r"^\d+\.\d+", first):
                        section_starts.append((index, match.group(1), first))
                for position, (start, section_number, title) in enumerate(section_starts):
                    end = section_starts[position + 1][0] if position + 1 < len(section_starts) else len(rows)
                    points = []
                    categories = []
                    for row_number in range(start, end):
                        values = rows[row_number]
                        point = next(
                            (value.replace("\n", "") for value in values if re.match(rf"^{re.escape(section_number)}\.\d+", value.replace("\n", ""))),
                            None,
                        )
                        if point:
                            points.append(point)
                            categories.append(next((value.replace("\n", "") for value in values[2:] if value), ""))
                    if len(points) < 2:
                        continue
                    profession = max(set(categories), key=categories.count, default="")
                    evidence_id = "approved-shadow-section-" + hashlib.sha256(
                        f"{path}|{worksheet.title}|{title}|{start + 1}|{end}|{profession}".encode("utf-8")
                    ).hexdigest()[:24]
                    self.atomic[evidence_id] = {
                        "evidence_id": evidence_id,
                        "document_id": document_id,
                        "section_id": None,
                        "source_path": str(path),
                        "file_name": path.name,
                        "file_type": ".xlsx",
                        "heading_path": f"{worksheet.title} > {title}",
                        "location": {
                            "sheet_name": worksheet.title,
                            "row_start": start + 1,
                            "row_end": end,
                            "section": title,
                        },
                        "text": f"工作表：{worksheet.title}\n专业：{profession}\n{title}\n" + "\n".join(points),
                        "granularity": "xlsx_section",
                        "lineage_status": "LINEAGE_CONFIRMED",
                        "approved_shadow_source": True,
                    }
        finally:
            workbook.close()

    def answer(self, question: str, *, detect_growth: bool = True, source_paths: list[str] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        planner_started = time.perf_counter()
        plan = plan_query(question)
        planner_ms = (time.perf_counter() - planner_started) * 1000
        embedding_started = time.perf_counter()
        try:
            query_vector = self.dense.embed_query(question)
            dense_runtime = "LOCAL_BGE_M3_FP32"
        except Exception as error:
            query_vector = [0.0] * int(self.index.document_vectors.shape[1])
            dense_runtime = f"SPARSE_FALLBACK_{type(error).__name__}"
        embedding_ms = (time.perf_counter() - embedding_started) * 1000
        retrieval = self.index.retrieve(plan, query_vector)
        retrieval = _with_exact_atomic_rescue(retrieval, question, self.index.atomic)
        wanted_sources = {_normalize_source_path(path).casefold() for path in (source_paths or []) if str(path).strip()}
        if wanted_sources:
            retrieval = {
                **retrieval,
                "atomic_candidates": [
                    item for item in retrieval["atomic_candidates"]
                    if _normalize_source_path(item.get("source_path")).casefold() in wanted_sources
                ],
            }
        approved_records = [
            item for item in self.atomic.values()
            if item.get("approved_shadow_source") and (not wanted_sources or _normalize_source_path(item.get("source_path")).casefold() in wanted_sources)
        ]
        approved_results = search_atomic_evidence(question, approved_records, limit=10)
        if approved_results:
            approved_candidates = []
            for rank, item in enumerate(approved_results, start=1):
                record = item["record"]
                approved_candidates.append({
                    "evidence_id": record["evidence_id"],
                    "document_id": record["document_id"],
                    "section_id": record.get("section_id"),
                    "candidate_origin": "APPROVED_SHADOW_SOURCE",
                    "rank": rank,
                    "score": item["score"],
                    "location": record.get("location"),
                    "evidence_type": record.get("granularity"),
                    "source_path": record.get("source_path"),
                    "file_name": record.get("file_name"),
                    "facet_reasons": item.get("facet_reasons", []),
                    "text": record.get("text", "")[:900],
                    "lineage_status": record.get("lineage_status"),
                })
            compact_question = re.sub(r"\s+", "", question)
            existing_ids = {item["evidence_id"] for item in approved_candidates}
            for record in self.atomic.values():
                location = record.get("location") or {}
                section = re.sub(r"^\d+[.、]", "", str(location.get("section") or ""))
                profession = str(record.get("text") or "").split("专业：", 1)[-1].split("\n", 1)[0].strip()
                if (
                    record.get("approved_shadow_source")
                    and record.get("granularity") == "xlsx_section"
                    and (not wanted_sources or _normalize_source_path(record.get("source_path")).casefold() in wanted_sources)
                    and record.get("evidence_id") not in existing_ids
                    and section
                    and section in compact_question
                    and profession in plan.specialty
                ):
                    approved_candidates.insert(0, {
                        "evidence_id": record["evidence_id"],
                        "document_id": record["document_id"],
                        "section_id": record.get("section_id"),
                        "candidate_origin": "APPROVED_SECTION_RESCUE",
                        "rank": 1,
                        "score": 100.0,
                        "location": location,
                        "evidence_type": record.get("granularity"),
                        "source_path": record.get("source_path"),
                        "file_name": record.get("file_name"),
                        "facet_reasons": ["exact_section_and_profession"],
                        "text": record.get("text", "")[:900],
                        "lineage_status": record.get("lineage_status"),
                    })
                if (
                    record.get("approved_shadow_source")
                    and record.get("file_type") == ".pdf"
                    and (not wanted_sources or _normalize_source_path(record.get("source_path")).casefold() in wanted_sources)
                    and "设计价值创造点" in question
                    and (
                        extract_value_creation_summary(str(record.get("text") or ""))
                        and (
                            "多少个专业" in question
                            or ("各专业" in question and "多少条" in question)
                            or ("方案设计" in question and "施工图设计" in question)
                        )
                        or any(
                            row["professional"] in question
                            and row["stage"] in question
                            and f"第{row['number']}条" in question
                            and ("是什么" in question or "适用条件" in question)
                            for row in extract_value_creation_rows(str(record.get("text") or ""))
                        )
                    )
                ):
                    rescued = {
                        "evidence_id": record["evidence_id"],
                        "document_id": record["document_id"],
                        "section_id": record.get("section_id"),
                        "candidate_origin": "APPROVED_PDF_SUMMARY_RESCUE",
                        "rank": 1,
                        "score": 100.0,
                        "location": location,
                        "evidence_type": record.get("granularity"),
                        "source_path": record.get("source_path"),
                        "file_name": record.get("file_name"),
                        "facet_reasons": ["exact_value_creation_summary"],
                        "text": record.get("text", "")[:900],
                        "lineage_status": record.get("lineage_status"),
                    }
                    existing = next((item for item in approved_candidates if item["evidence_id"] == record["evidence_id"]), None)
                    if existing is None:
                        approved_candidates.insert(0, rescued)
                        existing_ids.add(record["evidence_id"])
                    else:
                        existing.update(rescued)
            retrieval = {**retrieval, "atomic_candidates": [*approved_candidates, *retrieval["atomic_candidates"]]}
        verification_started = time.perf_counter()
        bundle = _runtime_bundle(question, plan.to_dict(), retrieval, self.documents, self.atomic, self.structured_rows)
        verification_ms = (time.perf_counter() - verification_started) * 1000
        rendering_started = time.perf_counter()
        answer = render(bundle)
        rendering_ms = (time.perf_counter() - rendering_started) * 1000
        query_id = plan.query_id
        trace = {"question_id": query_id, "question": question, "bundle": bundle, "answer": answer}
        growth_started = time.perf_counter()
        candidate = candidate_for_trace(trace) if detect_growth else None
        growth_ms = (time.perf_counter() - growth_started) * 1000
        candidate_ids = []
        if candidate is not None:
            _append_jsonl(GROWTH / "trial_runtime_candidates.jsonl", candidate)
            candidate_ids.append(candidate["candidate_id"])
        evidence_by_id = {item.get("evidence_id"): item for item in bundle["candidate_evidence"]}
        citations = [_citation(item, evidence_by_id.get(item.get("evidence_id"))) for item in answer["citations"]]
        return {
            "query_id": query_id, "question": question, "mode": "V2_VERIFIED", "pipeline_version": "020C-020E-020F-020G",
            "answer": answer["answer_text"], "answer_status": answer["answer_status"], "status_label": _friendly_status(answer["answer_status"]),
            "claims": answer["claims"], "claim_evidence_map": answer["claim_evidence_map"], "citations": citations, "debug": {"query_plan": plan.to_dict(), "document_candidates": retrieval["document_candidates"], "section_candidates": retrieval["section_candidates"], "table_candidates": retrieval["table_candidates"], "evidence_bundle": bundle, "claim_evidence_map": answer["claim_evidence_map"], "conflicts": bundle["conflicting_evidence"], "lineage": {"bundle_status": bundle["bundle_status"], "structured_audit": self.structured_audit}},
            "growth_candidate_ids": candidate_ids, "latency": {"query_planner_ms": round(planner_ms, 3), "query_embedding_ms": round(embedding_ms, 3), "document_retrieval_ms": retrieval["timings"]["document_retrieval_ms"], "section_retrieval_ms": retrieval["timings"]["section_retrieval_ms"], "evidence_verification_ms": round(verification_ms, 3), "answer_rendering_ms": round(rendering_ms, 3), "growth_detection_ms": round(growth_ms, 3), "total_ms": round((time.perf_counter() - started) * 1000, 3)},
            "dense_runtime": dense_runtime, "provider_http_requests": 0, "gold_runtime_injection": 0,
        }


_engine: V2TrialEngine | None = None
_engine_lock = threading.Lock()


def _engine_instance() -> V2TrialEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = V2TrialEngine()
    return _engine


def _with_exact_atomic_rescue(retrieval: dict[str, Any], question: str, atomic: list[dict[str, Any]]) -> dict[str, Any]:
    """Add existing Shadow evidence only when the query names an exact core phrase."""
    phrases = _core_phrases(question)
    if not phrases:
        return retrieval
    existing_ids = {str(item.get("evidence_id") or "") for item in retrieval["atomic_candidates"]}
    matches = [
        record
        for record in atomic
        if str(record.get("evidence_id") or "") not in existing_ids
        and any(phrase in _compact(str(record.get("text") or "")) for phrase in phrases)
    ]
    if not matches:
        return retrieval
    rescued = []
    for rank, item in enumerate(search_atomic_evidence(question, matches, limit=3), start=1):
        record = item["record"]
        exact = [phrase for phrase in phrases if phrase in _compact(str(record.get("text") or ""))]
        rescued.append({
            "evidence_id": record.get("evidence_id"),
            "document_id": record.get("document_id"),
            "section_id": record.get("section_id"),
            "candidate_origin": "ATOMIC_EXACT_RESCUE",
            "rank": rank,
            "score": item["score"],
            "location": record.get("location"),
            "evidence_type": record.get("granularity"),
            "source_path": record.get("source_path"),
            "file_name": record.get("file_name"),
            "facet_reasons": ["exact_core_phrase"],
            "exact_core_phrase_matches": exact,
            "text": str(record.get("text") or "")[:900],
            "lineage_status": record.get("lineage_status"),
        })
    return {
        **retrieval,
        "atomic_candidates": [*rescued, *retrieval["atomic_candidates"]],
        "atomic_exact_rescue": {"invoked": True, "core_phrases": phrases, "rescued_evidence_ids": [item["evidence_id"] for item in rescued]},
    }


def _core_phrases(question: str) -> list[str]:
    phrases = []
    for part in re.split(r"[，,。；;：:？?！!]", question):
        value = re.split(r"(?:包含|包括|有哪些|哪些|什么|如何|多少|是否|主要|分别|其中)", part, maxsplit=1)[0]
        value = re.sub(r"(?:需要|应该|应当|是要|要)$", "", value).strip()
        if len(value) >= 4:
            phrases.append(_compact(value))
    return list(dict.fromkeys(phrases))


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


@router.get("/enabled")
def enabled() -> dict[str, Any]:
    return {"enabled": CONFIG.get("V2_VERIFIED_RAG_ENABLED") is True, "scope": "8010_LOCALHOST_ONLY", "dense_runtime": "LOCAL_BGE_M3_FP32_WITH_SPARSE_FALLBACK"}


@router.post("/warmup")
def warmup() -> dict[str, Any]:
    if CONFIG.get("V2_VERIFIED_RAG_ENABLED") is not True:
        return {"ready": False, "reason": "V2_VERIFIED_RAG_DISABLED"}
    started = time.perf_counter()
    try:
        _engine_instance().dense.load()
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"V2_DENSE_WARMUP_FAILED:{type(error).__name__}") from error
    return {"ready": True, "dense_runtime": "LOCAL_BGE_M3_FP32", "warmup_ms": round((time.perf_counter() - started) * 1000, 3), "provider_http_requests": 0}


@router.post("/query")
def query(request: V2QueryRequest) -> dict[str, Any]:
    _ensure_user(request.trial_user)
    if CONFIG.get("V2_VERIFIED_RAG_ENABLED") is not True:
        raise HTTPException(status_code=503, detail="V2_VERIFIED_RAG_DISABLED")
    result = _engine_instance().answer(request.question)
    audit = {"timestamp": _now(), "trial_user": request.trial_user, "query_id": result["query_id"], "question": request.question, "pipeline_version": result["pipeline_version"], "answer_status": result["answer_status"], "document_ids": sorted({item.get("document_id") for item in result["debug"]["evidence_bundle"]["candidate_evidence"] if item.get("document_id")}), "evidence_ids": [item["evidence_id"] for item in result["citations"]], "citation_ids": [item["citation_id"] for item in result["citations"]], "bundle_status": result["debug"]["evidence_bundle"]["bundle_status"], "growth_candidate_ids": result["growth_candidate_ids"], "latency": result["latency"], "feedback": None, "gold_runtime_injection": 0}
    _append_jsonl(TRIAL / "trial_audit.jsonl", audit)
    return result


@router.post("/feedback")
def feedback(request: V2FeedbackRequest) -> dict[str, Any]:
    _ensure_user(request.trial_user)
    event = {"feedback_id": "v2-feedback-" + uuid.uuid4().hex, "timestamp": _now(), "trial_user": request.trial_user, "query_id": request.query_id, "feedback_type": request.feedback_type, "comment": request.comment, "source_path": request.source_path, "source_location": request.source_location, "expected_answer": request.expected_answer, "required_terms": _clean_terms(request.required_terms), "growth_candidate_id": None}
    if _feedback_profile(request.feedback_type)["creates_candidate"]:
        candidate = _feedback_growth_candidate(event)
        event["growth_candidate_id"] = candidate["candidate_id"]
        existing = {row.get("candidate_id") for row in _read_jsonl(FEEDBACK_CANDIDATES)}
        if candidate["candidate_id"] not in existing:
            _append_jsonl(FEEDBACK_CANDIDATES, candidate)
        _register_trial_question(event, candidate)
    _append_jsonl(TRIAL / "feedback_events.jsonl", event)
    return {"saved": True, "feedback_event": event, "closure_status": "PENDING_BUSINESS_REVIEW" if event["growth_candidate_id"] else "RECORDED", "automatic_knowledge_publish": 0}


@router.get("/growth-candidates")
def growth_candidates() -> dict[str, Any]:
    rows = _read_jsonl(GROWTH / "growth_candidates.jsonl") + _read_jsonl(GROWTH / "trial_runtime_candidates.jsonl") + _read_jsonl(FEEDBACK_CANDIDATES)
    reviews = {row["candidate_id"]: row for row in _read_jsonl(GROWTH / "review_records.jsonl")}
    visible = []
    for row in rows:
        review = reviews.get(row["candidate_id"])
        effective = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "DEFER": "DEFERRED", "MERGE": "REVIEWED"}.get((review or {}).get("decision"), row.get("review_status"))
        if effective == "PROPOSED":
            visible.append({**row, "latest_review": review, "effective_review_status": effective})
    return {"candidates": visible, "automatic_publish": 0}


@router.get("/feedback-closures")
def feedback_closures() -> dict[str, Any]:
    candidates = _latest_by_id(_read_jsonl(FEEDBACK_CANDIDATES), "candidate_id")
    events = _latest_by_id((row for row in _read_jsonl(TRIAL / "feedback_events.jsonl") if row.get("growth_candidate_id")), "growth_candidate_id")
    reviews = _latest_by_id(_read_jsonl(GROWTH / "review_records.jsonl"), "candidate_id")
    cases = _latest_by_id(_read_jsonl(FEEDBACK_CASES), "candidate_id")
    runs = _latest_by_id(_read_jsonl(FEEDBACK_RUNS), "candidate_id")
    rows = []
    for candidate_id, candidate in candidates.items():
        event, review, case, run = events.get(candidate_id), reviews.get(candidate_id), cases.get(candidate_id), runs.get(candidate_id)
        case = _case_with_readiness(case) if case else None
        rows.append({**candidate, "feedback_event": event, "latest_review": review, "regression_case": case, "latest_regression": run, "closure_status": _closure_status(review, case, run)})
    return {"closures": sorted(rows, key=lambda item: str(item.get("latest_seen_at") or item.get("created_at") or ""), reverse=True), "automatic_knowledge_publish": 0}


@router.post("/growth-review")
def growth_review(request: GrowthReviewRequest) -> dict[str, Any]:
    _ensure_user(request.trial_user)
    if request.decision not in {"APPROVE", "REJECT", "DEFER", "MERGE"}:
        raise HTTPException(status_code=422, detail="INVALID_REVIEW_DECISION")
    record = {"candidate_id": request.candidate_id, "reviewer": request.trial_user, "review_time": _now(), "decision": request.decision, "comment": request.comment, "approved_action": request.approved_action, "confirmed_source_path": request.confirmed_source_path.strip(), "confirmed_source_location": request.confirmed_source_location.strip(), "required_terms": _clean_terms(request.required_terms), "publish_triggered": False}
    regression_case = None
    if request.decision == "APPROVE":
        regression_case = _create_regression_case(request, record)
        record["regression_case_id"] = regression_case["case_id"]
    _append_jsonl(GROWTH / "review_records.jsonl", record)
    return {"saved": True, "review": record, "regression_case": regression_case, "automatic_knowledge_publish": 0}


@router.post("/growth-regression")
def growth_regression(request: GrowthRegressionRequest) -> dict[str, Any]:
    _ensure_user(request.trial_user)
    case = _latest_by_id(_read_jsonl(FEEDBACK_CASES), "candidate_id").get(request.candidate_id)
    if case is None:
        raise HTTPException(status_code=404, detail="REGRESSION_CASE_NOT_FOUND")
    case = _case_with_readiness(case)
    if not case.get("ready"):
        return {"candidate_id": request.candidate_id, "regression_status": "NOT_READY", "reason": case["regression_ready_reason"], "source_runtime_status": case["source_runtime_status"], "invalid_required_terms": case["invalid_required_terms"], "automatic_knowledge_publish": 0}
    result = _engine_instance().answer(str(case["question"]), detect_growth=False)
    run = _evaluate_feedback_regression(case, result, request.trial_user)
    _append_jsonl(FEEDBACK_RUNS, run)
    return {"candidate_id": request.candidate_id, "regression": run, "automatic_knowledge_publish": 0}


@router.get("/page", response_class=FileResponse)
def page() -> FileResponse:
    return FileResponse(str(STATIC), headers={"Cache-Control": "no-store, max-age=0"})


def _friendly_status(value: str) -> str:
    return {"ANSWERED": "已回答", "PARTIAL_ANSWER": "部分回答", "CONFLICTING_ANSWER": "资料存在冲突", "SOURCE_SCOPE_MISSING": "当前知识范围暂无可靠来源", "INSUFFICIENT_EVIDENCE": "证据不足"}.get(value, "需要人工查看")


def _citation(item: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    location = item.get("location") or {}
    return {"citation_id": item["citation_id"], "evidence_id": item.get("evidence_id"), "file_name": item.get("file_name"), "source_path": item.get("source_path"), "location": location, "display_location": _display_location(location), "excerpt": str((evidence or {}).get("text") or "")[:900]}


def _display_location(location: dict[str, Any]) -> str:
    if location.get("page"):
        return f"第{location['page']}页"
    if location.get("sheet_name"):
        start = location.get("row_start", location.get("row", "?"))
        end = location.get("row_end", start)
        rows = f"第{start}-{end}行" if end != start else f"第{start}行"
        return f"{location['sheet_name']}，{rows}"
    if location.get("table"):
        start, end = location.get("row_start"), location.get("row_end")
        return f"表{location['table']}" + (f"，第{start}-{end}行" if start else "")
    if location.get("line_start"):
        return f"第{location['line_start']}-{location.get('line_end', location['line_start'])}行"
    return "位置已记录"


def _ensure_user(user_id: str) -> None:
    if user_id not in USERS:
        raise HTTPException(status_code=403, detail="TRIAL_USER_NOT_ALLOWED")


def _feedback_profile(feedback_type: str) -> dict[str, str | bool]:
    profiles = {
        "回答正确": {"creates_candidate": False, "failure_type": "POSITIVE_FEEDBACK", "growth_type": "NONE", "priority": "P3", "governance_status": "NOT_REQUIRED"},
        "回答不完整": {"creates_candidate": True, "failure_type": "ANSWER_INCOMPLETE", "growth_type": "QA_GROWTH", "priority": "P1", "governance_status": "REQUIRES_ANSWER_REVIEW"},
        "答案错误": {"creates_candidate": True, "failure_type": "ANSWER_INCORRECT", "growth_type": "QA_GROWTH", "priority": "P0", "governance_status": "REQUIRES_EVIDENCE_AND_ANSWER_REVIEW"},
        "引用不对": {"creates_candidate": True, "failure_type": "CITATION_MISMATCH", "growth_type": "QA_GROWTH", "priority": "P0", "governance_status": "REQUIRES_CITATION_REVIEW"},
        "没有回答我的问题": {"creates_candidate": True, "failure_type": "ANSWER_GAP", "growth_type": "QA_GROWTH", "priority": "P1", "governance_status": "REQUIRES_RETRIEVAL_REVIEW"},
        "资料缺失": {"creates_candidate": True, "failure_type": "INSUFFICIENT_EVIDENCE", "growth_type": "KNOWLEDGE_GROWTH", "priority": "P1", "governance_status": "REQUIRES_EVIDENCE_COMPLETENESS_REVIEW"},
        "答案冲突": {"creates_candidate": True, "failure_type": "CONFLICTING_EVIDENCE", "growth_type": "CONFLICT_REVIEW_CANDIDATE", "priority": "P0", "governance_status": "REQUIRES_BUSINESS_CONFLICT_REVIEW"},
    }
    return profiles.get(feedback_type, {"creates_candidate": True, "failure_type": "ANSWER_GAP", "growth_type": "QA_GROWTH", "priority": "P1", "governance_status": "REQUIRES_BUSINESS_REVIEW"})


def _clean_terms(values: list[str]) -> list[str]:
    return list(dict.fromkeys(re.sub(r"\s+", "", value) for value in values if value and re.sub(r"\s+", "", value)))


def _latest_by_id(rows: Any, key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if value:
            result[value] = row
    return result


def _closure_status(review: dict[str, Any] | None, case: dict[str, Any] | None, run: dict[str, Any] | None) -> str:
    if case and not case.get("ready"):
        return "SOURCE_CLOSURE_REQUIRED" if case.get("source_runtime_status") not in {"INDEXED_SHADOW", "VERIFIED_RUNTIME"} else "KEY_FACT_CONFIRMATION_REQUIRED"
    if run and run.get("regression_status") == "PASSED":
        return "CLOSED"
    if run and run.get("regression_status") == "FAILED":
        return "REPAIR_REQUIRED"
    if case and case.get("ready"):
        return "REGRESSION_READY"
    if review and review.get("decision") == "APPROVE":
        return "SOURCE_CONFIRMATION_REQUIRED"
    return "PENDING_BUSINESS_REVIEW"


def _create_regression_case(request: GrowthReviewRequest, review: dict[str, Any]) -> dict[str, Any]:
    candidates = _latest_by_id(_read_jsonl(FEEDBACK_CANDIDATES), "candidate_id")
    candidate = candidates.get(request.candidate_id, {})
    events = _latest_by_id((row for row in _read_jsonl(TRIAL / "feedback_events.jsonl") if row.get("growth_candidate_id")), "growth_candidate_id")
    event = events.get(request.candidate_id, {})
    source_path = _normalize_source_path(review["confirmed_source_path"] or str(event.get("source_path") or ""))
    source_location = review["confirmed_source_location"] or str(event.get("source_location") or "")
    requested_terms = review["required_terms"] or _clean_terms(event.get("required_terms") or [])
    case = {
        "case_id": "RG_" + uuid.uuid5(uuid.NAMESPACE_URL, request.candidate_id).hex[:16],
        "candidate_id": request.candidate_id,
        "created_at": _now(),
        "question": candidate.get("question") or event.get("question") or "",
        "feedback_type": event.get("feedback_type") or candidate.get("feedback_type"),
        "owner_asserted_answer": str(event.get("expected_answer") or ""),
        "expected_source_path": source_path,
        "expected_source_location": source_location,
        "requested_required_terms": requested_terms,
        "required_terms": requested_terms,
        "ready": False,
        "source_confirmation_status": "OWNER_CONFIRMED" if source_path else "PENDING_OWNER_CONFIRMATION",
        "created_by": review["reviewer"],
        "runtime_input": False,
        "formal_knowledge_publish": False,
    }
    case = _case_with_readiness(case)
    _append_jsonl(FEEDBACK_CASES, case)
    return case


def _evaluate_feedback_regression(case: dict[str, Any], result: dict[str, Any], reviewer: str) -> dict[str, Any]:
    answer = str(result.get("answer") or "")
    citations = result.get("citations") or []
    source_hit = any(_same_source_path(case["expected_source_path"], item.get("source_path")) for item in citations)
    expected_location = str(case.get("expected_source_location") or "").strip()
    location_hit = not expected_location or any(expected_location in str(item.get("display_location") or "") for item in citations)
    missing_terms = [term for term in case["required_terms"] if term not in answer]
    passed = result.get("answer_status") == "ANSWERED" and source_hit and location_hit and not missing_terms
    return {
        "run_id": "RR_" + uuid.uuid4().hex,
        "candidate_id": case["candidate_id"],
        "case_id": case["case_id"],
        "run_at": _now(),
        "reviewer": reviewer,
        "answer_status": result.get("answer_status"),
        "citation_source_hit": source_hit,
        "citation_location_hit": location_hit,
        "missing_required_terms": missing_terms,
        "regression_status": "PASSED" if passed else "FAILED",
        "repair_status": "VALIDATED" if passed else "REPAIR_REQUIRED",
        "answer_excerpt": answer[:600],
        "citation_ids": [item.get("citation_id") for item in citations],
        "provider_http_requests": result.get("provider_http_requests"),
        "gold_runtime_injection": 0,
        "formal_knowledge_publish": False,
    }


def _same_source_path(left: Any, right: Any) -> bool:
    return _normalize_source_path(left).casefold() == _normalize_source_path(right).casefold()


def _normalize_source_path(value: Any) -> str:
    return str(value or "").strip().strip("\"'“”").replace("/", "\\").rstrip("\\")


def _valid_key_fact(value: str) -> bool:
    return len(value) >= 2 and value not in {"目录", "封面", "说明", "附件", "正文", "文件", "文档", "页码"}


def _declared_source_status(source_path: str) -> str:
    if not SOURCE_CLOSURE_REGISTER.exists():
        return "SOURCE_IDENTIFIED"
    file_name = source_path.rsplit("\\", 1)[-1].casefold()
    for row in _read_jsonl(SOURCE_CLOSURE_REGISTER):
        known_path = _normalize_source_path(row.get("correct_source_path"))
        known_file = str(row.get("correct_source_file_name") or "").casefold()
        if known_path and _same_source_path(source_path, known_path):
            return str(row.get("source_status") or "SOURCE_IDENTIFIED")
        if not known_path and file_name and file_name == known_file:
            return "SOURCE_IDENTIFIED"
    return "SOURCE_IDENTIFIED"


def _source_runtime_status(source_path: str) -> str:
    if not source_path:
        return "PENDING_OWNER_CONFIRMATION"
    if any(_same_source_path(source_path, source.get("path")) for source in _approved_shadow_sources() if source.get("approval_status") == "USER_APPROVED_SHADOW_READ"):
        return "INDEXED_SHADOW" if _normalize_source_path(source_path) in LOADED_SHADOW_PATHS else "SOURCE_IDENTIFIED"
    try:
        indexed = any(_same_source_path(source_path, row.get("source_path")) for row in _engine_instance().index.atomic)
    except Exception:
        indexed = False
    return "INDEXED_SHADOW" if indexed else _declared_source_status(source_path)


def _approved_shadow_sources() -> list[dict[str, str]]:
    sources = [dict(row) for row in CONFIG.approved_shadow_sources]
    seen = {_normalize_source_path(row.get("path")) for row in sources}
    for row in _read_jsonl(BATCH_SOURCE_REGISTER):
        path = str(row.get("path") or row.get("source_path") or "")
        if row.get("status") != "APPROVED" or not path:
            continue
        normalized = _normalize_source_path(path)
        if normalized in seen:
            continue
        sources.append({"path": path, "approval_status": "USER_APPROVED_SHADOW_READ"})
        seen.add(normalized)
    return sources


def _case_with_readiness(case: dict[str, Any]) -> dict[str, Any]:
    value = dict(case)
    source_path = _normalize_source_path(value.get("expected_source_path"))
    requested = _clean_terms(value.get("requested_required_terms") or value.get("required_terms") or [])
    required = [term for term in requested if _valid_key_fact(term)]
    invalid = [term for term in requested if term not in required]
    source_state = _source_runtime_status(source_path)
    ready = bool(source_path and required and source_state in {"INDEXED_SHADOW", "VERIFIED_RUNTIME"})
    if not source_path:
        reason = "需要确认来源文件路径后，才能建立回归。"
    elif source_state not in {"INDEXED_SHADOW", "VERIFIED_RUNTIME"}:
        reason = "来源尚未进入当前Shadow索引；请先完成Source Closure，不运行回归。"
    elif not required:
        reason = "关键事实不能仅为目录、封面、说明等文件结构词；请填写可验证的业务事实。"
    else:
        reason = "已具备Shadow回归条件。"
    value.update({"expected_source_path": source_path, "requested_required_terms": requested, "required_terms": required, "invalid_required_terms": invalid, "source_runtime_status": source_state, "ready": ready, "regression_ready_reason": reason})
    return value


def _feedback_growth_candidate(event: dict[str, Any]) -> dict[str, Any]:
    audit = next((row for row in reversed(_read_jsonl(TRIAL / "trial_audit.jsonl")) if row.get("query_id") == event["query_id"]), {})
    profile = _feedback_profile(event["feedback_type"])
    return {"candidate_id": "FG_" + uuid.uuid5(uuid.NAMESPACE_URL, f"{event['query_id']}:{event['feedback_type']}").hex[:16], "candidate_fingerprint": f"feedback:{event['query_id']}:{event['feedback_type']}", "created_at": event["timestamp"], "source_query_id": event["query_id"], "question": audit.get("question", ""), "feedback_type": event["feedback_type"], "failure_type": profile["failure_type"], "growth_type": profile["growth_type"], "priority": profile["priority"], "reason": f"试用用户反馈：{event['feedback_type']}", "current_answer_status": audit.get("answer_status"), "affected_document_ids": audit.get("document_ids", []), "affected_section_ids": [], "affected_evidence_ids": audit.get("evidence_ids", []), "knowledge_gap": "待业务审核确认", "retrieval_gap": None, "answer_gap": event.get("comment") or None, "owner_asserted_source": {"source_path": event.get("source_path"), "source_location": event.get("source_location")}, "owner_asserted_answer": event.get("expected_answer"), "owner_required_terms": event.get("required_terms", []), "recommended_action": "人工确认来源文件、位置和关键事实后，建立只用于Shadow回归的业务验收用例。", "suggested_source": None, "suggested_metadata_fix": None, "suggested_qa": None, "evidence_snapshot": {"trial_audit": audit}, "governance_status": profile["governance_status"], "review_status": "PROPOSED", "reviewer": None, "review_comment": None, "closure_status": "PENDING_BUSINESS_REVIEW", "repair_status": "PENDING_TRIAGE", "regression_status": "NOT_READY", "created_by": "AI_PROPOSED", "knowledge_origin": "AI_PROPOSED", "schema_version": "knowledge_growth.v1", "occurrence_count": 1, "latest_seen_at": event["timestamp"], "related_query_ids": [event["query_id"]], "regression_question_ids": [], "feedback_event_id": event["feedback_id"]}


def _register_trial_question(event: dict[str, Any], candidate: dict[str, Any]) -> None:
    existing = {row.get("candidate_id") for row in _read_jsonl(TRIAL_FEEDBACK_QUESTIONS)}
    if candidate["candidate_id"] in existing:
        return
    source_path = _normalize_source_path(event.get("source_path"))
    _append_jsonl(TRIAL_FEEDBACK_QUESTIONS, {
        "schema_version": "trial-cycle-01.business-question.v1",
        "question_id": "TF_" + candidate["candidate_id"][3:],
        "candidate_id": candidate["candidate_id"],
        "question": candidate["question"],
        "business_domain": None,
        "organization": None,
        "project": None,
        "year": None,
        "specialty": None,
        "answer_type": "UNCONFIRMED",
        "correct_source_path": source_path or None,
        "correct_source_file_name": source_path.rsplit("\\", 1)[-1] if source_path else None,
        "correct_location": str(event.get("source_location") or "") or None,
        "key_facts": _clean_terms(event.get("required_terms") or []),
        "must_include_claims": [],
        "must_not_use_sources": [],
        "expected_runtime_status": "OBSERVE_ONLY",
        "source_governance_status": "SOURCE_IDENTIFIED" if source_path else "SOURCE_UNKNOWN",
        "owner_confirmation_status": "UNCONFIRMED",
        "created_from": "8010_feedback_event",
        "registry_set": "TRIAL_QUESTION",
        "regression_enabled": False,
        "runtime_input": False,
        "formal_knowledge_publish": False,
        "created_at": _now(),
    })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
