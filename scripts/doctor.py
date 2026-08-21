from __future__ import annotations

import importlib.util
import json
import shutil
import sys

from app.config import Settings


def _torch_cuda() -> bool | None:
    if importlib.util.find_spec("torch") is None:
        return None
    import torch

    return bool(torch.cuda.is_available())


def main() -> None:
    settings = Settings.load()
    dependencies = [
        "fastapi",
        "httpx",
        "qdrant_client",
        "FlagEmbedding",
        "rank_bm25",
        "jieba",
        "fitz",
        "docx",
        "openpyxl",
        "pptx",
    ]
    report = {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "pip": bool(shutil.which("pip")),
        "api_configured": settings.api_ready,
        "vault_exists": settings.vault_root.is_dir(),
        "vault_path": str(settings.vault_root),
        "cuda_available": _torch_cuda(),
        "dependencies": {
            name: importlib.util.find_spec(name) is not None for name in dependencies
        },
        "max_local_chunks": settings.max_local_chunks,
        "note": "敏感 API Key 不会输出。",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
