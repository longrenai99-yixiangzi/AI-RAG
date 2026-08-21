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
