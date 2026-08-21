from __future__ import annotations

from pathlib import Path
from typing import Iterable

from qdrant_client import QdrantClient, models

from .domain import Chunk


COLLECTION_NAME = "design_management_chunks"
VECTOR_SIZE = 1_024


class VectorStore:
    """A single-process Qdrant Local wrapper; do not open this path from two processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self.client = QdrantClient(path=str(path))
        self.ensure_collection()

    def _collection_exists(self) -> bool:
        names = {collection.name for collection in self.client.get_collections().collections}
        return COLLECTION_NAME in names

    def ensure_collection(self) -> None:
        if not self._collection_exists():
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
            return
        config = self.client.get_collection(COLLECTION_NAME).config.params.vectors
        current_size = getattr(config, "size", None)
        if current_size != VECTOR_SIZE:
            raise RuntimeError(
                "现有向量库维度与 BGE-M3 不一致。请停止服务后重建索引，不要混用模型。"
            )

    def reset(self) -> None:
        if self._collection_exists():
            self.client.delete_collection(COLLECTION_NAME)
        self.ensure_collection()

    def upsert(self, chunks: Iterable[Chunk], vectors: Iterable[object]) -> None:
        points = [
            models.PointStruct(
                id=chunk.chunk_id,
                vector=vector.tolist() if hasattr(vector, "tolist") else vector,
                payload={
                    "document_id": chunk.document_id,
                    "file_name": chunk.file_name,
                    "source_path": chunk.source_path,
                    "heading_path": chunk.heading_path,
                    "location": chunk.location,
                    "metadata": chunk.metadata,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        if points:
            self.client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)

    def query(
        self,
        vector: object,
        limit: int = 20,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        query_filter = None
        if allowed_ids:
            query_filter = models.Filter(
                must=[models.HasIdCondition(has_id=list(allowed_ids))]
            )
        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector.tolist() if hasattr(vector, "tolist") else vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=False,
        )
        return [(str(point.id), float(point.score)) for point in response.points]

    def count(self) -> int:
        return int(self.client.count(COLLECTION_NAME, exact=True).count)

    def close(self) -> None:
        self.client.close()
