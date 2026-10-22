$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOutput = Join-Path $taskRoot 'evaluation\browser_trial_20261019'
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskExisting = Get-NetTCPConnection -LocalPort 8878 -State Listen -ErrorAction SilentlyContinue
if ($taskExisting) {
    $taskStatus = Invoke-RestMethod 'http://127.0.0.1:8878/api/status'
    if ($taskStatus.kind -ne 'ISOLATED_NATIVE_WORKBENCH') { throw '8878已被其他服务使用，未替换。' }
    $taskManifest = Get-Content -LiteralPath (Join-Path $taskRoot 'data\shadow\browser_trial_20261019\manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($taskStatus.candidate_hash -ne $taskManifest.candidate_hash) { throw '当前8878候选版本不同，未替换或重新启动。' }
    Write-Output '独立试用已运行：http://127.0.0.1:8878/'
    return
}
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Start-Process -FilePath $taskPython -ArgumentList '-B','-m','uvicorn','app.trial.native_workbench:app','--host','127.0.0.1','--port','8878' -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskOutput "server-$taskStamp.stdout.log") -RedirectStandardError (Join-Path $taskOutput "server-$taskStamp.stderr.log") | Out-Null
Write-Output '正在启动独立试用：http://127.0.0.1:8878/ 。8010与8000未作切换。'
