from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .domain import Chunk, ParsedDocument


class IndexDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _open(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._open() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL UNIQUE,
                    file_name TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    parse_status TEXT NOT NULL,
                    index_status TEXT NOT NULL,
                    error TEXT,
                    board TEXT,
                    knowledge_type TEXT,
                    discipline TEXT,
                    building_type TEXT,
                    project_stage TEXT,
                    topic TEXT,
                    document_level TEXT,
                    source_organization TEXT,
                    publish_date TEXT,
                    project_name TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    needs_ocr INTEGER NOT NULL DEFAULT 0,
                    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    source_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    heading_path TEXT NOT NULL,
                    location_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(document_id) REFERENCES documents(document_id)
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS query_logs (
                    query_id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    analysis_json TEXT NOT NULL DEFAULT '{}',
                    retrieval_count INTEGER NOT NULL DEFAULT 0,
                    answer_status TEXT NOT NULL,
                    confidence REAL,
                    answer TEXT,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_query_logs_created_at ON query_logs(created_at);
                CREATE TABLE IF NOT EXISTS knowledge_gaps (
                    gap_id TEXT PRIMARY KEY,
                    normalized_topic TEXT NOT NULL UNIQUE,
                    latest_query TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    frequency INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    candidate_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_status ON knowledge_gaps(status);
                CREATE TABLE IF NOT EXISTS growth_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    gap_id TEXT NOT NULL UNIQUE,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(gap_id) REFERENCES knowledge_gaps(gap_id)
                );
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL UNIQUE,
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    description TEXT NOT NULL DEFAULT '',
                    source_document_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS facts (
                    fact_id TEXT PRIMARY KEY,
                    subject_entity_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_text TEXT NOT NULL,
                    object_entity_id TEXT,
                    evidence_chunk_id TEXT NOT NULL,
                    confidence REAL,
                    review_status TEXT NOT NULL DEFAULT 'AUTO',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(subject_entity_id) REFERENCES entities(entity_id),
                    FOREIGN KEY(evidence_chunk_id) REFERENCES chunks(chunk_id)
                );
                CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_entity_id);
                CREATE INDEX IF NOT EXISTS idx_facts_evidence ON facts(evidence_chunk_id);
                CREATE TABLE IF NOT EXISTS relationships (
                    relationship_id TEXT PRIMARY KEY,
                    subject_entity_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_entity_id TEXT NOT NULL,
                    evidence_chunk_id TEXT NOT NULL,
                    confidence REAL,
                    review_status TEXT NOT NULL DEFAULT 'AUTO',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._ensure_columns(connection, "documents", {
                "board": "TEXT",
                "knowledge_type": "TEXT",
                "discipline": "TEXT",
                "building_type": "TEXT",
                "project_stage": "TEXT",
                "topic": "TEXT",
                "document_level": "TEXT",
                "source_organization": "TEXT",
                "publish_date": "TEXT",
                "project_name": "TEXT",
                "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
                "needs_ocr": "INTEGER NOT NULL DEFAULT 0",
            })
            self._ensure_columns(connection, "chunks", {"metadata_json": "TEXT NOT NULL DEFAULT '{}'"})

    @staticmethod
    def _ensure_columns(
        connection: sqlite3.Connection, table: str, columns: dict[str, str]
    ) -> None:
        existing = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def reset(self) -> None:
        with self._open() as connection:
            connection.execute("DELETE FROM facts")
            connection.execute("DELETE FROM relationships")
            connection.execute("DELETE FROM entities")
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")

    def store_document(self, document: ParsedDocument, chunks: list[Chunk]) -> None:
        with self._open() as connection:
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document.document_id,))
            metadata = document.metadata or {}
            connection.execute(
                """
                INSERT OR REPLACE INTO documents (
                    document_id, source_path, file_name, file_type, file_size, mtime_ns,
                    sha256, parse_status, index_status, error, board, knowledge_type,
                    discipline, building_type, project_stage, topic, document_level,
                    source_organization, publish_date, project_name, metadata_json, needs_ocr
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    document.document_id,
                    document.source_path,
                    document.file_name,
                    document.file_type,
                    document.file_size,
                    document.mtime_ns,
                    document.sha256,
                    document.parse_status,
                    "indexed" if chunks else "skipped",
                    document.error,
                    metadata.get("board"),
                    metadata.get("knowledge_type"),
                    metadata.get("discipline"),
                    metadata.get("building_type"),
                    metadata.get("project_stage"),
                    json.dumps(metadata.get("topic") or [], ensure_ascii=False),
                    metadata.get("document_level"),
                    metadata.get("source_organization"),
                    metadata.get("publish_date"),
                    metadata.get("project_name"),
                    json.dumps(metadata, ensure_ascii=False),
                    int(document.needs_ocr),
                ),
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO chunks (
                    chunk_id, document_id, ordinal, source_path, file_name,
                    text, heading_path, location_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.ordinal,
                        chunk.source_path,
                        chunk.file_name,
                        chunk.text,
                        chunk.heading_path,
                        json.dumps(chunk.location, ensure_ascii=False),
                        json.dumps(chunk.metadata, ensure_ascii=False),
                    )
                    for chunk in chunks
                ],
            )

    def get_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._open() as connection:
            rows = connection.execute(
                f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})", chunk_ids
            ).fetchall()
        by_id = {
            row["chunk_id"]: Chunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                ordinal=row["ordinal"],
                source_path=row["source_path"],
                file_name=row["file_name"],
                text=row["text"],
                heading_path=row["heading_path"],
                location=json.loads(row["location_json"]),
                metadata=json.loads(row["metadata_json"] or "{}"),
            )
            for row in rows
        }
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]

    def find_chunk_ids(
        self,
        *,
        source_terms: list[str] | None = None,
        text_terms: list[str] | None = None,
    ) -> list[str]:
        """Return deterministic evidence candidates for a routed question."""
        source_terms = [term for term in (source_terms or []) if term]
        text_terms = [term for term in (text_terms or []) if term]
        clauses: list[str] = []
        parameters: list[str] = []
        if source_terms:
            clauses.append("(" + " OR ".join("source_path LIKE ?" for _ in source_terms) + ")")
            parameters.extend(f"%{term}%" for term in source_terms)
        if text_terms:
            clauses.append("(" + " OR ".join("text LIKE ?" for _ in text_terms) + ")")
            parameters.extend(f"%{term}%" for term in text_terms)
        if not clauses:
            return []
        query = "SELECT chunk_id FROM chunks WHERE " + " AND ".join(clauses)
        with self._open() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [str(row[0]) for row in rows]

    def document_fingerprints(self) -> dict[str, dict[str, Any]]:
        with self._open() as connection:
            rows = connection.execute(
                "SELECT source_path, file_size, mtime_ns, sha256, parse_status FROM documents"
            ).fetchall()
        return {str(row["source_path"]).casefold(): dict(row) for row in rows}

    def chunk_ids_for_metadata(self, filters: dict[str, Any]) -> set[str]:
        if not filters:
            return set()
        # ponytail: O(n) JSON scan is sufficient below the 18k local-chunk guard;
        # add normalized metadata columns or an FTS/JSON index if that ceiling moves.
        with self._open() as connection:
            rows = connection.execute("SELECT chunk_id, metadata_json FROM chunks").fetchall()
        result: set[str] = set()
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                continue
            if all(self._metadata_matches(metadata, key, value) for key, value in filters.items()):
                result.add(str(row["chunk_id"]))
        return result

    @staticmethod
    def _metadata_matches(metadata: dict[str, Any], key: str, expected: Any) -> bool:
        actual = metadata.get(key)
        expected_values = expected if isinstance(expected, list) else [expected]
        actual_values = actual if isinstance(actual, list) else [actual]
        return any(value and value in expected_values for value in actual_values)

    def record_query(
        self,
        *,
        query: str,
        analysis: dict[str, Any],
        retrieval_count: int,
        answer_status: str,
        answer: str | None,
        citations: list[dict[str, Any]],
        confidence: float | None,
        normalized_topic: str | None = None,
        gap_reason: str | None = None,
    ) -> dict[str, Any]:
        query_id = str(uuid.uuid4())
        gap: dict[str, Any] | None = None
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO query_logs (
                    query_id, query, intent, analysis_json, retrieval_count,
                    answer_status, confidence, answer, citations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query_id,
                    query,
                    str(analysis.get("intent", "GENERAL_RAG")),
                    json.dumps(analysis, ensure_ascii=False),
                    retrieval_count,
                    answer_status,
                    confidence,
                    answer,
                    json.dumps(citations, ensure_ascii=False),
                ),
            )
            if normalized_topic and gap_reason:
                row = connection.execute(
                    "SELECT * FROM knowledge_gaps WHERE normalized_topic = ?",
                    (normalized_topic,),
                ).fetchone()
                if row:
                    connection.execute(
                        """
                        UPDATE knowledge_gaps
                        SET latest_query = ?, reason = ?, frequency = frequency + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE gap_id = ?
                        """,
                        (query, gap_reason, row["gap_id"]),
                    )
                    gap_id = row["gap_id"]
                else:
                    gap_id = str(uuid.uuid4())
                    connection.execute(
                        """
                        INSERT INTO knowledge_gaps (
                            gap_id, normalized_topic, latest_query, reason
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (gap_id, normalized_topic, query, gap_reason),
                    )
                gap_row = connection.execute(
                    "SELECT * FROM knowledge_gaps WHERE normalized_topic = ?",
                    (normalized_topic,),
                ).fetchone()
                gap = dict(gap_row) if gap_row else {"gap_id": gap_id}
        return {"query_id": query_id, "gap": gap}

    def attach_growth_candidate(self, gap_id: str, path: str) -> dict[str, Any]:
        candidate_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"knowledge-gap:{gap_id}"))
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO growth_candidates (candidate_id, gap_id, path)
                VALUES (?, ?, ?)
                ON CONFLICT(gap_id) DO UPDATE SET path = excluded.path,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (candidate_id, gap_id, path),
            )
            connection.execute(
                """
                UPDATE knowledge_gaps
                SET candidate_count = 1, updated_at = CURRENT_TIMESTAMP
                WHERE gap_id = ?
                """,
                (gap_id,),
            )
            row = connection.execute(
                "SELECT * FROM growth_candidates WHERE gap_id = ?", (gap_id,)
            ).fetchone()
        return dict(row) if row else {"candidate_id": candidate_id, "gap_id": gap_id, "path": path}

    def store_knowledge_graph(
        self,
        entities: list[dict[str, Any]],
        facts: list[dict[str, Any]],
    ) -> None:
        if not entities and not facts:
            return
        with self._open() as connection:
            for entity in entities:
                connection.execute(
                    """
                    INSERT INTO entities (
                        entity_id, entity_type, canonical_name, aliases_json,
                        description, source_document_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(entity_id) DO UPDATE SET
                        canonical_name = excluded.canonical_name,
                        aliases_json = excluded.aliases_json,
                        description = excluded.description,
                        source_document_id = excluded.source_document_id,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        entity["entity_id"],
                        entity.get("entity_type", "ENTITY"),
                        entity["canonical_name"],
                        json.dumps(entity.get("aliases", []), ensure_ascii=False),
                        entity.get("description", ""),
                        entity.get("source_document_id"),
                    ),
                )
            for fact in facts:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO facts (
                        fact_id, subject_entity_id, predicate, object_text,
                        object_entity_id, evidence_chunk_id, confidence, review_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact["fact_id"],
                        fact["subject_entity_id"],
                        fact["predicate"],
                        fact["object_text"],
                        fact.get("object_entity_id"),
                        fact["evidence_chunk_id"],
                        fact.get("confidence"),
                        fact.get("review_status", "AUTO"),
                    ),
                )
            connection.execute(
                "DELETE FROM facts WHERE evidence_chunk_id NOT IN (SELECT chunk_id FROM chunks)"
            )
            connection.execute(
                """
                UPDATE facts
                SET review_status = 'CONFLICT', updated_at = CURRENT_TIMESTAMP
                WHERE (subject_entity_id, predicate) IN (
                    SELECT subject_entity_id, predicate
                    FROM facts
                    GROUP BY subject_entity_id, predicate
                    HAVING COUNT(DISTINCT object_text) > 1
                )
                """
            )

    def lookup_facts(self, question: str) -> list[dict[str, Any]]:
        folded = question.casefold()
        with self._open() as connection:
            rows = connection.execute(
                """
                SELECT f.*, e.canonical_name, e.aliases_json
                FROM facts f JOIN entities e ON e.entity_id = f.subject_entity_id
                ORDER BY f.updated_at DESC
                """
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            aliases = json.loads(row["aliases_json"] or "[]")
            names = [row["canonical_name"], *aliases]
            if not any(str(name).casefold() in folded for name in names if name):
                continue
            item = dict(row)
            item["aliases"] = aliases
            item.pop("aliases_json", None)
            results.append(item)
        return results

    def fact_conflicts(self) -> list[dict[str, Any]]:
        with self._open() as connection:
            groups = connection.execute(
                """
                SELECT f.subject_entity_id, f.predicate, e.canonical_name,
                       COUNT(DISTINCT f.object_text) AS value_count
                FROM facts f JOIN entities e ON e.entity_id = f.subject_entity_id
                GROUP BY f.subject_entity_id, f.predicate
                HAVING COUNT(DISTINCT f.object_text) > 1
                ORDER BY e.canonical_name, f.predicate
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for group in groups:
                facts = connection.execute(
                    """
                    SELECT fact_id, object_text, evidence_chunk_id, confidence, review_status
                    FROM facts WHERE subject_entity_id = ? AND predicate = ?
                    ORDER BY updated_at DESC
                    """,
                    (group["subject_entity_id"], group["predicate"]),
                ).fetchall()
                result.append({**dict(group), "facts": [dict(row) for row in facts]})
        return result

    def get_growth_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self._open() as connection:
            row = connection.execute(
                """
                SELECT g.*, c.candidate_id, c.path AS candidate_path, c.status AS candidate_status
                FROM growth_candidates c JOIN knowledge_gaps g ON g.gap_id = c.gap_id
                WHERE c.candidate_id = ?
                """,
                (candidate_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_candidate_status(self, candidate_id: str, status: str) -> dict[str, Any] | None:
        with self._open() as connection:
            connection.execute(
                "UPDATE growth_candidates SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE candidate_id = ?",
                (status, candidate_id),
            )
            row = connection.execute(
                "SELECT * FROM growth_candidates WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_gap_status(self, gap_id: str, status: str) -> dict[str, Any] | None:
        allowed = {"OPEN", "REVIEWING", "RESOLVED", "IGNORED"}
        if status not in allowed:
            raise ValueError(f"不支持的知识缺口状态：{status}")
        with self._open() as connection:
            connection.execute(
                "UPDATE knowledge_gaps SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE gap_id = ?",
                (status, gap_id),
            )
            connection.execute(
                "UPDATE growth_candidates SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE gap_id = ?",
                ("RESOLVED" if status == "RESOLVED" else "PENDING_REVIEW", gap_id),
            )
            row = connection.execute(
                """
                SELECT g.*, c.candidate_id, c.path AS candidate_path, c.status AS candidate_status
                FROM knowledge_gaps g LEFT JOIN growth_candidates c ON c.gap_id = g.gap_id
                WHERE g.gap_id = ?
                """,
                (gap_id,),
            ).fetchone()
        return dict(row) if row else None

    def growth_snapshot(self, limit: int = 50) -> dict[str, Any]:
        with self._open() as connection:
            gaps = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT g.*, c.candidate_id, c.path AS candidate_path, c.status AS candidate_status
                    FROM knowledge_gaps g LEFT JOIN growth_candidates c ON c.gap_id = g.gap_id
                    ORDER BY g.updated_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            ]
            logs = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM query_logs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
            counts = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS count FROM knowledge_gaps GROUP BY status"
                ).fetchall()
            }
        for row in gaps + logs:
            for key in ("analysis_json", "citations_json"):
                if key in row:
                    try:
                        row[key.removesuffix("_json")] = json.loads(row.pop(key) or "{}")
                    except json.JSONDecodeError:
                        row[key.removesuffix("_json")] = {}
        return {"stats": counts, "gaps": gaps, "query_logs": logs}

    def list_documents(
        self,
        query: str = "",
        limit: int = 200,
        *,
        board: str | None = None,
        knowledge_type: str | None = None,
        building_type: str | None = None,
        project_stage: str | None = None,
        document_level: str | None = None,
    ) -> list[dict[str, Any]]:
        pattern = f"%{query.strip()}%"
        with self._open() as connection:
            rows = connection.execute(
                """
                SELECT document_id, source_path, file_name, file_type, file_size,
                       mtime_ns, parse_status, index_status, error, needs_ocr,
                       metadata_json, indexed_at
                FROM documents
                WHERE (? = '' OR file_name LIKE ? OR source_path LIKE ?)
                  AND (? IS NULL OR board = ?)
                  AND (? IS NULL OR knowledge_type = ?)
                  AND (? IS NULL OR building_type = ?)
                  AND (? IS NULL OR project_stage = ?)
                  AND (? IS NULL OR document_level = ?)
                ORDER BY mtime_ns DESC LIMIT ?
                """,
                (
                    query.strip(), pattern, pattern,
                    board, board,
                    knowledge_type, knowledge_type,
                    building_type, building_type,
                    project_stage, project_stage,
                    document_level, document_level,
                    limit,
                ),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            except json.JSONDecodeError:
                item["metadata"] = {}
            result.append(item)
        return result

    def stats(self) -> dict[str, Any]:
        with self._open() as connection:
            document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            ocr_count = connection.execute(
                "SELECT COUNT(*) FROM documents WHERE needs_ocr = 1 OR parse_status = 'needs_ocr'"
            ).fetchone()[0]
            file_types = {
                str(row["file_type"]): int(row["count"])
                for row in connection.execute(
                    "SELECT file_type, COUNT(*) AS count FROM documents GROUP BY file_type"
                ).fetchall()
            }
            statuses = {
                str(row["parse_status"]): int(row["count"])
                for row in connection.execute(
                    "SELECT parse_status, COUNT(*) AS count FROM documents GROUP BY parse_status"
                ).fetchall()
            }
            entity_count = connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            fact_count = connection.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            conflict_count = connection.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT subject_entity_id, predicate FROM facts
                    GROUP BY subject_entity_id, predicate
                    HAVING COUNT(DISTINCT object_text) > 1
                )
                """
            ).fetchone()[0]
        return {
            "documents": document_count,
            "chunks": chunk_count,
            "ocr_pending": ocr_count,
            "file_types": file_types,
            "parse_status": statuses,
            "entities": entity_count,
            "facts": fact_count,
            "fact_conflicts": conflict_count,
        }
