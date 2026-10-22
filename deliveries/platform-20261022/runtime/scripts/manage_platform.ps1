param([ValidateSet('Start','Stop','Status')][string]$Action = 'Status')
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$baseUrl = 'http://127.0.0.1:8896'
$expectedHash = (Get-Content -LiteralPath (Join-Path $repoPath 'data/shadow/unified_entry_20261020_r1/manifest.json') -Raw | ConvertFrom-Json).candidate_hash

function Get-OwnedProcesses {
    $eligible = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -and
        ($_.CommandLine -match '-m uvicorn app\.trial\.unified_preview:app .*--port 8894(\s|$)' -or
         $_.CommandLine -match '-m uvicorn app\.trial\.platform_app:live_app .*--port 8896(\s|$)')
    })
    $processes = @($eligible | Where-Object { $_.CommandLine.Contains($repoPath) })
    # A venv launcher can spawn the shared Python runtime; require its verified parent and exact arguments.
    foreach ($child in $eligible) {
        $parent = $processes | Where-Object { $_.ProcessId -eq $child.ParentProcessId } | Select-Object -First 1
        if ($parent -and $child.CommandLine.Substring($child.CommandLine.IndexOf(' -m ')) -eq $parent.CommandLine.Substring($parent.CommandLine.IndexOf(' -m '))) {
            $processes += $child
        }
    }
    return $processes
}

if ($Action -eq 'Start') {
    & (Join-Path $repoPath 'evaluation/platform_existing_content_20261021/start_system.ps1')
}
if ($Action -eq 'Stop') {
    $owned = @(Get-OwnedProcesses)
    foreach ($port in @(8896,8894)) {
        foreach ($listener in @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
            if ($listener.OwningProcess -notin $owned.ProcessId) { throw "$port 由其他进程占用，停止操作已取消。" }
        }
    }
    if (-not $owned.Count) { Write-Output '工作版已经停止。'; exit 0 }
    $platform = @($owned | Where-Object { $_.CommandLine -match 'platform_app:live_app' })
    if ($platform.Count) {
        $state = Invoke-RestMethod -Uri "$baseUrl/api/platform/state" -TimeoutSec 15
        if (@($state.runs | Where-Object { $_.status -eq 'RUNNING' }).Count -or
            @($state.jobs | Where-Object { $_.status -in @('QUEUED','PROCESSING') }).Count -or
            @($state.generations | Where-Object { $_.status -eq 'EXECUTING' }).Count) {
            throw '仍有任务执行中，请等待结束后再停止。'
        }
        $backup = Invoke-RestMethod -Uri "$baseUrl/api/platform/backups" -Method Post -ContentType 'application/json' -Headers @{'X-Platform-Request'='1'} -Body '{"actor":"local-stop-backup"}' -TimeoutSec 60
        Write-Output "停止前备份已保存：$($backup.backup_id)"
    }
    # Stop only verified workbench processes; never stop by a port alone.
    foreach ($item in @($owned | Sort-Object @{Expression={if ($_.CommandLine -match 'platform_app') {0} else {1}}})) {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($item.ProcessId)"
        if ($current -and $current.CommandLine -eq $item.CommandLine -and $current.CreationDate -eq $item.CreationDate) {
            Stop-Process -Id $item.ProcessId -ErrorAction Stop
        }
    }
    Write-Output '工作版已停止，资料和记录保留。'
    exit 0
}

try {
    $retrieval = Invoke-RestMethod -Uri 'http://127.0.0.1:8894/api/v2/unified/status' -TimeoutSec 10
    $state = Invoke-RestMethod -Uri "$baseUrl/api/platform/state" -TimeoutSec 15
    if ($retrieval.candidate_hash -ne $expectedHash -or $state.runtime.candidate_hash -ne $expectedHash -or
        -not $state.runtime.ready -or $retrieval.model_http_enabled -or $state.mode -ne 'EXISTING_CONTENT_TRIAL') {
        throw '服务索引身份或运行模式不符合交付约定。'
    }
    Write-Output "工作版正常：$baseUrl/manage"
    Write-Output "现有来源 $($retrieval.sources)，索引片段 $($retrieval.records)，问题记录 $($state.runs.Count)。"
    Write-Output '本机单用户；连续公网模型未开启。模型整理须逐次审查与批准。'
} catch {
    throw "工作版未就绪：$($_.Exception.Message) 请双击启动知识库；若仍失败，查看使用交接中的日志位置。"
}
