$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $projectRoot 'logs\trial\trial_service.pid'

$listener = Get-NetTCPConnection -State Listen -LocalPort 8010 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $listener) {
    $pidValue = [int]$listener.OwningProcess
} elseif (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Output 'Internal Trial Service is not running.'
    exit 0
} else {
    $pidValue = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
    if ($null -ne (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
        # A stale PID with no listener is not a reason to kill an unknown process.
        throw 'STOP_BLOCKED: trial PID has no 8010 listener; formal services were not touched.'
    }
    Remove-Item -LiteralPath $pidPath -Force
    Write-Output 'Removed stale Internal Trial PID file; no service process was running.'
    exit 0
}
$trialProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'app\.trial\.main:app' -and $_.CommandLine -match '--port\s+8010(?:\s|$)'
})
if ($trialProcesses.Count -eq 0 -or -not ($trialProcesses | Where-Object { $_.ProcessId -eq $pidValue })) {
    throw 'STOP_BLOCKED: PID is not the V1 Internal Trial Service; formal services were not touched.'
}

# The Windows launcher can retain a parent python process which respawns the
# uvicorn child after the listener is stopped. Stop every process in the
# explicitly-scoped 8010 trial group so a restart really reloads the pointer.
foreach ($trialProcess in ($trialProcesses | Sort-Object ProcessId -Descending)) {
    Stop-Process -Id $trialProcess.ProcessId -Force -ErrorAction SilentlyContinue
}
Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
Write-Output 'Only the Internal Trial Service on port 8010 was stopped.'
