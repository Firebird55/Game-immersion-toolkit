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
    if ($Process.HasExited) { return }
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
    $frontend = $null
    try {
        $backendRecord = New-CompanionProcessRecord $backend $Root
        $wrangler = Join-Path $Source 'node_modules\wrangler\bin\wrangler.js'
        $frontend = Start-CompanionProcess $node @($wrangler,'dev','--config','dist/server/wrangler.json','--ip','127.0.0.1','--port',[string]$frontendPort,'--inspector-port',[string]($frontendPort+16000)) $Source (Join-Path $logs "frontend-$frontendPort")
        $frontendRecord = New-CompanionProcessRecord $frontend $Root
    } catch {
        $failure=$_
        foreach($process in @($frontend,$backend)) {
            if($process){try{Stop-CompanionProcessHandle $process}catch{Write-Warning 'A newly started companion process could not be cleaned up.'}}
        }
        throw $failure
    }
    return [ordered]@{source=$Source; python=$Python; apiPort=$apiPort; frontendPort=$frontendPort;
                       backend=$backend.Id; frontend=$frontend.Id;
                       processRecords=@{backend=$backendRecord;frontend=$frontendRecord}}
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
    if (-not $process) { throw 'Replacement backend exited before activation; current capture was kept active.' }
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
