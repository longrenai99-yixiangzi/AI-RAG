from __future__ import annotations

import json
import sys
from pathlib import Path

from app.config import Settings


def main() -> int:
    try:
        import torch
    except ImportError as exc:
        print(json.dumps({"status": "failed", "error": f"torch unavailable: {exc}"}, ensure_ascii=False))
        return 2

    cuda_available = bool(torch.cuda.is_available())
    settings = Settings.load()
    model_paths = {
        "embedding": Path(settings.embedding_model),
        "reranker": Path(settings.reranker_model),
    }
    report = {
        "status": "ok" if cuda_available and all(path.is_dir() for path in model_paths.values()) else "failed",
        "python": sys.executable,
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_available": cuda_available,
        "gpu_count": int(torch.cuda.device_count()) if cuda_available else 0,
        "gpu_names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
        if cuda_available
        else [],
        "embedding_model": str(model_paths["embedding"]),
        "embedding_model_exists": model_paths["embedding"].is_dir(),
        "reranker_model": str(model_paths["reranker"]),
        "reranker_model_exists": model_paths["reranker"].is_dir(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
