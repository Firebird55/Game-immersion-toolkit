param([Parameter(Mandatory=$true)][string]$RuntimeRoot,
      [Parameter(Mandatory=$true)][string]$Provenance,
      [string]$Output=(Join-Path $PSScriptRoot '../output/checks/r19-frozen-populated-state-copy.json'))
$ErrorActionPreference='Stop'
$ProbeCase='authored-populated-state-copy-v1'
if ($PSVersionTable.PSEdition -ne 'Core' -or -not $IsWindows) {
    throw 'The populated-state harness requires Windows PowerShell 7 on the build host.'
}
. (Join-Path $PSScriptRoot 'r19-runtime-inventory.ps1')
$slotSourceOperation=Join-Path $PSScriptRoot 'companion-runtime.ps1'

# Reuse only exact named bounded I/O/inventory/contender operations. Never
# execute an old harness body or import its case/projector/receipt decisions.
foreach ($selection in @(
    @{file='probe-frozen-slots.ps1';names=@('Assert-SlotEntryName','Assert-SlotInventory','Invoke-SlotLeaseObservation')},
    @{file='probe-frozen-data-copy.ps1';names=@('New-DataCopyControlReader','Read-DataCopyControlLine','Assert-DataCopyPortsFree')})) {
    $tokens=$null; $parseErrors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $selection.file),[ref]$tokens,[ref]$parseErrors)
    if ($parseErrors) { throw 'An existing populated-state support operation could not be parsed.' }
    foreach ($name in $selection.names) {
        $definitions=@($ast.FindAll({param($node)
            $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name
        },$true))
        if ($definitions.Count -ne 1) { throw 'Need one exact existing populated-state support operation.' }
        . ([scriptblock]::Create($definitions[0].Extent.Text))
    }
}

function Start-PopulatedOwner {
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName=Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe'
    $info.Arguments='--runtime-probe host'
    $info.UseShellExecute=$false
    $info.RedirectStandardOutput=$info.RedirectStandardError=$info.RedirectStandardInput=$true
    $info.WorkingDirectory=$temporary
    $info.Environment.Clear()
    foreach ($name in @('WINDIR','SystemRoot','COMSPEC','PATHEXT')) {
        $value=[Environment]::GetEnvironmentVariable($name)
        if ($value) { $info.Environment[$name]=$value }
    }
    $info.Environment['PATH']="$env:WINDIR/System32;$env:WINDIR"
    foreach ($name in @('TEMP','TMP','USERPROFILE','HOME','LOCALAPPDATA','APPDATA')) {
        $info.Environment[$name]=Join-Path $temporary 'empty-host'
    }
    foreach ($name in $roots.Keys) { $info.Environment[$name]=$roots[$name] }
    $info.Environment['PROXY_TRANSCRIPT_STANDBY']='1'
    $info.Environment['PYINSTALLER_RESET_ENVIRONMENT']='1'
    $process=[Diagnostics.Process]::new()
    $owned.Add($process)  # Retain the actual object before any Start uncertainty.
    $process.StartInfo=$info
    if (-not $process.Start()) { throw 'Fixed populated-state owner did not start.' }
    $null=$process.Handle
    $script:stderrDiscard=$process.StandardError.BaseStream.CopyToAsync([IO.Stream]::Null,4096)
    $script:controlReader=New-DataCopyControlReader $process.StandardOutput.BaseStream $script:stderrDiscard
    $process.StandardInput.WriteLine($ProbeCase); $process.StandardInput.Flush()
    return $process
}

function Assert-PopulatedSourceBaseline {
    # Seeding precedes lease entry. No target lease observation is attempted
    # while its parent has not yet been created by the genuine coordinator.
    if ((Invoke-SlotLeaseObservation $legacyRoot 'legacy-source') -cne 'open') {
        throw 'The seeded unowned source operation did not enter and close.'
    }
    $script:seededBaseline=$true
}
function Assert-PopulatedLeases([ValidateSet('open','blocked')][string]$Expected) {
    foreach ($path in $leasePaths) {
        if ((Invoke-SlotLeaseObservation $path) -cne $Expected) {
            throw 'The populated-state native lease exclusion differs.'
        }
    }
    if ((Invoke-SlotLeaseObservation $legacyRoot 'legacy-source') -cne $Expected) {
        throw 'The populated-state actual source operation exclusion differs.'
    }
    if ($Expected -ceq 'blocked') { $script:sourceBlocks++ }
}

function Convert-PopulatedControl([string]$Line) {
    if ([Text.Encoding]::UTF8.GetByteCount($Line) -gt 8192) {
        throw 'The populated control exceeds its byte limit.'
    }
    # The existing byte reader already enforces strict UTF8/8KiB. Enumerate the
    # flat JSON object before conversion so duplicate exact keys cannot vanish.
    $document=$null
    try {
        if ([Text.UTF8Encoding]::new($false,$true).GetByteCount($Line) -gt 8192) {
            throw 'The populated control exceeds its byte bound.'
        }
        $document=[Text.Json.JsonDocument]::Parse($Line)
        if ($document.RootElement.ValueKind -ne [Text.Json.JsonValueKind]::Object) {
            throw 'The populated control must be an object.'
        }
        $value=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
        foreach ($property in $document.RootElement.EnumerateObject()) {
            if ($value.ContainsKey($property.Name)) { throw 'Duplicate populated control key.' }
            switch ($property.Value.ValueKind) {
                ([Text.Json.JsonValueKind]::String) { $item=$property.Value.GetString() }
                ([Text.Json.JsonValueKind]::True) { $item=$true }
                ([Text.Json.JsonValueKind]::False) { $item=$false }
                ([Text.Json.JsonValueKind]::Number) {
                    $item=[long]0
                    if (-not $property.Value.TryGetInt64([ref]$item)) { throw 'Noninteger populated count.' }
                }
                default { throw 'Unsupported populated control value.' }
            }
            $value.Add($property.Name,$item)
        }
        return ,$value
    } catch { throw 'The populated control JSON is invalid.' }
    finally { if ($null -ne $document) { $document.Dispose() } }
}
function Get-PopulatedExpectedPhase([string]$Phase) {
    switch -CaseSensitive ($Phase) {
        'seeded-before-owner' { return @{phase='seeded-before-owner';generation=0;writers_created=0;writers_resumed=0;writers_signaled=0;strict_drains=0;owner_interval='not-entered';api_readback='not-run';copy_verification='not-run';service_readback='not-run';source_bytes='not-run';snapshot_bytes='not-run';source_logical='not-run';external_state='not-run';pointer='not-entered';old_barrier_refused=$false;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'owner-entered' { return @{phase='owner-entered';generation=0;writers_created=0;writers_resumed=0;writers_signaled=0;strict_drains=0;owner_interval='leases-held';api_readback='not-run';copy_verification='not-run';service_readback='not-run';source_bytes='not-run';snapshot_bytes='not-run';source_logical='not-run';external_state='not-run';pointer='baseline-unchanged';old_barrier_refused=$false;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'api-populated-checked' { return @{phase='api-populated-checked';generation=1;writers_created=2;writers_resumed=2;writers_signaled=0;strict_drains=0;owner_interval='leases-held';api_readback='first-cohort-passed';copy_verification='not-run';service_readback='not-run';source_bytes='not-run';snapshot_bytes='not-run';source_logical='not-run';external_state='not-run';pointer='baseline-unchanged';old_barrier_refused=$false;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'strict-drain-complete' { return @{phase='strict-drain-complete';generation=1;writers_created=2;writers_resumed=2;writers_signaled=0;strict_drains=1;owner_interval='leases-held';api_readback='first-cohort-passed';copy_verification='not-run';service_readback='not-run';source_bytes='not-run';snapshot_bytes='not-run';source_logical='not-run';external_state='not-run';pointer='baseline-unchanged';old_barrier_refused=$false;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'writers-signaled' { return @{phase='writers-signaled';generation=1;writers_created=2;writers_resumed=2;writers_signaled=2;strict_drains=1;owner_interval='leases-held';api_readback='first-cohort-passed';copy_verification='not-run';service_readback='not-run';source_bytes='not-run';snapshot_bytes='not-run';source_logical='not-run';external_state='not-run';pointer='baseline-unchanged';old_barrier_refused=$false;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'copy-progress' { return @{phase='copy-progress';generation=1;writers_created=2;writers_resumed=2;writers_signaled=2;strict_drains=1;owner_interval='leases-held';api_readback='first-cohort-passed';copy_verification='not-run';service_readback='not-run';source_bytes='not-run';snapshot_bytes='not-run';source_logical='not-run';external_state='not-run';pointer='baseline-unchanged';old_barrier_refused=$false;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'copy-verified' { return @{phase='copy-verified';generation=1;writers_created=2;writers_resumed=2;writers_signaled=2;strict_drains=1;owner_interval='leases-held';api_readback='first-cohort-passed';copy_verification='passed';service_readback='passed';source_bytes='preserved-before-resume';snapshot_bytes='unchanged-after-readback';source_logical='not-run';external_state='preserved-before-resume';pointer='baseline-unchanged';old_barrier_refused=$false;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'source-resumed' { return @{phase='source-resumed';generation=2;writers_created=4;writers_resumed=4;writers_signaled=2;strict_drains=1;owner_interval='leases-held';api_readback='both-cohorts-passed';copy_verification='passed';service_readback='passed';source_bytes='preserved-before-resume';snapshot_bytes='unchanged-after-readback';source_logical='passed-after-fresh-source-cohort';external_state='preserved-before-and-after-resume';pointer='baseline-unchanged';old_barrier_refused=$true;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'final-strict-drain-complete' { return @{phase='final-strict-drain-complete';generation=2;writers_created=4;writers_resumed=4;writers_signaled=2;strict_drains=2;owner_interval='leases-held';api_readback='both-cohorts-passed';copy_verification='passed';service_readback='passed';source_bytes='preserved-before-resume';snapshot_bytes='unchanged-after-readback';source_logical='passed-after-fresh-source-cohort';external_state='preserved-before-and-after-resume';pointer='baseline-unchanged';old_barrier_refused=$true;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'final-writers-signaled' { return @{phase='final-writers-signaled';generation=2;writers_created=4;writers_resumed=4;writers_signaled=4;strict_drains=2;owner_interval='leases-held';api_readback='both-cohorts-passed';copy_verification='passed';service_readback='passed';source_bytes='preserved-before-resume';snapshot_bytes='unchanged-after-readback';source_logical='passed-after-fresh-source-cohort';external_state='preserved-before-and-after-resume';pointer='baseline-unchanged';old_barrier_refused=$true;status='observing';failure='none';fixture_seed='complete-before-owner'} }
        'released' { return @{phase='released';generation=2;writers_created=4;writers_resumed=4;writers_signaled=4;strict_drains=2;owner_interval='leases-released';api_readback='both-cohorts-passed';copy_verification='passed';service_readback='passed';source_bytes='preserved-before-resume';snapshot_bytes='unchanged-after-readback';source_logical='passed-after-fresh-source-cohort';external_state='preserved-before-and-after-resume';pointer='baseline-unchanged';old_barrier_refused=$true;status='passed';failure='none';fixture_seed='complete-before-owner'} }
        default { throw 'Unknown fixed populated-state phase.' }
    }
}
function Read-PopulatedEvent([string]$Phase) {
    $line=Read-DataCopyControlLine $script:controlReader
    if (-not $line) { throw 'The populated-state control event is unavailable.' }
    $value=Convert-PopulatedControl $line
    $keys=@('api_external_side_effects','api_readback','authority','browser','build_id','case','copy_verification','credentials','dynamic_writer_admission','external_state','failure','fixture_seed','generation','installer','keeper_loss','kind','native_owned_process_tree','old_barrier_refused','owner_interval','phase','physical_replace','pointer','production_activation','r19_complete','rights_review','schema','scope','service_readback','setup_sql_fences','snapshot_bytes','source_bytes','source_commit','source_logical','sqlite','status','strict_drains','target_activation','wal_claim','warm_routing','windows11','writer_console_mode','writers_created','writers_resumed','writers_signaled')
    if ($value.Count -ne $keys.Count) { throw 'The populated-state key count differs.' }
    foreach ($name in $keys) {
        if (-not $value.ContainsKey($name)) { throw 'The populated-state keys differ.' }
    }
    $fixed=@{schema='proxy-r19-frozen-populated-state-copy-probe-v1';kind='populated-state-copy';case='authored-populated-state-copy-v1';scope='authored-mapped-populated-copy-with-living-coordinator';setup_sql_fences='setup-only-never-writer-proof';api_external_side_effects='fixed-mock-transport';sqlite='real';native_owned_process_tree='real';writer_console_mode='detached-process';authority='retained-creation-objects-and-typed-barrier';credentials='test-envelope-only-no-real-credentials';wal_claim='not-tested';browser='not-run';keeper_loss='unavailable';dynamic_writer_admission='unavailable';warm_routing='unavailable';physical_replace='unavailable';windows11='not-run';rights_review='pending-exact-output';production_activation=$false;target_activation=$false;installer='not-built';r19_complete=$false}
    foreach ($entry in $fixed.GetEnumerator()) {
        $actual=$value[$entry.Key]
        if ($actual.GetType() -ne $entry.Value.GetType() -or $actual -cne $entry.Value) {
            throw 'The populated-state fixed policy differs.'
        }
    }
    if ($value['phase'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['phase'] -cnotin @('seeded-before-owner','owner-entered','api-populated-checked','strict-drain-complete','writers-signaled','copy-progress','copy-verified','source-resumed','final-strict-drain-complete','final-writers-signaled','released','recovery-required')) { throw 'The populated-state enum differs.' }
    if ($value['status'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['status'] -cnotin @('observing','passed','failed')) { throw 'The populated-state enum differs.' }
    if ($value['failure'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['failure'] -cnotin @('none','fixture-unavailable','setup-close-unconfirmed','setup-still-open','cohort-unconfirmed','owned-host-unconfirmed','copy-refused','copy-result-unconfirmed','schema-unconfirmed','authored-rows-differ','pointer-changed','source-changed','control-unavailable','control-invalid','lease-release-unconfirmed','unexpected-data-copy-failure','interrupted-copy-unconfirmed','populated-state-unconfirmed','account-fixture-unconfirmed','api-semantics-unconfirmed')) { throw 'The populated-state enum differs.' }
    if ($value['source_commit'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['build_id'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['generation'] -isnot [long] -or $value['generation'] -lt 0 -or $value['generation'] -gt 2) { throw 'The populated-state count differs.' }
    if ($value['writers_created'] -isnot [long] -or $value['writers_created'] -lt 0 -or $value['writers_created'] -gt 4) { throw 'The populated-state count differs.' }
    if ($value['writers_resumed'] -isnot [long] -or $value['writers_resumed'] -lt 0 -or $value['writers_resumed'] -gt 4) { throw 'The populated-state count differs.' }
    if ($value['writers_signaled'] -isnot [long] -or $value['writers_signaled'] -lt 0 -or $value['writers_signaled'] -gt 4) { throw 'The populated-state count differs.' }
    if ($value['strict_drains'] -isnot [long] -or $value['strict_drains'] -lt 0 -or $value['strict_drains'] -gt 2) { throw 'The populated-state count differs.' }
    if ($value['owner_interval'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['owner_interval'] -cnotin @('not-entered','leases-held','leases-released')) { throw 'The populated-state enum differs.' }
    if ($value['api_readback'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['api_readback'] -cnotin @('not-run','first-cohort-passed','both-cohorts-passed')) { throw 'The populated-state enum differs.' }
    if ($value['copy_verification'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['copy_verification'] -cnotin @('not-run','passed')) { throw 'The populated-state enum differs.' }
    if ($value['service_readback'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['service_readback'] -cnotin @('not-run','passed')) { throw 'The populated-state enum differs.' }
    if ($value['source_bytes'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['source_bytes'] -cnotin @('not-run','preserved-before-resume')) { throw 'The populated-state enum differs.' }
    if ($value['snapshot_bytes'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['snapshot_bytes'] -cnotin @('not-run','unchanged-after-readback')) { throw 'The populated-state enum differs.' }
    if ($value['source_logical'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['source_logical'] -cnotin @('not-run','passed-after-fresh-source-cohort')) { throw 'The populated-state enum differs.' }
    if ($value['external_state'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['external_state'] -cnotin @('not-run','preserved-before-resume','preserved-before-and-after-resume')) { throw 'The populated-state enum differs.' }
    if ($value['pointer'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['pointer'] -cnotin @('not-entered','baseline-unchanged')) { throw 'The populated-state enum differs.' }
    if ($value['old_barrier_refused'] -isnot [bool]) { throw 'The populated-state bool type differs.' }
    if ($value['fixture_seed'] -isnot [string]) { throw 'The populated-state string type differs.' }
    if ($value['fixture_seed'] -cnotin @('not-run','complete-before-owner')) { throw 'The populated-state enum differs.' }
    if ($value['source_commit'] -cnotmatch '\A[a-f0-9]{40}\z' -or
        $value['source_commit'] -cne $proof.source_commit -or $value['build_id'] -cne $proof.build_id -or
        $value['generation'] -gt 2 -or $value['writers_created'] -gt 2*$value['generation'] -or
        $value['writers_resumed'] -gt $value['writers_created'] -or
        $value['writers_signaled'] -gt $value['writers_created']) {
        throw 'The populated-state build or count relationship differs.'
    }
    if ($value['phase'] -ceq 'recovery-required') {
        if ($value['status'] -cne 'failed' -or $value['failure'] -ceq 'none') {
            throw 'The populated-state recovery status differs.'
        }
        # Earlier real observations may remain in this failed event. They do
        # not replace the last fully validated regular frame or approve a copy.
        $script:failureCategory=$value['failure']
        throw 'The populated-state owner requires recovery.'
    }
    $expected=Get-PopulatedExpectedPhase $Phase
    foreach ($entry in $expected.GetEnumerator()) {
        if ($value[$entry.Key] -cne $entry.Value) { throw 'The populated-state phase/result order differs.' }
    }
    $script:lastEvent=$value
}

function Assert-PopulatedSink([string]$Path, [bool]$CreateParents=$false) {
    $full=[IO.Path]::GetFullPath($Path)
    $parent=[IO.Path]::GetDirectoryName($full)
    $chain=[Collections.Generic.List[string]]::new()
    while ($parent) {
        $chain.Insert(0,$parent)
        $parent=[IO.Path]::GetDirectoryName($parent)
    }
    foreach ($directory in $chain) {
        try { $attributes=[IO.File]::GetAttributes($directory) }
        catch {
            $base=$_.Exception.GetBaseException()
            if ($base -isnot [IO.FileNotFoundException] -and $base -isnot [IO.DirectoryNotFoundException]) {
                throw 'The populated receipt ancestor is unavailable.'
            }
            if (-not $CreateParents) { return $full }  # Admission has no writes or descendant inspection.
            # Only this missing child of already inspected ancestors is made.
            # No existing directory or unrelated content is ever removed.
            $null=[IO.Directory]::CreateDirectory($directory)
            $attributes=[IO.File]::GetAttributes($directory)
        }
        if (($attributes -band [IO.FileAttributes]::ReparsePoint) -or
            -not ($attributes -band [IO.FileAttributes]::Directory)) {
            throw 'The populated receipt ancestor is linked or not a directory.'
        }
    }
    # GetAttributes observes this leaf only after all ancestors. Absence is
    # necessary, but CreateNew below is the final exclusive no-overwrite check.
    try { $null=[IO.File]::GetAttributes($full) }
    catch {
        $base=$_.Exception.GetBaseException()
        if ($base -is [IO.FileNotFoundException]) { return $full }
        throw 'The populated receipt leaf is unavailable.'
    }
    throw 'The populated receipt leaf already exists.'
}
function Write-PopulatedSink([string]$Json) {
    if ($null -ne $script:receiptSink) { throw 'The populated receipt sink is already used.' }
    $bytes=[Text.UTF8Encoding]::new($false,$true).GetBytes($Json+[char]10)
    if ($bytes.Length -gt 16384) { throw 'The populated receipt exceeds its bound.' }
    $public=Assert-PopulatedSink $Output $true
    $pending=[IO.Path]::Combine([IO.Path]::GetDirectoryName($public),
        ('.r19-p2-'+[guid]::NewGuid().ToString('N')+'.pending'))
    $path=Assert-PopulatedSink $pending
    $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $script:receiptSink=@{stream=$stream;path=$path;public=$public;state='open';published=$false;
        errors=[Collections.Generic.List[object]]::new()}
    $writeFailed=$false; $closeFailed=$false
    try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) }
    catch { $script:receiptSink.errors.Add($_); $writeFailed=$true }
    try { $stream.Dispose() }
    catch { $script:receiptSink.errors.Add($_); $closeFailed=$true }
    $script:receiptSink.state=$(if ($closeFailed) {'unconfirmed'} else {'closed'})
    if ($writeFailed -or $closeFailed) {
        # Keep the actual stream record and owned partial file. Never retry an
        # uncertain close, overwrite it with a different result or blind-delete.
        throw 'The populated receipt publication is unconfirmed.'
    }
    try {
        $null=Assert-PopulatedSink $public
        [IO.File]::Move($path,$public)  # Same directory, exclusive no-overwrite publication.
        $script:receiptSink.published=$true
    } catch {
        $script:receiptSink.errors.Add($_)
        throw 'The populated receipt publication is unconfirmed.'
    }
}
function Write-PopulatedReceipt([ValidateSet('passed','failed')][string]$Status) {
    $passed=$Status -ceq 'passed'
    if ($passed -and (-not $script:seededBaseline -or -not $script:ownerExitConfirmed -or
        -not $script:privateCleanupConfirmed -or $script:sourceBlocks -ne 9 -or
        $null -eq $script:lastEvent -or $script:lastEvent['phase'] -cne 'released')) {
        throw 'The populated-state receipt cannot precede containment and cleanup.'
    }
    $receipt=[ordered]@{
        case='authored-populated-state-copy-v1'
        scope='authored-mapped-populated-copy-with-living-coordinator'
        setup_sql_fences='setup-only-never-writer-proof'
        api_external_side_effects='fixed-mock-transport'
        sqlite='real'
        native_owned_process_tree='real'
        writer_console_mode='detached-process'
        authority='retained-creation-objects-and-typed-barrier'
        credentials='test-envelope-only-no-real-credentials'
        wal_claim='not-tested'
        browser='not-run'
        keeper_loss='unavailable'
        dynamic_writer_admission='unavailable'
        warm_routing='unavailable'
        physical_replace='unavailable'
        windows11='not-run'
        rights_review='pending-exact-output'
        production_activation=$false
        target_activation=$false
        installer='not-built'
        r19_complete=$false
        schema='proxy-r19-frozen-populated-state-copy-receipt-v1'
        legacy_source_operation='existing-enter-operation'
        semantic_coverage='normal-api-and-disposable-clone-services'
        strict_writer_runtime_budget_ms=30000
        http_transport_timeout_ms=35000
        expected_database_schema_pins=@(0,0,0,0)
        expected_current_transcript_rows=3
        expected_retained_legacy_transcript_rows=1
        expected_local_grammar_overrides=2
        expected_export_sentence_records=1
        expected_export_references=3
        fixture_model='four-marked-roots-populated-before-owner'
        status=$Status
        source_commit=$proof.source_commit
        build_id=$proof.build_id
        legacy_source_sha256=$script:legacySourceHash
        source_operation_blocked_observations=$script:sourceBlocks
        source_cohorts=$(if ($null -ne $script:lastEvent) {$script:lastEvent['generation']} else {0})
        retained_writer_signals=$(if ($null -ne $script:lastEvent) {$script:lastEvent['writers_signaled']} else {0})
        strict_drains=$(if ($null -ne $script:lastEvent) {$script:lastEvent['strict_drains']} else {0})
        fixture_seed=$(if ($passed) {'complete-before-owner'} else {'not-approved'})
        initial_source_operation=$(if ($passed) {'open-before-owner'} else {'not-approved'})
        copy_verification=$(if ($passed) {'passed'} else {'not-approved'})
        api_readback=$(if ($passed) {'both-cohorts-passed'} else {'not-approved'})
        service_readback=$(if ($passed) {'passed'} else {'not-approved'})
        source_bytes=$(if ($passed) {'preserved-before-resume'} else {'not-approved'})
        snapshot_bytes=$(if ($passed) {'unchanged-after-readback'} else {'not-approved'})
        source_logical=$(if ($passed) {'passed-after-fresh-source-cohort'} else {'not-approved'})
        external_state=$(if ($passed) {'preserved-before-and-after-resume'} else {'not-approved'})
        pointer=$(if ($passed) {'baseline-unchanged'} else {'not-approved'})
        old_barrier=$(if ($passed) {'refused-after-new-generation'} else {'not-approved'})
        cleanup=$(if ($passed) {'retained-writers-signaled-leases-released-private-tree-removed'} else {'unconfirmed-recovery-required'})
        failure_stage=$(if ($passed) {'none'} else {$script:stage})
        failure_category=$(if ($passed) {'none'} else {$script:failureCategory})
    }
    Write-PopulatedSink ($receipt | ConvertTo-Json -Depth 5)
}
function Wait-PopulatedRecovery {
    # Keep genuine owner/input/readers/lease objects in the calling scope. No
    # PID adoption, finally-kill, automatic lease release or private cleanup.
    try { [Console]::Error.WriteLine('Populated-state recovery required; retain the actual owner and its exclusion. A deadline is a failed attempt with unconfirmed cleanup.') } catch {}
    while ($true) { Start-Sleep -Seconds 5 }
}
function Complete-PopulatedHarness([bool]$Failed) {
    try { Write-PopulatedReceipt $(if ($Failed) {'failed'} else {'passed'}) }
    catch { $Failed=$true }  # Never remove a preexisting/linked/unowned output.
    if ($Failed) {
        if (-not $script:ownerExitConfirmed) {
            foreach ($process in $owned) {
                try { $exited=$process.HasExited } catch { Wait-PopulatedRecovery }
                if ($exited -isnot [bool] -or -not $exited) { Wait-PopulatedRecovery }
            }
        }
        throw 'Authored frozen populated-state probe failed; retain private evidence.'
    }
}

# No installed root or operator-provided mutable path is accepted. RuntimeRoot
# is the exact immutable extracted experiment; every mutable root is new below
# this private bootstrap envelope and independently revalidated by Python.
$RuntimeRoot=(Get-Item -LiteralPath $RuntimeRoot).FullName
$proof=Get-Content -LiteralPath $Provenance -Raw | ConvertFrom-Json
if ($proof.schema -cne 'proxy-runtime-candidate-v1' -or $proof.profile -cne 'runtime-experiment' -or
    $proof.r19_complete -isnot [bool] -or $proof.r19_complete -ne $false -or
    $proof.source_commit -isnot [string] -or $proof.source_commit -cnotmatch '\A[a-f0-9]{40}\z' -or
    $proof.source_commit -cne $env:GITHUB_SHA -or $proof.build_id -isnot [string] -or
    @($proof.files).Count -lt 1) {
    throw 'Need the exact submitted quarantined candidate, not an installed release.'
}
Assert-SlotInventory $RuntimeRoot $proof
$null=Assert-PopulatedSink $Output
$legacySourceHash=(Get-FileHash -LiteralPath $slotSourceOperation -Algorithm SHA256).Hash.ToLowerInvariant()
if ($legacySourceHash -cnotin @('c0cb1b456c029e8cb843501ffaf17cf2b054bdfecad8e788dd35d9a85ae2d3ef',
    'f9469ccb51c99b814a615e66eb9b337e8b1ba8598a0fd794dbe420c8be4c8e9e')) {
    throw 'Need the exact reviewed LF or CRLF legacy source operation.'
}
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('r19-p2-'+[guid]::NewGuid().ToString('N'))
$private=Join-Path $temporary 'empty-host/p2'
$roots=@{PROXY_TRANSCRIPT_SETTINGS_ROOT=$private;PROXY_TRANSCRIPT_DATA_ROOT=(Join-Path $private 'data-v1');
    PROXY_TRANSCRIPT_CACHE_ROOT=(Join-Path $private 'cache-v1');PROXY_TRANSCRIPT_WORK_ROOT=(Join-Path $private 'cache-v1/work');
    PROXY_TRANSCRIPT_TOOL_ROOT=(Join-Path $private 'tools-v1');PROXY_TRANSCRIPT_STATE_ROOT=(Join-Path $private 'host-v1');
    PROXY_TRANSCRIPT_DEFAULT_EXPORT_ROOT=(Join-Path $private 'exports')}
$fixture=Join-Path $roots.PROXY_TRANSCRIPT_WORK_ROOT 'p2-native'
$legacyRoot=Join-Path $fixture 'legacy'
$leasePaths=@((Join-Path $legacyRoot 'data/companion-operation.lock'),
    (Join-Path $fixture 'private-target/host-v1/migration-runtime.lock'))
$owned=[Collections.Generic.List[Diagnostics.Process]]::new()
$controlReader=$null; $stderrDiscard=$null; $lastEvent=$null
$receiptSink=$null
$ownerExitConfirmed=$false; $privateCleanupConfirmed=$false; $seededBaseline=$false
$sourceBlocks=0; $stage='prepare'; $failureCategory='harness-unconfirmed'; $failed=$false
try {
    New-Item -ItemType Directory -Path $temporary -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $roots.PROXY_TRANSCRIPT_STATE_ROOT -Force | Out-Null
    @{build_id=$proof.build_id;synthetic=$true} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $roots.PROXY_TRANSCRIPT_STATE_ROOT 'synthetic-probe.json') -Encoding utf8NoBOM
    Assert-DataCopyPortsFree
    $process=Start-PopulatedOwner
    $phases=@('seeded-before-owner','owner-entered','api-populated-checked','strict-drain-complete',
        'writers-signaled','copy-progress','copy-verified','source-resumed',
        'final-strict-drain-complete','final-writers-signaled')
    foreach ($phase in $phases) {
        $stage=$phase
        Read-PopulatedEvent $phase
        if ($phase -ceq 'seeded-before-owner') { Assert-PopulatedSourceBaseline }
        else { Assert-PopulatedLeases 'blocked' }
        # Only these independently completed native observations permit ACK.
        $process.StandardInput.WriteLine('observed '+$phase); $process.StandardInput.Flush()
    }
    $stage='release'
    Read-PopulatedEvent 'released'  # Terminal, deliberately no ACK.
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(15000) -or $process.ExitCode -ne 0) {
        throw 'Retained populated-state owner did not exit successfully.'
    }
    $script:ownerExitConfirmed=$true
    if ($null -ne (Read-DataCopyControlLine $script:controlReader 5000 $true)) {
        throw 'Unexpected trailing populated-state control event.'
    }
    if (-not $stderrDiscard.Wait(5000)) { throw 'Populated-state stderr discard did not finish.' }
    $null=$stderrDiscard.GetAwaiter().GetResult()
    Assert-PopulatedLeases 'open'
    Assert-DataCopyPortsFree
    Assert-SlotInventory $RuntimeRoot $proof
    if ((Get-FileHash -LiteralPath $slotSourceOperation -Algorithm SHA256).Hash.ToLowerInvariant() -cne $legacySourceHash) {
        throw 'The actual legacy source changed during the populated-state attempt.'
    }
    $stage='private-cleanup'
    foreach ($process in $owned) { $process.Dispose() }
    Remove-Item -LiteralPath $temporary -Recurse -Force
    $script:privateCleanupConfirmed=$true
} catch {
    $failed=$true
    if ($null -ne $controlReader -and $controlReader.fault -cin @('control-overflow','control-eof',
        'control-invalid-utf8','control-reader-unavailable','control-deadline','stderr-unavailable')) {
        $failureCategory=$controlReader.fault
    }
}
# Publication cannot precede native/process/stream/inventory/private cleanup.
Complete-PopulatedHarness $failed
Write-Host 'Authored populated-state copy verified with living coordinator and fresh source cohort; production migration remains disabled.'
