from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # Windows-only fallback for processes started before User variables were refreshed.
    import winreg
except ImportError:  # pragma: no cover - keeps local tests portable.
    winreg = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENTAL_ROOTS = (
    Path(r"D:\工作\设计支持中心\局制度文件"),
    Path(r"D:\工作\二公司技术部\2026\知识库\价值创造点清单"),
)


def _user_environment_value(name: str) -> str | None:
    """Read a Windows User environment value without printing it."""
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value).strip() or None


def _setting(name: str, default: str = "") -> str:
    return (os.getenv(name) or _user_environment_value(name) or default).strip()


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(_setting(name, str(default)))
        return value if value > 0 else default
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    data_root: Path
    model_root: Path
    vault_root: Path
    api_base_url: str
    chat_model: str
    api_key: str
    embedding_model: str
    reranker_model: str
    reranker_mode: str
    max_local_chunks: int
    max_file_size_mb: int

    @property
    def database_path(self) -> Path:
        return self.data_root / "index.sqlite3"

    @property
    def qdrant_path(self) -> Path:
        return self.data_root / "qdrant"

    @property
    def bm25_path(self) -> Path:
        return self.data_root / "indexes" / "bm25.json"

    @property
    def report_root(self) -> Path:
        return self.data_root / "reports"

    @property
    def routing_policy_path(self) -> Path:
        return self.project_root / "config" / "retrieval_routing.yaml"

    @property
    def cache_root(self) -> Path:
        return self.data_root / "cache" / "huggingface"

    @property
    def supplemental_roots(self) -> tuple[Path, ...]:
        return SUPPLEMENTAL_ROOTS

    @property
    def embedding_model_path(self) -> Path:
        return self.model_root / "bge-m3"

    @property
    def reranker_model_path(self) -> Path:
        return self.model_root / "bge-reranker-v2-m3"

    @property
    def api_ready(self) -> bool:
        return bool(self.api_base_url and self.chat_model and self.api_key)

    @classmethod
    def load(cls) -> "Settings":
        data_root = PROJECT_ROOT / "data"
        return cls(
            project_root=PROJECT_ROOT,
            data_root=data_root,
            model_root=PROJECT_ROOT / "models",
            vault_root=Path(_setting("RAG_VAULT_PATH", r"D:\设计管理")),
            api_base_url=_setting("RAG_API_BASE_URL").rstrip("/"),
            chat_model=_setting("RAG_CHAT_MODEL"),
            api_key=_setting("RAG_API_KEY"),
            # V0.1 locks vector dimensions to BGE-M3's 1024 dimensions.
            embedding_model="BAAI/bge-m3",
            reranker_model="BAAI/bge-reranker-v2-m3",
            reranker_mode=_setting("RAG_ENABLE_RERANKER", "auto").lower(),
            max_local_chunks=_positive_int("RAG_MAX_LOCAL_CHUNKS", 18_000),
            max_file_size_mb=_positive_int("RAG_MAX_FILE_SIZE_MB", 150),
        )

    def ensure_runtime_directories(self) -> None:
        for path in (
            self.data_root,
            self.bm25_path.parent,
            self.report_root,
            self.cache_root,
            self.embedding_model_path,
            self.reranker_model_path,
        ):
            path.mkdir(parents=True, exist_ok=True)
