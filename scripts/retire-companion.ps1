param([Parameter(Mandatory=$true)][string]$Record, [Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'companion-runtime.ps1')
# Windows PowerShell emits a JSON array as one pipeline object. Keep that
# array directly so foreach receives individual process records in every host.
try { $retiring = Get-Content -LiteralPath $Record -Raw | ConvertFrom-Json }
catch { return }
Start-Sleep -Seconds 130
foreach ($entry in $retiring) {
    Stop-CompanionProcess $entry $Root
}
