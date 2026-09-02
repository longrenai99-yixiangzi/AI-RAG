from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.bm25 import BM25Index
from app.domain import Chunk
from app.ingestion.pipeline import PipelineResult, run_document_pipeline
from app.ingestion.publisher.staging_reader import read_staging_json
from app.retrieval.citation import build_citations, validate_citations
from app.retrieval.context_builder import build_context
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import HybridRetriever, MockDenseProvider, RetrievalResult
from app.retrieval.reranker_provider import BGERerankerProvider
from app.evaluation.gold_dataset_loader import GoldQuestion
from app.parsers import iter_source_files


@dataclass(slots=True)
class ModeMetrics:
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    citation_completeness: float
    evaluated_questions: int
    failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FullCorpusEvaluation:
    corpus_files: int
    corpus_documents: int
    corpus_chunks: int
    metadata_complete_chunks: int
    location_complete_chunks: int
    gold_questions: int
    gold_status: str
    modes: dict[str, ModeMetrics]


def evaluate_full_corpus(
    root: Path,
    questions: list[GoldQuestion],
    *,
    bge_model_path: Path,
    reranker_model_path: Path,
    max_file_size_mb: int = 150,
) -> FullCorpusEvaluation:
    files = iter_source_files(root)
    pipeline = run_document_pipeline(root, files=files)
    chunks = [chunk for document in pipeline.documents for chunk in document.chunks]
    metadata_by_chunk = {
        chunk_id: metadata
        for document in pipeline.documents
        for chunk_id, metadata in document.chunk_metadata.items()
    }
    bm25 = BM25Index(Path("memory-full-corpus-bm25.json"))
    bm25.build(chunks)
    bm25_results = _run_mode(bm25, chunks, questions, MockDenseProvider())

    dense = BGEM3DenseProvider(
        bge_model_path,
        collection_name="full_corpus_shadow_bge_m3",
        batch_size=32,
    )
    dense.index_chunks(chunks)
    dense_map = {
        question.question: dense.search(question.question, limit=20)
        for question in questions
    }
    hybrid_results = _run_mode(bm25, chunks, questions, MockDenseProvider(dense_map))
    dense.close()

    reranker = BGERerankerProvider(reranker_model_path)
    rerank_results = _run_mode(
        bm25,
        chunks,
        questions,
        MockDenseProvider(dense_map),
        reranker=reranker,
    )
    reranker.close()

    metadata_complete = sum(
        1 for metadata in metadata_by_chunk.values() if metadata.get("file_type") and metadata.get("sha256")
    )
    location_complete = sum(bool(chunk.location) for chunk in chunks)
    return FullCorpusEvaluation(
        corpus_files=len(files),
        corpus_documents=len(pipeline.documents),
        corpus_chunks=len(chunks),
        metadata_complete_chunks=metadata_complete,
        location_complete_chunks=location_complete,
        gold_questions=len(questions),
        gold_status="provisional_gold_requires_owner_review",
        modes={
            "BM25-only": _metrics(questions, bm25_results),
            "Hybrid": _metrics(questions, hybrid_results),
            "Hybrid+Reranker": _metrics(questions, rerank_results),
        },
    )


def _run_mode(
    bm25: BM25Index,
    chunks: list[Chunk],
    questions: list[GoldQuestion],
    dense: MockDenseProvider,
    *,
    reranker: BGERerankerProvider | None = None,
) -> list[RetrievalResult]:
    retriever = HybridRetriever(bm25, chunks, dense=dense, reranker=reranker)
    return [
        retriever.search(
            question.question,
            rerank_limit=5 if reranker is not None else 20,
            final_limit=5,
        )
        for question in questions
    ]


def _metrics(questions: list[GoldQuestion], results: list[RetrievalResult]) -> ModeMetrics:
    ranks: list[int | None] = []
    citation_success = 0
    failures: list[dict[str, Any]] = []
    for question, result in zip(questions, results, strict=True):
        relevant_ids = [
            index + 1
            for index, hit in enumerate(result.hits)
            if _is_relevant(question, hit.chunk)
        ]
        rank = min(relevant_ids) if relevant_ids else None
        ranks.append(rank)
        context = build_context(result.hits)
        citations = build_citations(context)
        valid, errors = validate_citations(citations, context)
        complete = bool(citations) and valid and all(citation.get("location") for citation in citations)
        citation_success += int(complete)
        if rank is None:
            failures.append(
                {
                    "id": question.id,
                    "question": question.question,
                    "top_files": [hit.chunk.file_name for hit in result.hits[:3]],
                    "citation_errors": errors,
                }
            )
    total = len(questions)
    return ModeMetrics(
        recall_at_1=_recall(ranks, 1),
        recall_at_3=_recall(ranks, 3),
        recall_at_5=_recall(ranks, 5),
        mrr=sum(1 / rank if rank else 0 for rank in ranks) / total,
        citation_completeness=citation_success / total,
        evaluated_questions=total,
        failures=failures,
    )


def _is_relevant(question: GoldQuestion, chunk: Chunk) -> bool:
    file_name = chunk.file_name.casefold()
    if question.expected_files and any(expected.casefold() == file_name for expected in question.expected_files):
        return True
    searchable = f"{chunk.file_name} {chunk.heading_path} {chunk.text}".casefold()
    topic_hits = sum(topic.casefold() in searchable for topic in question.expected_topics)
    required = max(1, (len(question.expected_topics) + 1) // 2)
    return topic_hits >= required


def _recall(ranks: list[int | None], k: int) -> float:
    return sum(rank is not None and rank <= k for rank in ranks) / len(ranks)
