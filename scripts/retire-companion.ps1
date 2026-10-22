param([Parameter(Mandatory=$true)][string]$Record, [Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'companion-runtime.ps1')
try { $retiring = @(Get-Content -LiteralPath $Record -Raw | ConvertFrom-Json) }
catch { return }
Start-Sleep -Seconds 130
foreach ($entry in $retiring) {
    Stop-CompanionProcess $entry $Root
}
