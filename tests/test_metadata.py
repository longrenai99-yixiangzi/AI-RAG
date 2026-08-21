from pathlib import Path

from app.database import IndexDatabase
from app.domain import Chunk, ParsedDocument
from app.metadata import infer_metadata


RULES = Path(__file__).parents[1] / "config" / "metadata_rules.yaml"


def test_metadata_is_rule_based_and_missing_values_are_allowed(tmp_path: Path) -> None:
    path = tmp_path / "raw" / "医院项目设计策划.md"
    text = "# 医院项目设计策划\n\nEPC医院项目施工图设计与设计评审。"
    metadata = infer_metadata(path, text, RULES)

    assert metadata["building_type"] == "医院"
    assert metadata["project_stage"] == "施工图设计"
    assert "设计策划" in metadata["topic"]
    assert metadata["discipline"] is None


def test_metadata_round_trips_through_sqlite(tmp_path: Path) -> None:
    database = IndexDatabase(tmp_path / "index.sqlite3")
    metadata = {"board": "设计管理", "topic": ["EPC"], "project_name": None}
    document = ParsedDocument(
        document_id="doc",
        source_path="x.md",
        file_name="x.md",
        file_type=".md",
        sha256="hash",
        file_size=1,
        mtime_ns=1,
        blocks=[],
        parse_status="parsed",
        metadata=metadata,
    )
    chunk = Chunk(
        chunk_id="chunk",
        document_id="doc",
        ordinal=0,
        source_path="x.md",
        file_name="x.md",
        text="EPC",
        heading_path="",
        location={},
        metadata=metadata,
    )

    database.store_document(document, [chunk])

    assert database.get_chunks(["chunk"])[0].metadata["board"] == "设计管理"
    assert database.chunk_ids_for_metadata({"topic": "EPC"}) == {"chunk"}
