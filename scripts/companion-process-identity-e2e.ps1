param([string]$BaselineRevision, [switch]$VerifyBaseline)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Process tree fixtures require Windows; no Windows verification was performed.' }
$repository = Split-Path -Parent $PSScriptRoot
$shell = (Get-Process -Id $PID).Path
$clock = [Diagnostics.Stopwatch]::StartNew()
if ($VerifyBaseline) {
    $ErrorActionPreference = 'Continue'
    try { $output = & $shell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -BaselineRevision '7ae7e6991a6cc848334109720fb9ef608bca6999' 2>&1 | Out-String; $baselineExit=$LASTEXITCODE }
    finally { $ErrorActionPreference = 'Stop' }
    if ($baselineExit -eq 0 -or $output -notmatch 'UNVERIFIED_PID_WAS_STOPPED') { throw 'Baseline did not reproduce the expected unverified PID regression.' }
    Write-Host 'Baseline regression reproduced: a legacy PID-only record terminates an unrelated fixture without ownership evidence.'
}
. (Join-Path $repository 'scripts\companion-runtime.ps1')
$root = Join-Path ([System.IO.Path]::GetTempPath()) ('companion-identity-'+[guid]::NewGuid().ToString('N'))
$scripts = Join-Path $root 'scripts'
$data = Join-Path $root 'data'
$recordFile = Join-Path $data 'processes.json'
$children = @()
New-Item -ItemType Directory -Path $scripts,$data -Force | Out-Null
function Assert-Alive($Process, [string]$Message) { $Process.Refresh(); if ($Process.HasExited) { throw $Message } }
function Assert-FixtureIdentity($Record, [string]$Stage) {
    $verified=Get-CompanionOwnedProcess $Record $root
    if($verified){$verified.Dispose();return}
    $details=[ordered]@{stage=$Stage;recordIsObject=($Record -isnot [ValueType] -and $Record -isnot [string]);
        idValid=([string]$Record.id -match '^[1-9][0-9]*$');startedValid=([string]$Record.started -match '^[1-9][0-9]*$')}
    $observed=$null
    try{
        $details.rootMatches=([IO.Path]::GetFullPath([string]$Record.root) -eq [IO.Path]::GetFullPath($root))
        $observed=Get-Process -Id ([int]$Record.id) -ErrorAction Stop
        $null=$observed.Handle
        $details.live=(-not $observed.HasExited)
        $details.idMatches=($observed.Id -eq $Record.id)
        $details.startedMatches=($observed.StartTime.ToUniversalTime().Ticks.ToString() -eq [string]$Record.started)
        $details.executableMatches=([IO.Path]::GetFullPath($observed.Path) -eq [IO.Path]::GetFullPath([string]$Record.executable))
    }catch{$details.exceptionType=$_.Exception.GetType().FullName}
    finally{if($observed){$observed.Dispose()}}
    throw ('Owned fixture identity was rejected: '+($details|ConvertTo-Json -Compress))
}
function Start-Fixture {
    $process=Start-Process $shell -ArgumentList '-NoProfile -Command "Start-Sleep -Seconds 180"' -PassThru -WindowStyle Hidden
    $null=$process.Handle
    $script:children+=,$process
    return $process
}
function Invoke-Stop { & (Join-Path $scripts 'stop-companion.ps1') }
try {
    foreach ($name in @('stop-companion.ps1','start-companion.ps1','retire-companion.ps1','companion-runtime.ps1')) {
        if ($BaselineRevision) {
            $source = & git -C $repository show ($BaselineRevision+':scripts/'+$name)
            if ($LASTEXITCODE -ne 0) { throw 'Cannot read baseline scripts.' }
            [IO.File]::WriteAllText((Join-Path $scripts $name), ($source -join "`n"))
        } else { Copy-Item (Join-Path $repository ('scripts\'+$name)) (Join-Path $scripts $name) }
    }
    $unrelated=Start-Fixture
    $valid=New-CompanionProcessRecord $unrelated $root
    if (-not $BaselineRevision) {
        Assert-FixtureIdentity $valid 'initial capture'
        Write-Host 'Owned fixture identity capture passed.'
    }
    $wrongStart=@{};foreach($key in $valid.Keys){$wrongStart[$key]=$valid[$key]}
    $wrongStart.started=([long]$valid.started-1).ToString()
    # The legacy format has no start time at all; demonstrate the unsafe
    # numeric-record behavior in both revisions before testing richer records.
    Save-CompanionJson $recordFile @{backend=$valid.id}
    Invoke-Stop
    Assert-Alive $unrelated 'UNVERIFIED_PID_WAS_STOPPED'
    if ($BaselineRevision) { throw 'Baseline unexpectedly contains the process identity repair.' }
    Save-CompanionJson $recordFile @{backend=$wrongStart}
    Invoke-Stop
    Assert-Alive $unrelated 'A process with the wrong start time was stopped.'
    Assert-FixtureIdentity $valid 'before priority restoration'
    $unrelated.PriorityClass='BelowNormal'
    $priorityRejected=$false
    try { Set-CompanionNormalPriority $wrongStart $root } catch { $priorityRejected=$true }
    $unrelated.Refresh()
    if (-not $priorityRejected -or $unrelated.PriorityClass -ne 'BelowNormal') { throw 'Priority change accepted an unverified identity.' }
    Set-CompanionNormalPriority $valid $root
    $unrelated.Refresh()
    if ($unrelated.PriorityClass -ne 'Normal') { throw 'Owned replacement priority was not restored.' }
    Write-Host 'Priority identity rejection and owned restoration passed.'

    # A surviving process can retain an old parent PID after that PID is reused.
    # Synthetic CIM parentage must not override the child's earlier start time.
    Start-Sleep -Milliseconds 100
    $priorityParent=Start-Fixture
    $unrelated.PriorityClass='BelowNormal'
    function Get-CimInstance {
        param([string]$ClassName,[string]$Filter,[string]$ErrorAction)
        if($Filter -eq ('ParentProcessId='+$priorityParent.Id) -or $Filter -eq ('ProcessId='+$unrelated.Id)){
            return [pscustomobject]@{ProcessId=$unrelated.Id;ParentProcessId=$priorityParent.Id}
        }
    }
    $priorityRecord=New-CompanionProcessRecord $priorityParent $root
    try{
        Assert-FixtureIdentity $priorityRecord 'synthetic stale parent'
        Set-CompanionNormalPriority $priorityRecord $root
        Stop-CompanionProcess $priorityRecord $root
    }
    finally{Remove-Item Function:\Get-CimInstance}
    $unrelated.Refresh()
    if($unrelated.PriorityClass -ne 'BelowNormal'){throw 'Stale parent PID promoted an older unrelated process.'}
    Assert-Alive $unrelated 'Stale parent PID terminated an older unrelated process.'
    if(-not $priorityParent.WaitForExit(10000)){throw 'Validated parent of the synthetic stale link was not stopped.'}
    Write-Host 'Synthetic stale parent link rejected for priority and termination; no actual PID reuse was induced.'

    # Override only this exact owned fixture object's native termination method.
    $unrelated|Add-Member -MemberType ScriptMethod -Name Kill -Value {throw [ComponentModel.Win32Exception]::new(5)} -Force
    $stopRejected=$false
    try { Stop-CompanionProcessHandle $unrelated } catch { if($_.Exception.Message -notmatch 'Windows refused'){throw};$stopRejected=$true }
    finally { $unrelated.PSObject.Members.Remove('Kill') }
    if (-not $stopRejected) { throw 'Failed termination was reported as success.' }
    Assert-Alive $unrelated 'Termination refusal fixture unexpectedly exited.'
    Write-Host 'Controlled native termination refusal was reported.'

    foreach ($invalid in @($valid.id, @{id=$valid.id}, @{id=$valid.id;started=$valid.started},
        @{id=$valid.id;started=$valid.started;executable=$valid.executable;root=(Join-Path $root 'other')},
        @{id=$valid.id;started=$valid.started;executable=(Join-Path $root 'other.exe');root=$root})) {
        Save-CompanionJson $recordFile @{backend=$invalid}
        Invoke-Stop
        Assert-Alive $unrelated 'Invalid or legacy process identity terminated a live fixture.'
    }
    foreach ($invalidJson in @('{broken', 'null', '[]', '{}', '{"backend":{"id":"not-a-pid"}}')) {
        [IO.File]::WriteAllText($recordFile,$invalidJson)
        Invoke-Stop
        Assert-Alive $unrelated 'Corrupt process file terminated a live fixture.'
    }
    Remove-Item $recordFile
    Invoke-Stop
    $exited=Start-Fixture
    $exitedRecord=New-CompanionProcessRecord $exited $root
    $exited.Kill();$exited.WaitForExit()
    Save-CompanionJson $recordFile @{backend=$exitedRecord}
    Invoke-Stop
    Assert-Alive $unrelated 'Exited process record affected an unrelated fixture.'

    $owned=Start-Fixture
    $ownedRecord=New-CompanionProcessRecord $owned $root
    Save-CompanionJson $recordFile @{backend=$ownedRecord}
    Invoke-Stop
    if (-not $owned.WaitForExit(10000)) { throw 'A correctly identified owned process was not stopped.' }
    Invoke-Stop
    Assert-Alive $unrelated 'Repeated stop affected an unrelated fixture.'

    # A real three-generation Windows tree verifies recursive parent-first
    # termination against actual CIM relationships, without any unrelated PIDs.
    $treeScript=Join-Path $root 'tree-fixture.ps1'
    [IO.File]::WriteAllText($treeScript,@'
param([string]$Shell,[string]$Root,[int]$Depth)
$ErrorActionPreference='Stop'
. (Join-Path $Root 'scripts\companion-runtime.ps1')
$self=Get-Process -Id $PID
$null=$self.Handle
Save-CompanionJson (Join-Path $Root ('tree-'+$Depth+'.json')) (New-CompanionProcessRecord $self $Root)
if($Depth -gt 0){
    $arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -Shell "'+$Shell+'" -Root "'+$Root+'" -Depth '+($Depth-1)
    $child=Start-Process $Shell -ArgumentList $arguments -PassThru -WindowStyle Hidden
    $null=$child.Handle
}
Start-Sleep -Seconds 180
'@)
    $treeArguments='-NoProfile -ExecutionPolicy Bypass -File "'+$treeScript+'" -Shell "'+$shell+'" -Root "'+$root+'" -Depth 2'
    $treeParent=Start-Process $shell -ArgumentList $treeArguments -PassThru -WindowStyle Hidden
    $null=$treeParent.Handle
    $children+=,$treeParent
    $treeRecord=New-CompanionProcessRecord $treeParent $root
    $treeDescendants=@()
    foreach($depth in @(1,0)){
        $identityFile=Join-Path $root ('tree-'+$depth+'.json')
        $deadline=[DateTime]::UtcNow.AddSeconds(30)
        while(-not (Test-Path $identityFile)){
            if([DateTime]::UtcNow -gt $deadline){throw 'Owned process tree did not become ready.'}
            Start-Sleep -Milliseconds 50
        }
        $identity=Get-Content $identityFile -Raw|ConvertFrom-Json
        Assert-FixtureIdentity $identity ('owned tree depth '+$depth)
        $descendant=Get-CompanionOwnedProcess $identity $root
        $children+=,$descendant
        $treeDescendants+=,$descendant
    }
    Stop-CompanionProcess $treeRecord $root
    foreach($process in @($treeParent)+$treeDescendants){
        if(-not $process.WaitForExit(10000)){throw 'A legitimate owned process tree member survived termination.'}
    }
    Assert-Alive $unrelated 'Owned process tree termination affected an unrelated fixture.'
    Write-Host 'Real owned parent, child and grandchild terminated successfully.'

    $retired=Start-Fixture
    $retireFile=Join-Path $data 'retire.json'
    Save-CompanionJson $retireFile @($wrongStart,(New-CompanionProcessRecord $retired $root))
    function Start-Sleep { }
    try { & (Join-Path $scripts 'retire-companion.ps1') -Record $retireFile -Root $root }
    finally { Remove-Item Function:\Start-Sleep }
    if (-not $retired.WaitForExit(10000)) { throw 'Retirement did not stop its correctly identified fixture.' }
    Assert-Alive $unrelated 'Retirement stopped a fixture with the wrong start time.'

    # Run the actual launcher; only network probes and process creation are
    # controlled. A healthy endpoint alone must not prove process ownership.
    Add-Content (Join-Path $scripts 'companion-runtime.ps1') @'
function Test-CompanionEndpoint([string]$Url) { return $true }
function Start-CompanionProcess { throw 'Launcher attempted to duplicate a healthy owned process.' }
'@
    Save-CompanionJson $recordFile @{backend=$valid;frontend=$valid}
    & (Join-Path $scripts 'start-companion.ps1') -NoBrowser
    Save-CompanionJson $recordFile @{backend=$wrongStart;frontend=$wrongStart}
    $rejected=$false
    try { & (Join-Path $scripts 'start-companion.ps1') -NoBrowser }
    catch { if ($_.Exception.Message -notmatch 'without a verified companion process record') { throw }; $rejected=$true }
    if (-not $rejected) { throw 'Launcher reused live processes with a mismatched identity.' }
    Assert-Alive $unrelated 'Launcher terminated a process with a mismatched identity.'
    Write-Host 'Windows identity fixtures passed: identity mismatch, synthetic stale parent link, owned process tree, missing/exited, corrupt/incomplete/legacy, executable/root mismatch, owned stop, repeat stop, retirement and launch reuse.'
} finally {
    foreach ($process in $children) {
        try {
            if (-not $process.HasExited) {
                try { Stop-CompanionProcessHandle $process }
                catch { if (-not $process.HasExited) { $process.Kill(); $process.WaitForExit() } }
            }
        } catch { }
        finally { $process.Dispose() }
    }
    Remove-Item -LiteralPath $root -Recurse -Force
    $clock.Stop()
    $evidence=Join-Path $repository 'output\checks'
    New-Item -ItemType Directory -Path $evidence -Force | Out-Null
    @{check='windows-process-identity';baseline=[bool]$BaselineRevision;elapsedMs=$clock.ElapsedMilliseconds;platform='Windows'} | ConvertTo-Json | Set-Content (Join-Path $evidence ('windows-process-identity'+$(if($BaselineRevision){'-baseline'}else{''})+'.json'))
}
