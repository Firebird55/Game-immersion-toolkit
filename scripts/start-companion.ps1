param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $projectRoot 'data'
$python = Join-Path $env:LOCALAPPDATA 'Programs\Proxy Transcript\venv\Scripts\python.exe'
$processFile = Join-Path $dataDir 'processes.json'
$productionConfig = Join-Path $projectRoot 'dist\server\wrangler.json'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Setup has not been run. Run scripts\setup.ps1 first.'
}

if (-not (Test-Path -LiteralPath $productionConfig)) {
    throw 'The Proxy Transcript frontend is not built. Run scripts\setup.ps1 first.'
}

New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

function Test-LocalEndpoint([string]$url) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

$started = [ordered]@{}
if (Test-Path -LiteralPath $processFile) {
    try {
        $previous = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
        foreach ($property in $previous.PSObject.Properties) {
            if (Get-Process -Id ([int]$property.Value) -ErrorAction SilentlyContinue) {
                $started[$property.Name] = [int]$property.Value
            }
        }
    }
    catch { }
}

if (-not (Test-LocalEndpoint 'http://127.0.0.1:8766/api/health')) {
    # Data and game-file refreshes now run behind the live API so the interface
    # opens immediately, even after a large ZZZ update.
    $env:PROXY_TRANSCRIPT_PROJECT_ROOT = $projectRoot
    $backend = Start-Process -FilePath $python `
        -ArgumentList '-m', 'backend.main' `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
    $started.backend = $backend.Id
}

if (-not (Test-LocalEndpoint 'http://127.0.0.1:3000/')) {
    $wrangler = Join-Path $projectRoot 'node_modules\wrangler\bin\wrangler.js'
    if (-not (Test-Path -LiteralPath $wrangler)) {
        $store = Join-Path $projectRoot 'node_modules\.pnpm'
        $package = Get-ChildItem -LiteralPath $store -Directory -ErrorAction SilentlyContinue |
            Where-Object Name -like 'wrangler@*' | Select-Object -First 1
        if ($package) { $wrangler = Join-Path $package.FullName 'node_modules\wrangler\bin\wrangler.js' }
    }
    if (-not (Test-Path -LiteralPath $wrangler)) { throw 'Wrangler is missing. Restore node_modules from the ZIP.' }
    $node = (Get-Command node -ErrorAction Stop).Source
    $frontend = Start-Process -FilePath $node `
        -ArgumentList $wrangler, 'dev', '--config', 'dist\server\wrangler.json', '--port', '3000' `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
    $started.frontend = $frontend.Id
}

$started | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding UTF8

$ready = $false
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if ((Test-LocalEndpoint 'http://127.0.0.1:8766/api/health') -and (Test-LocalEndpoint 'http://127.0.0.1:3000/')) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    throw 'Proxy Transcript did not finish starting within one minute.'
}

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
