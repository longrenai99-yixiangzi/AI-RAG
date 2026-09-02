from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "internal_trial.yaml"
USERS_PATH = PROJECT_ROOT / "config" / "trial_users.yaml"


@dataclass(frozen=True, slots=True)
class TrialConfig:
    values: dict[str, Any]

    @classmethod
    def load(cls) -> "TrialConfig":
        values = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        if not isinstance(values, dict):
            raise ValueError("internal trial config must be a mapping")
        return cls(values)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    @property
    def port(self) -> int:
        return int(self.get("port", 8010))

    @property
    def host(self) -> str:
        return str(self.get("host", "127.0.0.1"))

    @property
    def root001_path(self) -> Path:
        return Path(str(self.get("root001_path", r"D:\设计管理")))

    @property
    def root002_mode(self) -> str:
        return str(self.get("root002_mode", "frozen_shadow_pending_approval"))

    @property
    def root002_governance(self) -> str:
        return str(self.get("root002_governance", "PENDING_APPROVAL"))

    @property
    def shadow_index_path(self) -> Path:
        return PROJECT_ROOT / str(self.get("shadow_index_path", "data/shadow/full_corpus_qdrant"))

    @property
    def atomic_evidence_path(self) -> Path:
        return PROJECT_ROOT / str(self.get("atomic_evidence_path", "data/shadow/atomic_evidence/records.jsonl"))

    @property
    def audit_path(self) -> Path:
        return PROJECT_ROOT / str(self.get("trial_audit_path", "logs/trial/trial_audit.jsonl"))

    @property
    def feedback_path(self) -> Path:
        return PROJECT_ROOT / str(self.get("trial_feedback_path", "data/trial_feedback"))

    @property
    def pid_path(self) -> Path:
        return PROJECT_ROOT / str(self.get("trial_pid_path", "logs/trial/trial_service.pid"))

    @property
    def approved_shadow_sources(self) -> list[dict[str, str]]:
        values = self.get("approved_shadow_sources", [])
        if not isinstance(values, list):
            return []
        rows: list[dict[str, str]] = []
        for value in values:
            if isinstance(value, dict) and value.get("path"):
                row = {
                    "path": str(value["path"]),
                    "approval_status": str(value.get("approval_status", "USER_APPROVED_SHADOW_READ")),
                }
                if value.get("cache_path"):
                    row["cache_path"] = str(value["cache_path"])
                rows.append(row)
            elif isinstance(value, str):
                rows.append({"path": value, "approval_status": "USER_APPROVED_SHADOW_READ"})
        return rows


def load_users() -> dict[str, dict[str, str]]:
    values = yaml.safe_load(USERS_PATH.read_text(encoding="utf-8")) or {}
    users = values.get("users", []) if isinstance(values, dict) else []
    return {
        str(user["user_id"]): {
            "user_id": str(user["user_id"]),
            "display_name": str(user.get("display_name", user["user_id"])),
            "role": str(user.get("role", "BUSINESS_REVIEWER")),
        }
        for user in users
        if isinstance(user, dict) and user.get("user_id")
    }
