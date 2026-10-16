param([Parameter(Mandatory=$true)][string]$Record)
$ErrorActionPreference = 'Stop'
$retiring = Get-Content -LiteralPath $Record -Raw | ConvertFrom-Json
Start-Sleep -Seconds 130
foreach ($entry in $retiring) {
    $process = Get-Process -Id ([int]$entry.id) -ErrorAction SilentlyContinue
    # Never terminate a reused process ID belonging to another application.
    if ($process -and $process.StartTime.ToUniversalTime().Ticks -eq [long]$entry.started) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
    }
}
