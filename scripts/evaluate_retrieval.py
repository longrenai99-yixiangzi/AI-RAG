from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bm25 import BM25Index
from app.config import Settings
from app.database import IndexDatabase
from app.embeddings import EmbeddingService, RerankerService
from app.retriever import Retriever
from app.vector_store import VectorStore


def _contains_expected(value: str, expected: list[str]) -> bool:
    folded = value.casefold()
    return not expected or any(item.casefold() in folded for item in expected)


def _expected_file_hit(hits: list[Any], expected: list[str], limit: int) -> bool:
    if not expected:
        return False
    for hit in hits[:limit]:
        haystack = f"{hit.chunk.file_name}\n{hit.chunk.source_path}"
        if _contains_expected(haystack, expected):
            return True
    return False


def _expected_chunk_file_hit(chunks: list[Any], expected: list[str]) -> bool:
    return any(
        _contains_expected(f"{chunk.file_name}\n{chunk.source_path}", expected)
        for chunk in chunks
    )


def _metadata_hit(hits: list[Any], expected: dict[str, Any], limit: int) -> bool:
    if not expected:
        return True
    for hit in hits[:limit]:
        matched = True
        for field, value in expected.items():
            actual = hit.chunk.metadata.get(field)
            if isinstance(value, list):
                actual_values = actual if isinstance(actual, list) else [actual]
                matched = matched and all(item in actual_values for item in value)
            else:
                matched = matched and (value in actual if isinstance(actual, list) else actual == value)
        if matched:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against golden questions.")
    parser.add_argument("--golden", type=Path, default=Path("tests/golden_questions.yaml"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    golden = yaml.safe_load(args.golden.read_text(encoding="utf-8")) or []
    settings = Settings.load()
    output = args.output or settings.report_root / f"retrieval-eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    vector_store = None
    try:
        database = IndexDatabase(settings.database_path)
        vector_store = VectorStore(settings.qdrant_path)
        bm25 = BM25Index(settings.bm25_path)
        if not bm25.load():
            raise RuntimeError("BM25 index is not ready")
    except Exception as error:
        if vector_store is not None:
            vector_store.close()
        report = {
            "status": "blocked_no_active_index",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "golden_questions": len(golden),
            "error": f"{type(error).__name__}: {error}",
            "rows": [],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report_path": str(output), "status": report["status"]}, ensure_ascii=False))
        return
    retriever = Retriever(
        database,
        vector_store,
        EmbeddingService(settings),
        bm25,
        RerankerService(settings),
        settings,
    )
    rows: list[dict[str, Any]] = []
    try:
        for item in golden:
            question = str(item.get("question", "")).strip()
            hits, retrieval = retriever.search(question, dense_limit=20, bm25_limit=20, final_limit=10)
            expected_files = [str(value) for value in item.get("expected_files", [])]
            expected_keywords = [str(value) for value in item.get("expected_keywords", [])]
            expected_metadata = item.get("expected_metadata") or {}
            top_text = "\n".join(hit.chunk.text for hit in hits)
            before_ids = retrieval.get("pre_rerank_ids", [])
            after_ids = retrieval.get("post_rerank_ids", [])
            before_chunks = database.get_chunks([str(value) for value in before_ids])
            after_chunks = database.get_chunks([str(value) for value in after_ids])
            rows.append(
                {
                    "question": question,
                    "recall_at_5": _expected_file_hit(hits, expected_files, 5),
                    "recall_at_10": _expected_file_hit(hits, expected_files, 10),
                    "keywords_hit": all(keyword.casefold() in top_text.casefold() for keyword in expected_keywords),
                    "metadata_hit": _metadata_hit(hits, expected_metadata, 10),
                    "expected_files": expected_files,
                    "hits": [hit.chunk.source_path for hit in hits],
                    "reranker_before_hit": _expected_chunk_file_hit(before_chunks, expected_files) if expected_files else None,
                    "reranker_after_hit": _expected_chunk_file_hit(after_chunks, expected_files) if expected_files else None,
                    "retrieval": retrieval,
                }
            )
    finally:
        vector_store.close()

    file_cases = [row for row in rows if row["expected_files"]]
    report = {
        "status": "completed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "golden_questions": len(rows),
        "recall_at_5": sum(row["recall_at_5"] for row in file_cases) / len(file_cases) if file_cases else None,
        "recall_at_10": sum(row["recall_at_10"] for row in file_cases) / len(file_cases) if file_cases else None,
        "reranker_used_cases": sum(bool(row["retrieval"].get("reranker_used")) for row in rows),
        "metadata_filter_cases": sum(bool(row["retrieval"].get("metadata_filter_used")) for row in rows),
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(output), "recall_at_5": report["recall_at_5"], "recall_at_10": report["recall_at_10"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
