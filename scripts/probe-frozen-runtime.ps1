param([Parameter(Mandatory = $true)][string]$RuntimeRoot,
      [Parameter(Mandatory = $true)][string]$Provenance)
$ErrorActionPreference = 'Stop'
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
function Start-Owned([string]$image, [string]$arguments) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $image; $info.Arguments = $arguments
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
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
    $tasks[$process.Id] = @($process.StandardOutput.ReadToEndAsync(), $process.StandardError.ReadToEndAsync())
    return $process
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
function Inventory([string]$folder) {
    return @((Get-ChildItem -LiteralPath $folder -File -Recurse | Sort-Object FullName | ForEach-Object {
        $_.FullName.Substring($folder.Length + 1).Replace('\', '/') + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }))
}
$native = $null; $asr = $null; $api = $null; $websocket = $null
New-Item -ItemType Directory -Path (Join-Path $temporary 'empty-host'), $roots.PROXY_TRANSCRIPT_STATE_ROOT -Force | Out-Null
@{build_id=$manifest.build_id; synthetic=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $roots.PROXY_TRANSCRIPT_STATE_ROOT 'synthetic-probe.json') -Encoding utf8NoBOM
try {
    $proof = Get-Content -LiteralPath $Provenance -Raw | ConvertFrom-Json
    $before = @(Inventory $RuntimeRoot)
    $expected = @($proof.files | ForEach-Object { $_.path + ':' + $_.sha256 } | Sort-Object)
    if (@(Compare-Object @($before | Sort-Object) $expected).Count) { throw 'Extracted files differ from the complete candidate inventory.' }
    Get-ChildItem -LiteralPath $RuntimeRoot -File -Recurse | ForEach-Object { $_.IsReadOnly = $true }
    # No SDK, compiler, package manager or external interpreter is inherited.
    $native = Finish-Probe (Start-Owned (Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe') '--runtime-probe native') 'native'
    $asr = Finish-Probe (Start-Owned (Join-Path $RuntimeRoot 'asr/ProxyTranscriptAsr.exe') '--runtime-probe asr') 'asr'
    foreach ($port in @(3000, 8766)) {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
        try { $listener.Start() } finally { $listener.Stop() }
    }
    $frontend = Start-Owned (Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe') '--runtime-child frontend -- --port 3000'
    $api = Start-Owned (Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe') '--runtime-probe api'
    $deadline = [DateTime]::UtcNow.AddSeconds(60); $ready = $false
    do {
        if ($api.HasExited -or $frontend.HasExited) { throw 'Integrated frozen service exited before readiness.' }
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8766/api/health' -TimeoutSec 2
            $page = Invoke-WebRequest 'http://127.0.0.1:3000/' -TimeoutSec 2
            $ready = $health.status -eq 'ok' -and $page.StatusCode -eq 200
        } catch { $ready = $false }
        if (-not $ready) { Start-Sleep -Milliseconds 200 }
    } until ($ready -or [DateTime]::UtcNow -ge $deadline)
    if (-not $ready) { throw 'Integrated frozen service startup deadline expired.' }
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
    $after = @(Inventory $RuntimeRoot)
    if (@(Compare-Object $before $after).Count) { throw 'Frozen runtime wrote into its application tree.' }
    $forbidden = @(Get-ChildItem -LiteralPath $temporary -File -Recurse | Where-Object { $_.Extension -eq '.dpapi' })
    if ($forbidden.Count) { throw 'Synthetic probes unexpectedly wrote protected account state.' }
} finally {
    if ($websocket) { $websocket.Abort(); $websocket.Dispose() }
    foreach ($process in $owned) {
        if (-not $process.HasExited) { $process.Kill($true) }
        if (-not $process.WaitForExit(10000)) { throw 'An owned runtime process did not stop.' }
        $process.Dispose()
    }
    Get-ChildItem -LiteralPath $RuntimeRoot -File -Recurse | ForEach-Object { $_.IsReadOnly = $false }
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
    native=$native; asr=$asr; frontend_api_http_ws='passed'; api_external_side_effects='mocked';
    developer_environment='cleared; only OS essentials and synthetic roots'; application_writes_observed=$false;
    owned_cleanup='passed'; r19_complete=$false; rights_review='pending-exact-output'; native_windows_11_acceptance='unavailable';
    native_ocr_capture='not-run'; installed_game_playback='not-run'; installer='not-built'} |
    ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $output -Encoding utf8
