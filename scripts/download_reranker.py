from __future__ import annotations

from huggingface_hub import snapshot_download

from app.config import Settings


def main() -> None:
    settings = Settings.load()
    settings.ensure_runtime_directories()
    path = snapshot_download(
        repo_id="BAAI/bge-reranker-v2-m3",
        local_dir=str(settings.reranker_model_path),
        cache_dir=str(settings.cache_root),
        allow_patterns=["*.bin", "*.safetensors", "*.json", "*.txt", "*.model", "tokenizer*", "special_tokens_map.json"],
    )
    print(path)


if __name__ == "__main__":
    main()
