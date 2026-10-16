param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'companion-runtime.ps1')
$dataDir = Join-Path $projectRoot 'data'
$processFile = Join-Path $dataDir 'processes.json'
$statePath = Join-Path $dataDir 'companion-runtime.json'
$python = Join-Path $env:LOCALAPPDATA 'Programs\Proxy Transcript\venv\Scripts\python.exe'
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
$started = [ordered]@{}
if (Test-Path -LiteralPath $processFile) {
    $previous = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    foreach ($property in $previous.PSObject.Properties) {
        if (Get-Process -Id ([int]$property.Value) -ErrorAction SilentlyContinue) {
            $started[$property.Name] = [int]$property.Value
        }
    }
}
$state = $null
if (Test-Path -LiteralPath $statePath) { $state=Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json }
if (-not ((Test-CompanionEndpoint 'http://127.0.0.1:8766/api/health') -and (Test-CompanionEndpoint 'http://127.0.0.1:3000/'))) {
    if (-not $state -and (Test-CompanionEndpoint 'http://127.0.0.1:8766/api/health')) {
        # Existing direct-port installs remain usable until the updater performs
        # their first prepared handover. Do not stop a working capture service.
        $node=(Get-Command node -ErrorAction Stop).Source
        $wrangler=Join-Path $projectRoot 'node_modules\wrangler\bin\wrangler.js'
        $frontend=Start-CompanionProcess $node @($wrangler,'dev','--config','dist/server/wrangler.json','--port','3000') $projectRoot ''
        $started.frontend=$frontend.Id
    } else {
        $source=$projectRoot
        if ($state -and (Test-Path -LiteralPath $state.active.source)) {
            $source=$state.active.source
            $python=$state.active.python
        }
        if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts\setup.ps1 first.' }
        if (-not (Test-Path -LiteralPath (Join-Path $source 'dist\server\wrangler.json'))) { throw 'The frontend is not built. Run scripts\setup.ps1 first.' }
        $slotReady=$state -and (Test-CompanionEndpoint ('http://127.0.0.1:'+$state.active.apiPort+'/api/health')) -and (Test-CompanionEndpoint ('http://127.0.0.1:'+$state.active.frontendPort+'/'))
        if (-not $slotReady) {
            foreach ($name in @('backend','frontend')) { if($started.Contains($name)){$started['retired_'+$started[$name]]=$started[$name]} }
            $slot=Start-CompanionSlot $projectRoot $source $python
            $state=@{version=1;active=$slot}
            Save-CompanionJson $statePath $state
            $started.backend=$slot.backend
            $started.frontend=$slot.frontend
        }
        if (-not $started.Contains('router')) {
            # A legacy frontend without its backend can still own port 3000.
            if (Test-CompanionEndpoint 'http://127.0.0.1:3000/') {
                foreach($name in @($started.Keys | Where-Object {$_ -like 'retired_*'})) { & taskkill.exe /PID $started[$name] /T /F | Out-Null }
            }
            $router=Start-CompanionRouter $projectRoot $source
            $started.router=$router.Id
        }
    }
    Save-CompanionJson $processFile $started
}
$ready=$false
for($attempt=0;$attempt -lt 120;$attempt++) {
    if ((Test-CompanionEndpoint 'http://127.0.0.1:8766/api/health') -and (Test-CompanionEndpoint 'http://127.0.0.1:3000/')) {$ready=$true;break}
    Start-Sleep -Milliseconds 500
}
if(-not $ready){throw 'Companion did not finish starting; see data/runtime-logs.'}

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
