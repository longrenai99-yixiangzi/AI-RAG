param([ValidateSet('knowledge','viewer','tls','open')][string]$Role='open')
$ErrorActionPreference='Stop'
$repoPath=Split-Path $PSScriptRoot -Parent
$accessPath='D:\example-access'
if ($Role -eq 'open') {
    foreach ($name in @('DesignKnowledge-Local','DesignKnowledge-Viewer','DesignKnowledge-TLS')) {
        $task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task -and $task.State -ne 'Running' -and $task.State -ne 'Disabled') {Start-ScheduledTask -TaskName $name}
    }
    Start-Process 'http://127.0.0.1:8898/framework'
    return
}
Set-Location -LiteralPath $repoPath
if ($Role -eq 'knowledge') {
    $binary=Join-Path $repoPath '.venv-gpu/Scripts/python.exe'
    $arguments=@('-m','uvicorn','app.trial.candidate_platform:trial_app','--factory','--host','127.0.0.1','--port','8898','--workers','1','--no-proxy-headers')
} elseif ($Role -eq 'viewer') {
    $binary=Join-Path $repoPath '.venv/Scripts/python.exe'
    $arguments=@('-m','uvicorn','app.trial.lan_access:app','--host','127.0.0.1','--port','8890','--workers','1','--no-proxy-headers','--no-access-log')
} else {
    $binary=Join-Path $accessPath 'caddy.exe'
    $arguments=@('run','--config',('"'+(Join-Path $accessPath 'Caddyfile')+'"'),'--adapter','caddyfile')
}
$runner=Start-Process -FilePath $binary -ArgumentList $arguments -WorkingDirectory $repoPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $accessPath "$Role.stdout.log") -RedirectStandardError (Join-Path $accessPath "$Role.stderr.log") -Wait -PassThru
exit $runner.ExitCode
