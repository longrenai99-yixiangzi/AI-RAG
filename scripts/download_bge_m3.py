from __future__ import annotations

import json

from huggingface_hub import snapshot_download

from app.config import Settings


def main() -> None:
    settings = Settings.load()
    settings.ensure_runtime_directories()
    path = snapshot_download(
        repo_id=settings.embedding_model,
        local_dir=str(settings.embedding_model_path),
        cache_dir=str(settings.cache_root),
        allow_patterns=[
            "config.json",
            "modules.json",
            "pytorch_model.bin",
            "model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "sentencepiece.bpe.model",
            "sparse_linear.pt",
            "colbert_linear.pt",
            "1_Pooling/*",
            "README.md",
        ],
    )
    print(json.dumps({"model": settings.embedding_model, "path": path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
