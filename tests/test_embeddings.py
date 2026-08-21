from dataclasses import replace

import pytest

from app.config import Settings
from app.embeddings import EmbeddingService, ModelUnavailable


def test_missing_embedding_weights_fail_fast(tmp_path) -> None:
    settings = replace(Settings.load(), model_root=tmp_path)

    with pytest.raises(ModelUnavailable, match="权重文件"):
        EmbeddingService(settings).load()
