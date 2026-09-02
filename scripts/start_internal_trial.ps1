$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$readinessScript = Join-Path $PSScriptRoot 'trial_readiness_check.py'
$pidPath = Join-Path $projectRoot 'logs\trial\trial_service.pid'
$logDir = Join-Path $projectRoot 'logs\trial'
$stdoutLog = Join-Path $logDir 'trial_service.stdout.log'
$stderrLog = Join-Path $logDir 'trial_service.stderr.log'
$hostAddress = '127.0.0.1'
$healthHost = '127.0.0.1'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "V1 Python environment not found: $pythonPath"
}

& $pythonPath $readinessScript
if ($LASTEXITCODE -ne 0) {
    throw 'STARTUP_BLOCKED: Trial readiness check failed.'
}

$arguments = @('-m', 'uvicorn', 'app.trial.main:app', '--host', $hostAddress, '--port', '8010')
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pidPath) | Out-Null
$process = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru

$ready = $false
for ($index = 0; $index -lt 90; $index++) {
    try {
        $health = Invoke-WebRequest -Uri "http://${healthHost}:8010/api/health" -UseBasicParsing -TimeoutSec 2
        if ($health.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $ready) {
    if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
        Stop-Process -Id $process.Id -Force
    }
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    throw 'Trial Service did not become ready on port 8010.'
}

$v2Config = Get-Content -LiteralPath (Join-Path $projectRoot 'config\internal_trial.yaml') -Raw
if ($v2Config -match 'V2_VERIFIED_RAG_ENABLED:\s*true') {
    try {
        $warmup = Invoke-RestMethod -Uri "http://${healthHost}:8010/api/v2/warmup" -Method Post -UseBasicParsing -TimeoutSec 75
        if (-not $warmup.ready) { throw 'V2 warmup returned not ready.' }
    } catch {
        if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
            Stop-Process -Id $process.Id -Force
        }
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        throw "STARTUP_BLOCKED: V2 local model warmup failed. $($_.Exception.Message)"
    }
}

$listener = Get-NetTCPConnection -State Listen -LocalPort 8010 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $listener) {
    throw 'Trial Service reported ready but no process is listening on port 8010.'
}
$listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
if ($null -eq $listenerProcess -or $listenerProcess.CommandLine -notmatch 'app\.trial\.main:app') {
    throw 'STARTUP_BLOCKED: port 8010 is not owned by the V1 Internal Trial Service.'
}
Set-Content -LiteralPath $pidPath -Value $listener.OwningProcess -Encoding ascii

Start-Process "http://${healthHost}:8010/v2-trial" | Out-Null
Write-Output 'Internal Trial Service is ready on localhost port 8010.'
