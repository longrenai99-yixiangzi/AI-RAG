import importlib.util,json
from pathlib import Path
import httpx,pytest
from fastapi.testclient import TestClient

@pytest.fixture
def gateway(tmp_path,monkeypatch):
    from app.trial import lan_access as m
    monkeypatch.setattr(m,'HOME',tmp_path)
    (tmp_path/'access.json').write_text(json.dumps({'ip':'192.0.2.10'}))
    calls=[]
    async def fake(method,path,body=None):
        calls.append((method,path,body))
        return httpx.Response(200,json={'result':{'answer':'答复','citations':[{'source_path':'D:/private','excerpt':'原文'}]},'source_path':'D:/private'})
    monkeypatch.setattr(m,'upstream',fake)
    with TestClient(m.app) as c:yield c,m,calls

@pytest.mark.parametrize('method,path',[
 ('get','/api/platform/state'),('get','/api/platform/export'),('get','/api/platform/backups'),
 ('get','/api/platform/runs/QR_123'),('post','/api/platform/sources'),('post','/api/platform/daily-model-policy'),
 ('post','/api/platform/generation-preview'),('get','/api/platform/library/SRC_x/original'),
 ('get','/api/library/../../setup'),('delete','/api/library'),
])
def test_forbidden_routes(gateway,method,path):
    c,m,calls=gateway
    r=c.request(method,path,headers={'host':'192.0.2.10:8899','origin':'https://192.0.2.10:8899','x-viewer-request':'1'})
    assert r.status_code in {403,404,405} and not calls

def test_query_is_new_readonly_and_redacted(gateway):
    c,m,calls=gateway
    headers={'origin':'https://192.0.2.10:8899','x-viewer-request':'1'}
    for _ in range(2):
        r=c.post('/api/query',json={'question':'业务问题'},headers=headers)
        assert r.status_code==200 and 'D:/private' not in r.text
    assert calls[0][2]['actor']=='局域网只读用户' and calls[0][2]['request_id']!=calls[1][2]['request_id']
    assert c.post('/api/query',json={'question':'问题','actor':'管理员'},headers=headers).status_code==422

def test_csrf_and_local_setup(gateway):
    c,m,calls=gateway
    assert c.post('/api/query',json={'question':'问题'},headers={'origin':'https://evil.example','x-viewer-request':'1'}).status_code==403
    assert c.get('/setup',headers={'host':'192.0.2.10:8899'}).status_code==403
    assert c.post('/setup',json={'username':'viewer','password':'long-test-password'},headers={'host':'127.0.0.1:8890','origin':'http://127.0.0.1:8890','x-viewer-request':'1'}).status_code==403
    assert not calls

def test_fail_closed_config(gateway):
    c,m,calls=gateway
    assert '503' in m.caddyfile() and 'reverse_proxy' not in m.caddyfile()
    authenticated=m.caddyfile('viewer','$2a$hash')
    assert 'basic_auth' in authenticated and 'respond @setup 404' in authenticated
    assert 'persist_config off' in authenticated

def test_password_stdin_and_no_command_line_secret(gateway,monkeypatch):
    from types import SimpleNamespace
    c,m,calls=gateway
    commands=[]
    def run(args,**kwargs):
        commands.append((args,kwargs))
        return SimpleNamespace(stdout=b'$2a$synthetic-test-hash\n',returncode=0)
    monkeypatch.setattr(m.subprocess,'run',run)
    headers={'host':'127.0.0.1:8890','origin':'http://127.0.0.1:8890','x-viewer-request':'1','x-setup-token':m.TOKEN}
    password='safe-test-password'
    assert c.post('/setup',json={'username':'viewer','password':password},headers=headers).status_code==200
    assert commands[0][1]['input']==password.encode()+b'\n'
    assert all(password not in str(args) for args,_ in commands)
    commands.clear()
    assert c.post('/setup',json={'username':'viewer','password':'汉'*30},headers=headers).status_code==422
    assert not commands
