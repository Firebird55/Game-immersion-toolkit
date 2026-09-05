$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $projectRoot 'data'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$processFile = Join-Path $dataDir 'processes.json'
$productionConfig = Join-Path $projectRoot 'dist\server\wrangler.json'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Setup has not been run. Run scripts\setup.ps1 first.'
}

if (-not (Test-Path -LiteralPath $productionConfig)) {
    Push-Location -LiteralPath $projectRoot
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw 'The Proxy Transcript production build failed.'
        }
    }
    finally {
        Pop-Location
    }
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

if (-not (Test-LocalEndpoint 'http://127.0.0.1:8766/api/health')) {
    # Data and game-file refreshes now run behind the live API so the interface
    # opens immediately, even after a large ZZZ update.
    $backend = Start-Process -FilePath $python `
        -ArgumentList '-m', 'backend.main' `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
    $started.backend = $backend.Id
}

if (-not (Test-LocalEndpoint 'http://localhost:3000/')) {
    $frontend = Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/d', '/c', 'npm run start' `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
    $started.frontend = $frontend.Id
}

$started | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding UTF8

$ready = $false
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if ((Test-LocalEndpoint 'http://127.0.0.1:8766/api/health') -and (Test-LocalEndpoint 'http://localhost:3000/')) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    throw 'Proxy Transcript did not finish starting within one minute.'
}

Add-Type -AssemblyName System.Windows.Forms
$primary = [System.Windows.Forms.Screen]::PrimaryScreen
$portrait = [System.Windows.Forms.Screen]::AllScreens |
    Where-Object { $_.Bounds.Height -gt $_.Bounds.Width -and $_.Bounds.X -ge $primary.Bounds.Right } |
    Sort-Object { [Math]::Abs($_.Bounds.X - $primary.Bounds.Right) } |
    Select-Object -First 1

if (-not $portrait) {
    $portrait = [System.Windows.Forms.Screen]::AllScreens |
        Where-Object { $_.Bounds.Height -gt $_.Bounds.Width } |
        Select-Object -First 1
}

if (-not $portrait) {
    $portrait = $primary
}

$chromeCandidates = @(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if ($chrome) {
    $area = $portrait.WorkingArea
    $arguments = @(
        '--new-window',
        "--window-position=$($area.X),$($area.Y)",
        "--window-size=$($area.Width),$($area.Height)",
        'http://localhost:3000/'
    )
    # A normal Chrome window keeps the Migaku toolbar button and uses the
    # user's existing Chrome profile, where the extension is installed.
    Start-Process -FilePath $chrome -ArgumentList $arguments -WindowStyle Normal
}
else {
    throw 'Google Chrome was not found. Install Chrome or update scripts\start-companion.ps1 with its location.'
}
