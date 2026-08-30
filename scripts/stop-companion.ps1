$ErrorActionPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$processFile = Join-Path $projectRoot 'data\processes.json'

if (Test-Path -LiteralPath $processFile) {
    $record = Get-Content -Raw -LiteralPath $processFile | ConvertFrom-Json
    foreach ($property in $record.PSObject.Properties) {
        $processId = [int]$property.Value
        if ($processId -gt 0) {
            & taskkill.exe /PID $processId /T /F | Out-Null
        }
    }
}
