param([Parameter(Mandatory = $true)][string]$RuntimeRoot,
      [Parameter(Mandatory = $true)][string]$Provenance)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'r19-runtime-inventory.ps1')
$RuntimeRoot = (Resolve-Path -LiteralPath $RuntimeRoot).Path
$manifest = Get-Content -LiteralPath (Join-Path $RuntimeRoot '_internal/runtime-manifest.json') -Raw | ConvertFrom-Json
if ($manifest.profile -ne 'runtime-experiment' -or $manifest.source_commit -ne $env:GITHUB_SHA) { throw 'Wrong extracted experiment identity.' }
$output = Join-Path $env:GITHUB_WORKSPACE 'output/checks/r19-frozen-runtime.json'
Remove-Item -LiteralPath $output -Force -ErrorAction SilentlyContinue
$temporary = Join-Path $env:RUNNER_TEMP ('R19 runtime space 漢字 ' + [guid]::NewGuid())
$state = Join-Path $temporary 'synthetic'
$roots = @{
    PROXY_TRANSCRIPT_SETTINGS_ROOT=$state; PROXY_TRANSCRIPT_DATA_ROOT=(Join-Path $state 'data-v1')
    PROXY_TRANSCRIPT_CACHE_ROOT=(Join-Path $state 'cache-v1'); PROXY_TRANSCRIPT_WORK_ROOT=(Join-Path $state 'cache-v1/work')
    PROXY_TRANSCRIPT_TOOL_ROOT=(Join-Path $state 'tools-v1'); PROXY_TRANSCRIPT_STATE_ROOT=(Join-Path $state 'host-v1')
    PROXY_TRANSCRIPT_DEFAULT_EXPORT_ROOT=(Join-Path $state 'exports')
}
$owned = [Collections.Generic.List[Diagnostics.Process]]::new()
$tasks = @{}
function Start-Owned([string]$image, [string]$arguments, [string]$HostCase='') {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $image; $info.Arguments = $arguments
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $info.RedirectStandardInput = [bool]$HostCase
    $info.WorkingDirectory = $temporary
    $info.Environment.Clear()
    foreach ($name in @('WINDIR', 'SystemRoot', 'COMSPEC', 'PATHEXT')) { if ([Environment]::GetEnvironmentVariable($name)) { $info.Environment[$name] = [Environment]::GetEnvironmentVariable($name) } }
    $info.Environment['PATH'] = "$env:WINDIR/System32;$env:WINDIR"
    foreach ($name in @('TEMP', 'TMP', 'USERPROFILE', 'HOME', 'LOCALAPPDATA', 'APPDATA')) { $info.Environment[$name] = (Join-Path $temporary 'empty-host') }
    foreach ($name in $roots.Keys) { $info.Environment[$name] = $roots[$name] }
    $info.Environment['PROXY_TRANSCRIPT_STANDBY'] = '1'
    $info.Environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $info
    if (-not $process.Start()) { throw 'Owned runtime process did not start.' }
    $owned.Add($process)
    if ($HostCase) {
        # This one private control line includes transient Job Object members.
        # It is consumed locally and never copied into public metadata.
        $tasks[$process.Id] = @($process.StandardOutput.ReadLineAsync(), $process.StandardError.ReadToEndAsync())
        $process.StandardInput.WriteLine($HostCase)
        $process.StandardInput.Flush()
    } else {
        $tasks[$process.Id] = @($process.StandardOutput.ReadToEndAsync(), $process.StandardError.ReadToEndAsync())
    }
    return $process
}
function Start-HostProbe([string]$Case='normal') {
    $image = Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe'
    $process = Start-Owned $image '--runtime-probe host' $Case
    $held = [Collections.Generic.List[Diagnostics.Process]]::new()
    try {
        if (-not $tasks[$process.Id][0].Wait(70000)) { throw 'Owned host startup deadline expired.' }
        $control = $tasks[$process.Id][0].GetAwaiter().GetResult() | ConvertFrom-Json
        if ($control.schema -ne 'proxy-r19-owned-host-probe-v1' -or $control.status -ne 'services-ready' -or
            $control.build_id -ne $manifest.build_id -or $control.source_commit -ne $env:GITHUB_SHA -or
            $control.native_owned_process_tree -ne 'real' -or $control.api_external_side_effects -ne 'mocked' -or
            $control.r19_complete -ne $false) { throw 'Owned host service/control identity is invalid.' }
        $members = @($control.job_members)
        if ($members.Count -lt 4 -or $members.Count -gt 16 -or @($members | Select-Object -Unique).Count -ne $members.Count) {
            throw 'Owned host did not retain its bootstraps and service processes.'
        }
        foreach ($member in $members) {
            if (($member -isnot [long] -and $member -isnot [int]) -or $member -lt 1) { throw 'Invalid private job member identity.' }
            $observer = [Diagnostics.Process]::GetProcessById([int]$member)
            $held.Add($observer)
            $null = $observer.Handle
            # These handles are for exit observation only. No PID/control
            # message authorizes a process termination or ownership adoption.
            if ($observer.HasExited -or $observer.StartTime.ToUniversalTime() -lt $process.StartTime.ToUniversalTime() -or
                [IO.Path]::GetFullPath($observer.MainModule.FileName) -ne [IO.Path]::GetFullPath($image)) {
                throw 'Owned host observation handle identity is unavailable.'
            }
        }
        return [pscustomobject]@{process=$process; held=$held; case=$Case}
    } catch {
        foreach ($observer in $held) { $observer.Dispose() }
        throw
    }
}
function Complete-HostProbe($Context, [ValidateSet('stop','exit-frontend','parent-crash','unprepared-index')][string]$Action) {
    $process = $Context.process
    try {
        if ($Action -eq 'parent-crash') {
            $process.Kill() # Only the already retained host handle; Job close owns child cleanup.
        } elseif ($Action -ne 'unprepared-index') {
            $process.StandardInput.WriteLine($Action)
            $process.StandardInput.Flush()
        }
        if (-not $process.WaitForExit(15000)) { throw 'Owned host stop/failure deadline expired.' }
        $remaining = $process.StandardOutput.ReadToEndAsync().GetAwaiter().GetResult()
        $null = $tasks[$process.Id][1].GetAwaiter().GetResult()
        foreach ($observer in $Context.held) {
            if (-not $observer.WaitForExit(10000) -or -not $observer.HasExited) { throw 'A retained native child handle is not signaled.' }
        }
        if ($Action -ne 'parent-crash') {
            $result = $remaining | ConvertFrom-Json
            $expectedFailure = if ($Action -eq 'exit-frontend') {'child-exited'} elseif ($Action -eq 'unprepared-index') {'unprepared-index-deadline'} else {''}
            if ($result.schema -ne 'proxy-r19-owned-host-probe-v1' -or $result.build_id -ne $manifest.build_id -or
                $result.source_commit -ne $env:GITHUB_SHA -or $result.owned_cleanup -ne 'confirmed' -or
                $result.api_external_side_effects -ne 'mocked' -or $result.native_owned_process_tree -ne 'real' -or
                $result.r19_complete -ne $false -or
                ($expectedFailure -and ($process.ExitCode -ne 2 -or $result.status -ne 'failed' -or $result.failure -ne $expectedFailure)) -or
                (-not $expectedFailure -and ($process.ExitCode -ne 0 -or $result.status -ne 'passed'))) {
                throw 'Owned host failure/recovery outcome is unexpected.'
            }
        } elseif ($process.ExitCode -eq 0) { throw 'Parent crash fixture did not terminate the actual host.' }
        foreach ($port in @(3000, 8766)) {
            $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
            try { $listener.Start() } finally { $listener.Stop() }
        }
        # No raw control records, Job members, native handles or logs escape.
        return @{case=$Action; status='passed'; retained_children=$Context.held.Count;
            child_exit='retained-handles-signaled'; canonical_ports='released'; native_owned_process_tree='real'; api_external_side_effects='mocked'}
    } finally {
        foreach ($observer in $Context.held) { $observer.Dispose() }
    }
}
function Test-ForeignHostListeners {
    # Authored fixture services have retained outer handles but are outside the
    # new host's Job. This is never a probe of an installed/source companion.
    $image = Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe'
    $foreignFrontend = Start-Owned $image '--runtime-child frontend -- --port 3000'
    $foreignApi = Start-Owned $image '--runtime-probe api'
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(60); $fixtureReady = $false
        do {
            if ($foreignFrontend.HasExited -or $foreignApi.HasExited) { throw 'Foreign-listener authored fixture exited.' }
            try {
                $fixtureReady = (Invoke-RestMethod 'http://127.0.0.1:8766/api/runtime/ready' -TimeoutSec 2).ready -and
                    (Invoke-WebRequest 'http://127.0.0.1:3000/' -TimeoutSec 2).StatusCode -eq 200
            } catch { $fixtureReady = $false }
            if (-not $fixtureReady) { Start-Sleep -Milliseconds 100 }
        } until ($fixtureReady -or [DateTime]::UtcNow -ge $deadline)
        if (-not $fixtureReady) { throw 'Foreign-listener authored fixture readiness expired.' }
        $candidate = Start-Owned $image '--runtime-probe host' 'normal'
        if (-not $tasks[$candidate.Id][0].Wait(70000)) { throw 'Foreign-listener refusal deadline expired.' }
        $control = $tasks[$candidate.Id][0].GetAwaiter().GetResult() | ConvertFrom-Json
        if (-not $candidate.WaitForExit(15000)) { throw 'Refused host did not stop its owned processes.' }
        $null = $candidate.StandardOutput.ReadToEndAsync().GetAwaiter().GetResult()
        $null = $tasks[$candidate.Id][1].GetAwaiter().GetResult()
        # An early owned-child bind failure is also a correct refusal. A ready
        # response from these foreign services must never produce services-ready.
        if ($candidate.ExitCode -ne 2 -or $control.schema -ne 'proxy-r19-owned-host-probe-v1' -or
            $control.status -ne 'failed' -or $control.failure -notin @('foreign-canonical-listener','child-exited') -or
            $control.owned_cleanup -ne 'confirmed' -or $control.build_id -ne $manifest.build_id -or
            $control.source_commit -ne $env:GITHUB_SHA -or $control.r19_complete -ne $false) {
            throw 'Existing ready listeners were mistaken for the new host-owned services.'
        }
        if ($foreignFrontend.HasExited -or $foreignApi.HasExited -or
            -not (Invoke-RestMethod 'http://127.0.0.1:8766/api/runtime/ready' -TimeoutSec 2).ready -or
            (Invoke-WebRequest 'http://127.0.0.1:3000/' -TimeoutSec 2).StatusCode -ne 200) {
            throw 'The refused host disturbed a listener outside its owned Job.'
        }
        return @{case='foreign-ready-listeners'; status='passed'; readiness='refused'; outside_job_services='retained-fixture-still-live'}
    } finally {
        foreach ($fixture in @($foreignFrontend, $foreignApi)) {
            if (-not $fixture.HasExited) { $fixture.Kill($true) } # Retained outer fixture handle only.
            if (-not $fixture.WaitForExit(10000)) { throw 'An outer authored listener fixture did not stop.' }
        }
    }
}
function Finish-Probe($process, [string]$kind) {
    if (-not $process.WaitForExit(300000)) { throw 'Runtime probe deadline expired.' }
    $stdout = $tasks[$process.Id][0].GetAwaiter().GetResult()
    $stderr = $tasks[$process.Id][1].GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) {
        # Private failure evidence stays on this disposable build host.
        [IO.File]::WriteAllText((Join-Path $temporary ($kind + '-failure.log')), $stdout + $stderr)
        try {
            $failure = $stdout | ConvertFrom-Json
            # This fixed probe's JSON excludes paths, fixture text and accounts.
            if ($failure.status -eq 'failed') { Write-Host ($failure.error | ConvertTo-Json -Compress) }
        } catch { }
        throw "Frozen $kind probe failed; inspect private build-host evidence."
    }
    $result = $stdout | ConvertFrom-Json
    if ($result.status -ne 'passed' -or $result.kind -ne $kind -or $result.build_id -ne $manifest.build_id -or $result.source_commit -ne $env:GITHUB_SHA -or $result.r19_complete -ne $false) { throw 'Frozen runtime probe identity or scope mismatch.' }
    return $result
}
$native = $null; $asr = $null; $hostChecks = @(); $websocket = $null
New-Item -ItemType Directory -Path (Join-Path $temporary 'empty-host'), $roots.PROXY_TRANSCRIPT_STATE_ROOT -Force | Out-Null
@{build_id=$manifest.build_id; synthetic=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $roots.PROXY_TRANSCRIPT_STATE_ROOT 'synthetic-probe.json') -Encoding utf8NoBOM
try {
    Test-R19RuntimeInventory $temporary
    $proof = Get-Content -LiteralPath $Provenance -Raw | ConvertFrom-Json
    $before = @(Get-R19RuntimeInventory $RuntimeRoot)
    $expected = @($proof.files | ForEach-Object { 'file:' + $_.path + ':' + $_.sha256 })
    $expected += @($proof.directories | ForEach-Object { 'directory:' + $_ })
    if (@(Compare-Object @($before | Sort-Object) @($expected | Sort-Object) -CaseSensitive).Count) { throw 'Extracted tree differs from the complete candidate inventory.' }
    Get-ChildItem -LiteralPath $RuntimeRoot -File -Recurse -Force | ForEach-Object { $_.IsReadOnly = $true }
    # No SDK, compiler, package manager or external interpreter is inherited.
    $native = Finish-Probe (Start-Owned (Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe') '--runtime-probe native') 'native'
    $asr = Finish-Probe (Start-Owned (Join-Path $RuntimeRoot 'asr/ProxyTranscriptAsr.exe') '--runtime-probe asr') 'asr'
    foreach ($port in @(3000, 8766)) {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
        try { $listener.Start() } finally { $listener.Stop() }
    }
    $hostProbe = Start-HostProbe
    $ready = $true
    $status = Invoke-RestMethod 'http://127.0.0.1:8766/api/status' -TimeoutSec 10
    if ($status.capture.running -or @($status.game_textmaps.PSObject.Properties).Count -lt 25) { throw 'Synthetic API capture/registry state is unexpected.' }
    $setup = Invoke-RestMethod 'http://127.0.0.1:8766/api/setup' -TimeoutSec 10
    if ('node' -in @($setup.requirements.id) -or 'runtime-acceptance' -notin @($setup.requirements.id) -or @($setup.games | Where-Object { $_.id -eq 'endfield' }).voice_hint -match 'SDK') { throw 'Frozen setup still asks for development tools or hides its acceptance gate.' }
    $blocked = Invoke-WebRequest 'http://127.0.0.1:8766/api/health' -Headers @{Origin='https://example.test'} -SkipHttpErrorCheck -TimeoutSec 5
    if ($blocked.StatusCode -ne 403) { throw 'Integrated API accepted a foreign origin.' }
    $websocket = [Net.WebSockets.ClientWebSocket]::new()
    $websocket.Options.SetRequestHeader('Origin', 'http://127.0.0.1:3000')
    $cancel = [Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(10))
    try {
        $websocket.ConnectAsync([Uri]'ws://127.0.0.1:8766/api/ws', $cancel.Token).GetAwaiter().GetResult()
        $buffer = [byte[]]::new(65536)
        $message = [IO.MemoryStream]::new()
        try {
            do {
                $received = $websocket.ReceiveAsync([ArraySegment[byte]]::new($buffer), $cancel.Token).GetAwaiter().GetResult()
                if ($received.Count -le 0 -or $received.MessageType -ne [Net.WebSockets.WebSocketMessageType]::Text) { throw 'Actual frozen API WebSocket did not produce a text event.' }
                $message.Write($buffer, 0, $received.Count)
                if ($message.Length -gt 1048576) { throw 'Frozen API event exceeded its fixture bound.' }
            } until ($received.EndOfMessage)
            $event = [Text.Encoding]::UTF8.GetString($message.ToArray()) | ConvertFrom-Json
            if ($event.type -ne 'snapshot' -or $event.snapshot.capture.running -or @($event.snapshot.game_textmaps.PSObject.Properties).Count -lt 25) { throw 'Actual frozen WebSocket snapshot lost capture or registry state.' }
        } finally { $message.Dispose() }
    } finally { $cancel.Dispose() }
    $websocket.Abort(); $websocket.Dispose(); $websocket = $null
    $hostChecks += Complete-HostProbe $hostProbe 'stop'
    $hostChecks += Complete-HostProbe (Start-HostProbe) 'exit-frontend'
    $hostChecks += Complete-HostProbe (Start-HostProbe) 'parent-crash'
    $hostChecks += Complete-HostProbe (Start-HostProbe 'unprepared-index') 'unprepared-index'
    $hostChecks += Test-ForeignHostListeners
    $after = @(Get-R19RuntimeInventory $RuntimeRoot)
    if (@(Compare-Object $before $after -CaseSensitive).Count) { throw 'Frozen runtime wrote into its application tree.' }
    $forbidden = @(Get-ChildItem -LiteralPath $temporary -File -Recurse -Force | Where-Object { $_.Extension -eq '.dpapi' })
    if ($forbidden.Count) { throw 'Synthetic probes unexpectedly wrote protected account state.' }
} finally {
    if ($websocket) { $websocket.Abort(); $websocket.Dispose() }
    foreach ($process in $owned) {
        if (-not $process.HasExited) { $process.Kill($true) }
        if (-not $process.WaitForExit(10000)) { throw 'An owned runtime process did not stop.' }
        $process.Dispose()
    }
    Get-ChildItem -LiteralPath $RuntimeRoot -File -Recurse -Force | ForEach-Object { $_.IsReadOnly = $false }
    # Keep failure logs private until the runner expires; success removes all
    # owned fixture data before any passing metadata can be written.
    if ($native -and $asr -and $ready -and $after -and -not $forbidden.Count) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
if (Test-Path -LiteralPath $temporary) { throw 'Owned runtime fixture cleanup is incomplete.' }
New-Item -ItemType Directory -Path (Split-Path $output) -Force | Out-Null
@{schema='proxy-r19-frozen-runtime-v1'; source_commit=$env:GITHUB_SHA; build_id=$manifest.build_id; status='passed';
    executable_sha256=(Get-FileHash -LiteralPath (Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe') -Algorithm SHA256).Hash.ToLowerInvariant();
    asr_executable_sha256=(Get-FileHash -LiteralPath (Join-Path $RuntimeRoot 'asr/ProxyTranscriptAsr.exe') -Algorithm SHA256).Hash.ToLowerInvariant();
    inventory_sha256=(Get-FileHash -LiteralPath (Join-Path (Split-Path $Provenance) 'RUNTIME-INVENTORY.json') -Algorithm SHA256).Hash.ToLowerInvariant();
    native=$native; asr=$asr; host=$hostChecks; frontend_api_http_ws='passed'; api_external_side_effects='mocked';
    developer_environment='cleared; only OS essentials and synthetic roots'; application_writes_observed=$false;
    hidden_system_inventory_fixture='passed';
    owned_cleanup='passed'; r19_complete=$false; rights_review='pending-exact-output'; native_windows_11_acceptance='unavailable';
    native_ocr_capture='not-run'; installed_game_playback='not-run'; installer='not-built'} |
    ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $output -Encoding utf8
