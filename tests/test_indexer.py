from dataclasses import replace

from app.config import Settings
from app.database import IndexDatabase
from app.indexer import index_vault
from app.vector_store import VectorStore


class FakeEmbedding:
    def load(self) -> None:
        pass

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1024 for _ in texts]


def test_indexer_publishes_only_a_verified_staged_index(tmp_path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "制度.md").write_text("# 设计策划\n\n项目启动后应编制设计策划。", encoding="utf-8")
    settings = replace(
        Settings.load(),
        project_root=tmp_path,
        data_root=tmp_path / "data",
        vault_root=vault,
        max_local_chunks=100,
    )

    report = index_vault(settings, FakeEmbedding())

    assert report["status"] == "completed"
    assert report["chunks"] > 0
    assert IndexDatabase(settings.database_path).stats()["chunks"] == report["chunks"]
    store = VectorStore(settings.qdrant_path)
    try:
        assert store.count() == report["chunks"]
    finally:
        store.close()
