param([ValidateSet('Start','Stop','Status')][string]$Action = 'Status')
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$baseUrl = 'http://127.0.0.1:8897'
$trialPath = Join-Path $repoPath 'evaluation/concise_trial_20261022'
$expectedHash = (Get-Content -LiteralPath (Join-Path $trialPath 'prepared.json') -Raw -Encoding UTF8 | ConvertFrom-Json).candidate_hash

function Get-OwnedProcesses {
    $eligible = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -and
        $_.CommandLine -match '-m uvicorn app\.trial\.concise_trial:trial_app .*--port 8897(\s|$)'
    })
    $processes = @($eligible | Where-Object { $_.ExecutablePath -eq (Join-Path $repoPath '.venv/Scripts/python.exe') })
    # A venv launcher can spawn the shared Python runtime; require its verified parent and exact arguments.
    foreach ($child in $eligible) {
        $parent = $processes | Where-Object { $_.ProcessId -eq $child.ParentProcessId } | Select-Object -First 1
        if ($parent -and [Math]::Abs(($child.CreationDate-$parent.CreationDate).TotalSeconds) -le 3 -and
            $child.CommandLine.Substring($child.CommandLine.IndexOf(' -m ')) -eq $parent.CommandLine.Substring($parent.CommandLine.IndexOf(' -m '))) {
            $processes += $child
        }
    }
    return $processes
}

function Save-StatusRecord($Record) {
    try {
        $folder = Join-Path $trialPath 'health'
        [void][IO.Directory]::CreateDirectory($folder)
        $recordPath = Join-Path $folder ((Get-Date).ToString('yyyyMMdd_HHmmss_fff') + '_' + [guid]::NewGuid().ToString('N') + '.json')
        [IO.File]::WriteAllText($recordPath, ($Record | ConvertTo-Json -Depth 4))
    } catch {
        Write-Warning '本次检查记录未能保存；服务检查结论保持原状，请核对磁盘与目录权限。'
    }
}

if ($Action -eq 'Start') {
    & (Join-Path $repoPath 'scripts/start_daily_system.ps1')
}
if ($Action -eq 'Stop') {
    $owned = @(Get-OwnedProcesses)
    foreach ($port in @(8897)) {
        foreach ($listener in @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
            if ($listener.OwningProcess -notin $owned.ProcessId) { throw "$port 由其他进程占用，停止操作已取消。" }
        }
    }
    if (-not $owned.Count) { Write-Output '工作版已经停止。'; exit 0 }
    $platform = @($owned | Where-Object { $_.CommandLine -match 'concise_trial:trial_app' })
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
    Write-Output '8897日常入口已停止，资料和额度保留；共享检索8894继续运行，避免影响旧入口。'
    exit 0
}

$statusRecord = @{schema_version=1; checked_at=(Get-Date).ToString('o'); result='NOT_READY'}
try {
    $owned = @(Get-OwnedProcesses)
    foreach ($listener in @(Get-NetTCPConnection -State Listen -LocalPort 8897 -ErrorAction SilentlyContinue)) {
        if ($listener.OwningProcess -notin $owned.ProcessId) { throw '8897不属于此项目的日常入口。' }
    }
    $retrieval = Invoke-RestMethod -Uri 'http://127.0.0.1:8894/api/v2/unified/status' -TimeoutSec 10
    $state = Invoke-RestMethod -Uri "$baseUrl/api/platform/state" -TimeoutSec 15
    if ($retrieval.candidate_hash -ne $expectedHash -or $state.runtime.candidate_hash -ne $expectedHash -or
        -not $state.runtime.ready -or $retrieval.model_http_enabled -or $state.mode -ne 'EXISTING_CONTENT_TRIAL' -or
        -not $state.daily_model -or $state.capabilities.generation_execution_enabled) {
        throw '服务索引身份或运行模式不符合交付约定。'
    }
    $statusRecord['result'] = 'READY'
    $statusRecord['candidate_hash'] = $retrieval.candidate_hash
    $statusRecord['sources'] = $retrieval.sources
    $statusRecord['records'] = $retrieval.records
    $statusRecord['recent_questions_shown'] = $state.runs.Count
    $statusRecord['daily_model'] = @{active=$state.daily_model.active; policy_sha256=$state.daily_model.policy_sha256; used_requests=$state.daily_model.used_requests; reserved_cny=$state.daily_model.reserved_cny; expires_at=$state.daily_model.expires_at}
    Write-Output "工作版正常：$baseUrl/manage"
    Write-Output "现有来源 $($retrieval.sources)，索引片段 $($retrieval.records)，最近问题记录 $($state.runs.Count) 条（最多显示50条，不是历史总数）。"
    Write-Output "日常模型批准资料 $($state.daily_model.material_count) 份；本期已用 $($state.daily_model.used_requests)/$($state.daily_model.max_requests) 次，预占 $($state.daily_model.reserved_cny)/$($state.daily_model.max_budget_cny) 元（不是实际账单）。"
    if ($state.daily_model.active) {
        $expires = [DateTimeOffset]::Parse($state.daily_model.expires_at).ToOffset([TimeSpan]::FromHours(8)).ToString('yyyy-MM-dd HH:mm:ss')
        Write-Output "限额日常模型已启用，到期时间：$expires（北京时间）。"
    }
    else { Write-Output '日常模型未启用、暂停或已到期；本地检索可用，不自动续费。' }
} catch {
    $statusRecord['failure_kind'] = $_.Exception.GetType().FullName
    throw "工作版未就绪：$($_.Exception.Message) 请双击启动知识库；若仍失败，查看使用交接中的日志位置。"
} finally {
    Save-StatusRecord $statusRecord
}
