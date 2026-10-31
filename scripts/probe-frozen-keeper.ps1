param([Parameter(Mandatory=$true)][string]$RuntimeRoot,
      [Parameter(Mandatory=$true)][string]$Provenance,
      [string]$Output=(Join-Path $PSScriptRoot '../output/checks/r19-frozen-keeper.json'))
$ErrorActionPreference='Stop'
Remove-Item -LiteralPath $Output -Force -ErrorAction SilentlyContinue
if ($PSVersionTable.PSEdition -ne 'Core' -or -not $IsWindows) { throw 'This authored keeper requires Windows PowerShell 7 on the build host.' }
. (Join-Path $PSScriptRoot 'r19-runtime-inventory.ps1')
$slotSourceOperation=Join-Path $PSScriptRoot 'companion-runtime.ps1'

# Reuse named fixed harness operations without executing either script body.
foreach ($selection in @(
    @{file='probe-frozen-slots.ps1';names=@('Assert-SlotEntryName','Assert-SlotInventory','Invoke-SlotLeaseObservation')},
    @{file='probe-frozen-runtime.ps1';names=@('Start-Owned')})) {
    $tokens=$null; $parseErrors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $selection.file),[ref]$tokens,[ref]$parseErrors)
    if ($parseErrors) { throw 'Existing fixed harness could not be parsed.' }
    foreach ($name in $selection.names) {
        $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
        if (-not $definition) { throw 'Missing existing fixed harness operation.' }
        . ([scriptblock]::Create($definition.Extent.Text))
    }
}

function Read-KeeperEvent([string]$Phase, [int]$Resumed, [int]$Timeout=120000) {
    if (-not $script:nextLine.Wait($Timeout)) { throw 'Fixed keeper phase timed out.' }
    $line=$script:nextLine.GetAwaiter().GetResult()
    if (-not $line -or $line.Length -gt 8192) { throw 'Fixed keeper event is unavailable.' }
    $value=$line | ConvertFrom-Json
    $knownFailures=@('registered-host-unconfirmed','keeper-control-unavailable','keeper-control-invalid',
        'keeper-guardian-startup','keeper-guardian-identity','keeper-guardian-descendants',
        'keeper-fixture-unavailable','keeper-lease-release-unconfirmed','unexpected-keeper-failure',
        'guardian-census-unavailable','guardian-census-truncated','guardian-census-close-unconfirmed',
        'registered-member-ownership-unconfirmed','unknown-registered-member','registered-cohort-incomplete',
        'registered-member-observer-unavailable','registered-cohort-aliased','registered-observer-close-unconfirmed',
        'registered-listener-unavailable','registered-listener-role-mismatch','registered-listener-changed',
        'registered-writer-not-live','registered-writer-drain-unconfirmed','members-remain-after-registered-stop',
        'readiness-deadline','keeper-recovery-required')
    if ($value.schema -eq 'proxy-r19-frozen-keeper-probe-v1' -and $value.phase -eq 'recovery-required' -and
        $value.status -eq 'failed' -and $value.failure -cin $knownFailures) {
        $script:failureCategory=$value.failure
    }
    if ($value.schema -ne 'proxy-r19-frozen-keeper-probe-v1' -or $value.kind -ne 'keeper' -or
        $value.phase -ne $Phase -or $value.case -ne $case -or $value.build_id -ne $proof.build_id -or
        $value.source_commit -ne $proof.source_commit -or $value.writers_resumed -ne $Resumed -or
        $value.api_external_side_effects -ne 'mocked' -or $value.native_owned_process_tree -ne 'real' -or
        $value.guardian -ne 'readonly-frozen-frontend-port-zero' -or $value.census -ne 'observations-only-not-lifetime-proof' -or
        $value.keeper_loss -ne 'unavailable' -or $value.dynamic_writer_admission -ne 'unavailable' -or
        $value.production_activation -ne $false -or $value.store_copy -ne $false -or
        $value.installer -ne 'not-built' -or $value.r19_complete -ne $false) { throw 'Fixed keeper event identity or scope differs.' }
    $expectedCreated=if ($Phase -eq 'roots-ready') {0} else {2}
    $expectedStatus=if ($Phase -eq 'released') {'passed'} else {'observing'}
    if ($value.writers_created -ne $expectedCreated -or $value.status -ne $expectedStatus -or
        ($Phase -in @('writers-signaled-leases-held','released') -and $value.guardian_exit -ne 'signaled')) {
        throw 'Fixed keeper lifecycle is unconfirmed.'
    }
    # Raw control events are private, never copied into the public receipt.
    $script:nextLine=$process.StandardOutput.ReadLineAsync()
}
function Send-KeeperCommand([string]$Command) {
    $process.StandardInput.WriteLine($Command); $process.StandardInput.Flush()
}
function Assert-KeeperLeases([ValidateSet('open','blocked')][string]$Expected) {
    foreach ($path in $leasePaths) {
        # Native blocked means exact ERROR_SHARING_VIOLATION32, not access denied.
        if ((Invoke-SlotLeaseObservation $path) -ne $Expected) { throw 'Legacy or target lease state differs.' }
    }
    # This independently invokes the unchanged source operation, not a custom
    # same-file contender treated as legacy interoperability evidence.
    if ((Invoke-SlotLeaseObservation $legacyRoot 'legacy-source') -ne $Expected) { throw 'Existing source operation exclusion differs.' }
    if ($Expected -eq 'blocked') { $script:sourceBlocks++ }
}
function Assert-KeeperPortsFree {
    foreach ($port in @(3000,8766)) {
        $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$port)
        try { $listener.Start() } finally { $listener.Stop() }
    }
}
function Write-KeeperReceipt([string]$Status) {
    $receipt=@{schema='proxy-r19-frozen-keeper-receipt-v1'; status=$Status; source_commit=$proof.source_commit; build_id=$proof.build_id;
        scope='authored-guardian-loss-with-living-frozen-keeper'; cases=$results.ToArray();
        legacy_source_sha256=(Get-FileHash -LiteralPath $slotSourceOperation -Algorithm SHA256).Hash.ToLowerInvariant();
        legacy_source_operation='existing-enter-operation'; source_operation_blocked_observations=$sourceBlocks;
        target_lease='separate-private-keeper-root'; writer_state='fresh-authored-state';
        authority='two-retained-createprocess-records'; guardian='retained-popen-readonly-frontend-port-zero';
        census='bounded-observations-and-onedir-source-inference-not-lifetime-proof';
        api_external_side_effects='mocked'; strict_writer_runtime_budget_ms=30000; http_transport_timeout_ms=35000;
        cleanup=$(if ($Status -eq 'passed') {'retained-writers-signaled-leases-explicitly-released-private-tree-removed'} else {'unconfirmed-recovery-required'});
        failure_stage=$(if ($Status -eq 'failed') {$stage} else {'none'}); keeper_loss='unavailable';
        failure_category=$(if ($Status -eq 'failed') {$failureCategory} else {'none'});
        dynamic_writer_admission='unavailable'; warm_routing='unavailable'; migration=$false; store_copy=$false;
        production_activation=$false; credentials='not-accessed'; installer='not-built'; r19_complete=$false}
    New-Item -ItemType Directory -Path (Split-Path $Output) -Force | Out-Null
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding utf8NoBOM
}
function Get-KeeperCaseRoots([string]$TemporaryRoot, [ValidateSet('keeper-before-resume','keeper-after-ready')][string]$Case) {
    # Start-Owned selects empty-host for TEMP/TMP. The frozen containment guard
    # requires authored work below that actual TEMP, not a sibling case root.
    $private=Join-Path (Join-Path $TemporaryRoot 'empty-host') $Case
    return @{PROXY_TRANSCRIPT_SETTINGS_ROOT=$private; PROXY_TRANSCRIPT_DATA_ROOT=(Join-Path $private 'data-v1');
        PROXY_TRANSCRIPT_CACHE_ROOT=(Join-Path $private 'cache-v1'); PROXY_TRANSCRIPT_WORK_ROOT=(Join-Path $private 'cache-v1/work');
        PROXY_TRANSCRIPT_TOOL_ROOT=(Join-Path $private 'tools-v1'); PROXY_TRANSCRIPT_STATE_ROOT=(Join-Path $private 'host-v1');
        PROXY_TRANSCRIPT_DEFAULT_EXPORT_ROOT=(Join-Path $private 'exports')}
}
function Wait-KeeperHarnessRecovery {
    try { [Console]::Error.WriteLine('Keeper recovery required; retained live owner and exclusive leases remain held. External keeper termination is an unverified failure boundary.') } catch {}
    while ($true) { Start-Sleep -Seconds 5 }
}
function Complete-KeeperHarness([bool]$Failed) {
    # Metadata publication is best effort on failure. A broken receipt channel
    # must never bypass the livekeeper hold or turn it into successful exit.
    try { Write-KeeperReceipt $(if ($Failed) {'failed'} else {'passed'}) }
    catch {
        $Failed=$true
        try { Remove-Item -LiteralPath $Output -Force -ErrorAction Stop } catch {}
    }
    if ($Failed) {
        $live=@($owned | Where-Object { try { $exited=$_.HasExited; ($exited -isnot [bool]) -or -not $exited } catch { $true } })
        if ($live.Count) { Wait-KeeperHarnessRecovery }
        throw 'Authored frozen keeper probe failed; retain private evidence.'
    }
}

$RuntimeRoot=(Get-Item -LiteralPath $RuntimeRoot).FullName
$proof=Get-Content -LiteralPath $Provenance -Raw | ConvertFrom-Json
if ($proof.schema -ne 'proxy-runtime-candidate-v1' -or $proof.profile -ne 'runtime-experiment' -or
    $proof.r19_complete -ne $false -or $proof.source_commit -ne $env:GITHUB_SHA -or @($proof.files).Count -lt 1) {
    throw 'Need the exact current quarantined candidate, not an installed release.'
}
Assert-SlotInventory $RuntimeRoot $proof
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('R19 frozen keeper space 漢字 '+[guid]::NewGuid().ToString('N'))
$owned=[Collections.Generic.List[Diagnostics.Process]]::new(); $tasks=@{}
$results=[Collections.Generic.List[object]]::new(); $sourceBlocks=0; $stage='prepare'; $failed=$false; $failureCategory='harness-unconfirmed'
New-Item -ItemType Directory -Path (Join-Path $temporary 'empty-host') -Force | Out-Null
try {
    foreach ($case in @('keeper-before-resume','keeper-after-ready')) {
        $stage='case-prepare'
        Assert-KeeperPortsFree
        $roots=Get-KeeperCaseRoots $temporary $case
        New-Item -ItemType Directory -Path $roots.PROXY_TRANSCRIPT_STATE_ROOT -Force | Out-Null
        @{build_id=$proof.build_id;synthetic=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $roots.PROXY_TRANSCRIPT_STATE_ROOT 'synthetic-probe.json') -Encoding utf8NoBOM
        $process=Start-Owned (Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe') '--runtime-probe host' $case
        $script:nextLine=$tasks[$process.Id][0]
        Read-KeeperEvent 'roots-ready' 0
        $fixture=Join-Path $roots.PROXY_TRANSCRIPT_WORK_ROOT 'keeper-fixture'
        $legacyRoot=Join-Path $fixture 'legacy'
        $leasePaths=@((Join-Path $legacyRoot 'data/companion-operation.lock'),(Join-Path $fixture 'private-target/host-v1/migration-runtime.lock'))
        Assert-KeeperLeases 'open'
        $stage='registered-start'
        Send-KeeperCommand 'start'
        $resumed=if ($case -eq 'keeper-after-ready') {2} else {0}
        Read-KeeperEvent $(if ($resumed) {'services-ready'} else {'writers-suspended'}) $resumed
        Assert-KeeperLeases 'blocked'
        $stage='guardian-loss'
        Send-KeeperCommand 'lose-guardian'
        Read-KeeperEvent 'writers-signaled-leases-held' $resumed
        Assert-KeeperLeases 'blocked'
        Assert-KeeperPortsFree
        $stage='explicit-release'
        Send-KeeperCommand 'release'
        Read-KeeperEvent 'released' $resumed
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(15000) -or $process.ExitCode -ne 0) { throw 'Retained keeper did not exit successfully.' }
        if (-not $script:nextLine.Wait(5000) -or $script:nextLine.GetAwaiter().GetResult()) { throw 'Unexpected trailing keeper control event.' }
        $null=$tasks[$process.Id][1].GetAwaiter().GetResult()
        Assert-KeeperLeases 'open'
        Assert-KeeperPortsFree
        Assert-SlotInventory $RuntimeRoot $proof
        $results.Add(@{case=$case;status='passed';writers_created=2;writers_resumed=$resumed;guardian_exit='signaled';
            writer_exit='retained-objects-signaled';legacy_exclusion='held-through-writer-exit';
            strict_writer_protocol=$(if ($resumed) {'existing-c2-paused-api'} else {'writers-never-resumed'})})
    }
    $stage='private-cleanup'
    Remove-Item -LiteralPath $temporary -Recurse -Force
    foreach ($process in $owned) { $process.Dispose() }
} catch {
    $failed=$true
}
# A passing receipt exists only after successful native/lease/private cleanup.
Complete-KeeperHarness $failed
Write-Host 'Fixed guardian-loss cases passed with a living frozen keeper; production and keeper-loss recovery remain unavailable.'
