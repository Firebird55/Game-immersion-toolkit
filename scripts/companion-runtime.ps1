$ErrorActionPreference = 'Stop'

function Test-CompanionEndpoint([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}

function Save-CompanionJson([string]$Path, $Value) {
    $pending = $Path + '.pending'
    $json = ConvertTo-Json -InputObject $Value -Depth 12
    [System.IO.File]::WriteAllText($pending, $json, [System.Text.UTF8Encoding]::new($false))
    # Same-volume replacement keeps the router on the last complete route.
    if ([System.IO.File]::Exists($Path)) { [System.IO.File]::Replace($pending, $Path, $Path+'.previous') }
    else { [System.IO.File]::Move($pending, $Path) }
}

function Start-CompanionProcess([string]$Executable, [string[]]$Arguments, [string]$Directory,
                                [string]$Log, [switch]$LowPriority) {
    $quoted = $Arguments | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }
    $parameters = @{FilePath=$Executable; ArgumentList=($quoted -join ' '); WorkingDirectory=$Directory;
                    WindowStyle='Hidden'; PassThru=$true}
    if ($Log) { $parameters.RedirectStandardOutput=$Log+'.out.log'; $parameters.RedirectStandardError=$Log+'.err.log' }
    $process = Start-Process @parameters
    # Windows PowerShell 5 must acquire the handle before a short-lived build
    # exits, otherwise Process.ExitCode can remain null after WaitForExit.
    $null = $process.Handle
    if ($LowPriority) { try { $process.PriorityClass='BelowNormal' } catch { } }
    return $process
}

function Invoke-CompanionBuild([string]$Executable, [string[]]$Arguments, [string]$Directory, [string]$Log) {
    $process = Start-CompanionProcess $Executable $Arguments $Directory $Log -LowPriority
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw 'Update preparation failed. The running companion was kept active; see the private update logs.' }
}

function Get-CompanionPort([int]$First, [int]$Last) {
    foreach ($port in $First..$Last) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
        try { $listener.Start(); return $port } catch { } finally { $listener.Stop() }
    }
    throw 'No free local companion port is available.'
}

function Start-CompanionSlot([string]$Root, [string]$Source, [string]$Python, [switch]$Standby) {
    $apiPort = Get-CompanionPort 8767 8799
    $frontendPort = Get-CompanionPort 3001 3039
    $logs = Join-Path $Root 'data\runtime-logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $node = (Get-Command node -ErrorAction Stop).Source
    $env:PROXY_TRANSCRIPT_PROJECT_ROOT = $Root
    $backendArguments = @('-m','backend.main','--port',[string]$apiPort)
    if ($Standby) { $backendArguments += '--standby' }
    $backend = Start-CompanionProcess $Python $backendArguments $Source (Join-Path $logs "api-$apiPort") -LowPriority:$Standby
    try {
        $wrangler = Join-Path $Source 'node_modules\wrangler\bin\wrangler.js'
        $frontend = Start-CompanionProcess $node @($wrangler,'dev','--config','dist/server/wrangler.json','--ip','127.0.0.1','--port',[string]$frontendPort,'--inspector-port',[string]($frontendPort+16000)) $Source (Join-Path $logs "frontend-$frontendPort")
    } catch { & taskkill.exe /PID $backend.Id /T /F | Out-Null; throw }
    return [ordered]@{source=$Source; python=$Python; apiPort=$apiPort; frontendPort=$frontendPort;
                       backend=$backend.Id; frontend=$frontend.Id}
}

function Copy-CompanionAssets([string]$Source, [string]$Root) {
    $assets = Join-Path $Root 'data\runtime-assets'
    New-Item -ItemType Directory -Path $assets -Force | Out-Null
    $static = Join-Path $Source 'dist\client\_next\static'
    if (Test-Path -LiteralPath $static) {
        Get-ChildItem -LiteralPath $static | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $assets -Recurse -Force }
    }
    return $assets
}

function Start-CompanionRouter([string]$Root, [string]$Source, [int]$ApiPort=8766, [int]$FrontendPort=3000) {
    $node = (Get-Command node -ErrorAction Stop).Source
    $assets = Copy-CompanionAssets $Source $Root
    $logs = Join-Path $Root 'data\runtime-logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    return Start-CompanionProcess $node @((Join-Path $Source 'scripts\companion-router.mjs'),'--state',(Join-Path $Root 'data\companion-runtime.json'),'--assets',$assets,'--api-port',[string]$ApiPort,'--frontend-port',[string]$FrontendPort) $Source (Join-Path $logs 'router')
}

function Set-CompanionNormalPriority([int]$ProcessId) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($process) { try { $process.PriorityClass='Normal' } catch { } }
    # venv launchers can have one real Python child. Promote it before the new
    # runtime starts its own explicitly lower-priority indexing processes.
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue |
        ForEach-Object { Set-CompanionNormalPriority ([int]$_.ProcessId) }
}
