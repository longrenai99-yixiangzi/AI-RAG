from __future__ import annotations

from pathlib import Path
from typing import Sequence
import uuid

from qdrant_client import QdrantClient, models

from app.domain import Chunk


class BGEM3DenseProvider:
    """Real BGE-M3 Dense provider backed by an isolated in-memory Qdrant collection."""

    VECTOR_SIZE = 1_024

    def __init__(
        self,
        model_path: Path | str,
        *,
        collection_name: str = "shadow_bge_m3",
        use_fp16: bool = False,
        batch_size: int = 4,
    ) -> None:
        self.model_path = Path(model_path)
        self.collection_name = collection_name
        self.use_fp16 = use_fp16
        self.batch_size = batch_size
        self.model: object | None = None
        self.client = QdrantClient(location=":memory:")
        self._point_to_chunk: dict[str, str] = {}

    @property
    def ready(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.model is not None:
            return
        if not self.model_path.is_dir():
            raise FileNotFoundError(f"BGE-M3 本地模型目录不存在：{self.model_path}")
        from FlagEmbedding import BGEM3FlagModel

        self.model = BGEM3FlagModel(str(self.model_path), use_fp16=self.use_fp16)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        self.load()
        assert self.model is not None
        result = self.model.encode(  # type: ignore[attr-defined]
            list(texts),
            batch_size=self.batch_size,
            max_length=1_024,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        vectors = result["dense_vecs"]
        return [vector.tolist() if hasattr(vector, "tolist") else list(vector) for vector in vectors]

    def embed_query(self, question: str) -> list[float]:
        return self.embed_documents([question])[0]

    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        vectors = self.embed_documents([chunk.text for chunk in chunks])
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.VECTOR_SIZE,
                distance=models.Distance.COSINE,
            ),
        )
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            point_id = _qdrant_point_id(chunk.chunk_id)
            self._point_to_chunk[point_id] = chunk.chunk_id
            points.append(
                models.PointStruct(
                    id=point_id,
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "file_name": chunk.file_name,
                    "source_path": chunk.source_path,
                    "heading_path": chunk.heading_path,
                    "location": chunk.location,
                },
            )
            )
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points, wait=True)

    def search(self, question: str, limit: int = 20) -> list[tuple[str, float]]:
        vector = self.embed_query(question)
        if not self.client.collection_exists(self.collection_name):
            return []
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        return [
            (
                str((point.payload or {}).get("chunk_id", self._point_to_chunk.get(str(point.id), point.id))),
                float(point.score),
            )
            for point in response.points
        ]

    def close(self) -> None:
        self.client.close()
        self.model = None


def _qdrant_point_id(chunk_id: str) -> str:
    try:
        uuid.UUID(chunk_id)
        return chunk_id
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))
