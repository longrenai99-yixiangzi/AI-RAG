from types import SimpleNamespace

from app.answer import _answer_sections, _context, generate_answer, validate_citations
from app.chunker import _tail_within_budget, estimate_tokens, split_text
from app.domain import Chunk, SearchHit
from app.retriever import reciprocal_rank_fusion


def test_heading_safe_chunking_keeps_all_text() -> None:
    text = "设计策划应形成任务书。\n\n" * 200
    chunks = split_text(text, target_tokens=80, max_tokens=120, overlap_tokens=12)
    assert len(chunks) > 1
    assert all(estimate_tokens(chunk) <= 140 for chunk in chunks)
    assert "任务书" in "".join(chunks)


def test_rrf_and_citation_validation() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
    assert fused[0][0] == "b"
    assert validate_citations("依据 [S1]。", {"S1"}) == (True, ["S1"], [])
    assert validate_citations("依据 [S9]。", {"S1"})[0] is False


def test_overlap_does_not_repeat_a_whole_large_paragraph() -> None:
    large_unit = "设计策划内容。" * 100
    assert _tail_within_budget([large_unit], 20) == []


def test_context_only_accepts_sources_that_were_sent_to_the_model() -> None:
    hits = [
        SearchHit(
            Chunk(
                chunk_id=str(index),
                document_id="d",
                ordinal=index,
                source_path="source.md",
                file_name="source.md",
                text="资料内容。" * 900,
                heading_path="章节",
                location={},
            ),
            score=1,
        )
        for index in range(10)
    ]
    context, records = _context(hits)
    assert len(context) <= 12_000
    assert len(records) < len(hits)


def test_answer_sections_follow_query_intent() -> None:
    assert "【依据】" in _answer_sections("FACT_LOOKUP")
    assert "【适用范围】" in _answer_sections("POLICY_QUERY")
    assert "【可借鉴点】" in _answer_sections("CASE_QUERY")


def test_answer_has_evidence_only_mode_without_api_configuration() -> None:
    hit = SearchHit(
        Chunk("c", "d", 0, "source.md", "source.md", "明确的证据内容。", "章节", {}),
        score=1,
    )
    result = generate_answer(
        "问题",
        [hit],
        SimpleNamespace(settings=SimpleNamespace(api_ready=False)),
    )
    assert result.citation_valid is True
    assert "未配置生成模型" in result.answer
