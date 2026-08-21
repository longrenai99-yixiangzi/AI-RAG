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
    )
    print(json.dumps({"model": settings.embedding_model, "path": path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
