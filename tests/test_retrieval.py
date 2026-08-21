from dataclasses import replace
from pathlib import Path

from app.bm25 import BM25Index
from app.config import Settings
from app.database import IndexDatabase
from app.domain import Chunk, ParsedDocument
from app.embeddings import ModelUnavailable
from app.retriever import Retriever, reciprocal_rank_fusion


def test_rrf_remains_the_fusion_stage() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])

    assert fused[0][0] == "b"
    assert fused[0][1] > fused[1][1]


class FakeEmbedding:
    def embed_query(self, query: str) -> list[float]:
        return [0.0]


class MissingEmbedding:
    def embed_query(self, query: str) -> list[float]:
        raise ModelUnavailable("test model unavailable")


class FakeReranker:
    error = None

    def score(self, query: str, passages: list[str]) -> None:
        return None


class FakeVectorStore:
    def __init__(self) -> None:
        self.allowed_calls: list[set[str] | None] = []

    def query(self, vector: object, limit: int = 20, allowed_ids: set[str] | None = None):
        self.allowed_calls.append(allowed_ids)
        pairs = [("c1", 0.99), ("c2", 0.98)]
        return [pair for pair in pairs if allowed_ids is None or pair[0] in allowed_ids]


class FakeBM25:
    ready = True

    def search(self, query: str, limit: int = 20, allowed_ids: set[str] | None = None):
        if allowed_ids is not None and "c" not in allowed_ids:
            return []
        return [("c", 1.0)]


def test_metadata_filter_is_soft_and_reaches_both_retrievers(tmp_path: Path) -> None:
    settings = replace(
        Settings.load(),
        project_root=Path(__file__).parents[1],
        data_root=tmp_path / "data",
    )
    database = IndexDatabase(settings.database_path)
    metadata_one = {
        "board": "设计管理",
        "building_type": "医院",
        "project_stage": "施工图设计",
        "topic": ["设计策划"],
    }
    metadata_two = {"board": "设计管理", "building_type": "住宅", "project_stage": "方案设计", "topic": []}
    for document_id, chunk_id, metadata in (("d1", "c1", metadata_one), ("d2", "c2", metadata_two)):
        document = ParsedDocument(
            document_id, f"{document_id}.md", f"{document_id}.md", ".md", document_id, 1, 1, [], "parsed", metadata=metadata
        )
        database.store_document(
            document,
            [Chunk(chunk_id, document_id, 0, document.source_path, document.file_name, "医院施工图设计策划" if chunk_id == "c1" else "住宅方案", "", {}, metadata=metadata)],
        )
    bm25 = BM25Index(tmp_path / "bm25.json")
    bm25.build(database.get_chunks(["c1", "c2"]))
    vector = FakeVectorStore()
    retriever = Retriever(database, vector, FakeEmbedding(), bm25, FakeReranker(), settings)

    hits, retrieval = retriever.search("医院项目施工图设计策划有哪些管理要求？")

    assert [hit.chunk.chunk_id for hit in hits] == ["c1"]
    assert retrieval["metadata_filter_used"] is True
    assert any(call == {"c1"} for call in vector.allowed_calls)


def test_bm25_fallback_remains_available_without_dense_model(tmp_path: Path) -> None:
    settings = replace(
        Settings.load(),
        project_root=Path(__file__).parents[1],
        data_root=tmp_path / "data",
    )
    database = IndexDatabase(settings.database_path)
    metadata = {"board": "设计管理", "topic": ["设计策划"]}
    document = ParsedDocument("d", "d.md", "d.md", ".md", "hash", 1, 1, [], "parsed", metadata=metadata)
    chunk = Chunk("c", "d", 0, "d.md", "d.md", "设计策划应形成管理文件", "", {}, metadata=metadata)
    database.store_document(document, [chunk])
    vector = FakeVectorStore()
    retriever = Retriever(database, vector, MissingEmbedding(), FakeBM25(), FakeReranker(), settings)

    hits, retrieval = retriever.search("设计策划")

    assert [hit.chunk.chunk_id for hit in hits] == ["c"]
    assert retrieval["dense_available"] is False
    assert retrieval["bm25_hits"] == 1
