$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$trialPath = Join-Path $repoPath 'evaluation/concise_trial_20261022'
$expectedHash = (Get-Content -LiteralPath (Join-Path $trialPath 'prepared.json') -Raw -Encoding UTF8 | ConvertFrom-Json).candidate_hash

function Assert-OwnedListener([int]$Port, [string]$Module, [string]$Runtime) {
    foreach ($listener in @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
        $child = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($child.ParentProcessId)"
        $python = Join-Path $repoPath "$Runtime/Scripts/python.exe"
        $pattern = '-m uvicorn ' + [regex]::Escape($Module) + ' .*--port ' + $Port + '(\s|$)'
        $direct = $child.ExecutablePath -eq $python
        $related = $parent -and $parent.ExecutablePath -eq $python -and $parent.CommandLine -match $pattern -and
            [Math]::Abs(($child.CreationDate-$parent.CreationDate).TotalSeconds) -le 3
        if ($child.CommandLine -notmatch $pattern -or -not ($direct -or $related)) { throw "$Port 由其他服务占用，未替换或结束进程。" }
    }
}

Assert-OwnedListener 8894 'app.trial.unified_preview:app' '.venv-gpu'
if (-not (Get-NetTCPConnection -State Listen -LocalPort 8894 -ErrorAction SilentlyContinue)) {
    $python = Join-Path $repoPath '.venv-gpu/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw '现有检索环境缺失，未创建替代环境。' }
    $pending = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match '-m uvicorn app\.trial\.unified_preview:app .*--port 8894(\s|$)' })
    if ($pending.Count) { throw '检索进程已经启动但尚未监听，请稍后检查。' }
    $logs = Join-Path $repoPath 'evaluation/platform_existing_content_20261021'
    $launch = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.trial.unified_preview:app','--host','127.0.0.1','--port','8894') -WorkingDirectory $repoPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'retrieval.stdout.log') -RedirectStandardError (Join-Path $logs 'retrieval.stderr.log') -PassThru
    $launch.Id | Set-Content -LiteralPath (Join-Path $logs 'retrieval_launcher.pid')
    Write-Output '正在加载已有检索索引，未解析资料或调用公网模型。'
}
$retrieval = $null
for ($attempt=0; $attempt -lt 60; $attempt++) {
    try { $retrieval = Invoke-RestMethod -Uri 'http://127.0.0.1:8894/api/v2/unified/status' -TimeoutSec 2; break } catch { Start-Sleep -Seconds 1 }
}
if ($retrieval.candidate_hash -ne $expectedHash -or $retrieval.model_http_enabled) { throw '检索尚未就绪或索引身份不符。' }
Assert-OwnedListener 8897 'app.trial.concise_trial:trial_app' '.venv'
if (-not (Get-NetTCPConnection -State Listen -LocalPort 8897 -ErrorAction SilentlyContinue)) {
    $pending = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match '-m uvicorn app\.trial\.concise_trial:trial_app .*--port 8897(\s|$)' })
    if ($pending.Count) { throw '日常入口已经启动但尚未监听，请稍后检查。' }
    & (Join-Path $repoPath 'scripts/start_concise_trial.ps1')
}
$ready = $false
for ($attempt=0; $attempt -lt 20; $attempt++) {
    try { $state = Invoke-RestMethod -Uri 'http://127.0.0.1:8897/api/platform/state' -TimeoutSec 2; $ready=$state.runtime.ready; if ($ready) { break } } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ready -or $state.runtime.candidate_hash -ne $expectedHash -or -not $state.daily_model -or $state.capabilities.generation_execution_enabled) { throw '日常入口尚未就绪或运行模式不符。' }
Write-Output '知识库日常入口已就绪：http://127.0.0.1:8897/manage?tab=query'
