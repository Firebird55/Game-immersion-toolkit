param([switch]$Watch)

$root = Split-Path -Parent $PSScriptRoot
$statusPath = Join-Path $root 'install-progress.json'
$dependencyStatusPath = Join-Path $root 'dependency-restore-progress.json'

function Get-EndpointStatus([string]$url) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return "HTTP $($response.StatusCode)"
    }
    catch { return 'not ready' }
}

do {
    Write-Output "[$(Get-Date -Format 'HH:mm:ss')] Proxy Transcript on $root"
    if (Test-Path -LiteralPath $statusPath) {
        $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        $entryPercent = if ($status.entriesTotal) { [Math]::Round(100 * $status.entriesDone / $status.entriesTotal, 1) } else { 100 }
        Write-Output "  ZIP extraction: $($status.phase) - $($status.percent)% by bytes, $entryPercent% by entries ($($status.entriesDone) / $($status.entriesTotal))"
        if ($status.error) { Write-Output "  Error: $($status.error)" }
    }
    else { Write-Output '  ZIP extraction: not started' }
    if (Test-Path -LiteralPath $dependencyStatusPath) {
        $dependencyStatus = Get-Content -LiteralPath $dependencyStatusPath -Raw | ConvertFrom-Json
        $dependencyEntryPercent = if ($dependencyStatus.entriesTotal) { [Math]::Round(100 * $dependencyStatus.entriesDone / $dependencyStatus.entriesTotal, 1) } else { 100 }
        Write-Output "  Dependency repair: $($dependencyStatus.phase) - $($dependencyStatus.percent)% by bytes, $dependencyEntryPercent% by entries"
        if ($dependencyStatus.error) { Write-Output "  Error: $($dependencyStatus.error)" }
    }
    try {
        $setupStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/setup' -TimeoutSec 5
        Write-Output "  Toolkit version: $($setupStatus.version) | Free space: $($setupStatus.free_gb) GB"
        foreach ($game in $setupStatus.games) {
            $toolState = if ($game.tools_missing.Count) { 'tools need setup' } else { 'tools ready' }
            Write-Output "  $($game.title): $($game.folder_state), $toolState, $($game.indexed_lines) indexed lines, $($game.voice_state)"
        }
        Write-Output '  Open Setup in the companion to choose folders, repair tools or refresh after a game patch.'
    } catch { Write-Output '  Setup status: start the companion to see game readiness.' }
    try {
        $liveStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/status' -TimeoutSec 3
        Write-Output "  Game-file updates: $($liveStatus.updates.progress)% - $($liveStatus.updates.message)"
        Write-Output "  Voice mode: $($liveStatus.audio.message)"
    } catch { }
    Write-Output "  Backend: $(Get-EndpointStatus 'http://127.0.0.1:8766/api/health') | Website: $(Get-EndpointStatus 'http://127.0.0.1:3000/')"
    if ($Watch) { Start-Sleep -Seconds 10 }
} while ($Watch)
