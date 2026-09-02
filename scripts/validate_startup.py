from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V1 FastAPI with isolated validation storage.")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()

    os.environ["RAG_EMBEDDING_MODEL_PATH"] = str(PROJECT_ROOT / "models" / "bge-m3")
    os.environ["RAG_RERANKER_MODEL_PATH"] = str(
        PROJECT_ROOT / "models" / "bge-reranker-v2-m3"
    )
    # Keep the local startup check independent of the optional remote LLM.
    os.environ["RAG_API_BASE_URL"] = " "
    os.environ["RAG_CHAT_MODEL"] = " "
    os.environ["RAG_API_KEY"] = " "

    import app.config as config

    # Keep validation storage separate from the active local Qdrant directory.
    with tempfile.TemporaryDirectory(prefix="rag-v1-startup-") as isolated_root:
        config.PROJECT_ROOT = Path(isolated_root)
        from app.main import app
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
