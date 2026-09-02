from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from app.bm25 import BM25Index
from app.domain import Chunk
from app.retrieval.citation import build_citations, validate_citations
from app.retrieval.context_builder import build_context
from app.retrieval.dense_provider import BGEM3DenseProvider
from app.retrieval.hybrid_retriever import HybridRetriever, MockDenseProvider
from app.retrieval.reranker_provider import BGERerankerProvider


RUN_MODEL_SHADOW = os.getenv("RUN_MODEL_SHADOW") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_MODEL_SHADOW,
    reason="real BGE/Reranker shadow requires RUN_MODEL_SHADOW=1 and explicit local model paths",
)


def _questions() -> list[dict]:
    path = Path(__file__).parent / "gold_questions" / "golden_questions.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]


def _chunks(questions: list[dict]) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"gold-{item['id']}",
            document_id=f"doc-{item['id']}",
            ordinal=index,
            source_path=f"D:/fixtures/{item['id']}.md",
            file_name=f"{item['id']}.md",
            text=f"{item['question']}\n关键词：{'、'.join(item['expected_keywords'])}",
            heading_path=item["category"],
            location={"line_start": index + 1, "line_end": index + 3},
        )
        for index, item in enumerate(questions)
    ]


def _metrics(questions: list[dict], results: list) -> dict[str, float]:
    ranks: list[int | None] = []
    citation_complete = 0
    for item, result in zip(questions, results, strict=True):
        expected = f"gold-{item['id']}"
        hit_ids = [hit.chunk.chunk_id for hit in result.hits]
        rank = hit_ids.index(expected) + 1 if expected in hit_ids else None
        ranks.append(rank)
        bundle = build_context(result.hits)
        citations = build_citations(bundle)
        valid, _ = validate_citations(citations, bundle)
        citation_complete += int(valid and all(citation["location"] for citation in citations))
    return {
        "Recall@1": sum(rank is not None and rank <= 1 for rank in ranks) / len(ranks),
        "Recall@3": sum(rank is not None and rank <= 3 for rank in ranks) / len(ranks),
        "Recall@5": sum(rank is not None and rank <= 5 for rank in ranks) / len(ranks),
        "MRR": sum(1 / rank if rank else 0 for rank in ranks) / len(ranks),
        "Citation完整率": citation_complete / len(ranks),
    }


def test_real_bge_and_reranker_shadow_metrics() -> None:
    questions = _questions()
    chunks = _chunks(questions)
    bm25 = BM25Index(Path("memory-model-shadow-bm25.json"))
    bm25.build(chunks)

    bm25_results = [
        HybridRetriever(bm25, chunks).search(item["question"], final_limit=5)
        for item in questions
    ]

    bge_path = Path(os.environ["RAG_SHADOW_BGE_PATH"])
    reranker_path = Path(os.environ["RAG_SHADOW_RERANKER_PATH"])
    dense = BGEM3DenseProvider(bge_path, collection_name="gold_shadow_bge_m3")
    dense_results = [
        HybridRetriever(bm25, chunks, dense=dense).search(item["question"], final_limit=5)
        for item in questions
    ]
    dense_map = {
        item["question"]: [
            (hit.chunk.chunk_id, float(hit.score)) for hit in result.hits
        ]
        for item, result in zip(questions, dense_results, strict=True)
    }
    dense.close()

    reranker = BGERerankerProvider(reranker_path)
    hybrid_rerank_results = [
        HybridRetriever(
            bm25,
            chunks,
            dense=MockDenseProvider(dense_map),
            reranker=reranker,
        ).search(item["question"], final_limit=5)
        for item in questions
    ]
    reranker.close()

    metrics = {
        "BM25-only": _metrics(questions, bm25_results),
        "Hybrid": _metrics(questions, dense_results),
        "Hybrid+Reranker": _metrics(questions, hybrid_rerank_results),
    }
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    assert all(value["Citation完整率"] == 1 for value in metrics.values())
