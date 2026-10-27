import json,re,hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.trial.platform_app import create_app

@pytest.fixture
def client(tmp_path):
    ui=tmp_path/'ui';ui.mkdir();(ui/'assets').mkdir()
    (ui/'index.html').write_text('<html>Knowledge OS framework shell</html>')
    (ui/'platform.html').write_text('<html>management workbench</html>')
    (ui/'assets/app.js').write_text('known UI asset')
    with TestClient(create_app(tmp_path/'state.json',ui_dist=ui)) as c:yield c

@pytest.mark.parametrize('path',['/','/framework','/ai','/materials','/catalog','/knowledge/design-code-02.01','/node/design-code-02.01','/sources','/search'])
def test_framework_routes_serve_original_shell_with_no_store(client,path):
    r=client.get(path);assert r.status_code==200 and 'Knowledge OS framework shell' in r.text
    assert r.headers['cache-control']=='no-store'

@pytest.mark.parametrize('path',['/manage','/manage/'])
def test_management_keeps_its_existing_entry(client,path):assert 'management workbench' in client.get(path).text

def test_api_is_not_replaced_by_html_and_assets_keep_their_bytes(client):
    assert client.get('/api/not-implemented').status_code==404
    assert client.get('/assets/app.js').text=='known UI asset'

def test_legacy_single_entry_remains_compatible(tmp_path):
    ui=tmp_path/'ui';ui.mkdir();(ui/'assets').mkdir();(ui/'platform.html').write_text('legacy entry')
    with TestClient(create_app(tmp_path/'state.json',ui_dist=ui)) as c:assert c.get('/framework').text=='legacy entry'
