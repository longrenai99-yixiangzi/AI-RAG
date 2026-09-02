param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HistoricalEnvName = [char]0x8bbe + [char]0x8ba1 + [char]0x7ba1 + [char]0x7406 + [char]0x77e5 + [char]0x8bc6 + [char]0x5e93
$Python = "D:\AI$HistoricalEnvName\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "CUDA Python environment not found: $Python"
}

Push-Location $ProjectRoot
try {
    & $Python -m scripts.check_gpu
    if ($LASTEXITCODE -ne 0) {
        throw "GPU preflight failed; service startup stopped."
    }
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
}
finally {
    Pop-Location
}
