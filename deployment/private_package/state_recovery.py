from __future__ import annotations

import json
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path


def checkpoint(runtime, backup):
    runtime, backup = Path(runtime).resolve(), Path(backup).resolve()
    if not backup.is_relative_to(runtime.parent):
        raise ValueError("BACKUP_OUTSIDE_DEPLOYMENT_WORKSPACE")
    if backup.exists() or backup.is_relative_to(runtime / "mutable"):
        raise ValueError("BACKUP_TARGET_MUST_BE_NEW_AND_OUTSIDE_STATE")
    backup.mkdir(parents=True)
    state = runtime / "mutable"
    if state.exists() and any(file.is_symlink() for file in state.rglob("*")):
        raise ValueError("STATE_LINKS_NOT_ALLOWED")
    if state.exists():
        shutil.copytree(state, backup / "mutable")
    files = [{"path": file.relative_to(state).as_posix(), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()} for file in state.rglob("*") if file.is_file()] if state.exists() else []
    record = {"runtime": str(runtime), "state_preexisted": state.exists(), "files": files, "port8000_preexisting_listener": False, "recorded_at": datetime.now(timezone.utc).isoformat()}
    (backup / "checkpoint.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def restore(runtime, backup):
    runtime, backup = Path(runtime).resolve(), Path(backup).resolve()
    if not backup.is_relative_to(runtime.parent):
        raise ValueError("BACKUP_OUTSIDE_DEPLOYMENT_WORKSPACE")
    record = json.loads((backup / "checkpoint.json").read_text(encoding="utf-8"))
    if record["runtime"] != str(runtime):
        raise ValueError("CHECKPOINT_RUNTIME_MISMATCH")
    for row in record["files"]:
        file = (backup / "mutable" / row["path"]).resolve()
        if not file.is_relative_to(backup / "mutable") or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("CHECKPOINT_STATE_HASH_MISMATCH")
    state = runtime / "mutable"
    archived = backup / "after_failure"
    if not state.resolve().is_relative_to(runtime) or not archived.resolve().is_relative_to(backup) or state.is_symlink() or state.is_junction():
        raise ValueError("RECOVERY_PATH_OUTSIDE_APPROVED_STATE")
    if archived.exists():
        raise ValueError("RECOVERY_ALREADY_USED_CREATE_NEW_CHECKPOINT")
    if state.exists():
        shutil.move(str(state), str(archived))
    if record["state_preexisted"]:
        shutil.copytree(backup / "mutable", state)
    return {"state_restored": True, "failed_state_preserved": archived.exists(), "prior_port_state": "STOPPED", "service_restart_performed": False}
