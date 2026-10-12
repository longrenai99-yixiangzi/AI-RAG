import importlib.util
import json
from pathlib import Path

import pytest


def load_entry():
    path = Path(__file__).resolve().parents[2] / 'deployment/private_package/start_release.py'
    spec = importlib.util.spec_from_file_location('synthetic_release_entry', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_formal_entry_rejects_incomplete_authorization(tmp_path):
    module = load_entry()
    auth = tmp_path / 'authorization.json'
    auth.write_text(json.dumps({'deployment_authorized': True}), encoding='utf-8')
    with pytest.raises(SystemExit, match='AUTHORIZATION_SCOPE_MISMATCH'):
        module.require_authorization(auth, {'package_manifest_sha256': 'synthetic'})


def test_precheck_does_not_mark_service_as_authorized(monkeypatch):
    module = load_entry()
    monkeypatch.delenv('RAG_RELEASE_AUTHORIZED', raising=False)
    monkeypatch.setattr('sys.argv', ['start_release.py'])
    monkeypatch.setattr(module, 'precheck', lambda: {'errors': [], 'serve_performed': False})
    monkeypatch.setattr(module, 'require_authorization', lambda *_: pytest.fail('precheck must not authorize serving'))
    assert module.main() == 0
    assert 'RAG_RELEASE_AUTHORIZED' not in module.os.environ
