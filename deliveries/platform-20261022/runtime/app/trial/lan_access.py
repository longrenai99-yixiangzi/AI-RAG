"""Loopback-only viewer gateway. Caddy owns LAN TLS and password authentication."""
import json, os, re, secrets, subprocess, uuid
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel, Field, ConfigDict

HOME = Path('D:/example-access')
UPSTREAM = 'http://127.0.0.1:8898'
TOKEN = secrets.token_urlsafe(32)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

def config():
    return json.loads((HOME/'access.json').read_text(encoding='utf-8'))

def caddyfile(username='', password_hash=''):
    ip=config()['ip']
    auth=f'basic_auth {{\n {username} {password_hash}\n }}\n' if username else ''
    handler=auth+'reverse_proxy 127.0.0.1:8890' if username else 'respond "Complete local access setup first" 503'
    storage=(HOME/'data').as_posix()
    return ('{\n admin 127.0.0.1:18919\n persist_config off\n auto_https disable_redirects\n skip_install_trust\n'
            f' storage file_system {{\n root "{storage}"\n }}\n}}\n'
            f'https://{ip}:8899 {{\n bind {ip}\n tls internal\n'
            ' @setup path /setup /setup/*\n respond @setup 404\n'
            ' header {\n X-Content-Type-Options nosniff\n X-Frame-Options DENY\n Referrer-Policy no-referrer\n Cache-Control no-store\n }\n'
            +handler+'\n}\n')

@app.middleware('http')
async def boundary(request:Request, call_next):
    if request.client and request.client.host not in {'127.0.0.1','::1','testclient'}:
        return Response(status_code=403)
    if request.method not in {'GET','HEAD'}:
        allowed={'http://127.0.0.1:8890',f"https://{config()['ip']}:8899"}
        if request.headers.get('origin') not in allowed or request.headers.get('x-viewer-request')!='1':
            return Response(status_code=403)
    if request.url.path.startswith('/setup'):
        if request.headers.get('host') not in {'127.0.0.1:8890','testserver'}:
            return Response(status_code=403)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response

def public(value):
    if isinstance(value,dict):
        return {k:public(v) for k,v in value.items() if k not in {'source_path','external_path','reference','debug','packet','body','traceback'}}
    if isinstance(value,list):return [public(v) for v in value]
    return value

async def upstream(method,path,body=None):
    try:
        async with httpx.AsyncClient(timeout=180,trust_env=False) as client:
            r=await client.request(method,UPSTREAM+path,json=body,headers={'X-Platform-Request':'1','Origin':UPSTREAM})
        if r.status_code!=200:raise HTTPException(r.status_code,'本机知识库暂未完成此操作，请稍后查看；不会自动重试。')
        return r
    except httpx.HTTPError:raise HTTPException(503,'本机知识库尚未就绪。未自动重试或追加模型调用。')

@app.get('/',response_class=HTMLResponse)
def page():return (Path(__file__).with_name('lan_viewer.html')).read_text(encoding='utf-8')

@app.get('/api/health')
async def health():
    state=(await upstream('GET','/api/platform/state')).json()
    daily=state.get('daily_model') or {}
    return {'runtime':public(state.get('runtime')), 'daily_model':{k:daily.get(k) for k in ('active','expires_at','used_requests','max_requests','reserved_cny','max_budget_cny','notice')},'access':'VIEW_AND_ASK_ONLY'}

@app.get('/api/library')
async def library(q:str='',offset:int=0):
    if len(q)>1000 or not 0<=offset<=10000:raise HTTPException(422)
    params=str(httpx.QueryParams({'q':q,'offset':offset,'limit':30}))
    return public((await upstream('GET','/api/platform/library?'+params)).json())

def source_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value):raise HTTPException(422)
    return value

@app.get('/api/evidence/{sid}')
async def evidence(sid:str):return public((await upstream('GET',f'/api/platform/library/{source_id(sid)}/evidence')).json())

@app.get('/api/page/{sid}/{number}')
async def original_page(sid:str,number:int):
    if not 1<=number<=10000:raise HTTPException(422)
    r=await upstream('GET',f'/api/platform/library/{source_id(sid)}/pages/{number}')
    return Response(r.content,media_type='image/png')

class Question(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question:str=Field(min_length=1,max_length=2000)

@app.post('/api/query')
async def query(value:Question):
    # The client cannot choose a prior request id or access the owner's history.
    body={'question':value.question,'request_id':uuid.uuid4().hex,'actor':'局域网只读用户'}
    return public((await upstream('POST','/api/platform/query',body)).json())

@app.get('/setup',response_class=HTMLResponse)
def setup():
    url=f"https://{config()['ip']}:8899"
    return f'''<!doctype html><meta charset="utf-8"><title>同事访问设置</title><style>body{{font:18px sans-serif;max-width:700px;margin:50px auto}}input,button{{padding:12px;margin:8px}}</style>
    <h1>同事只读入口设置</h1><p>局域网地址：{url}</p><p>只可查看和提问，不能管理资料或修改额度。请设置共享只读账号；密码不写入对话或日志。</p>
    <input id="u" placeholder="账号：英文字母、数字或下划线" autocomplete="username"><input id="p" type="password" placeholder="密码至少12位" autocomplete="new-password"><button onclick="save()">设置或更换账号</button><p id="m"></p>
    <p><a href="/setup/certificate">下载局域网根证书（公开证书）</a>，其他设备首次访问需导入信任。不要分享本机管理入口。</p>
    <p>本机管理：<a href="http://127.0.0.1:8898/manage?tab=query">打开知识库</a>。本机需保持开机联网，Windows登录后自动启动；地址变化需重新配置。</p>
    <script>async function save(){{let r=await fetch('/setup',{{method:'POST',headers:{{'Content-Type':'application/json','X-Viewer-Request':'1','X-Setup-Token':'{TOKEN}'}},body:JSON.stringify({{username:u.value,password:p.value}})}});p.value='';m.textContent=r.ok?'账号已生效，可在其他设备登录。':(await r.json()).detail}}</script>'''

class Account(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username:str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{2,31}$')
    password:str=Field(min_length=12,max_length=128)

@app.post('/setup')
def set_account(value:Account,request:Request):
    if not secrets.compare_digest(request.headers.get('x-setup-token',''),TOKEN):raise HTTPException(403)
    if any(ch in value.password for ch in '\r\n\0'):raise HTTPException(422,'密码不能包含换行。')
    if len(value.password.encode('utf-8'))>72:raise HTTPException(422,'密码过长，请控制在24个汉字或72个英文字符以内。')
    binary=str(HOME/'caddy.exe')
    # Caddy strips LF only; binary stdin avoids Windows text-mode CRLF translation.
    hashed=subprocess.run([binary,'hash-password','--algorithm','bcrypt'],input=value.password.encode('utf-8')+b'\n',capture_output=True,check=True,timeout=30).stdout.decode('ascii').strip()
    if not hashed.startswith('$2'):raise HTTPException(503,'密码散列失败，未启用。')
    draft=HOME/'Caddyfile.next'; draft.write_text(caddyfile(value.username,hashed),encoding='utf-8')
    result=subprocess.run([binary,'reload','--config',str(draft),'--adapter','caddyfile','--address','127.0.0.1:18919'],capture_output=True,timeout=30)
    if result.returncode:raise HTTPException(503,'加密网关尚未运行，未变更已启用账号。')
    draft.replace(HOME/'Caddyfile')
    return {'updated':True}

@app.get('/setup/certificate')
def certificate():
    roots=list((HOME/'data').rglob('pki/authorities/local/root.crt'))
    if len(roots)!=1:raise HTTPException(503,'加密网关尚未生成公开根证书。')
    return FileResponse(roots[0],filename='design-knowledge-root.crt',media_type='application/x-x509-ca-cert')
