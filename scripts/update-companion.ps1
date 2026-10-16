param([string]$SourceRoot=(Split-Path -Parent $PSScriptRoot),
      [string]$Root=(Split-Path -Parent $PSScriptRoot), [switch]$PreparedBuild,
      [int]$ApiPort=8766, [int]$FrontendPort=3000, [ValidateRange(1,1800)][int]$ReadyTimeoutSeconds=300)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'companion-runtime.ps1')
$Root = (Resolve-Path -LiteralPath $Root).Path
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$data = Join-Path $Root 'data'
$statePath = Join-Path $data 'companion-runtime.json'
$processFile = Join-Path $data 'processes.json'
if((Test-CompanionEndpoint ('http://127.0.0.1:'+$ApiPort+'/api/health')) -and -not (Test-Path -LiteralPath $processFile)) {
    throw 'Run the updater with -Root pointing to the current companion folder so its local data is preserved.'
}
$package = Get-Content -LiteralPath (Join-Path $SourceRoot 'package.json') -Raw | ConvertFrom-Json
if ($package.name -ne 'game-immersion-toolkit' -or $package.version -notmatch '^\d+\.\d+\.\d+(?:-[\w.-]+)?$') { throw 'Choose an extracted toolkit release or toolkit checkout.' }
$stage = Join-Path $data ('runtime-code\'+$package.version+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
$logs = Join-Path $data 'runtime-logs'
New-Item -ItemType Directory -Path $stage,$logs -Force | Out-Null
$originalState = $null
if (Test-Path -LiteralPath $statePath) { $originalState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json }
$oldProcesses = [ordered]@{}
if (Test-Path -LiteralPath $processFile) {
    $record = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    foreach ($property in $record.PSObject.Properties) { $oldProcesses[$property.Name]=[int]$property.Value }
}

# Only application source and owned frontend assets enter the candidate. Live
# databases, credentials, game indexes, recordings and calibration stay put.
foreach ($name in @('backend','scripts','public','vendor','assets','lib','app','components','hooks','styles')) {
    $source = Join-Path $SourceRoot $name
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $stage -Recurse -Force }
}
foreach ($name in @('package.json','package-lock.json','tsconfig.json','next-env.d.ts','next.config.ts','vite.config.ts','.npmrc','VERSION','release-version.json','requirements.lock.txt','LICENSE','THIRD_PARTY_NOTICES.md')) {
    $source = Join-Path $SourceRoot $name
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $stage $name) -Force }
}
New-Item -ItemType Directory -Path (Join-Path $stage '.openai') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $SourceRoot '.openai\hosting.json') -Destination (Join-Path $stage '.openai\hosting.json')
$node = (Get-Command node -ErrorAction Stop).Source
$npm = Join-Path (Split-Path -Parent (Get-Command npm -ErrorAction Stop).Source) 'node_modules\npm\bin\npm-cli.js'
if (-not (Test-Path -LiteralPath $npm)) {
    $npm = Join-Path (Split-Path -Parent $node) 'node_modules\npm\bin\npm-cli.js'
}
if (-not (Test-Path -LiteralPath $npm)) { throw 'The Node.js npm CLI could not be found.' }
$python = Join-Path $env:LOCALAPPDATA 'Programs\Proxy Transcript\venv\Scripts\python.exe'
if ($originalState -and $originalState.active.python) { $python=$originalState.active.python }
Write-Host 'Preparing the update while the current companion keeps capturing.'
Push-Location -LiteralPath $stage
try { & $python -m backend.check_environment (Join-Path $stage 'requirements.lock.txt') *> $null; $compatible=$LASTEXITCODE -eq 0 }
finally { Pop-Location }
if (-not $compatible) {
    Invoke-CompanionBuild $python @('-m','venv',(Join-Path $stage '.venv')) $stage (Join-Path $logs 'venv')
    $python=Join-Path $stage '.venv\Scripts\python.exe'
    Invoke-CompanionBuild $python @('-m','pip','install','--disable-pip-version-check','-r','requirements.lock.txt') $stage (Join-Path $logs 'python-install')
}
Invoke-CompanionBuild $node @($npm,'ci','--no-audit','--no-fund') $stage (Join-Path $logs 'npm-install')
$usePrebuilt=$PreparedBuild.IsPresent
$provenance=Join-Path $SourceRoot 'PROVENANCE.json'
if (Test-Path -LiteralPath $provenance) {
    $usePrebuilt=$usePrebuilt -or ((Get-Content -LiteralPath $provenance -Raw | ConvertFrom-Json).version -eq $package.version)
}
if ($usePrebuilt -and (Test-Path -LiteralPath (Join-Path $SourceRoot 'dist\server\wrangler.json'))) {
    Copy-Item -LiteralPath (Join-Path $SourceRoot 'dist') -Destination $stage -Recurse -Force
} else { Invoke-CompanionBuild $node @($npm,'run','build') $stage (Join-Path $logs 'frontend-build') }

$candidate=$null
$quiesced=$false
$handoff=$null
$oldApi=if($originalState){'http://127.0.0.1:'+$originalState.active.apiPort}else{'http://127.0.0.1:'+$ApiPort}
$headers=@{'X-Proxy-Transcript'='update'}
try {
    Write-Host 'Replacement prepared; warming capture while the current version stays active.'
    $candidate=Start-CompanionSlot $Root $stage $python -Standby
    $newApi='http://127.0.0.1:'+$candidate.apiPort
    $game=''
    try { $current=Invoke-RestMethod ($oldApi+'/api/status') -TimeoutSec 3; $game=[string]$current.capture.active_game } catch { }
    $query=if($game){'?game='+[uri]::EscapeDataString($game)}else{''}
    $ready=$false
    for($attempt=0;$attempt -lt ($ReadyTimeoutSeconds*2);$attempt++) {
        try {
            $warm=Invoke-RestMethod ($newApi+'/api/runtime/ready'+$query) -TimeoutSec 2
            if($warm.ready -and (Test-CompanionEndpoint ('http://127.0.0.1:'+$candidate.frontendPort+'/'))){$ready=$true;break}
        } catch { }
        if(-not (Get-Process -Id $candidate.backend -ErrorAction SilentlyContinue)){throw 'Replacement backend exited; current capture was kept active.'}
        Start-Sleep -Milliseconds 500
    }
    if(-not $ready){throw 'Replacement was not ready. The current companion was kept active.'}
    Write-Host 'Replacement is ready; transferring the current capture session.'
    $null=Copy-CompanionAssets $Root $Root
    $null=Copy-CompanionAssets $stage $Root
    # The candidate is fully warm before any old capture process is paused.
    $current=$null
    try {$current=Invoke-RestMethod ($oldApi+'/api/status') -TimeoutSec 3} catch { }
    if($current) {
        $handoff=@{running=[bool]$current.capture.running;session_id=$current.session.id}
        $quiesced=$true
        try { $handoff=Invoke-RestMethod -Method Post ($oldApi+'/api/runtime/quiesce') -Headers $headers -TimeoutSec 30 }
        catch {
            if(-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404){throw}
            $null=Invoke-RestMethod -Method Post ($oldApi+'/api/capture/stop') -TimeoutSec 20
        }
    } else { $handoff=@{running=$true} }
    Set-CompanionNormalPriority $candidate.backend
    $null=Invoke-RestMethod -Method Post ($newApi+'/api/runtime/activate') -Headers $headers -ContentType 'application/json' -Body ($handoff|ConvertTo-Json -Depth 12) -TimeoutSec 15
    Save-CompanionJson $statePath @{version=1;active=$candidate}
    $running=[ordered]@{backend=$candidate.backend;frontend=$candidate.frontend}
    if($originalState -and $oldProcesses.Contains('router') -and (Get-Process -Id $oldProcesses.router -ErrorAction SilentlyContinue)) {
        $running.router=$oldProcesses.router
    } else {
        # One-time migration from the direct-port launcher. Capture in the warm
        # replacement is already active while the stable local router starts.
        foreach($name in @('backend','frontend')) {
            if($oldProcesses.Contains($name)){& taskkill.exe /PID $oldProcesses[$name] /T /F | Out-Null}
        }
        $router=Start-CompanionRouter $Root $stage $ApiPort $FrontendPort
        $running.router=$router.Id
    }
    $retiring=@()
    foreach($name in @('backend','frontend')) {
        if($oldProcesses.Contains($name)){
            $process=Get-Process -Id $oldProcesses[$name] -ErrorAction SilentlyContinue
            if($process){$running['retired_'+$process.Id]=$process.Id;$retiring+=@{id=$process.Id;started=$process.StartTime.ToUniversalTime().Ticks}}
        }
    }
    Save-CompanionJson $processFile $running
    $routed=$false
    for($attempt=0;$attempt -lt 40;$attempt++){
        try{
            $response=Invoke-WebRequest ('http://127.0.0.1:'+$ApiPort+'/api/health') -UseBasicParsing -TimeoutSec 2
            if($response.Headers['X-Proxy-Transcript-Router'] -and (Test-CompanionEndpoint ('http://127.0.0.1:'+$FrontendPort+'/'))){$routed=$true;break}
        }catch{}
        Start-Sleep -Milliseconds 250
    }
    if(-not $routed){throw 'Prepared runtime could not take over the local connection.'}
    if($retiring.Count){
        $retireFile=Join-Path $logs ('retire-'+[guid]::NewGuid().ToString('N')+'.json')
        Save-CompanionJson $retireFile $retiring
        $shell=(Get-Process -Id $PID).Path
        $retirer=Start-CompanionProcess $shell @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $stage 'scripts\retire-companion.ps1'),'-Record',$retireFile) $stage ''
        $running['retirer_'+$retirer.Id]=$retirer.Id
        Save-CompanionJson $processFile $running
    }
    Write-Host ('Update '+$package.version+' is active. Capture, local data and open reading sessions were preserved.')
} catch {
    $failure=$_
    try{if($originalState){Save-CompanionJson $statePath $originalState}}catch{}
    try{if($oldProcesses.Count){Save-CompanionJson $processFile $oldProcesses}}catch{}
    if($quiesced){
        try {$null=Invoke-RestMethod -Method Post ($oldApi+'/api/runtime/activate') -Headers $headers -ContentType 'application/json' -Body ($handoff|ConvertTo-Json -Depth 12) -TimeoutSec 10}
        catch {if($handoff.running){try {$null=Invoke-RestMethod -Method Post ($oldApi+'/api/capture/start') -TimeoutSec 10} catch { }}}
    }
    if($candidate){foreach($name in @('backend','frontend')){& taskkill.exe /PID $candidate[$name] /T /F | Out-Null}}
    throw $failure
}
