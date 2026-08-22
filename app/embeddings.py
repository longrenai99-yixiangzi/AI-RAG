from __future__ import annotations

import os
from typing import Sequence

from .config import Settings


class ModelUnavailable(RuntimeError):
    pass


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model: object | None = None
        self.device = "cuda" if _cuda_available() else "cpu"
        self.error: str | None = None

    @property
    def ready(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.model is not None:
            return
        os.environ.setdefault("HF_HOME", str(self.settings.cache_root))
        try:
            from FlagEmbedding import BGEM3FlagModel

            self.model = BGEM3FlagModel(
                self.settings.embedding_model,
                use_fp16=self.device == "cuda",
            )
            self.error = None
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            raise ModelUnavailable("Embedding 模型无法加载。请先运行依赖安装和模型下载。") from error

    def _encode(self, texts: Sequence[str]) -> object:
        if not texts:
            return []
        self.load()
        assert self.model is not None
        try:
            result = self.model.encode(  # type: ignore[attr-defined]
                list(texts),
                batch_size=4,
                max_length=1_024,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            return result["dense_vecs"]
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            raise ModelUnavailable("本地向量化失败；请降低批量或检查 GPU/内存。") from error

    def embed_documents(self, texts: Sequence[str]) -> object:
        return self._encode(texts)

    def embed_query(self, query: str) -> object:
        vectors = self._encode([query])
        return vectors[0]


class RerankerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model: object | None = None
        self.device = "cuda" if _cuda_available() else "cpu"
        self.error: str | None = None
        self.disabled = settings.reranker_mode in {"0", "false", "off", "no"}

    @property
    def ready(self) -> bool:
        return self.model is not None

    def load(self) -> bool:
        if self.disabled:
            return False
        if self.model is not None:
            return True
        os.environ.setdefault("HF_HOME", str(self.settings.cache_root))
        try:
            from FlagEmbedding import FlagReranker

            self.model = FlagReranker(
                self.settings.reranker_model,
                use_fp16=self.device == "cuda",
            )
            self.error = None
            return True
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            if self.settings.reranker_mode == "on":
                raise ModelUnavailable("重排模型无法加载。") from error
            self.disabled = True
            return False

    def score(self, query: str, passages: Sequence[str]) -> list[float] | None:
        if not passages or not self.load():
            return None
        assert self.model is not None
        try:
            scores = self.model.compute_score(  # type: ignore[attr-defined]
                [[query, passage] for passage in passages],
                batch_size=2,
                max_length=512,
                normalize=False,
            )
            return [float(score) for score in scores]
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            if self.settings.reranker_mode == "on":
                raise ModelUnavailable("重排模型运行失败。") from error
            self.disabled = True
            return None
