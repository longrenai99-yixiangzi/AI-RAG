$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot 'logs\trial\trial_service.pid'

if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Output 'Internal Trial Service is not running.'
    exit 0
}

$pidValue = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
$listener = Get-NetTCPConnection -State Listen -LocalPort 8010 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $listener) {
    $pidValue = [int]$listener.OwningProcess
}
$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -eq $pidValue -or $_.ParentProcessId -eq $pidValue
})
$trialProcesses = @($processes | Where-Object { $_.CommandLine -match 'app\.trial\.main:app' })
if ($trialProcesses.Count -eq 0 -or -not ($processes | Where-Object { $_.ProcessId -eq $pidValue -and $_.CommandLine -match 'app\.trial\.main:app' })) {
    throw 'STOP_BLOCKED: PID is not the V1 Internal Trial Service; formal services were not touched.'
}

foreach ($trialProcess in ($trialProcesses | Sort-Object ParentProcessId -Descending)) {
    Stop-Process -Id $trialProcess.ProcessId -Force -ErrorAction SilentlyContinue
}
Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $pidPath -Force
Write-Output 'Only the Internal Trial Service on port 8010 was stopped.'
