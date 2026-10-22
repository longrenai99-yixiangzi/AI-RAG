$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$trialPath = Join-Path $repoPath 'evaluation/concise_trial_20261022'
foreach ($file in @('prepared.json','state.json','platform-dist/platform.html')) {
    if (-not (Test-Path -LiteralPath (Join-Path $trialPath $file))) { throw "独立试用缺少 $file，未启动。" }
}
if (Get-NetTCPConnection -State Listen -LocalPort 8897 -ErrorAction SilentlyContinue) { throw '8897已占用，未重复启动或替换任何服务。' }
$prepared = Get-Content -LiteralPath (Join-Path $trialPath 'prepared.json') -Raw | ConvertFrom-Json
$retrieval = Invoke-RestMethod -Uri 'http://127.0.0.1:8894/api/v2/unified/status' -TimeoutSec 10
if ($retrieval.candidate_hash -ne $prepared.candidate_hash -or $retrieval.model_http_enabled) { throw '既有检索版本或模式不符合试用约定，未启动。' }
$launch = Start-Process -FilePath (Join-Path $repoPath '.venv/Scripts/python.exe') -ArgumentList @('-m','uvicorn','app.trial.concise_trial:trial_app','--factory','--host','127.0.0.1','--port','8897','--workers','1') -WorkingDirectory $repoPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $trialPath 'server.stdout.log') -RedirectStandardError (Join-Path $trialPath 'server.stderr.log') -PassThru
@{launcher_pid=$launch.Id;started_at=(Get-Date).ToString('o');module='app.trial.concise_trial:trial_app';port=8897;repo=$repoPath} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $trialPath 'launcher.json') -Encoding UTF8
Write-Output '独立试用启动中：http://127.0.0.1:8897/manage?tab=query'
Write-Output '新入口关闭模型执行；8896、8894、8010保持，不启动或切换8000。'
