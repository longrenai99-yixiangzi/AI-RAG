from pathlib import Path

from app.database import IndexDatabase
from app.domain import Chunk, ParsedDocument, SourceBlock
from app.knowledge_graph import extract_entity_facts


def test_entity_facts_require_explicit_text_and_evidence(tmp_path: Path) -> None:
    source = tmp_path / "wiki" / "entities" / "示例项目.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\naliases: [示例工程]\n---\n\n# 示例项目\n\n- **实施单位**：示例公司\n",
        encoding="utf-8",
    )
    text = "# 示例项目\n\n- **实施单位**：示例公司"
    document = ParsedDocument(
        "doc", str(source), source.name, ".md", "hash", 1, 1,
        [SourceBlock("doc", str(source), source.name, text)], "parsed",
    )
    chunk = Chunk("chunk", "doc", 0, str(source), source.name, text, "", {})

    entities, facts = extract_entity_facts(document, [chunk])

    assert entities[0]["canonical_name"] == "示例项目"
    assert entities[0]["aliases"] == ["示例工程"]
    assert facts[0]["predicate"] == "IMPLEMENTING_ORGANIZATION"
    assert facts[0]["evidence_chunk_id"] == "chunk"

    database = IndexDatabase(tmp_path / "index.sqlite3")
    database.store_document(document, [chunk])
    database.store_knowledge_graph(entities, facts)
    assert database.lookup_facts("示例项目由谁实施？")[0]["object_text"] == "示例公司"


def test_conflicting_facts_are_marked_for_review(tmp_path: Path) -> None:
    database = IndexDatabase(tmp_path / "index.sqlite3")
    document = ParsedDocument("doc", "source.md", "source.md", ".md", "hash", 1, 1, [], "parsed")
    chunks = [
        Chunk("c1", "doc", 0, "source.md", "source.md", "证据一", "", {}),
        Chunk("c2", "doc", 1, "source.md", "source.md", "证据二", "", {}),
    ]
    database.store_document(document, chunks)
    entity = {
        "entity_id": "entity",
        "entity_type": "PROJECT",
        "canonical_name": "冲突项目",
        "aliases": [],
        "description": "",
        "source_document_id": "doc",
    }
    facts = [
        {"fact_id": "f1", "subject_entity_id": "entity", "predicate": "OWNER", "object_text": "甲公司", "evidence_chunk_id": "c1", "confidence": 0.5},
        {"fact_id": "f2", "subject_entity_id": "entity", "predicate": "OWNER", "object_text": "乙公司", "evidence_chunk_id": "c2", "confidence": 0.5},
    ]

    database.store_knowledge_graph([entity], facts)

    assert len(database.fact_conflicts()) == 1
    assert database.stats()["fact_conflicts"] == 1
