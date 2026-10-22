$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOutput = Join-Path $taskRoot 'evaluation\browser_trial_20261019'
$taskPending = Get-ChildItem (Join-Path $taskOutput 'jobs') -Filter state.json -Recurse -ErrorAction SilentlyContinue | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json } | Where-Object { $_.status -in @('queued','running') }
if ($taskPending) { throw '仍有试用问题在执行，未停止。请等任务结束后再停止。' }
$taskListener = Get-NetTCPConnection -LocalPort 8878 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $taskListener) { Write-Output '独立试用当前未运行。'; return }
$taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($taskListener.OwningProcess)"
if ($taskProcess.CommandLine -notlike '*app.trial.native_workbench:app*') { throw '端口属于其他进程，拒绝停止。' }
$taskStatus = Invoke-RestMethod 'http://127.0.0.1:8878/api/status'
if ($taskStatus.kind -ne 'ISOLATED_NATIVE_WORKBENCH') { throw '入口身份不符，拒绝停止。' }
$taskManifest = Get-Content -LiteralPath (Join-Path $taskRoot 'data\shadow\browser_trial_20261019\manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($taskStatus.candidate_hash -ne $taskManifest.candidate_hash) { throw '候选版本不同，拒绝停止其他候选服务。' }
Stop-Process -Id $taskListener.OwningProcess
Write-Output '已停止8878独立试用。问题记录保留；8010与8000未操作。'
