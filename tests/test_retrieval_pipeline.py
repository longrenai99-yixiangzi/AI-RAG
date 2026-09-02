from pathlib import Path

import yaml

from app.bm25 import BM25Index
from app.domain import Chunk
from app.retrieval.citation import build_citations, validate_citations
from app.retrieval.context_builder import build_context
from app.retrieval.hybrid_retriever import HybridRetriever, MockDenseProvider


GOLD_PATH = Path(__file__).parent / "gold_questions" / "golden_questions.yaml"


def _gold_questions() -> list[dict]:
    return yaml.safe_load(GOLD_PATH.read_text(encoding="utf-8"))["questions"]


def _gold_chunks(questions: list[dict]) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"gold-{item['id']}",
            document_id=f"doc-{item['id']}",
            ordinal=index,
            source_path=f"D:/fixtures/{item['id']}.md",
            file_name=f"{item['id']}.md",
            text=(
                f"{item['question']}\n"
                f"关键词：{'、'.join(item['expected_keywords'])}\n"
                "这是用于检索基准的可核查证据。"
            ),
            heading_path=f"{item['category']} > {item['id']}",
            location={"line_start": index + 1, "line_end": index + 3},
        )
        for index, item in enumerate(questions)
    ]


def test_fifty_gold_questions_have_top_k_chunk_and_complete_citation() -> None:
    questions = _gold_questions()
    chunks = _gold_chunks(questions)
    index = BM25Index(Path("memory-bm25.json"))
    index.build(chunks)
    retriever = HybridRetriever(index, chunks, dense=MockDenseProvider())

    for item in questions:
        result = retriever.search(item["question"], final_limit=5)

        assert result.hits
        assert result.hits[0].chunk.chunk_id == f"gold-{item['id']}"
        assert result.analysis.question_type == item["category"]
        assert all(hit.chunk.chunk_id for hit in result.hits)
        context = build_context(result.hits)
        citations = build_citations(context)
        valid, errors = validate_citations(citations, context)
        assert valid, errors
        assert all(citation["location"] for citation in citations)


def test_dense_mock_is_fused_by_chunk_id() -> None:
    questions = _gold_questions()
    chunks = _gold_chunks(questions)
    index = BM25Index(Path("memory-bm25-dense.json"))
    index.build(chunks)
    question = questions[0]["question"]
    dense = MockDenseProvider({question: [("gold-GQ-002", 0.99)]})
    result = HybridRetriever(index, chunks, dense=dense).search(question, final_limit=5)

    assert result.debug["dense_hits"] == 1
    assert any(hit.chunk.chunk_id == "gold-GQ-002" for hit in result.hits)
    assert any(hit.dense_rank == 1 for hit in result.hits)
