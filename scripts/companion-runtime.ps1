$ErrorActionPreference = 'Stop'

# Runtime state retains numeric backend/frontend fields for the router and
# capture handoff. Only these separately recorded identities authorize process
# reuse or termination. Ticks are strings so JSON readers cannot round them.
function Read-CompanionProcessImage([IntPtr]$Handle) {
    if (-not ('ProxyTranscript.CompanionProcessImage' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
namespace ProxyTranscript {
    public static class CompanionProcessImage {
        [DllImport("kernel32.dll", ExactSpelling=true, CharSet=CharSet.Unicode, SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool QueryFullProcessImageNameW(IntPtr process, uint flags, StringBuilder image, ref uint size);
        public static string Read(IntPtr process) {
            const int capacity = 32768;
            var image = new StringBuilder(capacity);
            uint size = capacity;
            if (!QueryFullProcessImageNameW(process, 0, image, ref size)) {
                int error = Marshal.GetLastWin32Error();
                throw new Win32Exception(error, "Windows could not read the companion executable identity (error " + error + ").");
            }
            if (size == 0 || size >= capacity || image.Length != size) {
                throw new InvalidOperationException("Windows returned an invalid companion executable identity.");
            }
            return image.ToString();
        }
    }
}
'@
    }
    return [ProxyTranscript.CompanionProcessImage]::Read($Handle)
}

function Get-CompanionProcessExecutable($Process) {
    $handle = $Process.Handle
    if ($Process.HasExited) { throw 'Companion process exited while its executable identity was being read.' }
    # Module lists can be missing or inconsistent during startup. Query the
    # kernel image using the already retained handle, without reopening a PID.
    try { $executable = Read-CompanionProcessImage $handle }
    finally { [GC]::KeepAlive($Process) }
    if ($Process.HasExited) { throw 'Companion process exited while its executable identity was being read.' }
    if ([string]::IsNullOrEmpty($executable) -or -not [IO.Path]::IsPathRooted($executable)) {
        throw 'Windows returned an invalid companion executable identity.'
    }
    try { return [IO.Path]::GetFullPath($executable) }
    catch { throw 'Windows returned an invalid companion executable identity.' }
}

function New-CompanionProcessRecord($Process, [string]$Root) {
    $null = $Process.Handle
    if ($Process.HasExited) { throw 'Companion process exited before its identity could be recorded.' }
    $started = $Process.StartTime.ToUniversalTime().Ticks.ToString()
    $executable = Get-CompanionProcessExecutable $Process
    if ($Process.HasExited -or $Process.StartTime.ToUniversalTime().Ticks.ToString() -ne $started) {
        throw 'Companion process changed or exited before its identity could be recorded.'
    }
    return [ordered]@{id=$Process.Id; started=$started; executable=$executable; root=[IO.Path]::GetFullPath($Root)}
}

function Get-CompanionOwnedProcess($Record, [string]$Root) {
    $process = $null
    try {
        # PID-only records, partial writes and inaccessible processes are never
        # sufficient evidence that a live process belongs to this installation.
        if (-not $Record -or $Record -is [ValueType] -or $Record -is [string]) { return $null }
        if ([string]$Record.id -notmatch '^[1-9][0-9]*$' -or [string]$Record.started -notmatch '^[1-9][0-9]*$') { return $null }
        if (-not [System.IO.Path]::IsPathRooted([string]$Record.executable) -or -not [System.IO.Path]::IsPathRooted([string]$Record.root)) { return $null }
        if ([System.IO.Path]::GetFullPath([string]$Record.root) -ne [System.IO.Path]::GetFullPath($Root)) { return $null }
        $process = Get-Process -Id ([int]$Record.id) -ErrorAction SilentlyContinue
        if (-not $process) { return $null }
        # Keep the process handle open while checking and stopping it. Windows
        # cannot recycle this process ID while this handle is held.
        $null = $process.Handle
        if ($process.HasExited -or $process.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$Record.started) {
            $process.Dispose(); return $null
        }
        $executable = Get-CompanionProcessExecutable $process
        if ($process.HasExited -or $process.StartTime.ToUniversalTime().Ticks.ToString() -ne [string]$Record.started -or
            $executable -ne [System.IO.Path]::GetFullPath([string]$Record.executable)) {
            $process.Dispose(); return $null
        }
        return $process
    } catch { if ($process) { $process.Dispose() }; return $null }
}

function Test-CompanionProcess($Record, [string]$Root) {
    $process = Get-CompanionOwnedProcess $Record $Root
    if (-not $process) { return $false }
    $process.Dispose()
    return $true
}

function Get-CompanionChildProcessHandles($Parent, [long]$Started, $Seen) {
    # The caller holds the parent's handle, including after termination, so its
    # PID cannot be reused while child identities are checked. A stale parent
    # ID left by an earlier process must also fail the creation-time check.
    $children = @()
    try {
        $candidates = @(Get-CimInstance Win32_Process -Filter ('ParentProcessId='+$Parent.Id) -ErrorAction Stop)
        foreach ($candidate in $candidates) {
            $child = $null
            try {
                if ($Seen.ContainsKey([int]$candidate.ProcessId)) { continue }
                $child = Get-Process -Id ([int]$candidate.ProcessId) -ErrorAction SilentlyContinue
                if (-not $child) { continue }
                $null = $child.Handle
                $live = Get-CimInstance Win32_Process -Filter ('ProcessId='+$child.Id) -ErrorAction Stop
                if (-not $child.HasExited -and $live.ParentProcessId -eq $Parent.Id -and
                    $child.StartTime.ToUniversalTime().Ticks -ge $Started) {
                    $Seen[$child.Id] = $true
                    $children += ,$child
                    $child = $null # Transfer this retained handle to the caller.
                }
            } catch {
                # A child can finish between enumeration and handle acquisition.
                if (-not $child -or -not $child.HasExited) { throw }
            } finally { if ($child) { $child.Dispose() } }
        }
        return $children
    } catch {
        foreach ($child in $children) { $child.Dispose() }
        throw 'Windows could not verify companion child processes; cleanup may be incomplete.'
    }
}

function Stop-CompanionProcessTreeNode($Process, $Seen) {
    $started = $Process.StartTime.ToUniversalTime().Ticks
    if (-not $Process.HasExited) {
        try { $Process.Kill() }
        catch { if (-not $Process.HasExited) { throw 'Windows refused to stop a verified companion process.' } }
        if (-not $Process.WaitForExit(5000)) { throw 'A verified companion process did not stop.' }
    }
    # Stop each parent before enumerating its children: it cannot spawn another
    # child after this snapshot. Retained handles reserve every ancestor PID.
    $children = @(Get-CompanionChildProcessHandles $Process $started $Seen)
    $failure = $null
    try {
        foreach ($child in $children) {
            try { Stop-CompanionProcessTreeNode $child $Seen }
            catch { if (-not $failure) { $failure = $_ } }
        }
    } finally { foreach ($child in $children) { $child.Dispose() } }
    if ($failure) { throw $failure }
}

function Stop-CompanionProcessHandle($Process) {
    # Call only with a validated identity handle or the exact Start-Process
    # object owned by this invocation, including partial-start cleanup.
    $null = $Process.Handle
    # An exited parent can still own live descendants. Its retained handle
    # reserves the PID while the tree walker verifies their parentage/start time.
    $seen = @{}
    $seen[$Process.Id] = $true
    Stop-CompanionProcessTreeNode $Process $seen
}

function Stop-CompanionProcess($Record, [string]$Root) {
    $process = Get-CompanionOwnedProcess $Record $Root
    if (-not $process) { return }
    try {
        Stop-CompanionProcessHandle $process
    }
    finally { $process.Dispose() }
}

function Stop-CompanionCaptureOwner($Record, [string]$Root) {
    # Capture handoff requires proof of shutdown. Generic stale-record cleanup
    # intentionally does nothing on identity failure; that is not sufficient to
    # authorize another capturer, including rollback to the previous backend.
    $process = Get-CompanionOwnedProcess $Record $Root
    if (-not $process) {
        $unverified = $null
        try { $unverified = [Diagnostics.Process]::GetProcessById([int]$Record.id) }
        catch [ArgumentException] { return } # The recorded process is gone.
        try {
            if (-not $unverified.HasExited) { throw 'Capture ownership could not be verified; no replacement capture was activated.' }
        } finally { if ($unverified) { $unverified.Dispose() } }
        return
    }
    try {
        $seen = @{}
        $seen[$process.Id] = $true
        # Keep the validated handle even if the parent exits just now, so its
        # retained identity can still authorize reaping verified descendants.
        Stop-CompanionProcessTreeNode $process $seen
    } finally { $process.Dispose() }
}

function Read-CompanionProcesses([string]$Path, [string]$Root) {
    $result = [ordered]@{}
    try {
        $record = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($record -isnot [System.Management.Automation.PSCustomObject]) { return $result }
        foreach ($property in $record.PSObject.Properties) {
            if ($property.Name -match '^(backend|frontend|router|retired_[0-9]+|retirer_[0-9]+)$' -and (Test-CompanionProcess $property.Value $Root)) {
                $result[$property.Name] = $property.Value
            }
        }
    } catch { }
    return $result
}

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

function Enter-CompanionOperation([string]$Root, [int]$TimeoutSeconds=1200) {
    # The open file handle is the installation lock, also across Windows logon
    # sessions. Leave its path in place; deleting it would split ownership.
    $data = Join-Path $Root 'data'
    New-Item -ItemType Directory -Path $data -Force | Out-Null
    $path = Join-Path $data 'companion-operation.lock'
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ($true) {
        try { return [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
        catch [IO.IOException] {
            if ([DateTime]::UtcNow -ge $deadline) { throw 'Another companion start or update is still in progress. Try again when it finishes.' }
            Start-Sleep -Milliseconds 200
        }
    }
}

function Start-CompanionBackend([string]$Root, [string]$Source, [string]$Python, [int]$Port, [switch]$Standby,
                                [Collections.Generic.List[Diagnostics.Process]]$OwnedProcesses) {
    $logs = Join-Path $Root 'data\runtime-logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $previousRoot = $env:PROXY_TRANSCRIPT_PROJECT_ROOT
    $env:PROXY_TRANSCRIPT_PROJECT_ROOT = $Root
    $arguments = @('-m','backend.main','--port',[string]$Port)
    if ($Standby) { $arguments += '--standby' }
    $process = $null
    try {
        $process = Start-CompanionProcess $Python $arguments $Source (Join-Path $logs "api-$Port") -LowPriority:$Standby
        if ($null -ne $OwnedProcesses) { $OwnedProcesses.Add($process) }
        return New-CompanionProcessRecord $process $Root
    } catch {
        if ($process) { Stop-CompanionProcessHandle $process }
        throw
    } finally {
        if ($process -and $null -eq $OwnedProcesses) { $process.Dispose() }
        $env:PROXY_TRANSCRIPT_PROJECT_ROOT = $previousRoot
    }
}

function Start-CompanionFrontend([string]$Root, [string]$Source, [int]$Port,
                                 [Collections.Generic.List[Diagnostics.Process]]$OwnedProcesses) {
    $logs = Join-Path $Root 'data\runtime-logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $node = (Get-Command node -ErrorAction Stop).Source
    $wrangler = Join-Path $Source 'node_modules\wrangler\bin\wrangler.js'
    $process = $null
    try {
        $process = Start-CompanionProcess $node @($wrangler,'dev','--config','dist/server/wrangler.json','--ip','127.0.0.1','--port',[string]$Port,'--inspector-port',[string]($Port+16000)) $Source (Join-Path $logs "frontend-$Port")
        if ($null -ne $OwnedProcesses) { $OwnedProcesses.Add($process) }
        return New-CompanionProcessRecord $process $Root
    } catch {
        if ($process) { Stop-CompanionProcessHandle $process }
        throw
    } finally { if ($process -and $null -eq $OwnedProcesses) { $process.Dispose() } }
}

function Start-CompanionSlot([string]$Root, [string]$Source, [string]$Python, [switch]$Standby) {
    $apiPort = Get-CompanionPort 8767 8799
    $frontendPort = Get-CompanionPort 3001 3039
    $backend = Start-CompanionBackend $Root $Source $Python $apiPort -Standby:$Standby
    try { $frontend = Start-CompanionFrontend $Root $Source $frontendPort }
    catch { Stop-CompanionProcess $backend $Root; throw }
    return [ordered]@{source=$Source; python=$Python; apiPort=$apiPort; frontendPort=$frontendPort;
                       backend=$backend.id; frontend=$frontend.id;
                       processRecords=@{backend=$backend;frontend=$frontend}}
}

function Wait-CompanionService([string]$Url, $Record, [string]$Root, [switch]$Backend) {
    for ($attempt=0; $attempt -lt 120; $attempt++) {
        if (-not (Test-CompanionProcess $Record $Root)) { throw 'A newly started companion process exited; see data/runtime-logs.' }
        if ($Backend) {
            try { if ((Invoke-RestMethod ($Url+'/api/runtime/ready') -TimeoutSec 2).ready) { return } } catch { }
        } elseif (Test-CompanionEndpoint ($Url+'/')) { return }
        Start-Sleep -Milliseconds 500
    }
    throw 'Companion did not finish starting; see data/runtime-logs.'
}

function Wait-CompanionRoutes([int]$Attempts=8) {
    # A route may briefly reject an old pooled connection after its target is
    # replaced. Give the existing router time to reconnect before retiring it.
    for ($attempt=0; $attempt -lt $Attempts; $attempt++) {
        if ((Test-CompanionEndpoint 'http://127.0.0.1:8766/api/health') -and (Test-CompanionEndpoint 'http://127.0.0.1:3000/')) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Get-CompanionStartupHandoff([string]$Api) {
    # Match backend lifespan policy after a crash/fresh install. Setup exposes
    # the persisted auto-start choice and completion flag without account writes.
    $setup = Invoke-RestMethod ($Api+'/api/setup') -TimeoutSec 5
    return @{running=([bool]$setup.completed -and [bool]$setup.auto_start)}
}

function Repair-CompanionRuntime([string]$Root, [string]$Python, $Started, $State) {
    # Caller holds Enter-CompanionOperation before reading state or identities.
    $data = Join-Path $Root 'data'
    $processFile = Join-Path $data 'processes.json'
    $statePath = Join-Path $data 'companion-runtime.json'
    $publicApi = Test-CompanionEndpoint 'http://127.0.0.1:8766/api/health'
    $publicFrontend = Test-CompanionEndpoint 'http://127.0.0.1:3000/'
    if (($publicApi -and -not ($Started.Contains('router') -or $Started.Contains('backend'))) -or
        ($publicFrontend -and -not ($Started.Contains('router') -or $Started.Contains('frontend')))) {
        throw 'A local service is already running without a verified companion process record. Close the existing launcher before starting this installation.'
    }
    if ($State -and ($publicApi -or $publicFrontend) -and -not $Started.Contains('router')) { throw 'A public endpoint has no verified companion router process record.' }
    if (-not $State -and $Started.Contains('router')) { throw 'The owned router has no readable runtime state. Restore its state before starting this installation.' }

    # Direct-port installations keep their healthy backend until a prepared
    # update. A frontend-only repair does not migrate or pause capture.
    if (-not $State -and $publicApi) {
        if (-not $publicFrontend) {
            $createdProcesses = [Collections.Generic.List[Diagnostics.Process]]::new()
            try {
                if ($Started.Contains('frontend')) { Stop-CompanionProcess $Started.frontend $Root }
                $Started.frontend = Start-CompanionFrontend $Root $Root 3000 -OwnedProcesses $createdProcesses
                Save-CompanionJson $processFile $Started
                Wait-CompanionService 'http://127.0.0.1:3000' $Started.frontend $Root
            } catch {
                $failure = $_
                foreach ($process in $createdProcesses) { try { Stop-CompanionProcessHandle $process } catch { Write-Warning 'A newly started companion process could not be cleaned up.' } }
                throw $failure
            } finally { foreach ($process in $createdProcesses) { $process.Dispose() } }
        }
        return
    }

    $source = $Root
    $active = [ordered]@{source=$Root;python=$Python;apiPort=8766;frontendPort=3000;backend=$null;frontend=$null;processRecords=@{}}
    if ($State) {
        if (-not $State.active -or -not $State.active.source -or -not $State.active.python) { throw 'Companion runtime state is incomplete.' }
        foreach ($key in @('source','python','apiPort','frontendPort','backend','frontend')) { $active[$key] = $State.active.$key }
        $source = $active.source
        $Python = $active.python
        foreach ($name in @('backend','frontend')) {
            if ($Started.Contains($name) -and $active[$name] -ne $Started[$name].id) { throw 'The active runtime does not match its verified companion process record.' }
        }
    }
    if (-not $Started.Contains('backend')) {
        # An inaccessible/reused identity must not authorize termination, but a
        # live unverified backend also cannot safely authorize another capturer.
        $unverifiedIds = @($active.backend)
        try {
            $persisted = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
            $unverifiedIds += $(if ($persisted.backend -is [ValueType]) { $persisted.backend } else { $persisted.backend.id })
        } catch { }
        foreach ($unverifiedId in $unverifiedIds) {
            $parsedId = 0
            if ([int]::TryParse([string]$unverifiedId, [ref]$parsedId) -and $parsedId -gt 0) {
                $unverified = Get-Process -Id $parsedId -ErrorAction SilentlyContinue
                if ($unverified) {
                    try { if (-not $unverified.HasExited) { throw 'A live backend has no verified companion process record. Close the existing launcher before starting this installation.' } }
                    finally { $unverified.Dispose() }
                }
            }
        }
    }
    $backendReady = $Started.Contains('backend') -and (Test-CompanionEndpoint ('http://127.0.0.1:'+$active.apiPort+'/api/health'))
    $frontendReady = $State -and $Started.Contains('frontend') -and (Test-CompanionEndpoint ('http://127.0.0.1:'+$active.frontendPort+'/'))
    if ($State) {
        foreach ($name in @('backend','frontend')) {
            $endpoint = if ($name -eq 'backend') { 'http://127.0.0.1:'+$active.apiPort+'/api/health' } else { 'http://127.0.0.1:'+$active.frontendPort+'/' }
            if (-not $Started.Contains($name) -and (Test-CompanionEndpoint $endpoint)) { throw 'An active endpoint has no verified companion process record.' }
        }
    }
    if (-not $backendReady -or -not $frontendReady) {
        if (-not $backendReady -and -not (Test-Path -LiteralPath $Python)) { throw 'Run scripts\setup.ps1 first.' }
        if (-not (Test-Path -LiteralPath (Join-Path $source 'dist\server\wrangler.json'))) { throw 'The frontend is not built. Run scripts\setup.ps1 first.' }
    }
    # Retain exact Start-Process handles until publication succeeds or rollback
    # finishes. A later image/identity lookup failure must not orphan capture.
    $createdProcesses = [Collections.Generic.List[Diagnostics.Process]]::new()
    $running = [ordered]@{}
    foreach ($key in $Started.Keys) { $running[$key] = $Started[$key] }
    try {
        if (-not $frontendReady) {
            if ($running.Contains('frontend')) { Stop-CompanionProcess $running.frontend $Root }
            $active.frontendPort = Get-CompanionPort 3001 3039
            $running.frontend = Start-CompanionFrontend $Root $source $active.frontendPort -OwnedProcesses $createdProcesses
            Wait-CompanionService ('http://127.0.0.1:'+$active.frontendPort) $running.frontend $Root
        }
        if (-not $backendReady) {
            $oldApi = 'http://127.0.0.1:'+$active.apiPort
            $active.apiPort = Get-CompanionPort 8767 8799
            $candidate = Start-CompanionBackend $Root $source $Python $active.apiPort -Standby -OwnedProcesses $createdProcesses
            $newApi = 'http://127.0.0.1:'+$active.apiPort
            Wait-CompanionService $newApi $candidate $Root -Backend
            $handoff = Get-CompanionStartupHandoff $newApi
            if ($running.Contains('backend')) {
                try {
                    $current = Invoke-RestMethod ($oldApi+'/api/status') -TimeoutSec 3
                    $handoff = @{running=[bool]$current.capture.running;session_id=$current.session.id}
                    $handoff = Invoke-RestMethod -Method Post ($oldApi+'/api/runtime/quiesce') -Headers @{'X-Proxy-Transcript'='update'} -TimeoutSec 30
                } catch { }
                # Even an unresponsive owned process may still capture. Reap it
                # (and its verified descendants) before activating a replacement.
                Stop-CompanionCaptureOwner $running.backend $Root
            }
            Set-CompanionNormalPriority $candidate $Root
            $null = Invoke-RestMethod -Method Post ($newApi+'/api/runtime/activate') -Headers @{'X-Proxy-Transcript'='update'} -ContentType 'application/json' -Body ($handoff|ConvertTo-Json -Depth 12) -TimeoutSec 15
            $running.backend = $candidate
        }
        foreach ($name in @('backend','frontend')) { $active[$name] = $running[$name].id; $active.processRecords[$name] = $running[$name] }
        Save-CompanionJson $processFile $running
        Save-CompanionJson $statePath @{version=1;active=$active}
        # A dead/stuck router is independent of both private services. After
        # repairing either target, verify both routes before replacing it.
        if (-not $running.Contains('router') -or -not (Wait-CompanionRoutes)) {
            if ($running.Contains('router')) { Stop-CompanionProcess $running.router $Root }
            $router = Start-CompanionRouter $Root $source
            $createdProcesses.Add($router)
            $running.router = New-CompanionProcessRecord $router $Root
            Save-CompanionJson $processFile $running
        }
        for ($attempt=0; $attempt -lt 120; $attempt++) {
            if ((Test-CompanionEndpoint 'http://127.0.0.1:8766/api/health') -and (Test-CompanionEndpoint 'http://127.0.0.1:3000/')) { return }
            Start-Sleep -Milliseconds 500
        }
        throw 'Companion did not finish starting; see data/runtime-logs.'
    } catch {
        $failure = $_
        for ($index=$createdProcesses.Count-1; $index -ge 0; $index--) {
            try { Stop-CompanionProcessHandle $createdProcesses[$index] } catch { Write-Warning 'A newly started companion process could not be cleaned up.' }
        }
        throw $failure
    } finally { foreach ($process in $createdProcesses) { $process.Dispose() } }
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

function Set-CompanionNormalPriority($Record, [string]$Root) {
    $process = Get-CompanionOwnedProcess $Record $Root
    if (-not $process) { throw 'Replacement backend exited before activation.' }
    try {
        try { $process.PriorityClass='Normal' } catch { }
        # venv launchers can have one real Python child. Hold both process
        # handles and recheck parentage before recording/promoting that child.
        Get-CimInstance Win32_Process -Filter ('ParentProcessId='+$process.Id) -ErrorAction SilentlyContinue | ForEach-Object {
            $child=$null
            try {
                $child=Get-Process -Id ([int]$_.ProcessId) -ErrorAction Stop
                $null=$child.Handle
                $live=Get-CimInstance Win32_Process -Filter ('ProcessId='+$child.Id) -ErrorAction Stop
                if (-not $child.HasExited -and $live.ParentProcessId -eq $process.Id -and
                    $child.StartTime.ToUniversalTime().Ticks -ge $process.StartTime.ToUniversalTime().Ticks) {
                    Set-CompanionNormalPriority (New-CompanionProcessRecord $child $Root) $Root
                }
            } catch { }
            finally { if($child){$child.Dispose()} }
        }
    } finally { $process.Dispose() }
}
