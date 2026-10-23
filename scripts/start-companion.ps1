param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'companion-runtime.ps1')
$python = Join-Path $env:LOCALAPPDATA 'Programs\Proxy Transcript\venv\Scripts\python.exe'
$operation = Enter-CompanionOperation $projectRoot
try {
    # Read after acquiring the lock: another launcher/updater may have replaced
    # every process while this invocation was waiting.
    $processFile = Join-Path $projectRoot 'data\processes.json'
    $statePath = Join-Path $projectRoot 'data\companion-runtime.json'
    $started = Read-CompanionProcesses $processFile $projectRoot
    $state = $null
    try { if (Test-Path -LiteralPath $statePath) { $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } } catch { }
    Repair-CompanionRuntime $projectRoot $python $started $state
} finally { $operation.Dispose() }

if ($NoBrowser) { return }

Add-Type -AssemblyName System.Windows.Forms
$primary = [System.Windows.Forms.Screen]::PrimaryScreen
$screens = [System.Windows.Forms.Screen]::AllScreens
$targetScreen = $screens |
    Where-Object { -not $_.Primary -and $_.Bounds.Height -gt $_.Bounds.Width } |
    Sort-Object { [Math]::Abs($_.Bounds.X - $primary.Bounds.Right) } |
    Select-Object -First 1

if (-not $targetScreen) {
    $targetScreen = $screens |
        Where-Object { -not $_.Primary } |
        Sort-Object { [Math]::Abs($_.Bounds.X - $primary.Bounds.Right) } |
        Select-Object -First 1
}

if (-not $targetScreen) { $targetScreen = $primary }

$chromeCandidates = @(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if ($chrome) {
    $area = $targetScreen.WorkingArea
    $arguments = @(
        '--new-window',
        '--start-maximized',
        "--window-position=$($area.X),$($area.Y)",
        "--window-size=$($area.Width),$($area.Height)",
        'http://127.0.0.1:3000/'
    )
    # A normal Chrome window keeps the Migaku toolbar button and uses the
    # user's existing Chrome profile, where the extension is installed.
    Start-Process -FilePath $chrome -ArgumentList $arguments -WindowStyle Normal
}
else {
    throw 'Google Chrome was not found. Install Chrome or update scripts\start-companion.ps1 with its location.'
}
