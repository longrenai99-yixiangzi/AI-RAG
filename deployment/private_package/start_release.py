from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import importlib.metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = Path(os.environ.get('RAG_RELEASE_TARGET', str(ROOT)))
HASH = "3626608a3d853f7bd1b107c35046a1098c2c025dbd1c883f157c4e952084f37b"
MODELS = Path(os.environ.get('RAG_EMBEDDING_MODEL_PATH', str(ROOT / 'models' / 'bge-m3')))


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def precheck():
    manifest_path = ROOT / "PACKAGE_MANIFEST_PRIVATE.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    if not manifest.get("files") or manifest.get("candidate_hash") != HASH:
        errors.append("PACKAGE_MANIFEST_EMPTY_OR_WRONG_CANDIDATE")
    for row in manifest["files"]:
        path = (ROOT / row["path"]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or sha(path) != row["sha256"]:
            errors.append(row["path"])
    for row in manifest.get("external_read_only_files", []):
        path = Path(row["path"])
        if not path.is_file() or sha(path) != row["sha256"]:
            errors.append("EXTERNAL_DEPENDENCY_CHANGED:" + row["path"])
    for name, version in manifest.get("installed_dependencies", {}).items():
        if importlib.metadata.version(name) != version:
            errors.append("INSTALLED_DEPENDENCY_CHANGED:" + name)
    if not MODELS.is_dir() or not (MODELS / "config.json").is_file():
        errors.append("LOCAL_EMBEDDING_MODEL_MISSING")
    result = {"status": "PASS" if not errors else "BLOCKED", "candidate_hash": HASH, "files_checked": len(manifest["files"]), "errors": errors, "package_manifest_sha256": sha(manifest_path), "serve_performed": False}
    return result


def require_authorization(path, check):
    auth = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    expected = {"deployment_authorized": True, "owned_service_stop_and_state_restore_authorized": True, "candidate_hash": HASH, "package_manifest_sha256": check["package_manifest_sha256"], "host": "127.0.0.1", "port": 8000, "deployment_target": str(TARGET), "state_write_root": str(TARGET / "runtime/mutable"), "log_write_root": str(TARGET / "logs"), "backup_write_root": str(TARGET / "backups"), "formal_legacy_qdrant_write": False, "formal_legacy_sqlite_write": False, "source_writeback": False}
    if any(auth.get(key) != value for key, value in expected.items()):
        raise SystemExit("AUTHORIZATION_SCOPE_MISMATCH")
    if ROOT.resolve() != TARGET.resolve():
        raise SystemExit("SERVE_ONLY_FROM_APPROVED_DEPLOYMENT_TARGET")


def main():
    parser = argparse.ArgumentParser(description="Default is read-only precheck; serving requires a separately authorized copied target.")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--authorization-file")
    args = parser.parse_args()
    check = precheck()
    if check["errors"]:
        print(json.dumps(check, ensure_ascii=False))
        return 2
    if not args.serve:
        print(json.dumps(check, ensure_ascii=False))
        return 0
    if not args.authorization_file:
        raise SystemExit("SEPARATE_DEPLOYMENT_AUTHORIZATION_REQUIRED")
    require_authorization(args.authorization_file, check)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            raise SystemExit("8000_OCCUPIED_DO_NOT_STOP_UNRELATED_SERVICE")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["OMP_NUM_THREADS"] = "4"
    os.environ["MKL_NUM_THREADS"] = "4"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    os.environ["RAG_EMBEDDING_MODEL_PATH"] = str(MODELS)
    runtime = ROOT / "runtime"
    os.chdir(runtime)
    sys.path.insert(0, str(runtime))
    import uvicorn
    from release_adapter import create_app
    uvicorn.run(create_app(), host="127.0.0.1", port=8000, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
