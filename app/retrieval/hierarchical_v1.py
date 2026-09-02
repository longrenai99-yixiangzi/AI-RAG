from __future__ import annotations

import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
from qdrant_client import QdrantClient

from app.bm25 import BM25Index, tokenize
from app.domain import Chunk
from app.ingestion.atomic_search import search_atomic_evidence
from app.ingestion.metadata.governance import GovernanceClassifier
from app.retrieval.rrf import reciprocal_rank_fusion
from app.retrieval.query_planner_v1 import QueryPlan


SCHEMA_VERSION = "hierarchical_retrieval.v1"


def build_shadow_index(
    *,
    v2_dir: Path,
    output_dir: Path,
    root1_qdrant: Path,
    root1_collection: str,
    root2_qdrant: Path,
    root2_collection: str,
) -> dict[str, Any]:
    documents = _read_jsonl(v2_dir / "documents.jsonl")
    headings = _read_jsonl(v2_dir / "headings.jsonl")
    sections = _read_jsonl(v2_dir / "sections.jsonl")
    tables = _read_jsonl(v2_dir / "tables.jsonl")
    atomic = _read_jsonl(v2_dir / "atomic_evidence.jsonl")
    lineages = _read_jsonl(v2_dir / "lineage.jsonl")
    compatibility = _read_jsonl(v2_dir / "compatibility_samples.jsonl")

    document_records = [_document_record(item, headings) for item in documents]
    section_records = [_section_record(item, document_records, tables) for item in sections]
    table_records = [_table_record(item, document_records, section_records) for item in tables]
    compatibility_lineage = {str(item.get("source_path") or "").casefold(): str(item.get("lineage_status") or "LINEAGE_NOT_APPLICABLE") for item in compatibility}
    root1_paths = {str(item["source_path"]).casefold(): item["document_id"] for item in documents}
    section_by_doc = _group(section_records, "document_id")
    vectors, frozen = _collect_vectors(
        root1_qdrant,
        root1_collection,
        root2_qdrant,
        root2_collection,
        root1_paths,
        section_by_doc,
        compatibility_lineage,
    )
    document_records.extend(frozen["documents"])
    section_records.extend(frozen["sections"])
    table_records.extend(frozen["tables"])
    all_sections_by_document = _group(section_records, "document_id")
    for document in document_records:
        facets = _document_type_facets(document, all_sections_by_document.get(document["document_id"], []))
        document["document_type_facets"] = facets
        document["document_search_text"] = _join([document.get("document_search_text"), " ".join(facets)])
    facets_by_document = {item["document_id"]: item["document_type_facets"] for item in document_records}
    for section in section_records:
        section["document_type_facets"] = facets_by_document[section["document_id"]]
    for table in table_records:
        table["document_type_facets"] = facets_by_document[table["document_id"]]
    lineage_by_document = {item["document_id"]: item.get("lineage_status", "LINEAGE_NOT_APPLICABLE") for item in document_records}
    for record in atomic:
        record.setdefault("lineage_status", lineage_by_document.get(record.get("document_id"), "LINEAGE_NOT_APPLICABLE"))
    atomic.extend(frozen["atomic_evidence"])
    document_vectors = _vectors_for(document_records, vectors["document"])
    section_vectors, section_dense_audit = _section_vectors_for(
        section_records,
        vectors["section"],
        vectors["document"],
    )
    index = HierarchicalIndex(document_records, section_records, table_records, atomic, document_vectors, section_vectors)
    index.save(output_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "documents": len(document_records),
        "sections": len(section_records),
        "tables": len(table_records),
        "atomic_evidence": len(atomic),
        "document_dense_coverage": round(float(np.count_nonzero(np.linalg.norm(document_vectors, axis=1))) / max(1, len(document_records)), 4),
        "section_dense_coverage": section_dense_audit["eligible_dense_coverage"],
        "section_dense_audit": section_dense_audit,
        "root2_mode": "FROZEN_SHADOW_ARTIFACT",
    }


class HierarchicalIndex:
    def __init__(
        self,
        documents: list[dict[str, Any]],
        sections: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        atomic: list[dict[str, Any]],
        document_vectors: np.ndarray,
        section_vectors: np.ndarray,
    ) -> None:
        self.documents = documents
        self.sections = sections
        self.tables = tables
        self.atomic = atomic
        self.document_vectors = document_vectors.astype(np.float32, copy=False)
        self.section_vectors = section_vectors.astype(np.float32, copy=False)
        self.document_by_id = {item["document_id"]: item for item in documents}
        self.section_by_id = {item["section_id"]: item for item in sections}
        self.table_by_id = {item["table_id"]: item for item in tables}
        self.section_ids_by_document: dict[str, list[str]] = defaultdict(list)
        for section in sections:
            self.section_ids_by_document[str(section["document_id"])].append(str(section["section_id"]))
        self.document_bm25 = _bm25(documents, "document_id", "document_search_text")
        self.section_bm25 = _bm25(sections, "section_id", "section_search_text")
        self.table_bm25 = _bm25(tables, "table_id", "table_search_text")

    @classmethod
    def load(cls, output_dir: Path) -> "HierarchicalIndex":
        documents = _read_jsonl(output_dir / "document_index" / "records.jsonl")
        sections = _read_jsonl(output_dir / "section_index" / "records.jsonl")
        tables = _read_jsonl(output_dir / "table_index" / "records.jsonl")
        atomic = _read_jsonl(output_dir / "atomic_evidence.jsonl")
        document_vectors = np.load(output_dir / "document_index" / "vectors.npy")
        section_vectors = np.load(output_dir / "section_index" / "vectors.npy")
        return cls(documents, sections, tables, atomic, document_vectors, section_vectors)

    def save(self, output_dir: Path) -> None:
        _write_jsonl(output_dir / "document_index" / "records.jsonl", self.documents)
        _write_jsonl(output_dir / "section_index" / "records.jsonl", self.sections)
        _write_jsonl(output_dir / "table_index" / "records.jsonl", self.tables)
        _write_jsonl(output_dir / "atomic_evidence.jsonl", self.atomic)
        (output_dir / "document_index").mkdir(parents=True, exist_ok=True)
        (output_dir / "section_index").mkdir(parents=True, exist_ok=True)
        np.save(output_dir / "document_index" / "vectors.npy", self.document_vectors)
        np.save(output_dir / "section_index" / "vectors.npy", self.section_vectors)
        _save_bm25(self.document_bm25, output_dir / "document_index" / "bm25.json")
        _save_bm25(self.section_bm25, output_dir / "section_index" / "bm25.json")
        _save_bm25(self.table_bm25, output_dir / "table_index" / "bm25.json")

    def retrieve(self, plan: QueryPlan, query_vector: list[float]) -> dict[str, Any]:
        import time

        document_started = time.perf_counter()
        document_candidates = self._rank_documents(plan, query_vector, limit=20)
        document_ms = (time.perf_counter() - document_started) * 1000
        top_documents = {item["document_id"] for item in document_candidates[:10]}
        section_started = time.perf_counter()
        local_sections = self._rank_records(self.sections, self.section_vectors, self.section_bm25, "section_id", plan, query_vector, limit=50, allowed_documents=top_documents, origin="HIERARCHICAL")
        global_sections = self._rank_records(self.sections, self.section_vectors, self.section_bm25, "section_id", plan, query_vector, limit=20, origin="GLOBAL_RESCUE")
        sections = _merge_section_candidates(local_sections, global_sections)
        section_ms = (time.perf_counter() - section_started) * 1000
        selected_documents = {item["document_id"] for item in document_candidates[:10]}
        selected_documents.update(item["document_id"] for item in sections[:20])
        evidence_started = time.perf_counter()
        table_candidates = self._rank_records(self.tables, np.empty((0, 0), dtype=np.float32), self.table_bm25, "table_id", plan, query_vector, limit=20, allowed_documents=selected_documents, origin="HIERARCHICAL")
        sections = _merge_table_parent_sections(sections, table_candidates, self.section_by_id)
        table_documents = {item["document_id"] for item in table_candidates[:5]}
        selected_sections = {item["section_id"] for item in sections[:20]}
        atomic_pool = [item for item in self.atomic if item.get("document_id") in selected_documents and (not item.get("section_id") or item.get("section_id") in selected_sections)]
        pool_ids = {id(item) for item in atomic_pool}
        atomic_pool.extend(item for item in self.atomic if item.get("document_id") in table_documents and id(item) not in pool_ids)
        if not atomic_pool:
            atomic_pool = [item for item in self.atomic if item.get("document_id") in selected_documents]
        atomic_results = search_atomic_evidence(plan.normalized_question, atomic_pool, limit=20)
        evidence_candidates = []
        section_origins = {item["section_id"]: item["candidate_origin"] for item in sections}
        for rank, item in enumerate(atomic_results, start=1):
            record = dict(item["record"])
            evidence_candidates.append({
                "evidence_id": record.get("evidence_id"),
                "document_id": record.get("document_id"),
                "section_id": record.get("section_id"),
                "candidate_origin": section_origins.get(record.get("section_id"), "HIERARCHICAL"),
                "rank": rank,
                "score": item["score"],
                "location": record.get("location"),
                "evidence_type": record.get("granularity"),
                "source_path": record.get("source_path"),
                "file_name": record.get("file_name"),
                "facet_reasons": item.get("facet_reasons", []),
                "text": str(record.get("text") or "")[:900],
                "lineage_status": _lineage_for_record(record),
            })
        evidence_ms = (time.perf_counter() - evidence_started) * 1000
        return {
            "document_candidates": document_candidates,
            "local_section_candidates": local_sections,
            "section_candidates": sections,
            "table_candidates": table_candidates,
            "atomic_candidates": evidence_candidates,
            "global_rescue_raw_candidates": global_sections,
            "global_rescue_candidates": [item for item in sections if item["candidate_origin"] == "GLOBAL_RESCUE"],
            "timings": {"document_retrieval_ms": round(document_ms, 3), "section_retrieval_ms": round(section_ms, 3), "evidence_candidate_ms": round(evidence_ms, 3)},
        }

    def _rank_documents(self, plan: QueryPlan, query_vector: list[float], *, limit: int) -> list[dict[str, Any]]:
        """Rank a document by its own representation and its best matching section.

        This remains one document stage: a section only supplies an alternate
        representation for its parent document, then the existing RRF combines
        sparse and dense ranks. It does not create an additional retrieval path.
        """
        document_ids = {str(item["document_id"]) for item in self.documents}
        doc_bm25_pairs = _bm25_pairs(self.documents, self.document_bm25, "document_id", "document_search_text", plan.normalized_question, document_ids)
        section_bm25_pairs = _collapse_section_pairs(
            _bm25_pairs(self.sections, self.section_bm25, "section_id", "section_search_text", plan.normalized_question, set(self.section_by_id)),
            self.section_by_id,
        )
        doc_dense_pairs = _dense_pairs(self.documents, self.document_vectors, query_vector, document_ids, "document_id")
        section_dense_pairs = _collapse_section_pairs(
            _dense_pairs(self.sections, self.section_vectors, query_vector, set(self.section_by_id), "section_id"),
            self.section_by_id,
        )
        rrf = reciprocal_rank_fusion({
            "document_bm25": [item_id for item_id, _ in doc_bm25_pairs],
            "best_section_bm25": [item_id for item_id, _ in section_bm25_pairs],
            "document_dense": [item_id for item_id, _ in doc_dense_pairs],
            "best_section_dense": [item_id for item_id, _ in section_dense_pairs],
        })
        doc_bm25_ranks = _rank_map(doc_bm25_pairs)
        section_bm25_ranks = _rank_map(section_bm25_pairs)
        doc_dense_ranks = _rank_map(doc_dense_pairs)
        section_dense_ranks = _rank_map(section_dense_pairs)
        doc_bm25_scores = dict(doc_bm25_pairs)
        section_bm25_scores = dict(section_bm25_pairs)
        doc_dense_scores = dict(doc_dense_pairs)
        section_dense_scores = dict(section_dense_pairs)
        result = []
        for item in rrf:
            record = self.document_by_id[item.chunk_id]
            boost, trace = _soft_boost(record, plan)
            representation = {
                "document_bm25_rank": doc_bm25_ranks.get(item.chunk_id),
                "best_section_bm25_rank": section_bm25_ranks.get(item.chunk_id),
                "document_dense_rank": doc_dense_ranks.get(item.chunk_id),
                "best_section_dense_rank": section_dense_ranks.get(item.chunk_id),
            }
            result.append({
                "document_id": item.chunk_id,
                "source_path": record.get("source_path"),
                "file_name": record.get("file_name"),
                "heading": None,
                "heading_path": None,
                "location": None,
                "bm25_rank": min((rank for rank in (representation["document_bm25_rank"], representation["best_section_bm25_rank"]) if rank is not None), default=None),
                "bm25_score": max((score for score in (doc_bm25_scores.get(item.chunk_id), section_bm25_scores.get(item.chunk_id)) if score is not None), default=None),
                "dense_rank": min((rank for rank in (representation["document_dense_rank"], representation["best_section_dense_rank"]) if rank is not None), default=None),
                "dense_score": max((score for score in (doc_dense_scores.get(item.chunk_id), section_dense_scores.get(item.chunk_id)) if score is not None), default=None),
                "rrf_score": item.score,
                "planner_boost": boost,
                "planner_match": trace,
                "metadata_match": trace.get("metadata_match", []),
                "document_type": record.get("document_type"),
                "document_type_facets": record.get("document_type_facets", []),
                "document_role": record.get("document_role"),
                "authority": record.get("authority_level"),
                "scope": record.get("scope"),
                "lineage_status": record.get("lineage_status"),
                "candidate_origin": "HIERARCHICAL",
                "representation_trace": representation,
                "record": record,
            })
        result.sort(key=lambda candidate: (-(candidate["rrf_score"] + candidate["planner_boost"]), candidate["document_id"]))
        for rank, candidate in enumerate(result, start=1):
            candidate["rank"] = rank
        return result[:limit]

    def _rank_records(
        self,
        records: list[dict[str, Any]],
        vectors: np.ndarray,
        bm25: BM25Index,
        id_key: str,
        plan: QueryPlan,
        query_vector: list[float],
        *,
        limit: int,
        allowed_documents: set[str] | None = None,
        origin: str,
    ) -> list[dict[str, Any]]:
        allowed_ids = {str(item[id_key]) for item in records if allowed_documents is None or item.get("document_id") in allowed_documents}
        bm25_pairs = [(item_id, score) for item_id, score in bm25.search(plan.normalized_question, limit=len(records)) if item_id in allowed_ids]
        if not bm25_pairs and allowed_ids:
            # ponytail: rank_bm25 can emit no positive score for a one-record index; lexical overlap keeps the candidate visible.
            terms = set(tokenize(plan.normalized_question))
            bm25_pairs = sorted(
                (
                    (str(record[id_key]), float(sum(term in str(record.get("document_search_text") or record.get("section_search_text") or record.get("table_search_text") or "") for term in terms)))
                    for record in records
                    if str(record[id_key]) in allowed_ids
                ),
                key=lambda item: (-item[1], item[0]),
            )
        dense_pairs = _dense_pairs(records, vectors, query_vector, allowed_ids, id_key)
        rrf = reciprocal_rank_fusion({"bm25": [item_id for item_id, _ in bm25_pairs], "dense": [item_id for item_id, _ in dense_pairs]})
        by_id = {str(item[id_key]): item for item in records}
        bm25_scores = dict(bm25_pairs)
        dense_scores = dict(dense_pairs)
        result = []
        for item in rrf:
            record = by_id[item.chunk_id]
            boost, trace = _soft_boost(record, plan)
            result.append({
                id_key: item.chunk_id,
                "document_id": record.get("document_id", item.chunk_id),
                "source_path": record.get("source_path"),
                "file_name": record.get("file_name"),
                "heading": record.get("heading"),
                "heading_path": record.get("heading_path"),
                "location": record.get("location") or record.get("source_location"),
                "bm25_rank": item.ranks.get("bm25"),
                "bm25_score": bm25_scores.get(item.chunk_id),
                "dense_rank": item.ranks.get("dense"),
                "dense_score": dense_scores.get(item.chunk_id),
                "rrf_score": item.score,
                "planner_boost": boost,
                "planner_match": trace,
                "metadata_match": trace.get("metadata_match", []),
                "document_type": record.get("document_type"),
                "document_role": record.get("document_role"),
                "authority": record.get("authority_level"),
                "scope": record.get("scope"),
                "lineage_status": record.get("lineage_status"),
                "candidate_origin": origin,
                "record": record,
            })
        result.sort(key=lambda item: (-(item["rrf_score"] + item["planner_boost"]), str(item[id_key])))
        for rank, item in enumerate(result, start=1):
            item["rank"] = rank
        return result[:limit]


def _document_record(document: dict[str, Any], headings: list[dict[str, Any]]) -> dict[str, Any]:
    profile = document.get("document_profile") or {}
    value = lambda field: (profile.get(field) or {}).get("value")
    heading_values = [item.get("heading_text", "") for item in headings if item.get("document_id") == document.get("document_id")][:20]
    fields = [
        document.get("file_name"),
        profile.get("profile_text", ""),
        value("document_type"),
        value("document_role"),
        value("organization"),
        value("project"),
        value("specialty"),
        value("year"),
        value("metrics"),
        " ".join(heading_values),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document["document_id"],
        "knowledge_root_id": document.get("knowledge_root_id", "Root-001"),
        "source_path": document["source_path"],
        "file_name": document["file_name"],
        "document_search_text": _join(fields),
        "document_type": value("document_type") or "OTHER",
        "document_role": value("document_role") or "其他",
        "authority_level": value("authority_level") or "UNKNOWN",
        "scope": value("applicable_scope") or {},
        "organization": value("organization") or [],
        "project": value("project") or [],
        "year": value("year") or [],
        "specialty": value("specialty") or [],
        "metric": value("metrics") or [],
        "lineage_status": (document.get("source_lineage") or {}).get("lineage_status", "LINEAGE_NOT_APPLICABLE"),
    }


def _section_record(section: dict[str, Any], documents: list[dict[str, Any]], tables: list[dict[str, Any]]) -> dict[str, Any]:
    document = next(item for item in documents if item["document_id"] == section["document_id"])
    table_titles = [str(item.get("table_title") or "") for item in tables if item.get("section_id") == section["section_id"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "section_id": section["section_id"],
        "document_id": section["document_id"],
        "knowledge_root_id": document["knowledge_root_id"],
        "source_path": document["source_path"],
        "file_name": document["file_name"],
        "heading": section.get("heading", ""),
        "heading_path": section.get("heading_path", ""),
        "parent_heading": section.get("heading_path", "").rsplit(" > ", 1)[0] if " > " in section.get("heading_path", "") else "",
        "location": {"start": section.get("location_start"), "end": section.get("location_end")},
        "section_content_text": section.get("section_text", ""),
        "section_search_text": _join([document["file_name"], document["document_search_text"], section.get("heading"), section.get("heading_path"), section.get("section_text", "")[:1_500], " ".join(table_titles)]),
        "document_type": document["document_type"],
        "document_role": document["document_role"],
        "authority_level": document["authority_level"],
        "scope": document["scope"],
        "lineage_status": document["lineage_status"],
    }


def _table_record(table: dict[str, Any], documents: list[dict[str, Any]], sections: list[dict[str, Any]]) -> dict[str, Any]:
    section = next(item for item in sections if item["section_id"] == table["section_id"])
    document = next(item for item in documents if item["document_id"] == table["document_id"])
    semantic = table.get("semantic") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "table_id": table["table_id"],
        "document_id": table["document_id"],
        "section_id": table["section_id"],
        "knowledge_root_id": document["knowledge_root_id"],
        "source_path": document["source_path"],
        "file_name": document["file_name"],
        "sheet_name": table.get("sheet_name"),
        "header": table.get("header", []),
        "source_location": table.get("source_location"),
        "table_search_text": _join([document["document_search_text"], section.get("heading"), semantic.get("title"), semantic.get("header"), semantic.get("semantic_summary"), semantic.get("business_fields"), table.get("sheet_name")]),
        "document_type": document["document_type"],
        "document_role": document["document_role"],
        "authority_level": document["authority_level"],
        "scope": document["scope"],
        "lineage_status": document["lineage_status"],
    }


def _collect_vectors(root1_path: Path, root1_collection: str, root2_path: Path, root2_collection: str, root1_paths: dict[str, str], section_by_doc: dict[str, list[dict[str, Any]]], compatibility_lineage: dict[str, str]) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, list[dict[str, Any]]]]:
    document_sums: dict[str, tuple[np.ndarray, int]] = {}
    section_sums: dict[str, tuple[np.ndarray, int]] = {}
    frozen_docs: dict[str, dict[str, Any]] = {}
    frozen_sections: dict[str, dict[str, Any]] = {}
    frozen_tables: dict[str, dict[str, Any]] = {}
    frozen_atomic: list[dict[str, Any]] = []
    governance = GovernanceClassifier()

    def add(store: dict[str, tuple[np.ndarray, int]], key: str, vector: Any) -> None:
        value = np.asarray(vector, dtype=np.float32)
        total, count = store.get(key, (np.zeros_like(value), 0))
        store[key] = (total + value, count + 1)

    def scan(path: Path, collection: str, root: str) -> None:
        client = QdrantClient(path=str(path))
        try:
            offset: Any = None
            while True:
                points, offset = client.scroll(collection_name=collection, limit=128, offset=offset, with_payload=True, with_vectors=True)
                for point in points:
                    payload = point.payload or {}
                    vector = point.vector
                    source_path = str(payload.get("source_path") or "")
                    if not source_path or vector is None:
                        continue
                    path_key = source_path.casefold()
                    if root == "Root-001":
                        did = root1_paths.get(path_key)
                        if did is None:
                            continue
                        section = _match_root1_section(section_by_doc.get(did, []), str(payload.get("heading_path") or ""), dict(payload.get("location") or {}))
                        add(document_sums, did, vector)
                        if section:
                            add(section_sums, section["section_id"], vector)
                    else:
                        did = str(uuid.uuid5(uuid.NAMESPACE_URL, f"frozen|{path_key}"))
                        info = frozen_docs.get(did)
                        if info is None:
                            classified = governance.classify(file_name=str(payload.get("file_name") or Path(source_path).name), source_path=source_path, heading_path=str(payload.get("heading_path") or ""), text=str(payload.get("text") or ""), metadata=payload.get("metadata") or {})
                            info = {
                                "schema_version": SCHEMA_VERSION,
                                "document_id": did,
                                "knowledge_root_id": "Root-002",
                                "source_path": source_path,
                                "file_name": str(payload.get("file_name") or Path(source_path).name),
                                "document_search_text": "",
                                "document_type": "REGISTER_PAGE" if "\\wiki\\sources\\" in path_key else "OTHER",
                                "document_role": classified.document_role,
                                "authority_level": classified.authority_level,
                                "scope": {"organization": [str(payload.get("source_organization"))] if payload.get("source_organization") else [], "project": [str(payload.get("project_name"))] if payload.get("project_name") else [], "year": [str(payload.get("publish_date"))] if payload.get("publish_date") else []},
                                "organization": [str(payload.get("source_organization"))] if payload.get("source_organization") else [],
                                "project": [str(payload.get("project_name"))] if payload.get("project_name") else [],
                                "year": [str(payload.get("publish_date"))] if payload.get("publish_date") else [],
                                "specialty": [str(payload.get("discipline"))] if payload.get("discipline") else [],
                                "metric": [],
                                "lineage_status": compatibility_lineage.get(path_key, "LINEAGE_NOT_APPLICABLE"),
                                "_headings": [],
                                "_text": [],
                            }
                            frozen_docs[did] = info
                        heading_path = str(payload.get("heading_path") or "")
                        location = dict(payload.get("location") or {})
                        section_key = heading_path or json.dumps(location, ensure_ascii=False, sort_keys=True)
                        sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"frozen-section|{did}|{section_key}"))
                        section = frozen_sections.get(sid)
                        if section is None:
                            section = {
                                "schema_version": SCHEMA_VERSION,
                                "section_id": sid,
                                "document_id": did,
                                "knowledge_root_id": "Root-002",
                                "source_path": source_path,
                                "file_name": info["file_name"],
                                "heading": heading_path or info["file_name"],
                                "heading_path": heading_path,
                                "parent_heading": heading_path.rsplit(" > ", 1)[0] if " > " in heading_path else "",
                                "location": location,
                                "section_content_text": "",
                                "section_search_text": "",
                                "document_type": info["document_type"],
                                "document_role": info["document_role"],
                                "authority_level": info["authority_level"],
                                "scope": info["scope"],
                                "lineage_status": info["lineage_status"],
                                "_text": [],
                            }
                            frozen_sections[sid] = section
                        info["_headings"].append(heading_path)
                        info["_text"].append(str(payload.get("text") or "")[:500])
                        section["_text"].append(str(payload.get("text") or "")[:500])
                        add(document_sums, did, vector)
                        add(section_sums, sid, vector)
                        frozen_atomic.append({
                            "schema_version": SCHEMA_VERSION,
                            "evidence_id": str(payload.get("chunk_id") or point.id),
                            "document_id": did,
                            "section_id": sid,
                            "paragraph_id": None,
                            "table_id": None,
                            "parent_heading_path": heading_path,
                            "parent_mapping_status": "FROZEN_ARTIFACT",
                            "source_path": source_path,
                            "file_name": info["file_name"],
                            "file_type": str(payload.get("file_type") or Path(source_path).suffix),
                            "granularity": "frozen_chunk",
                            "location": location,
                            "text": str(payload.get("text") or ""),
                            "lineage_status": info["lineage_status"],
                        })
                        file_type = str(payload.get("file_type") or "").lower()
                        table_marker = location.get("sheet_name") if file_type == ".xlsx" else location.get("table") if file_type == ".docx" else None
                        if table_marker is not None:
                            tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"frozen-table|{did}|{file_type}|{table_marker}"))
                            frozen_tables.setdefault(tid, {
                                "schema_version": SCHEMA_VERSION, "table_id": tid, "document_id": did, "section_id": sid, "knowledge_root_id": "Root-002", "source_path": source_path, "file_name": info["file_name"], "sheet_name": location.get("sheet_name"), "header": [], "source_location": location, "table_search_text": "", "document_type": info["document_type"], "document_role": info["document_role"], "authority_level": info["authority_level"], "scope": info["scope"], "lineage_status": info["lineage_status"], "_text": []
                            })["_text"].append(str(payload.get("text") or "")[:500])
                if offset is None:
                    break
        finally:
            client.close()

    scan(root1_path, root1_collection, "Root-001")
    scan(root2_path, root2_collection, "Root-002")
    for doc in frozen_docs.values():
        doc["document_type"] = _frozen_document_type(doc["file_name"], doc["_text"])
        doc["document_search_text"] = _join([doc["file_name"], doc["document_type"], doc["document_role"], doc["organization"], doc["project"], doc["year"], " ".join(doc.pop("_headings")[:20]), " ".join(doc.pop("_text")[:5])])
    for section in frozen_sections.values():
        section["document_type"] = frozen_docs[section["document_id"]]["document_type"]
        section["section_content_text"] = " ".join(section.pop("_text")[:5])
        section["section_search_text"] = _join([section["file_name"], section["heading"], section["heading_path"], section["section_content_text"]])
    for table in frozen_tables.values():
        table["document_type"] = frozen_docs[table["document_id"]]["document_type"]
        table["table_search_text"] = _join([table["file_name"], table["sheet_name"], " ".join(table.pop("_text")[:5])])
    return {
        "document": _average_vectors(document_sums),
        "section": _average_vectors(section_sums),
    }, {
        "documents": list(frozen_docs.values()),
        "sections": list(frozen_sections.values()),
        "tables": list(frozen_tables.values()),
        "atomic_evidence": frozen_atomic,
    }


def _match_root1_section(sections: list[dict[str, Any]], heading_path: str, location: dict[str, Any]) -> dict[str, Any] | None:
    matches = [item for item in sections if heading_path and (heading_path == item.get("heading_path") or heading_path.startswith(str(item.get("heading_path") or "") + " > "))]
    if matches:
        return max(matches, key=lambda item: len(str(item.get("heading_path") or "")))
    if location.get("page") is not None:
        return next((item for item in sections if (item.get("location_start") or {}).get("page") == location.get("page")), None)
    if location.get("sheet_name"):
        return next((item for item in sections if (item.get("location_start") or {}).get("sheet_name") == location.get("sheet_name")), None)
    return next((item for item in sections if item.get("heading_path") == ""), sections[0] if sections else None)


def _average_vectors(values: dict[str, tuple[np.ndarray, int]]) -> dict[str, np.ndarray]:
    result = {}
    for key, (total, count) in values.items():
        vector = total / max(1, count)
        norm = np.linalg.norm(vector)
        result[key] = vector / norm if norm else vector
    return result


def _vectors_for(records: list[dict[str, Any]], vectors: dict[str, np.ndarray]) -> np.ndarray:
    size = next((len(value) for value in vectors.values()), 1024)
    result = np.zeros((len(records), size), dtype=np.float32)
    key = "document_id" if records and "document_search_text" in records[0] else "section_id"
    for index, record in enumerate(records):
        vector = vectors.get(str(record[key]))
        if vector is not None:
            result[index] = vector
    return result


def _section_vectors_for(
    records: list[dict[str, Any]],
    direct_vectors: dict[str, np.ndarray],
    document_vectors: dict[str, np.ndarray],
) -> tuple[np.ndarray, dict[str, Any]]:
    size = next((len(value) for value in direct_vectors.values()), next((len(value) for value in document_vectors.values()), 1024))
    result = np.zeros((len(records), size), dtype=np.float32)
    excluded: dict[str, int] = defaultdict(int)
    direct = fallback = missing = eligible = eligible_covered = 0
    for index, record in enumerate(records):
        is_eligible, reason = _section_dense_eligible(record)
        if is_eligible:
            eligible += 1
        else:
            excluded[reason] += 1
        vector = direct_vectors.get(str(record["section_id"]))
        if vector is not None:
            result[index] = vector
            record["dense_vector_source"] = "SECTION_DIRECT"
            direct += 1
        else:
            vector = document_vectors.get(str(record["document_id"]))
            if vector is not None:
                result[index] = vector
                record["dense_vector_source"] = "PARENT_DOCUMENT_FALLBACK"
                fallback += 1
            else:
                record["dense_vector_source"] = "MISSING"
                missing += 1
        record["dense_eligible"] = is_eligible
        record["dense_exclusion_reason"] = reason
        if is_eligible and record["dense_vector_source"] != "MISSING":
            eligible_covered += 1
    return result, {
        "total_sections": len(records),
        "eligible_sections": eligible,
        "dense_indexed_sections": direct,
        "parent_document_fallback_sections": fallback,
        "missing_dense_sections": missing,
        "excluded_sections": len(records) - eligible,
        "exclusion_reason": dict(sorted(excluded.items())),
        "eligible_dense_covered_sections": eligible_covered,
        "eligible_dense_coverage": round(eligible_covered / max(1, eligible), 4),
        "direct_dense_coverage_all_sections": round(direct / max(1, len(records)), 4),
    }


def _section_dense_eligible(record: dict[str, Any]) -> tuple[bool, str | None]:
    text = " ".join(str(record.get("section_content_text") or "").split())
    if not text:
        return False, "EMPTY_OR_STRUCTURAL_SECTION"
    if len(text) < 8:
        return False, "SHORT_STRUCTURAL_SECTION"
    return True, None


def _document_type_facets(document: dict[str, Any], sections: list[dict[str, Any]]) -> list[str]:
    text = " ".join([
        str(document.get("file_name") or ""),
        " ".join(str(section.get("heading_path") or "") for section in sections),
        " ".join(str(section.get("section_content_text") or "") for section in sections),
    ])
    facets = [str(document.get("document_type") or "OTHER")]
    for document_type, terms in (
        ("DESIGN_TASK_BOOK", ("设计任务书", "施工图设计任务书")),
        ("RESPONSIBILITY_CONTRACT", ("责任状", "责任书")),
        ("TABLE_LEDGER", ("台账", "清单", "统计表")),
        ("WORK_PLAN", ("工作计划",)),
        ("MANAGEMENT_GUIDE", ("管理手册", "管理指南", "设计管理手册")),
    ):
        if any(term in text for term in terms):
            facets.append(document_type)
    return list(dict.fromkeys(facets))


def _bm25(records: list[dict[str, Any]], id_key: str, text_key: str) -> BM25Index:
    index = BM25Index(Path("unused.json"))
    index.build([Chunk(chunk_id=str(record[id_key]), document_id=str(record.get("document_id") or record[id_key]), ordinal=ordinal, source_path=str(record.get("source_path") or ""), file_name=str(record.get("file_name") or ""), text=str(record.get(text_key) or ""), heading_path=str(record.get("heading_path") or ""), location=dict(record.get("location") or {})) for ordinal, record in enumerate(records)])
    return index


def _save_bm25(index: BM25Index, path: Path) -> None:
    index.path = path
    index.save()


def _dense_pairs(records: list[dict[str, Any]], vectors: np.ndarray, query_vector: list[float], allowed_ids: set[str], id_key: str) -> list[tuple[str, float]]:
    query = np.asarray(query_vector, dtype=np.float32)
    if not query.size or not vectors.size:
        return []
    scores = vectors @ query
    candidates = [(str(record[id_key]), float(scores[index])) for index, record in enumerate(records) if str(record[id_key]) in allowed_ids and float(scores[index]) > 0]
    candidates.sort(key=lambda item: (-item[1], item[0]))
    return candidates


def _bm25_pairs(
    records: list[dict[str, Any]],
    bm25: BM25Index,
    id_key: str,
    text_key: str,
    question: str,
    allowed_ids: set[str],
) -> list[tuple[str, float]]:
    pairs = [(item_id, score) for item_id, score in bm25.search(question, limit=len(records)) if item_id in allowed_ids]
    if pairs or not allowed_ids:
        return pairs
    # ponytail: rank_bm25 can emit no positive score for a one-record index; lexical overlap keeps the candidate visible.
    terms = set(tokenize(question))
    return sorted(
        ((str(record[id_key]), float(sum(term in str(record.get(text_key) or "") for term in terms))) for record in records if str(record[id_key]) in allowed_ids),
        key=lambda item: (-item[1], item[0]),
    )


def _collapse_section_pairs(pairs: list[tuple[str, float]], section_by_id: dict[str, dict[str, Any]]) -> list[tuple[str, float]]:
    best: dict[str, float] = {}
    for section_id, score in pairs:
        section = section_by_id.get(str(section_id))
        if section is None:
            continue
        document_id = str(section["document_id"])
        if document_id not in best or score > best[document_id]:
            best[document_id] = score
    return sorted(best.items(), key=lambda item: (-item[1], item[0]))


def _rank_map(pairs: list[tuple[str, float]]) -> dict[str, int]:
    return {item_id: rank for rank, (item_id, _) in enumerate(pairs, start=1)}


def _soft_boost(record: dict[str, Any], plan: QueryPlan) -> tuple[float, dict[str, Any]]:
    searchable = json.dumps(record, ensure_ascii=False).casefold()
    metadata_match = []
    score = 0.0
    for field, values, weight in (
        ("organization", plan.organization, 0.06),
        ("project", plan.project, 0.10),
        ("year", plan.year, 0.05),
        ("specialty", plan.specialty, 0.04),
        ("metric", plan.metric, 0.03),
    ):
        matched = [value for value in values if value.casefold() in searchable]
        if matched:
            score += weight * len(matched)
            metadata_match.append({"field": field, "values": matched, "boost": weight * len(matched)})
    document_types = {str(record.get("document_type") or "")}
    document_types.update(str(value) for value in record.get("document_type_facets", []))
    matched_document_types = [value for value in plan.document_type_hint if value in document_types]
    if matched_document_types:
        score += 0.04
        metadata_match.append({"field": "document_type", "values": matched_document_types, "boost": 0.04})
    if record.get("document_role") in plan.document_role_hint:
        score += 0.03
        metadata_match.append({"field": "document_role", "values": [record.get("document_role")], "boost": 0.03})
    if record.get("document_type") == "REGISTER_PAGE":
        score -= 0.12
        metadata_match.append({"field": "registration_page_penalty", "values": ["REGISTER_PAGE"], "boost": -0.12})
    if plan.authority_requirement != "ANY" and metadata_match:
        authority = {"L1": 0.06, "L2": 0.05, "L3": 0.025}.get(str(record.get("authority_level")), 0.0)
        score += authority
        if authority:
            metadata_match.append({"field": "authority_same_scope", "values": [record.get("authority_level")], "boost": authority})
    return score, {"metadata_match": metadata_match, "soft_only": True}


def _merge_section_candidates(local: list[dict[str, Any]], global_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {item["section_id"]: dict(item) for item in local}
    for item in global_candidates:
        current = merged.get(item["section_id"])
        if current is None:
            merged[item["section_id"]] = dict(item)
        else:
            current["candidate_origin"] = "HIERARCHICAL"
            current["global_rescue_rank"] = item["rank"]
    result = sorted(merged.values(), key=lambda item: (item["rank"], item["section_id"]))
    for rank, item in enumerate(result, start=1):
        item["global_rank"] = rank
        item["local_rank"] = item["rank"] if item["candidate_origin"] == "HIERARCHICAL" else None
    return result


def _merge_table_parent_sections(sections: list[dict[str, Any]], tables: list[dict[str, Any]], section_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {item["section_id"]: dict(item) for item in sections}
    for table in tables[:10]:
        parent_id = (table.get("record") or {}).get("section_id")
        parent = section_by_id.get(parent_id)
        if parent is None:
            continue
        current = merged.get(parent_id)
        if current is not None:
            current["table_parent_rank"] = table["rank"]
            current["rank"] = min(current.get("rank", table["rank"]), table["rank"])
            current["local_rank"] = current["rank"]
            continue
        merged[parent_id] = {
            "section_id": parent_id,
            "document_id": parent["document_id"],
            "source_path": parent["source_path"],
            "file_name": parent["file_name"],
            "heading": parent.get("heading"),
            "heading_path": parent.get("heading_path"),
            "location": parent.get("location"),
            "bm25_rank": None,
            "bm25_score": None,
            "dense_rank": None,
            "dense_score": None,
            "rrf_score": 0.0,
            "planner_boost": 0.0,
            "planner_match": {"metadata_match": [{"field": "table_parent", "values": [table["table_id"]], "boost": 0.0}], "soft_only": True},
            "metadata_match": [{"field": "table_parent", "values": [table["table_id"]], "boost": 0.0}],
            "document_type": parent.get("document_type"),
            "document_role": parent.get("document_role"),
            "authority": parent.get("authority_level"),
            "scope": parent.get("scope"),
            "lineage_status": parent.get("lineage_status"),
            "candidate_origin": "HIERARCHICAL",
            "record": parent,
            "rank": table["rank"],
            "local_rank": table["rank"],
            "table_parent_rank": table["rank"],
        }
    result = sorted(merged.values(), key=lambda item: (item.get("rank", 10**9), item["section_id"]))
    for rank, item in enumerate(result, start=1):
        item["global_rank"] = rank
    return result


def _lineage_for_record(record: dict[str, Any]) -> str:
    return str(record.get("lineage_status") or "LINEAGE_NOT_APPLICABLE")


def _frozen_document_type(file_name: str, samples: list[str]) -> str:
    text = f"{file_name} {' '.join(samples[:2])}"
    for document_type, terms in (
        ("RESPONSIBILITY_CONTRACT", ("责任书", "责任状")),
        ("DESIGN_TASK_BOOK", ("任务书",)),
        ("TABLE_LEDGER", ("台账", "清单", "统计表")),
        ("WORK_PLAN", ("工作计划",)),
        ("MANAGEMENT_GUIDE", ("手册", "指南", "规范")),
        ("PROJECT_PLAN", ("策划", "方案")),
    ):
        if any(term in text for term in terms):
            return document_type
    return "OTHER"


def _group(rows: Iterable[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[str(row[field])].append(row)
    return result


def _join(values: Iterable[Any]) -> str:
    flattened = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            flattened.extend(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            flattened.append(str(value))
    return " ".join(flattened)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
