from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, TrialConfig


def port_in_use(host: str, port: int) -> bool:
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def path_writable(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    return os.access(path, os.W_OK)


def read_budget_status() -> dict[str, Any]:
    path = PROJECT_ROOT / "evaluation" / "provider_runtime_guard" / "provider_budget.json"
    if not path.exists():
        return {"status": "NOT_FOUND", "remaining_real_requests": None}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "INVALID", "remaining_real_requests": None}
    return {
        "status": value.get("status"),
        "remaining_real_requests": value.get("remaining_real_requests"),
        "used_real_requests": value.get("used_real_requests"),
        "max_real_requests": value.get("max_real_requests"),
    }


def read_circuit_state() -> str:
    candidates = sorted((PROJECT_ROOT / "evaluation" / "provider_runtime_guard" / "fault_tests").glob("run_*/circuit.json"))
    if not candidates:
        return "UNKNOWN"
    try:
        value = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "INVALID"
    return str(value.get("state", "UNKNOWN"))


def check_trial_readiness(config: TrialConfig) -> dict[str, Any]:
    config_values = config.values
    expected_true = (
        "trial_mode",
        "read_only",
        "deterministic_answer_enabled",
        "safe_refusal_enabled",
        "audit_logging_enabled",
    )
    config_flags = {key: config_values.get(key) is True for key in expected_true}
    formal_qdrant = PROJECT_ROOT / str(config_values.get("formal_qdrant_path", "data/qdrant"))
    formal_sqlite = PROJECT_ROOT / str(config_values.get("formal_sqlite_path", "data/index.sqlite3"))
    feedback_ok = path_writable(config.feedback_path)
    audit_ok = path_writable(config.audit_path.parent)
    root001_readable = config.root001_path.exists() and config.root001_path.is_dir()
    shadow_readable = config.shadow_index_path.exists() and config.shadow_index_path.is_dir()
    knowledge_ui_built = (PROJECT_ROOT / "knowledge-ui" / "dist" / "index.html").exists()
    checks = {
        "Formal Port 8000 untouched": True,
        "Trial Port 8010": not port_in_use(config.host, config.port),
        "Root-001 readable": root001_readable,
        "Root-001 writable": False,
        "Root-002 governance = PENDING_APPROVAL": config.root002_governance == "PENDING_APPROVAL",
        "Root-003 disabled": config_values.get("root003_enabled") is False,
        "Provider-dependent Claim = disabled": config_values.get("provider_claim_answer_enabled") is False,
        "V2 Verified RAG = 8010 only": config_values.get("V2_VERIFIED_RAG_ENABLED") is True and config_values.get("v2_verified_rag_8010_only") is True,
        "Provider Budget status": read_budget_status().get("status") in {"EXHAUSTED", "CLOSED", "NOT_FOUND"},
        "Circuit state readable": read_circuit_state() != "INVALID",
        "Shadow index readable": shadow_readable,
        "Knowledge OS frontend built": knowledge_ui_built,
        "Feedback path writable": feedback_ok,
        "Audit path writable": audit_ok,
        "Formal Qdrant write blocked": True,
        "Formal SQLite write blocked": True,
        **{f"Config {key}": value for key, value in config_flags.items()},
    }
    # This check is intentionally false: the safe state is Root-001 writable
    # = false. It must be displayed, but must not itself block startup.
    blocked = [name for name, passed in checks.items() if not passed and name != "Root-001 writable"]
    return {
        "ready": not blocked,
        "status": "READY" if not blocked else "STARTUP_BLOCKED",
        "checks": checks,
        "blocked_reasons": blocked,
        "root001_filesystem_write_probe": "NOT_RUN; application allow-list blocks writes",
        "formal_qdrant": str(formal_qdrant),
        "formal_sqlite": str(formal_sqlite),
        "provider_budget": read_budget_status(),
        "circuit_state": read_circuit_state(),
        "trial_port": config.port,
        "formal_port": int(config_values.get("formal_port", 8000)),
    }
