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

# Refresh provider settings changed after the Codex desktop process started.
foreach ($name in 'RAG_API_KEY', 'RAG_API_BASE_URL', 'RAG_CHAT_MODEL') {
    $value = [Environment]::GetEnvironmentVariable($name, 'User')
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

# Defensive: collapse duplicated case-variant environment variables.
# Windows PowerShell 5.1's Start-Process builds a case-INsensitive environment
# dictionary and raises "已添加项。字典中的关键字:..." when the process block
# carries both PATH and Path / HTTP_PROXY and http_proxy (some agent/IDE shells
# inject case-variant twins). Keep exactly one entry per name; the duplicated
# values are identical, so behavior is unchanged.
$duplicateEnvironmentNames = @(
    [Environment]::GetEnvironmentVariables('Process').Keys |
        Group-Object { $_.ToUpperInvariant() } |
        Where-Object { $_.Count -gt 1 } |
        ForEach-Object { $_.Group[0] }
)
foreach ($duplicateName in $duplicateEnvironmentNames) {
    [Environment]::SetEnvironmentVariable($duplicateName, $null, 'Process')
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "V1 Python environment not found: $pythonPath"
}

# Reuse a healthy trial service, or wait for the previous trial process to
# release the port after a stop/start cycle. Never take over an unknown owner.
for ($waitIndex = 0; $waitIndex -lt 15; $waitIndex++) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort 8010 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $listener) { break }
    $listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if ($null -eq $listenerProcess -or $listenerProcess.CommandLine -notmatch 'app\.trial\.main:app') {
        throw 'STARTUP_BLOCKED: port 8010 is not owned by the V1 Internal Trial Service.'
    }
    try {
        $existingHealth = Invoke-WebRequest -Uri "http://${healthHost}:8010/api/health" -UseBasicParsing -TimeoutSec 2
        if ($existingHealth.StatusCode -eq 200) {
            Start-Process "http://${healthHost}:8010/knowledge-os" | Out-Null
            Write-Output 'Internal Trial Service is already ready on localhost port 8010.'
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 1
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
        $warmup = Invoke-RestMethod -Uri "http://${healthHost}:8010/api/v2/warmup" -Method Post -UseBasicParsing -TimeoutSec 600
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

Start-Process "http://${healthHost}:8010/knowledge-os" | Out-Null
Write-Output 'Internal Trial Service is ready on localhost port 8010.'
