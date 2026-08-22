from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

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
                    FOREIGN KEY(document_id) REFERENCES documents(document_id)
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
                """
            )

    def reset(self) -> None:
        with self._open() as connection:
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")

    def store_document(self, document: ParsedDocument, chunks: list[Chunk]) -> None:
        with self._open() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO documents (
                    document_id, source_path, file_name, file_type, file_size, mtime_ns,
                    sha256, parse_status, index_status, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO chunks (
                    chunk_id, document_id, ordinal, source_path, file_name,
                    text, heading_path, location_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            )
            for row in rows
        }
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]

    def stats(self) -> dict[str, int]:
        with self._open() as connection:
            document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"documents": document_count, "chunks": chunk_count}
