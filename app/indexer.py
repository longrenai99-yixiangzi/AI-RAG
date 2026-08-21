from __future__ import annotations

import json
import os
import shutil
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from .bm25 import BM25Index
from .chunker import chunk_blocks
from .config import Settings
from .database import IndexDatabase
from .domain import Chunk, ParsedDocument
from .embeddings import EmbeddingService
from .index_state import detect_changes
from .knowledge_graph import extract_entity_facts
from .metadata import METADATA_FIELDS, infer_metadata, metadata_for_block
from .ocr import build_ocr_provider
from .parsers import iter_source_files, parse_file
from .vector_store import VectorStore


def _write_report(settings: Settings, report: dict[str, object]) -> Path:
    settings.report_root.mkdir(parents=True, exist_ok=True)
    name = f"index-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path = settings.report_root / name
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _publish_staged_index(settings: Settings, staging_root: Path) -> Path | None:
    """Publish a fully verified index while retaining any old index as a rollback backup."""
    backup_root = settings.data_root / f"backup-index-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    failed_root = settings.data_root / f"failed-publish-{uuid.uuid4().hex}"
    artifacts = [
        (staging_root / "qdrant", settings.qdrant_path, "qdrant"),
        (staging_root / "index.sqlite3", settings.database_path, "index.sqlite3"),
        (staging_root / "bm25.json", settings.bm25_path, "bm25.json"),
    ]
    old_artifacts: list[tuple[Path, Path]] = []
    try:
        for _, destination, name in artifacts:
            if destination.exists():
                backup_root.mkdir(parents=True, exist_ok=True)
                backup = backup_root / name
                shutil.move(str(destination), str(backup))
                old_artifacts.append((destination, backup))
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{settings.database_path}{suffix}")
            if sidecar.exists():
                backup_root.mkdir(parents=True, exist_ok=True)
                backup = backup_root / sidecar.name
                shutil.move(str(sidecar), str(backup))
                old_artifacts.append((sidecar, backup))
        for source, destination, _ in artifacts:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
    except Exception:
        # Preserve any newly published artifact and restore the complete old set.
        for source, destination, name in artifacts:
            if not source.exists() and destination.exists():
                failed_root.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(failed_root / name))
        for destination, backup in old_artifacts:
            if backup.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup), str(destination))
        raise
    return backup_root if old_artifacts else None


def index_vault(
    settings: Settings,
    embedding_service: EmbeddingService,
    *,
    limit: int | None = None,
    preflight: bool = False,
    file_paths: list[Path] | None = None,
    source_aliases: dict[str, str] | None = None,
    file_size_overrides: dict[str, int] | None = None,
) -> dict[str, object]:
    """Build in a staging directory, verify it, then publish it as the active local index."""
    settings.ensure_runtime_directories()
    if not settings.vault_root.is_dir():
        raise FileNotFoundError(f"知识源目录不存在：{settings.vault_root}")

    scan_errors: list[str] = []
    files = file_paths if file_paths is not None else iter_source_files(settings.vault_root, scan_errors=scan_errors)
    if limit is not None:
        files = files[:limit]
    try:
        previous = IndexDatabase(settings.database_path).document_fingerprints()
    except Exception:
        previous = {}
    change_status, _ = detect_changes(files, previous)
    ocr_provider = build_ocr_provider(settings.ocr_provider)
    documents: list[ParsedDocument] = []
    chunks_by_document: dict[str, list[Chunk]] = {}
    all_chunks: list[Chunk] = []
    entities: list[dict[str, object]] = []
    facts: list[dict[str, object]] = []
    statuses: Counter[str] = Counter()
    file_types: Counter[str] = Counter()
    errors: list[dict[str, str]] = []

    for path in files:
        size_limit = (file_size_overrides or {}).get(str(path), settings.max_file_size_mb)
        document = parse_file(path, size_limit, ocr_provider)
        alias = (source_aliases or {}).get(str(path))
        if alias:
            document.source_path = alias
            document.file_name = Path(alias).name
            document.file_type = Path(alias).suffix.lower()
            for block in document.blocks:
                block.source_path = alias
                block.file_name = Path(alias).name
        extracted_text = "\n".join(block.text for block in document.blocks)
        document.metadata = infer_metadata(
            path,
            extracted_text,
            settings.metadata_rules_path,
        )
        for block in document.blocks:
            block.metadata = metadata_for_block(document.metadata)
        document_chunks = chunk_blocks(document.blocks) if document.parse_status == "parsed" else []
        document_entities, document_facts = extract_entity_facts(document, document_chunks)
        entities.extend(document_entities)
        facts.extend(document_facts)
        documents.append(document)
        chunks_by_document[document.document_id] = document_chunks
        all_chunks.extend(document_chunks)
        statuses[document.parse_status] += 1
        file_types[document.file_type] += 1
        if document.error:
            errors.append({"path": document.source_path, "error": document.error})

    report: dict[str, object] = {
        "vault": str(settings.vault_root),
        "source_files": len(files),
        "file_types": dict(file_types),
        "parse_status": dict(statuses),
        "chunks": len(all_chunks),
        "max_local_chunks": settings.max_local_chunks,
        "errors": errors,
        "scan_errors": scan_errors,
        "rebuild": True,
        "change_status": dict(Counter(change_status.values())),
        "ocr_provider": ocr_provider.name,
        "ocr_pending": sum(1 for document in documents if document.needs_ocr),
        "metadata_coverage": {
            field: sum(
                bool(document.metadata.get(field))
                for document in documents
            )
            for field in METADATA_FIELDS
        },
        "entities": len(entities),
        "facts": len(facts),
    }
    if len(all_chunks) > settings.max_local_chunks:
        report["status"] = "blocked_requires_qdrant_server"
        report["reason"] = (
            "切片数量超过 Qdrant Local 的安全上限。请改用单独的 Qdrant Server，"
            "不要在 Local 模式继续索引。"
        )
        report["report_path"] = str(_write_report(settings, report))
        return report
    if not all_chunks:
        report["status"] = "blocked_no_extractable_text"
        report["reason"] = "未提取到可索引文本；已保留原有索引，未发布空索引。"
        report["report_path"] = str(_write_report(settings, report))
        return report
    if preflight:
        report["status"] = "preflight_completed"
        report["would_index_documents"] = sum(
            1 for document in documents if chunks_by_document[document.document_id]
        )
        report["report_path"] = str(_write_report(settings, report))
        return report

    # A model or download failure must not clear an existing usable index.
    try:
        embedding_service.load()
    except Exception as error:
        report["status"] = "model_load_failed"
        report["model_error"] = f"{type(error).__name__}: {error}"
        report["report_path"] = str(_write_report(settings, report))
        raise
    staging_root = settings.data_root / f".build-{uuid.uuid4().hex}"
    staging_root.mkdir(parents=True, exist_ok=False)
    database = IndexDatabase(staging_root / "index.sqlite3")
    vector_store = VectorStore(staging_root / "qdrant")
    build_error: Exception | None = None
    try:
        for start in range(0, len(all_chunks), 8):
            batch = all_chunks[start : start + 8]
            vectors = embedding_service.embed_documents([chunk.text for chunk in batch])
            vector_store.upsert(batch, vectors)
        for document in documents:
            database.store_document(document, chunks_by_document[document.document_id])
        database.store_knowledge_graph(entities, facts)
        bm25 = BM25Index(staging_root / "bm25.json")
        bm25.build(all_chunks)
        bm25.save()
        if (
            vector_store.count() != len(all_chunks)
            or database.stats()["chunks"] != len(all_chunks)
            or (all_chunks and not bm25.ready)
        ):
            raise RuntimeError("临时索引校验失败，未发布任何新索引。")
        report["status"] = "completed"
        report["indexed_documents"] = sum(
            1 for document in documents if chunks_by_document[document.document_id]
        )
        report["vector_points"] = vector_store.count()
        report["entities"] = len(entities)
        report["facts"] = len(facts)
    except Exception as error:
        report["status"] = "build_failed"
        report["build_error"] = f"{type(error).__name__}: {error}"
        report["report_path"] = str(_write_report(settings, report))
        build_error = error
    finally:
        vector_store.close()
    if build_error is not None:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise build_error
    try:
        backup_root = _publish_staged_index(settings, staging_root)
        if backup_root:
            report["previous_index_backup"] = str(backup_root)
    except Exception as error:
        report["status"] = "publish_failed"
        report["publish_error"] = f"{type(error).__name__}: {error}"
        report["report_path"] = str(_write_report(settings, report))
        raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
    report["report_path"] = str(_write_report(settings, report))
    return report
