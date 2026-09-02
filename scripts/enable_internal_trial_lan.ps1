$ErrorActionPreference = 'Stop'
$ruleName = 'AI设计管理知识库 Internal Trial 8010'

if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8010 -Profile Private,Public -RemoteAddress LocalSubnet -ErrorAction Stop | Out-Null
}

Write-Output 'Local-subnet inbound firewall rule for TCP 8010 is enabled.'
