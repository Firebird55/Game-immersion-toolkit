param([Parameter(Mandatory=$true)][string]$RuntimeRoot,
      [Parameter(Mandatory=$true)][string]$Provenance,
      [string]$Output=(Join-Path $PSScriptRoot '../output/checks/r19-guarded-slots.json'))
$ErrorActionPreference = 'Stop'
$slotSourceOperation=Join-Path $PSScriptRoot 'companion-runtime.ps1'
Remove-Item -LiteralPath $Output -Force -ErrorAction SilentlyContinue
. (Join-Path $PSScriptRoot 'r19-runtime-inventory.ps1')

function Assert-SlotEntryName([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name) -or $Name.Contains('\') -or [IO.Path]::IsPathRooted($Name) -or
        @($Name.Split('/') | Where-Object { -not $_ -or $_ -in @('.','..') -or $_.Contains(':') -or $_ -match '[. ]$|[\x00-\x1f]' -or $_ -match '^(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$' }).Count) {
        throw 'Unsafe immutable slot inventory name.'
    }
}
function Assert-SlotInventory([string]$Root, $Proof) {
    foreach ($ancestor in @((Get-Item -LiteralPath $Root), (Get-Item -LiteralPath $Root).Parent)) {
        while ($ancestor) {
            if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Slot roots cannot follow reparse points.' }
            $ancestor = $ancestor.Parent
        }
    }
    if (@(Get-ChildItem -LiteralPath $Root -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw 'Immutable slots cannot contain reparse points.'
    }
    $aliases = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $expected = @()
    foreach ($entry in $Proof.files) {
        Assert-SlotEntryName $entry.path
        if (-not $aliases.Add($entry.path) -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$' -or $entry.bytes -lt 0) { throw 'Invalid immutable file identity.' }
        $file = Join-Path $Root $entry.path
        if (-not [IO.File]::Exists($file) -or (Get-Item -LiteralPath $file).Length -ne $entry.bytes) { throw 'Immutable slot file size differs.' }
        $expected += 'file:' + $entry.path + ':' + $entry.sha256
    }
    foreach ($directory in $Proof.directories) {
        Assert-SlotEntryName $directory
        if (-not $aliases.Add($directory)) { throw 'Aliased immutable slot directory.' }
        $expected += 'directory:' + $directory
    }
    if (@(Compare-Object @($expected | Sort-Object) @(Get-R19RuntimeInventory $Root | Sort-Object) -CaseSensitive).Count) {
        throw 'Complete immutable slot inventory differs.'
    }
    $identity = Get-Content -LiteralPath (Join-Path $Root '_internal/runtime-manifest.json') -Raw | ConvertFrom-Json
    if ($identity.profile -ne 'runtime-experiment' -or $identity.build_id -ne $Proof.build_id -or $identity.source_commit -ne $Proof.source_commit) {
        throw 'Immutable slot manifest identity differs.'
    }
}
function Invoke-SlotLeaseObservation([string]$Path, [ValidateSet('native','legacy-source')][string]$Kind='native') {
    # Independent, fixed contender: no profiles, arbitrary script or path text
    # interpolation. Its only input is the guardian's authored lease path.
    $command = @'
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
try {
    $inputRecord=[Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($inputRecord.kind -eq 'legacy-source') {
        $tokens=$null; $parseErrors=$null
        $ast=[Management.Automation.Language.Parser]::ParseFile([string]$inputRecord.source,[ref]$tokens,[ref]$parseErrors)
        if ($parseErrors) { throw 'Source operation parse failure.' }
        $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Enter-CompanionOperation'},$true)
        if (-not $definition) { throw 'Missing source operation.' }
        . ([scriptblock]::Create($definition.Extent.Text))
        try {
            $stream=Enter-CompanionOperation ([string]$inputRecord.path) -TimeoutSeconds 0
            $stream.Dispose()
            [Console]::Out.WriteLine('open')
        } catch {
            if ($_.Exception.Message -ceq 'Another companion start or update is still in progress. Try again when it finishes.') { [Console]::Out.WriteLine('blocked') }
            else { [Console]::Out.WriteLine('unavailable') }
        }
    } elseif ($inputRecord.kind -eq 'native') {
        try {
            $stream=[IO.File]::Open([string]$inputRecord.path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
            $stream.Dispose()
            [Console]::Out.WriteLine('open')
        } catch {
            if (($_.Exception.GetBaseException().HResult -band 0xffff) -eq 32) { [Console]::Out.WriteLine('blocked') }
            else { [Console]::Out.WriteLine('unavailable') }
        }
    } else { throw 'Unknown fixed contender.' }
} catch { [Console]::Out.WriteLine('unavailable') }
'@
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = [Environment]::ProcessPath
    $info.Arguments = '-NoProfile -NonInteractive -EncodedCommand ' + [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $info.UseShellExecute=$false; $info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true; $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
    $info.StandardInputEncoding=[Text.UTF8Encoding]::new($false)
    $info.StandardOutputEncoding=[Text.UTF8Encoding]::new($false)
    $info.StandardErrorEncoding=[Text.UTF8Encoding]::new($false)
    $info.Environment['POWERSHELL_TELEMETRY_OPTOUT']='1'
    $info.Environment['POWERSHELL_UPDATECHECK']='Off'
    $contender = [Diagnostics.Process]::new(); $contender.StartInfo=$info
    try {
        if (-not $contender.Start()) { throw 'Independent lease observer did not start.' }
        $null=$contender.Handle
        $stdout=$contender.StandardOutput.ReadToEndAsync(); $stderr=$contender.StandardError.ReadToEndAsync()
        $inputRecord=@{kind=$Kind;path=$Path;source=$slotSourceOperation}
        $contender.StandardInput.Write(($inputRecord | ConvertTo-Json -Compress)); $contender.StandardInput.Close()
        if (-not $contender.WaitForExit(10000)) { throw 'Independent lease observation timed out.' }
        $value=$stdout.GetAwaiter().GetResult().Trim(); $null=$stderr.GetAwaiter().GetResult()
        if ($contender.ExitCode -ne 0 -or $value -notin @('open','blocked')) { throw 'Independent lease observation is unavailable.' }
        return $value
    } finally {
        if ($contender.Id -and -not $contender.HasExited) {
            $contender.Kill()
            if (-not $contender.WaitForExit(5000)) { throw 'Retained lease contender did not exit.' }
        }
        $contender.Dispose()
    }
}
function Assert-SlotLeasesBlocked {
    foreach ($path in $leasePaths) {
        if ((Invoke-SlotLeaseObservation $path) -ne 'blocked') { throw 'Legacy or target exclusion was released during the operation.' }
    }
    if ((Invoke-SlotLeaseObservation $legacyRoot 'legacy-source') -ne 'blocked') { throw 'The existing source operation entered while the guardian owned its legacy lease.' }
    $script:sourceOperationBlocks++
}
function Write-SlotStage([string]$Stage) {
    $script:stage=$Stage
    $stages.Add($Stage)
    $journal=@{schema='proxy-r19-private-slot-attempt-v1'; stage=$Stage; sequence=$stages.Count;
        build_id=$proof.build_id; source_commit=$proof.source_commit; authority='live-guardian-handles-only'; activation_allowed=$false}
    $pending=Join-Path $guardianRoot 'journal.pending'; $path=Join-Path $guardianRoot 'journal.json'
    $bytes=[Text.Encoding]::UTF8.GetBytes(($journal | ConvertTo-Json))
    $stream=[IO.File]::Open($pending, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
    if ([IO.File]::Exists($path)) { [IO.File]::Replace($pending,$path,$path+'.previous') }
    else { [IO.File]::Move($pending,$path) }
}
function Start-GuardedSlot([ValidateSet('A','B')][string]$Name, [string]$Case='normal') {
    Assert-SlotLeasesBlocked
    $script:RuntimeRoot=$slots[$Name].application
    $script:manifest=Get-Content -LiteralPath (Join-Path $RuntimeRoot '_internal/runtime-manifest.json') -Raw | ConvertFrom-Json
    $script:roots=$slots[$Name].roots
    Assert-SlotInventory $RuntimeRoot $proof
    $context=Start-HostProbe $Case
    $context | Add-Member -NotePropertyName closed -NotePropertyValue $false
    $contexts.Add($context)
    Assert-SlotLeasesBlocked
    return $context
}
function Assert-SlotPortsFree {
    foreach ($port in @(3000,8766)) {
        $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$port)
        try { $listener.Start() } finally { $listener.Stop() }
    }
}
function Stop-GuardedSlot($Context, [ValidateSet('stop','crash','unprepared-index')][string]$Action='stop') {
    if ($Context.closed) { return }
    Assert-SlotLeasesBlocked
    $process=$Context.process
    $exited=$process.HasExited
    if ($exited -isnot [bool]) { throw 'Retained slot host state is unavailable.' }
    if ($Action -eq 'crash' -and -not $exited) { $process.Kill() }
    elseif ($Action -eq 'stop' -and -not $exited) { $process.StandardInput.WriteLine('stop'); $process.StandardInput.Flush() }
    $stopBudget=[Diagnostics.Stopwatch]::StartNew()
    if (-not $process.WaitForExit(15000)) { throw 'Owned slot host did not stop.' }
    foreach ($observer in $Context.held) {
        $remaining=[int][Math]::Max(0,15000-$stopBudget.ElapsedMilliseconds)
        if (-not $observer.WaitForExit($remaining)) { throw 'A retained slot child handle is not signaled.' }
    }
    if ($Action -ne 'crash') {
        $result=$process.StandardOutput.ReadToEndAsync().GetAwaiter().GetResult() | ConvertFrom-Json
        $expectedStatus=if ($Action -eq 'stop') {'passed'} else {'failed'}
        $expectedExit=if ($Action -eq 'stop') {0} else {2}
        if ($process.ExitCode -ne $expectedExit -or $result.schema -ne 'proxy-r19-owned-host-probe-v1' -or
            $result.status -ne $expectedStatus -or $result.owned_cleanup -ne 'confirmed' -or
            $result.build_id -ne $proof.build_id -or $result.source_commit -ne $proof.source_commit -or
            $result.native_owned_process_tree -ne 'real' -or $result.api_external_side_effects -ne 'mocked' -or $result.r19_complete -ne $false -or
            ($Action -eq 'unprepared-index' -and $result.failure -ne 'unprepared-index-deadline')) { throw 'Slot cleanup outcome is unconfirmed.' }
    }
    $null=$tasks[$process.Id][1].GetAwaiter().GetResult()
    # Ownership cleanup is confirmed before separate contention/port checks.
    # A failed postcondition must not discard that native exit observation.
    $Context.closed=$true
    Assert-SlotLeasesBlocked
    Assert-SlotPortsFree
}
function Invoke-StrictSlotDrain {
    Assert-SlotLeasesBlocked
    $handoff=Invoke-RestMethod -Method Post 'http://127.0.0.1:8766/api/runtime/quiesce?writers=true' -Headers @{'X-Proxy-Transcript'='update'} -TimeoutSec 35
    if ($handoff.running -ne $false) { throw 'Only paused authored capture may enter this probe.' }
    $ordinary=Invoke-WebRequest 'http://127.0.0.1:8766/api/status' -SkipHttpErrorCheck -TimeoutSec 3
    if ($ordinary.StatusCode -ne 503 -or (Invoke-RestMethod 'http://127.0.0.1:8766/api/health' -TimeoutSec 3).status -ne 'ok') {
        throw 'Strict writer admission did not close while control remained available.'
    }
    Assert-SlotLeasesBlocked
    return $handoff
}
function Resume-StrictSlot($Handoff) {
    if ($Handoff.running -ne $false) { throw 'Authored slot activation cannot start capture.' }
    $result=Invoke-RestMethod -Method Post 'http://127.0.0.1:8766/api/runtime/activate?writers=true' -Headers @{'X-Proxy-Transcript'='update'} -ContentType 'application/json' -Body ($Handoff | ConvertTo-Json -Depth 12) -TimeoutSec 35
    $status=Invoke-RestMethod 'http://127.0.0.1:8766/api/status' -TimeoutSec 5
    $ready=Invoke-RestMethod 'http://127.0.0.1:8766/api/runtime/ready' -TimeoutSec 3
    if ($result.active -ne $true -or $status.capture.running -ne $false -or $status.session.id -ne $Handoff.session_id -or $ready.standby -ne $false) {
        throw 'Strict paused handoff or request recovery was not preserved.'
    }
    Assert-SlotLeasesBlocked
}

if ($PSVersionTable.PSEdition -ne 'Core' -or -not $IsWindows) { throw 'This authored guardian requires Windows PowerShell 7 on the build host.' }
$sourceRuntime=(Get-Item -LiteralPath $RuntimeRoot).FullName
$proof=Get-Content -LiteralPath $Provenance -Raw | ConvertFrom-Json
if ($proof.schema -ne 'proxy-runtime-candidate-v1' -or $proof.profile -ne 'runtime-experiment' -or $proof.r19_complete -ne $false -or
    $proof.source_commit -ne $env:GITHUB_SHA -or @($proof.files).Count -lt 1) { throw 'Need the exact current quarantined candidate, not an installed release.' }
Assert-SlotInventory $sourceRuntime $proof
$tokens=$null; $parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'probe-frozen-runtime.ps1'),[ref]$tokens,[ref]$parseErrors)
if ($parseErrors) { throw 'Existing C1 host harness could not be parsed.' }
foreach ($name in @('Start-Owned','Get-HostObserverIdentityCategory','Get-HostObserverRole','Start-HostProbe')) {
    $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
    if (-not $definition) { throw 'Missing existing fixed C1 harness operation.' }
    . ([scriptblock]::Create($definition.Extent.Text))
}
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('R19 cold slots space 漢字 '+[guid]::NewGuid().ToString('N'))
$legacyRoot=Join-Path $temporary 'legacy'
$targetRoot=Join-Path $temporary 'private-target'
$guardianRoot=Join-Path $targetRoot 'host-v1'
$owned=[Collections.Generic.List[Diagnostics.Process]]::new(); $tasks=@{}
$contexts=[Collections.Generic.List[object]]::new(); $stages=[Collections.Generic.List[string]]::new()
$slots=@{}; $leases=[Collections.Generic.List[IO.FileStream]]::new(); $stage='prepare'; $failed=$false; $sourceOperationBlocks=0
$leasePaths=@((Join-Path $legacyRoot 'data/companion-operation.lock'),(Join-Path $guardianRoot 'migration-runtime.lock'))
New-Item -ItemType Directory -Path $guardianRoot,(Join-Path $temporary 'empty-host') -Force | Out-Null
Remove-Item -LiteralPath $Output -Force -ErrorAction SilentlyContinue
try {
    $requiredBytes=[long](($proof.files | Measure-Object -Property bytes -Sum).Sum)*2 + 512MB
    $volume=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($temporary))
    if ($volume.AvailableFreeSpace -lt $requiredBytes) { throw 'Insufficient space for both immutable application copies.' }
    foreach ($name in @('A','B')) {
        $application=Join-Path $temporary ('applications/'+$name)
        New-Item -ItemType Directory -Path (Split-Path $application) -Force | Out-Null
        Copy-Item -LiteralPath $sourceRuntime -Destination $application -Recurse
        Assert-SlotInventory $application $proof
        Get-ChildItem -LiteralPath $application -File -Recurse -Force | ForEach-Object { $_.IsReadOnly=$true }
        $private=Join-Path $temporary ('authored-state/'+$name)
        $slotRoots=@{PROXY_TRANSCRIPT_SETTINGS_ROOT=$private; PROXY_TRANSCRIPT_DATA_ROOT=(Join-Path $private 'data-v1');
            PROXY_TRANSCRIPT_CACHE_ROOT=(Join-Path $private 'cache-v1'); PROXY_TRANSCRIPT_WORK_ROOT=(Join-Path $private 'cache-v1/work');
            PROXY_TRANSCRIPT_TOOL_ROOT=(Join-Path $private 'tools-v1'); PROXY_TRANSCRIPT_STATE_ROOT=(Join-Path $private 'host-v1');
            PROXY_TRANSCRIPT_DEFAULT_EXPORT_ROOT=(Join-Path $private 'exports')}
        New-Item -ItemType Directory -Path $slotRoots.PROXY_TRANSCRIPT_STATE_ROOT -Force | Out-Null
        @{build_id=$proof.build_id; synthetic=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $slotRoots.PROXY_TRANSCRIPT_STATE_ROOT 'synthetic-probe.json') -Encoding utf8NoBOM
        $slots[$name]=@{application=$application; roots=$slotRoots}
    }
    if ((Invoke-SlotLeaseObservation $legacyRoot 'legacy-source') -ne 'open') { throw 'Existing source operation baseline could not enter its authored root.' }
    foreach ($path in $leasePaths) {
        New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
        if ((Invoke-SlotLeaseObservation $path) -ne 'open') { throw 'Lease baseline permissions could not be established.' }
        $leases.Add([IO.File]::Open($path,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None))
    }
    Write-SlotStage 'leases-held'
    $current=Start-GuardedSlot 'A'; Write-SlotStage 'slot-a-ready'
    $handoff=Invoke-StrictSlotDrain; Write-SlotStage 'slot-a-drained'
    Stop-GuardedSlot $current; Write-SlotStage 'slot-a-reaped'
    $current=Start-GuardedSlot 'B'; Resume-StrictSlot $handoff; Write-SlotStage 'slot-b-paused-active'
    $null=Invoke-StrictSlotDrain; Stop-GuardedSlot $current
    $current=Start-GuardedSlot 'A'; Resume-StrictSlot $handoff; Write-SlotStage 'cold-rollback-a'
    $null=Invoke-StrictSlotDrain; Stop-GuardedSlot $current
    $current=Start-GuardedSlot 'B' 'unprepared-index'
    Stop-GuardedSlot $current 'unprepared-index'; Write-SlotStage 'candidate-readiness-failure-reaped'
    $current=Start-GuardedSlot 'A'; Resume-StrictSlot $handoff; Write-SlotStage 'rollback-after-readiness-failure'
    Stop-GuardedSlot $current 'crash'; Write-SlotStage 'host-crash-children-signaled-leases-held'
    foreach ($slot in $slots.Values) {
        Assert-SlotInventory $slot.application $proof
        if (@(Get-ChildItem -LiteralPath $slot.application -File -Recurse -Force | Where-Object { -not $_.IsReadOnly }).Count) { throw 'Application immutability attributes changed.' }
    }
} catch {
    $failed=$true
    Write-SlotStage 'recovery-required'
} finally {
    foreach ($context in $contexts) {
        if (-not $context.closed) {
            try { Stop-GuardedSlot $context 'crash' } catch { $failed=$true }
        }
    }
    # A failed early registration cannot borrow ownership from PIDs or ports.
    # Keep the guardian/leases alive rather than create a legacy-release gap.
    $registered=@($contexts | ForEach-Object { $_.process.Id })
    $unregistered=@($owned | Where-Object { $_.Id -notin $registered })
    if ($unregistered.Count -or @($contexts | Where-Object { -not $_.closed }).Count) {
        [Console]::Error.WriteLine('Guarded slot recovery required; live guardian leases retained. Guardian termination remains an unverified failure boundary.')
        while ($true) { Start-Sleep -Seconds 5 }
    }
    for ($index=$leases.Count-1; $index -ge 0; $index--) { $leases[$index].Dispose() }
    foreach ($path in $leasePaths) {
        if ([IO.File]::Exists($path) -and (Invoke-SlotLeaseObservation $path) -ne 'open') { $failed=$true }
    }
    if ((Invoke-SlotLeaseObservation $legacyRoot 'legacy-source') -ne 'open') { $failed=$true }
    foreach ($context in $contexts) { foreach ($observer in $context.held) { $observer.Dispose() } }
    foreach ($process in $owned) { $process.Dispose() }
}
if (-not $failed) {
    try {
        foreach ($slot in $slots.Values) { Get-ChildItem -LiteralPath $slot.application -File -Recurse -Force | ForEach-Object { $_.IsReadOnly=$false } }
        Remove-Item -LiteralPath $temporary -Recurse -Force
    } catch { $failed=$true }
}
# Publish success only after all owned native cleanup, lease release checks,
# attribute restoration and private-tree removal have succeeded.
$receipt=@{schema='proxy-r19-guarded-cold-slot-probe-v1'; source_commit=$proof.source_commit; build_id=$proof.build_id;
    status=$(if ($failed) {'failed'} else {'passed'}); scope='authored-cold-slot-lifecycle'; candidate_versions='two-identical-verified-copies';
    stages=$stages.ToArray(); strict_writer_protocol=$(if ($stages.Contains('slot-a-drained')) {'actual-api-paused-capture'} else {'not-completed'});
    native_owned_process_tree=$(if ($contexts.Count) {'observed-existing-c1'} else {'not-started'}); api_external_side_effects='mocked';
    legacy_exclusion=$(if ($stages.Contains('host-crash-children-signaled-leases-held')) {'guardian-exclusive-open-through-retained-child-exit'} elseif ($stages.Contains('leases-held')) {'partial-held-observations'} else {'not-acquired'});
    legacy_source_operation=$(if ($sourceOperationBlocks) {'existing-enter-operation-blocked'} else {'not-completed'}); source_operation_blocked_observations=$sourceOperationBlocks;
    legacy_source_sha256=(Get-FileHash -LiteralPath $slotSourceOperation -Algorithm SHA256).Hash.ToLowerInvariant();
    target_lease='separate-private-guardian-root'; strict_writer_runtime_budget_ms=30000; http_transport_timeout_ms=35000; source_updater_invoked=$false;
    migration=$false; store_copy=$false; warm_candidate_before_drain='not-proved'; router_takeover='not-tested';
    credentials='not-accessed'; guardian_crash='unavailable'; early_unregistered_host_crash='recovery-required';
    production_activation=$false; r19_complete=$false; installer='not-built'}
New-Item -ItemType Directory -Path (Split-Path $Output) -Force | Out-Null
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding utf8NoBOM
if ($failed) { throw 'Guarded cold-slot experiment failed; retain private evidence.' }
Write-Host 'Authored guarded cold-slot probe passed; production update and migration remain unavailable.'
