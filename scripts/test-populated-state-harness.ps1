# Pure authored PS7 projector/output-file contracts; never runs the harness body.
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core') { throw 'Need PowerShell 7 for authored populated-state contracts.' }
$source=Join-Path $PSScriptRoot 'probe-frozen-populated-state.ps1'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)
if ($errors) { throw 'The populated-state source did not parse.' }
foreach ($name in @('Convert-PopulatedControl','Get-PopulatedExpectedPhase','Read-PopulatedEvent',
    'Assert-PopulatedSink','Write-PopulatedSink','Write-PopulatedReceipt')) {
    $defs=@($ast.FindAll({param($n)
        $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name
    },$true))
    if ($defs.Count -ne 1) { throw 'The authored function count differs.' }
    . ([scriptblock]::Create($defs[0].Extent.Text))
}
# This reader supplies bounded authored records only. It cannot exercise the
# actual byte reader, native owner, HTTP, lease, process or copy path.
function Read-DataCopyControlLine($Reader) { return $script:authoredLine }
function Assert-Authored([bool]$Value) {
    if (-not $Value) { throw 'An authored populated-state contract failed.' }
}
$cases=0; $temporary=$null; $cleanupConfirmed=$false
try {
    # Independent fixed fixture policy and phase differences; no production
    # table or projector supplies an expected value to this oracle.
    $script:authoredBase=@'
{"schema":"proxy-r19-frozen-populated-state-copy-probe-v1","kind":"populated-state-copy","case":"authored-populated-state-copy-v1","scope":"authored-mapped-populated-copy-with-living-coordinator","setup_sql_fences":"setup-only-never-writer-proof","api_external_side_effects":"fixed-mock-transport","sqlite":"real","native_owned_process_tree":"real","writer_console_mode":"detached-process","authority":"retained-creation-objects-and-typed-barrier","credentials":"test-envelope-only-no-real-credentials","wal_claim":"not-tested","browser":"not-run","keeper_loss":"unavailable","dynamic_writer_admission":"unavailable","warm_routing":"unavailable","physical_replace":"unavailable","windows11":"not-run","rights_review":"pending-exact-output","production_activation":false,"target_activation":false,"installer":"not-built","r19_complete":false,"phase":"seeded-before-owner","generation":0,"writers_created":0,"writers_resumed":0,"writers_signaled":0,"strict_drains":0,"owner_interval":"not-entered","api_readback":"not-run","copy_verification":"not-run","service_readback":"not-run","source_bytes":"not-run","snapshot_bytes":"not-run","source_logical":"not-run","external_state":"not-run","pointer":"not-entered","old_barrier_refused":false,"status":"observing","failure":"none","fixture_seed":"complete-before-owner","source_commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","build_id":"authored-build"}
'@ | ConvertFrom-Json -AsHashtable
    function New-AuthoredFrame($Changes) {
        $frame=[ordered]@{}
        foreach ($entry in $script:authoredBase.GetEnumerator()) { $frame[$entry.Key]=$entry.Value }
        foreach ($entry in $Changes.GetEnumerator()) { $frame[$entry.Key]=$entry.Value }
        return [pscustomobject]$frame
    }
    $phaseChanges=@'
[
{"phase":"seeded-before-owner"},
{"phase":"owner-entered","owner_interval":"leases-held","pointer":"baseline-unchanged"},
{"phase":"api-populated-checked","generation":1,"writers_created":2,"writers_resumed":2,"owner_interval":"leases-held","api_readback":"first-cohort-passed","pointer":"baseline-unchanged"},
{"phase":"strict-drain-complete","generation":1,"writers_created":2,"writers_resumed":2,"strict_drains":1,"owner_interval":"leases-held","api_readback":"first-cohort-passed","pointer":"baseline-unchanged"},
{"phase":"writers-signaled","generation":1,"writers_created":2,"writers_resumed":2,"writers_signaled":2,"strict_drains":1,"owner_interval":"leases-held","api_readback":"first-cohort-passed","pointer":"baseline-unchanged"},
{"phase":"copy-progress","generation":1,"writers_created":2,"writers_resumed":2,"writers_signaled":2,"strict_drains":1,"owner_interval":"leases-held","api_readback":"first-cohort-passed","pointer":"baseline-unchanged"},
{"phase":"copy-verified","generation":1,"writers_created":2,"writers_resumed":2,"writers_signaled":2,"strict_drains":1,"owner_interval":"leases-held","api_readback":"first-cohort-passed","copy_verification":"passed","service_readback":"passed","source_bytes":"preserved-before-resume","snapshot_bytes":"unchanged-after-readback","external_state":"preserved-before-resume","pointer":"baseline-unchanged"},
{"phase":"source-resumed","generation":2,"writers_created":4,"writers_resumed":4,"writers_signaled":2,"strict_drains":1,"owner_interval":"leases-held","api_readback":"both-cohorts-passed","copy_verification":"passed","service_readback":"passed","source_bytes":"preserved-before-resume","snapshot_bytes":"unchanged-after-readback","source_logical":"passed-after-fresh-source-cohort","external_state":"preserved-before-and-after-resume","pointer":"baseline-unchanged","old_barrier_refused":true},
{"phase":"final-strict-drain-complete","generation":2,"writers_created":4,"writers_resumed":4,"writers_signaled":2,"strict_drains":2,"owner_interval":"leases-held","api_readback":"both-cohorts-passed","copy_verification":"passed","service_readback":"passed","source_bytes":"preserved-before-resume","snapshot_bytes":"unchanged-after-readback","source_logical":"passed-after-fresh-source-cohort","external_state":"preserved-before-and-after-resume","pointer":"baseline-unchanged","old_barrier_refused":true},
{"phase":"final-writers-signaled","generation":2,"writers_created":4,"writers_resumed":4,"writers_signaled":4,"strict_drains":2,"owner_interval":"leases-held","api_readback":"both-cohorts-passed","copy_verification":"passed","service_readback":"passed","source_bytes":"preserved-before-resume","snapshot_bytes":"unchanged-after-readback","source_logical":"passed-after-fresh-source-cohort","external_state":"preserved-before-and-after-resume","pointer":"baseline-unchanged","old_barrier_refused":true},
{"phase":"released","generation":2,"writers_created":4,"writers_resumed":4,"writers_signaled":4,"strict_drains":2,"owner_interval":"leases-released","api_readback":"both-cohorts-passed","copy_verification":"passed","service_readback":"passed","source_bytes":"preserved-before-resume","snapshot_bytes":"unchanged-after-readback","source_logical":"passed-after-fresh-source-cohort","external_state":"preserved-before-and-after-resume","pointer":"baseline-unchanged","old_barrier_refused":true,"status":"passed"}
]
'@ | ConvertFrom-Json -AsHashtable
    $mutations=@'
[
{"name":"wrong-case","changes":{"case":"private-case"},"remove":[]},
{"name":"wrong-source","changes":{"source_commit":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},"remove":[]},
{"name":"wrong-build","changes":{"build_id":"private-build"},"remove":[]},
{"name":"wrong-policy","changes":{"production_activation":true},"remove":[]},
{"name":"bool-count","changes":{"generation":false},"remove":[]},
{"name":"fractional-count","changes":{"generation":0.1},"remove":[]},
{"name":"excess-count","changes":{"writers_created":5},"remove":[]},
{"name":"nested","changes":{"authority":{"path":"private-root"}},"remove":[]},
{"name":"null","changes":{"status":null},"remove":[]},
{"name":"wrong-phase","changes":{"phase":"owner-entered"},"remove":[]},
{"name":"private-enum","changes":{"api_readback":"private-token"},"remove":[]},
{"name":"unknown-key","changes":{"private-key":"private-value"},"remove":[]},
{"name":"failed-normal","changes":{"status":"failed","failure":"copy-refused"},"remove":[]},
{"name":"missing-key","changes":{},"remove":["phase"]}
]
'@ | ConvertFrom-Json -AsHashtable
    $negative=@(foreach ($mutation in $mutations) {
        $frame=New-AuthoredFrame $mutation.changes
        foreach ($key in $mutation.remove) { $frame.PSObject.Properties.Remove($key) }
        [pscustomobject]@{name=$mutation.name;raw=($frame | ConvertTo-Json -Compress -Depth 5)}
    })
    $baseRaw=New-AuthoredFrame @{} | ConvertTo-Json -Compress -Depth 5
    $negative+=@(
        [pscustomobject]@{name='duplicate';raw=($baseRaw.TrimEnd('}')+',"case":"private-duplicate"}')},
        [pscustomobject]@{name='trailing-record';raw=($baseRaw+$baseRaw)},
        [pscustomobject]@{name='oversized';raw=($baseRaw+(' '*8193))}
    )
    $recoveryChanges=@'
{"phase":"recovery-required","generation":1,"writers_created":2,"writers_resumed":2,"owner_interval":"leases-held","api_readback":"first-cohort-passed","pointer":"baseline-unchanged","status":"failed","failure":"control-invalid"}
'@ | ConvertFrom-Json -AsHashtable
    $vectors=[pscustomobject]@{
        frames=@(foreach ($phase in $phaseChanges) { New-AuthoredFrame $phase })
        negative=$negative
        recovery=(New-AuthoredFrame $recoveryChanges)
    }
    $script:proof=[pscustomobject]@{source_commit=('a'*40);build_id='authored-build'}
    $script:controlReader=@{}; $script:failureCategory='harness-unconfirmed'; $script:lastEvent=$null
    foreach ($frame in $vectors.frames) {
        $script:authoredLine=$frame | ConvertTo-Json -Compress -Depth 4
        Read-PopulatedEvent $frame.phase
        Assert-Authored ($script:lastEvent['phase'] -ceq $frame.phase)
        $cases++
    }
    $original=$script:lastEvent
    foreach ($case in $vectors.negative) {
        $script:authoredLine=$case.raw; $refused=$false
        try { Read-PopulatedEvent 'seeded-before-owner' } catch { $refused=$true }
        Assert-Authored ($refused -and [object]::ReferenceEquals($script:lastEvent,$original))
        $cases++
    }
    $script:authoredLine=$vectors.recovery | ConvertTo-Json -Compress -Depth 4
    $refused=$false
    try { Read-PopulatedEvent 'strict-drain-complete' } catch { $refused=$true }
    Assert-Authored ($refused -and $script:failureCategory -ceq 'control-invalid' -and
        [object]::ReferenceEquals($script:lastEvent,$original))
    $cases++
    $temporary=Join-Path ([IO.Path]::GetTempPath()) ('r19-p2-check-'+[guid]::NewGuid().ToString('N'))
    $null=New-Item -ItemType Directory -Path $temporary -ErrorAction Stop
    $script:Output=Join-Path $temporary 'missing/parents/receipt.json'
    $script:receiptSink=$null
    $null=Assert-PopulatedSink $script:Output
    Assert-Authored (-not [IO.Directory]::Exists((Join-Path $temporary 'missing')))
    Write-PopulatedSink '{"authored":true}'
    Assert-Authored ($script:receiptSink.state -ceq 'closed' -and
        [IO.File]::ReadAllText($script:Output) -ceq ('{"authored":true}'+[char]10))
    $cases++
    $refused=$false
    try { Write-PopulatedSink '{"authored":false}' } catch { $refused=$true }
    Assert-Authored ($refused -and [IO.File]::ReadAllText($script:Output) -ceq ('{"authored":true}'+[char]10))
    $cases++
    $script:receiptSink=$null
    $refused=$false
    try { Write-PopulatedSink '{"authored":false}' } catch { $refused=$true }
    Assert-Authored ($refused -and [IO.File]::ReadAllText($script:Output) -ceq ('{"authored":true}'+[char]10))
    $cases++
    $outside=Join-Path $temporary 'outside'; $null=New-Item -ItemType Directory -Path $outside
    $sentinel=Join-Path $outside 'receipt.json'; [IO.File]::WriteAllText($sentinel,'owned-sentinel')
    $link=Join-Path $temporary 'linked-parent'
    $null=New-Item -ItemType SymbolicLink -Path $link -Target $outside -ErrorAction Stop
    $script:Output=Join-Path $link 'new.json'; $script:receiptSink=$null
    $refused=$false
    try { Write-PopulatedSink '{"authored":false}' } catch { $refused=$true }
    Assert-Authored ($refused -and -not [IO.File]::Exists((Join-Path $outside 'new.json')))
    $cases++
    Remove-Item -LiteralPath $link -Force -ErrorAction Stop
    $link=Join-Path $temporary 'linked-leaf.json'
    $null=New-Item -ItemType SymbolicLink -Path $link -Target $sentinel -ErrorAction Stop
    $script:Output=$link; $script:receiptSink=$null; $refused=$false
    try { Write-PopulatedSink '{"authored":false}' } catch { $refused=$true }
    Assert-Authored ($refused -and [IO.File]::ReadAllText($sentinel) -ceq 'owned-sentinel')
    $cases++
    Remove-Item -LiteralPath $link -Force -ErrorAction Stop
    $script:Output=Join-Path $temporary 'passed.json'; $script:receiptSink=$null
    $script:seededBaseline=$true; $script:ownerExitConfirmed=$true; $script:privateCleanupConfirmed=$true
    $script:sourceBlocks=9; $script:legacySourceHash='c0cb1b456c029e8cb843501ffaf17cf2b054bdfecad8e788dd35d9a85ae2d3ef'
    Write-PopulatedReceipt 'passed'
    $receipt=Get-Content -LiteralPath $script:Output -Raw | ConvertFrom-Json
    Assert-Authored ($receipt.status -ceq 'passed' -and $receipt.source_cohorts -eq 2 -and
        $receipt.retained_writer_signals -eq 4 -and @($receipt.PSObject.Properties.Name).Count -eq 55 -and
        $receipt.r19_complete -eq $false -and $receipt.production_activation -eq $false)
    $cases++
    $script:Output=Join-Path $temporary 'failed.json'; $script:receiptSink=$null
    $script:stage='strict-drain-complete'; $script:failureCategory='control-invalid'; $script:sourceBlocks=2
    $script:authoredLine=$vectors.frames[2] | ConvertTo-Json -Compress -Depth 4
    Read-PopulatedEvent 'api-populated-checked'
    Write-PopulatedReceipt 'failed'
    $receipt=Get-Content -LiteralPath $script:Output -Raw | ConvertFrom-Json
    Assert-Authored ($receipt.status -ceq 'failed' -and $receipt.source_cohorts -eq 1 -and
        $receipt.retained_writer_signals -eq 0 -and $receipt.strict_drains -eq 0 -and
        $receipt.source_operation_blocked_observations -eq 2 -and
        $receipt.initial_source_operation -ceq 'not-approved' -and
        $receipt.api_readback -ceq 'not-approved' -and $receipt.r19_complete -eq $false)
    $cases++
    $script:Output=Join-Path $temporary 'no-early-pass.json'; $script:receiptSink=$null
    $script:privateCleanupConfirmed=$false; $refused=$false
    try { Write-PopulatedReceipt 'passed' } catch { $refused=$true }
    Assert-Authored ($refused -and -not [IO.File]::Exists($script:Output))
    $cases++
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction Stop
    $cleanupConfirmed=$true
    [Console]::Out.WriteLine('Authored populated-state projector and sink contracts passed: '+$cases)
} catch {
    # Unknown resources/fixture are retained. Never print raw errors/paths/JSON.
    [Console]::Error.WriteLine('Authored populated-state projector or sink contracts failed; private fixture retained.')
    exit 2
}
