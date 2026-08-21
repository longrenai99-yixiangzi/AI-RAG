from __future__ import annotations

import json
import sqlite3
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
        return {
            "documents": document_count,
            "chunks": chunk_count,
            "ocr_pending": ocr_count,
            "file_types": file_types,
            "parse_status": statuses,
        }
