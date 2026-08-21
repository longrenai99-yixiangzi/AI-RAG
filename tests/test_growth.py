from pathlib import Path

from app.database import IndexDatabase
from app.growth import GrowthManager


def test_unanswered_queries_merge_and_create_reviewable_candidate(tmp_path: Path) -> None:
    database = IndexDatabase(tmp_path / "index.sqlite3")
    manager = GrowthManager(database, tmp_path / "data")
    retrieval = {
        "fused_hits": 0,
        "query_analysis": {
            "intent": "FACT_LOOKUP",
            "filters": {"project_name": "示例项目"},
        },
    }

    first = manager.record(
        question="示例项目由哪个公司实施？",
        retrieval=retrieval,
        answer="当前知识库未检索到足够依据。",
        citations=[],
        citation_valid=True,
    )
    second = manager.record(
        question="示例项目由哪个公司实施？",
        retrieval=retrieval,
        answer="当前知识库未检索到足够依据。",
        citations=[],
        citation_valid=True,
    )

    assert first["answer_status"] == "NO_RETRIEVAL"
    assert first["gap"]["gap_id"] == second["gap"]["gap_id"]
    assert second["gap"]["frequency"] == 2
    candidate_path = Path(first["candidate"]["path"])
    assert candidate_path.is_file()
    assert "formal_write: forbidden" in candidate_path.read_text(encoding="utf-8")
    draft = manager.create_formal_draft(first["candidate"]["candidate_id"])
    assert Path(draft["path"]).is_file()
    assert "formal_write: forbidden" in Path(draft["path"]).read_text(encoding="utf-8")

    snapshot = database.growth_snapshot()
    assert snapshot["stats"]["OPEN"] == 1
    assert database.update_gap_status(first["gap"]["gap_id"], "REVIEWING")["status"] == "REVIEWING"
