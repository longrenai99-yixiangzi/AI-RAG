$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$pythonPath = Join-Path $repoPath '.venv\Scripts\python.exe'
$listener = Get-NetTCPConnection -State Listen -LocalPort 8896 -ErrorAction SilentlyContinue
if ($listener -and (Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue)) { throw '8896 端口已被占用。请检查现有进程，不要重复启动。' }
$launch = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.trial.platform_app:live_app', '--factory', '--host', '127.0.0.1', '--port', '8896', '--workers', '1') -WorkingDirectory $repoPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server.stderr.log') -PassThru
$launch.Id | Set-Content (Join-Path $PSScriptRoot 'launcher.pid')
Write-Output '管理工作台启动中：http://127.0.0.1:8896/manage'
