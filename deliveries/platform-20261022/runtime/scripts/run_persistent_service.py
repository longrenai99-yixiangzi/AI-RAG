"""Windows scheduled-task entry; never depends on Codex process lifetime."""
import os,subprocess,sys,traceback
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
home=Path('D:/example-access')
role=sys.argv[1]
commands={
 'knowledge':[repo/'.venv-gpu/Scripts/python.exe','-m','uvicorn','app.trial.candidate_platform:trial_app','--factory','--host','127.0.0.1','--port','8898','--workers','1','--no-proxy-headers'],
 'viewer':[repo/'.venv/Scripts/python.exe','-m','uvicorn','app.trial.lan_access:app','--host','127.0.0.1','--port','8890','--workers','1','--no-proxy-headers','--no-access-log'],
 'tls':[home/'caddy.exe','run','--config',home/'Caddyfile','--adapter','caddyfile'],
}
try:
    with (home/(role+'.stdout.log')).open('ab') as out,(home/(role+'.stderr.log')).open('ab') as err:
        result=subprocess.run([str(x) for x in commands[role]],cwd=repo,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(result.returncode)
except Exception:
    (home/(role+'.launcher_error.log')).write_text(traceback.format_exc(),encoding='utf-8')
    sys.exit(1)
