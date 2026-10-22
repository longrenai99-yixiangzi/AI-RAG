$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$retrievalUrl = 'http://127.0.0.1:8894/api/v2/unified/status'
$retrievalListener = Get-NetTCPConnection -State Listen -LocalPort 8894 -ErrorAction SilentlyContinue
if (-not $retrievalListener -or -not (Get-Process -Id $retrievalListener.OwningProcess -ErrorAction SilentlyContinue)) {
    $retrievalPython = Join-Path $repoPath '.venv-gpu\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $retrievalPython)) { throw '现有检索运行环境缺失，未启动替代环境。' }
    $retrievalProcess = Start-Process -FilePath $retrievalPython -ArgumentList @('-m','uvicorn','app.trial.unified_preview:app','--host','127.0.0.1','--port','8894') -WorkingDirectory $repoPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'retrieval.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'retrieval.stderr.log') -PassThru
    $retrievalProcess.Id | Set-Content (Join-Path $PSScriptRoot 'retrieval_launcher.pid')
    Write-Output '正在加载已有知识索引，未解析新资料。'
}
$retrievalStatus = $null
for ($attempt = 0; $attempt -lt 180; $attempt++) {
    if ($retrievalProcess -and $retrievalProcess.HasExited -and $retrievalProcess.ExitCode -ne 0) { throw '检索进程启动失败，请查看 evaluation/platform_existing_content_20261021/retrieval.stderr.log；未改动索引。' }
    try { $retrievalStatus = Invoke-RestMethod -Uri $retrievalUrl -TimeoutSec 3; break } catch { Start-Sleep -Seconds 1 }
}
if (-not $retrievalStatus.candidate_hash -or -not $retrievalStatus.same_candidate_for_sources_and_retrieval) { throw '现有检索服务尚未就绪，未切换索引或占用其他端口。' }
$platformListener = Get-NetTCPConnection -State Listen -LocalPort 8896 -ErrorAction SilentlyContinue
if (-not $platformListener -or -not (Get-Process -Id $platformListener.OwningProcess -ErrorAction SilentlyContinue)) {
    & (Join-Path $repoPath 'evaluation\platform_workbench_20261021\start.ps1')
}
$platformStatus = $null
for ($attempt = 0; $attempt -lt 10; $attempt++) {
    try { $platformStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8896/api/platform/state' -TimeoutSec 5; break } catch { Start-Sleep -Seconds 1 }
}
if ($platformStatus.mode -ne 'EXISTING_CONTENT_TRIAL' -or $platformStatus.runtime.candidate_hash -ne $retrievalStatus.candidate_hash) { throw '工作台尚未连接到同一套现有知识索引，请检查端口及日志。' }
Write-Output '知识库工作版已就绪：http://127.0.0.1:8896/manage'
Write-Output '可浏览现有资料、问答及引用，记录反馈和管理审核知识。连续公网生成没有开启。'
