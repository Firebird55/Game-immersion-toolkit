$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'companion-runtime.ps1')
$processFile = Join-Path $projectRoot 'data\processes.json'
$record = Read-CompanionProcesses $processFile $projectRoot
foreach ($name in @($record.Keys)) {
    Stop-CompanionProcess $record[$name] $projectRoot
}
