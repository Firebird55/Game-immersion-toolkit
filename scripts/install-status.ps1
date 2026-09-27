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
    $oldCheckout = 'C:\gamesentenceminer'
    $retiredCheckout = 'E:\_retired-C-attempts\gamesentenceminer'
    if (Test-Path -LiteralPath $oldCheckout) {
        $remaining = Get-ChildItem -LiteralPath $oldCheckout -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum
        $moved = if (Test-Path -LiteralPath $retiredCheckout) {
            Get-ChildItem -LiteralPath $retiredCheckout -Recurse -File -Force -ErrorAction SilentlyContinue |
                Measure-Object -Property Length -Sum
        } else { $null }
        $movedBytes = if ($moved) { [double]$moved.Sum } else { 0.0 }
        $remainingBytes = [double]$remaining.Sum
        $cleanupPercent = if ($movedBytes + $remainingBytes -gt 0) {
            [Math]::Round(100 * $movedBytes / ($movedBytes + $remainingBytes), 1)
        } else { 0.0 }
        Write-Output "  C checkout move: $cleanupPercent% by bytes ($($moved.Count) files moved, $($remaining.Count) remaining)"
    }
    else { Write-Output '  C checkout move: complete' }
    if (Test-Path -LiteralPath 'C:\ProxyTranscript') {
        $leftover = (Get-ChildItem -LiteralPath 'C:\ProxyTranscript' -Force -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Name) -join ', '
        Write-Output "  C ProxyTranscript cleanup: remaining $leftover"
    }
    else { Write-Output '  C ProxyTranscript cleanup: complete' }
    $agentLog = Join-Path $root 'data\agent-voices\update.log'
    if (Test-Path -LiteralPath $agentLog) {
        $last = Select-String -LiteralPath $agentLog -Pattern '(\d+)/(\d+) clips indexed' |
            Select-Object -Last 1
        if ($last -and $last.Matches[0].Groups[2].Value -gt 0) {
            $done = [int]$last.Matches[0].Groups[1].Value
            $total = [int]$last.Matches[0].Groups[2].Value
            $percent = [Math]::Round(100 * $done / $total, 1)
            Write-Output "  Agent voice index: $percent% ($done / $total clips)"
        }
        elseif (Select-String -LiteralPath $agentLog -Pattern '^Complete' -Quiet) {
            Write-Output '  Agent voice index: 100% complete'
        }
    }
    Write-Output "  Backend: $(Get-EndpointStatus 'http://127.0.0.1:8766/api/health') | Website: $(Get-EndpointStatus 'http://127.0.0.1:3000/')"
    if ($Watch) { Start-Sleep -Seconds 10 }
} while ($Watch)
