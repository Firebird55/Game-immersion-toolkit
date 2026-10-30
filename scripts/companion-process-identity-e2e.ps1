param([string]$BaselineRevision, [switch]$VerifyBaseline, [switch]$ImageFixturesOnly, [switch]$RetirementFixturesOnly)
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$shell = (Get-Process -Id $PID).Path
. (Join-Path $repository 'scripts\companion-runtime.ps1')
function Test-ImageAcquisition {
    # Mock only the native image-query boundary. Synthetic handles never reach
    # Windows; real current-process and fresh-child queries run below on Windows.
    function New-ImageProbe {
        $probe=[pscustomobject]@{Id=1;Handle=[IntPtr]1024;HasExited=$false;StartTime=[datetime]::new(2026,1,1,0,0,0,[DateTimeKind]::Utc);
            Executable=$shell;Queries=0;ExitOnQuery=$false;ChangeStartOnQuery=$false;QueryError=$false;Disposed=$false;
            Path=(Join-Path $repository 'unstable-module.exe')}
        $probe|Add-Member -MemberType ScriptMethod -Name get_MainModule -Value {return [pscustomobject]@{FileName=$this.Path}}
        $probe|Add-Member -MemberType ScriptMethod -Name Dispose -Value {$this.Disposed=$true}
        return $probe
    }
    function Read-CompanionProcessImage([IntPtr]$Handle) {
        if($Handle -ne $nativeProbe.Handle){throw 'Image query did not receive the retained process handle.'}
        $nativeProbe.Queries++
        if($nativeProbe.QueryError){throw [ComponentModel.Win32Exception]::new(5,'CONTROLLED_NATIVE_QUERY_FAILURE')}
        if($nativeProbe.ExitOnQuery){$nativeProbe.HasExited=$true}
        if($nativeProbe.ChangeStartOnQuery){$nativeProbe.StartTime=$nativeProbe.StartTime.AddTicks(1)}
        return $nativeProbe.Executable
    }
    function Get-Process {param([int]$Id,[string]$ErrorAction);if($Id -ne $imageLookup.Id){throw 'Unexpected synthetic PID lookup.'};return $imageLookup}
    $nativeProbe=New-ImageProbe
    $identity=New-CompanionProcessRecord $nativeProbe $repository
    if($nativeProbe.Queries -ne 1 -or $identity.executable -ne [IO.Path]::GetFullPath($shell)){
        throw 'Native image query did not supply the executable identity independently of module metadata.'
    }
    $nativeProbe=New-ImageProbe
    $imageLookup=$nativeProbe
    $verified=Get-CompanionOwnedProcess $identity $repository
    if(-not $verified -or $nativeProbe.Queries -ne 1){throw 'Owned lookup did not use its retained handle image query.'}
    $verified.Dispose()
    $nativeProbe=New-ImageProbe
    $imageLookup=$nativeProbe
    $mismatch=@{id=$identity.id;started=([long]$identity.started-1).ToString();executable=$identity.executable;root=$identity.root}
    if((Get-CompanionOwnedProcess $mismatch $repository) -or $nativeProbe.Queries -ne 0){throw 'Start-time mismatch reached the image query.'}
    $nativeProbe=New-ImageProbe
    $imageLookup=$nativeProbe
    $mismatch.started=$identity.started
    $mismatch.executable=Join-Path $repository 'different-executable.exe'
    if((Get-CompanionOwnedProcess $mismatch $repository) -or $nativeProbe.Queries -ne 1){throw 'Executable mismatch was accepted or retried.'}
    foreach($case in @('empty','exited','invalid','access','changed-start')){
        $nativeProbe=New-ImageProbe
        $expected='invalid companion executable'
        switch($case){
            empty {$nativeProbe.Executable=''}
            exited {$nativeProbe.ExitOnQuery=$true;$expected='exited'}
            invalid {$nativeProbe.Executable='relative.exe'}
            access {$nativeProbe.QueryError=$true;$expected='CONTROLLED_NATIVE_QUERY_FAILURE'}
            changed-start {$nativeProbe.ChangeStartOnQuery=$true;$expected='changed or exited'}
        }
        $rejected=$false
        try{New-CompanionProcessRecord $nativeProbe $repository|Out-Null}catch{if($_.Exception.Message -notmatch $expected){throw};$rejected=$true}
        if(-not $rejected){throw ('Image acquisition accepted '+$case)}
        if($nativeProbe.Queries -ne 1){throw ('Image acquisition retried '+$case)}
    }
    Write-Host 'Controlled kernel image acquisition passed: retained handle, module independence, native failure, empty/invalid image, exit/start change and identity mismatch rejection.'
}
function Test-RetirementParsing([string]$Source) {
    if(-not $Source){$Source=Get-Content (Join-Path $repository 'scripts\retire-companion.ps1') -Raw}
    $temporary=Join-Path ([IO.Path]::GetTempPath()) ('companion-retirement-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temporary|Out-Null
    $retirementCalls=[Collections.ArrayList]::new()
    # Preserve an array as one pipeline object, as ConvertFrom-Json does in PS5.
    function ConvertFrom-Json {
        param([Parameter(ValueFromPipeline=$true)][string]$InputObject)
        process{return ,(Microsoft.PowerShell.Utility\ConvertFrom-Json -InputObject $InputObject)}
    }
    function Start-Sleep { }
    try{
        [IO.File]::WriteAllText((Join-Path $temporary 'retire-companion.ps1'),$Source)
        [IO.File]::WriteAllText((Join-Path $temporary 'companion-runtime.ps1'),@'
function Stop-CompanionProcess($Record,[string]$Root) {
    if($Record -is [array]){throw 'Retirement received a nested identity array.'}
    if($null -ne $Record){$null=$retirementCalls.Add([string]$Record.id)}
}
'@)
        $jsonFile=Join-Path $temporary 'retire.json'
        foreach($case in @(
            @{json='[{"id":101},{"id":202}]';expected='101,202'},
            @{json='[{"id":101}]';expected='101'},
            @{json='[]';expected=''},
            @{json='null';expected=''},
            @{json='{broken';expected=''}
        )){
            $retirementCalls.Clear()
            [IO.File]::WriteAllText($jsonFile,$case.json)
            & (Join-Path $temporary 'retire-companion.ps1') -Record $jsonFile -Root $temporary
            if(($retirementCalls -join ',') -ne $case.expected){throw 'Retirement parsing did not visit the expected individual identities.'}
        }
        Write-Host 'Controlled PS5 retirement parsing passed: multiple/single/empty/null/malformed records; no processes opened or stopped.'
    }finally{Remove-Item -LiteralPath $temporary -Recurse -Force}
}
function Test-LauncherRecovery {
    if (Get-NetTCPConnection -State Listen -LocalPort 3000,8766 -ErrorAction SilentlyContinue) {
        throw 'Recovery fixtures need free ports 3000 and 8766. Stop the owned companion before running this check.'
    }
    $recoveryRoot = Join-Path ([IO.Path]::GetTempPath()) ('companion-recovery-'+[guid]::NewGuid().ToString('N'))
    $recoveryScripts = Join-Path $recoveryRoot 'scripts'
    $recoveryData = Join-Path $recoveryRoot 'data'
    $recoveryRecordFile = Join-Path $recoveryData 'processes.json'
    $recoveryStateFile = Join-Path $recoveryData 'companion-runtime.json'
    $node = (Get-Command node -ErrorAction Stop).Source
    $gatewayPython = (& $node --input-type=module -e "import {resolvePython} from './scripts/python-runtime.mjs'; console.log(resolvePython().command)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $gatewayPython)) { throw 'Recovery fixtures require the prepared project Python environment.' }
    $launchers = @()
    New-Item -ItemType Directory -Path $recoveryScripts,$recoveryData,(Join-Path $recoveryRoot 'dist\server') -Force | Out-Null
    foreach ($name in @('start-companion.ps1','update-companion.ps1','companion-runtime.ps1','companion-router.mjs')) {
        Copy-Item (Join-Path $repository ('scripts\'+$name)) (Join-Path $recoveryScripts $name)
    }
    New-Item -ItemType Directory -Path (Join-Path $recoveryRoot 'backend') -Force | Out-Null
    foreach ($name in @('__init__.py','desktop_gateway.py','local_access.py')) {
        Copy-Item (Join-Path $repository ('backend\'+$name)) (Join-Path $recoveryRoot ('backend\'+$name))
    }
    Save-CompanionJson (Join-Path $recoveryData 'fixture-python.json') @{python=$gatewayPython}
    [IO.File]::WriteAllText((Join-Path $recoveryRoot 'dist\server\wrangler.json'),'{}')
    # Real HTTP fixture processes retain session/capture state. An activation
    # refuses to run alongside any other live fixture capturer, including one
    # whose health/status endpoints have failed. No game or account is loaded.
    [IO.File]::WriteAllText((Join-Path $recoveryScripts 'service-fixture.mjs'),@'
import http from 'node:http';
import {appendFileSync,existsSync,readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {join} from 'node:path';
const [role,port,root,standby]=process.argv.slice(2),data=join(root,'data');
const own=join(data,`capture-${process.pid}.json`),events=join(data,'recovery-events.jsonl');
let running=role==='backend'&&standby!=='true',session='fixture-session';
const note=name=>appendFileSync(events,JSON.stringify({name,role,pid:process.pid})+'\n');
const publish=()=>{if(role==='backend')writeFileSync(own,JSON.stringify({running,pid:process.pid}));};
const alive=pid=>{try{process.kill(pid,0);return true;}catch{return false;}};
const others=()=>readdirSync(data).filter(x=>/^capture-\d+\.json$/.test(x)).map(x=>JSON.parse(readFileSync(join(data,x),'utf8'))).filter(x=>x.pid!==process.pid&&x.running&&alive(x.pid));
publish();note('started');
http.createServer(async(request,response)=>{
 let body='';for await(const chunk of request)body+=chunk;
 const send=(value,status=200)=>{response.writeHead(status,{'Content-Type':'application/json'});response.end(JSON.stringify(value));};
 let control={};try{control=JSON.parse(readFileSync(join(data,'failure.json'),'utf8'));}catch{}
 if(role==='frontend'){send({ok:true});return;}
 if(control.pid===process.pid&&(control.mode==='unresponsive'||request.url==='/api/health')){send({failed:true},503);return;}
 if(request.url==='/api/runtime/ready'){send({ready:true});return;}
 if(request.url==='/api/setup'){
  let setup={};try{setup=JSON.parse(readFileSync(join(data,'startup-policy.json'),'utf8'));}catch{}
  send({completed:setup.completed!==false,auto_start:setup.auto_start!==false});return;
 }
 if(request.url==='/api/runtime/quiesce'){
  const handoff={running,session_id:session};running=false;publish();note('quiesced');send(handoff);return;
 }
 if(request.url==='/api/runtime/activate'){
  const handoff=JSON.parse(body);if(handoff.running&&others().length){note('capture-overlap');send({overlap:true},409);return;}
  running=!!handoff.running;session=handoff.session_id||session;publish();note('activated');send({active:true});return;
 }
 send({status:'ok',capture:{running},session:{id:session}});
}).listen(Number(port),'127.0.0.1');
'@)
    # Only executable selection is adapted. Identity acquisition, ports, HTTP,
    # router, launcher, locks and process-tree termination are production code.
    Add-Content (Join-Path $recoveryScripts 'companion-runtime.ps1') @'
$script:FixtureNativeStart = ${function:Start-CompanionProcess}
$script:FixtureOwnedLookup = ${function:Get-CompanionOwnedProcess}
$script:FixtureSaveJson = ${function:Save-CompanionJson}
function Save-CompanionJson([string]$Path,$Value) {
    $controlFile = Join-Path (Split-Path $Path -Parent) 'commit-failure.json'
    if ([IO.Path]::GetFileName($Path) -eq 'processes.json' -and (Test-Path $controlFile)) {
        $control = Get-Content $controlFile -Raw | ConvertFrom-Json
        $candidate = $Value[$control.role]
        if ($candidate -and $candidate.id -ne $control.id) {
            if ($control.role -eq 'backend') {
                $events = Get-Content (Join-Path (Split-Path $Path -Parent) 'recovery-events.jsonl') | ForEach-Object { $_ | ConvertFrom-Json }
                if (-not ($events | Where-Object { $_.pid -eq $candidate.id -and $_.name -eq 'activated' })) { throw 'Commit failure fixture did not reach capture activation.' }
            }
            [IO.File]::WriteAllText((Join-Path (Split-Path $Path -Parent) 'commit-failure-armed.json'),($candidate|ConvertTo-Json -Depth 12))
            throw [IO.IOException]::new('CONTROLLED_RUNTIME_PUBLICATION_FAILURE')
        }
    }
    & $script:FixtureSaveJson $Path $Value
}
function Get-CompanionOwnedProcess($Record,[string]$Root) {
    $commitFailure = Join-Path $Root 'data\commit-failure-armed.json'
    if (Test-Path $commitFailure) {
        $lost = Get-Content $commitFailure -Raw | ConvertFrom-Json
        if ($Record.id -eq $lost.id) { return $null }
    }
    $controlFile = Join-Path $Root 'data\identity-failure.json'
    if ((Test-Path $controlFile) -and (Test-Path (Join-Path $Root 'data\identity-failure-armed'))) {
        $control = Get-Content $controlFile -Raw | ConvertFrom-Json
        if ($Record.id -eq $control.id) { return $null }
    }
    return & $script:FixtureOwnedLookup $Record $Root
}
function Start-CompanionProcess([string]$Executable,[string[]]$Arguments,[string]$Directory,[string]$Log,[switch]$LowPriority) {
    if ($Arguments -contains 'backend.desktop_gateway') {
        # Run the real gateway with prepared dependencies, including the fresh
        # installation case whose backend executable is deliberately synthetic.
        $Executable = [string](Get-Content (Join-Path $Directory 'data\fixture-python.json') -Raw | ConvertFrom-Json).python
    }
    $role = if ($Arguments -contains 'backend.main') {'backend'} elseif ($Arguments -contains 'dev') {'frontend'} else {''}
    if ($role) {
        $port = $Arguments[[Array]::IndexOf($Arguments,'--port')+1]
        $standby = ($Arguments -contains '--standby').ToString().ToLowerInvariant()
        $Executable = (Get-Command node -ErrorAction Stop).Source
        $Arguments = @((Join-Path $Directory 'scripts\service-fixture.mjs'),$role,$port,$Directory,$standby)
        if ($role -eq 'frontend') { Start-Sleep -Milliseconds 700 }
        if ($role -eq 'backend' -and $standby -eq 'true' -and (Test-Path (Join-Path $Directory 'data\identity-failure.json'))) {
            [IO.File]::WriteAllText((Join-Path $Directory 'data\identity-failure-armed'),'armed after initial ownership read')
        }
    }
    $process = & $script:FixtureNativeStart $Executable $Arguments $Directory $Log -LowPriority:$LowPriority
    $identity = New-CompanionProcessRecord $process $Directory
    # A PID can be reused later in this fixture. Bind its role to this exact
    # start-time/executable identity rather than to a historical event by PID.
    $identity.fixtureRole = $role
    Save-CompanionJson (Join-Path $Directory ('data\fixture-owned-'+$process.Id+'.json')) $identity
    return $process
}
'@
    . (Join-Path $recoveryScripts 'companion-runtime.ps1')
    function Read-RecoveryRecords { return Read-CompanionProcesses $recoveryRecordFile $recoveryRoot }
    function Read-RecoveryStatus { return Invoke-RestMethod 'http://127.0.0.1:8766/api/status' -TimeoutSec 3 }
    function Start-RecoveryLauncher {
        $process = Start-CompanionProcess $shell @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $recoveryScripts 'start-companion.ps1'),'-NoBrowser') $recoveryRoot (Join-Path $recoveryData ('launch-'+[guid]::NewGuid().ToString('N')))
        $script:recoveryLaunchers += ,$process
        return $process
    }
    function Complete-RecoveryLauncher($Process,[bool]$Reject=$false) {
        if (-not $Process.WaitForExit(60000)) { throw 'Recovery launcher timed out.' }
        if (($Reject -and $Process.ExitCode -eq 0) -or (-not $Reject -and $Process.ExitCode -ne 0)) {
            $logs = @(Get-ChildItem $recoveryData -Filter '*.err.log' | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"
            throw ('Recovery launcher returned an unexpected exit code: '+$Process.ExitCode+'. '+$logs)
        }
    }
    function Invoke-RecoveryLauncher { Complete-RecoveryLauncher (Start-RecoveryLauncher) }
    function Assert-RecoveryStable($Before,[string[]]$Names,[bool]$Running=$true) {
        $after = Read-RecoveryRecords
        foreach ($name in $Names) {
            if ($after[$name].id -ne $Before[$name].id -or $after[$name].started -ne $Before[$name].started) { throw ('Recovery unnecessarily replaced the healthy '+$name) }
        }
        $status = Read-RecoveryStatus
        if ([bool]$status.capture.running -ne $Running -or $status.session.id -ne 'fixture-session') { throw 'Recovery lost the healthy capture session.' }
    }
    $script:recoveryLaunchers = @()
    try {
        $slot = Start-CompanionSlot $recoveryRoot $recoveryRoot $gatewayPython
        Wait-CompanionService ('http://127.0.0.1:'+$slot.apiPort) $slot.processRecords.backend $recoveryRoot -Backend
        Wait-CompanionService ('http://127.0.0.1:'+$slot.frontendPort) $slot.processRecords.frontend $recoveryRoot
        Save-CompanionJson $recoveryStateFile @{version=1;active=$slot}
        $router = Start-CompanionRouter $recoveryRoot $recoveryRoot
        Save-CompanionJson $recoveryRecordFile @{backend=$slot.processRecords.backend;frontend=$slot.processRecords.frontend;router=(New-CompanionProcessRecord $router $recoveryRoot)}
        Wait-CompanionService 'http://127.0.0.1:3000' (New-CompanionProcessRecord $router $recoveryRoot) $recoveryRoot
        $before = Read-RecoveryRecords
        Invoke-RecoveryLauncher
        Assert-RecoveryStable $before @('backend','frontend','router')

        Stop-CompanionProcess $before.frontend $recoveryRoot
        Invoke-RecoveryLauncher
        Assert-RecoveryStable $before @('backend','router')
        $after = Read-RecoveryRecords
        if ($after.frontend.id -eq $before.frontend.id) { throw 'Crashed frontend was not replaced.' }
        Write-Host 'Frontend crash: healthy backend identity/session and router preserved.'

        $before = $after
        Stop-CompanionProcess $before.router $recoveryRoot
        Invoke-RecoveryLauncher
        Assert-RecoveryStable $before @('backend','frontend')
        Write-Host 'Router crash: healthy backend identity/session and frontend preserved.'

        $before = Read-RecoveryRecords
        Stop-CompanionProcess $before.backend $recoveryRoot
        Invoke-RecoveryLauncher
        Assert-RecoveryStable $before @('frontend','router')
        $after = Read-RecoveryRecords
        if ($after.backend.id -eq $before.backend.id) { throw 'Crashed backend was not replaced.' }
        Write-Host 'Backend crash: standby replacement activated without replacing frontend/router.'

        foreach ($mode in @('unhealthy','unresponsive')) {
            $before = Read-RecoveryRecords
            $old = Get-CompanionOwnedProcess $before.backend $recoveryRoot
            try {
                Save-CompanionJson (Join-Path $recoveryData 'failure.json') @{pid=$before.backend.id;mode=$mode}
                Invoke-RecoveryLauncher
                if (-not $old.WaitForExit(5000)) { throw 'Old unhealthy backend survived replacement activation.' }
                Assert-RecoveryStable $before @('frontend','router')
            } finally { $old.Dispose() }
        }
        Write-Host 'Unhealthy/unresponsive live backend: owned tree stopped before replacement capture; responsive handoff preserves session.'

        $before = Read-RecoveryRecords
        $old = Get-CompanionOwnedProcess $before.backend $recoveryRoot
        try {
            Save-CompanionJson (Join-Path $recoveryData 'failure.json') @{pid=$before.backend.id;mode='unresponsive'}
            Save-CompanionJson (Join-Path $recoveryData 'identity-failure.json') @{id=$before.backend.id}
            Complete-RecoveryLauncher (Start-RecoveryLauncher) $true
            Assert-Alive $old 'Capture handoff stopped a backend after its identity became unverifiable.'
        } finally {
            $old.Dispose()
            Remove-Item (Join-Path $recoveryData 'failure.json'),(Join-Path $recoveryData 'identity-failure.json'),(Join-Path $recoveryData 'identity-failure-armed') -ErrorAction SilentlyContinue
        }
        Assert-RecoveryStable $before @('backend','frontend','router')
        Write-Host 'Late identity acquisition failure: no candidate activation, original capturer retained.'

        # Failure after startup (including capture activation) must reap exact
        # owned processes even when a later identity query becomes unavailable.
        foreach ($failedRole in @('backend','frontend','router')) {
            $before = Read-RecoveryRecords
            Stop-CompanionProcess $before[$failedRole] $recoveryRoot
            Save-CompanionJson (Join-Path $recoveryData 'commit-failure.json') @{role=$failedRole;id=$before[$failedRole].id}
            try {
                Complete-RecoveryLauncher (Start-RecoveryLauncher) $true
                $armed = Join-Path $recoveryData 'commit-failure-armed.json'
                if (-not (Test-Path $armed)) { throw ('Publication fault did not reach the new '+$failedRole) }
                $candidate = Get-Content $armed -Raw | ConvertFrom-Json
                $survivor = & $script:FixtureOwnedLookup $candidate $recoveryRoot
                if ($survivor) {
                    $survivor.Dispose()
                    throw ('UNTRACKED_RUNTIME_PROCESS_SURVIVED_PUBLICATION_FAILURE: '+$failedRole)
                }
                $remaining = Read-RecoveryRecords
                foreach ($healthyRole in @('backend','frontend','router') | Where-Object { $_ -ne $failedRole }) {
                    if ($remaining[$healthyRole].id -ne $before[$healthyRole].id -or $remaining[$healthyRole].started -ne $before[$healthyRole].started) { throw ('Publication rollback replaced healthy '+$healthyRole) }
                }
            } finally {
                Remove-Item (Join-Path $recoveryData 'commit-failure.json'),(Join-Path $recoveryData 'commit-failure-armed.json') -ErrorAction SilentlyContinue
            }
            Invoke-RecoveryLauncher
            Assert-RecoveryStable $before (@('backend','frontend','router') | Where-Object { $_ -ne $failedRole })
        }
        Write-Host 'Post-start publication failures: activated backend, frontend and router reaped with exact owned handles despite identity lookup failure; healthy processes retained.'

        $before = Read-RecoveryRecords
        $foreign = Start-CompanionProcess $shell @('-NoProfile','-Command','Start-Sleep -Seconds 180') $recoveryRoot ''
        $foreignIdentity = New-CompanionProcessRecord $foreign $recoveryRoot
        $wrong = @{};foreach ($key in $foreignIdentity.Keys) { $wrong[$key] = $foreignIdentity[$key] }
        $wrong.started = ([long]$wrong.started-1).ToString()
        $badRecords = [ordered]@{backend=$wrong;frontend=$before.frontend;router=$before.router}
        Save-CompanionJson $recoveryRecordFile $badRecords
        Complete-RecoveryLauncher (Start-RecoveryLauncher) $true
        Assert-Alive $foreign 'Recovery stopped a foreign process from a stale PID record.'
        Save-CompanionJson (Join-Path $recoveryData 'failure.json') @{pid=$before.backend.id;mode='unresponsive'}
        Complete-RecoveryLauncher (Start-RecoveryLauncher) $true
        Assert-Alive $foreign 'Recovery stopped a foreign process while the real backend was unresponsive.'
        Remove-Item (Join-Path $recoveryData 'failure.json')
        Save-CompanionJson $recoveryRecordFile $before
        Assert-RecoveryStable $before @('backend','frontend','router')
        Write-Host 'Stale foreign PID record: launcher rejects reuse and leaves every real service and foreign fixture alive.'

        $before = Read-RecoveryRecords
        Stop-CompanionProcess $before.frontend $recoveryRoot
        $first = Start-RecoveryLauncher
        $second = Start-RecoveryLauncher
        Complete-RecoveryLauncher $first
        Complete-RecoveryLauncher $second
        Assert-RecoveryStable $before @('backend','router')
        # Reproduce a stale event after synthetic PID reuse without asking
        # Windows to recycle an actual PID. The healthy backend must not be
        # counted as a frontend merely because an old event has the same PID.
        $eventFile = Join-Path $recoveryData 'recovery-events.jsonl'
        Add-Content $eventFile (@{name='started';role='frontend';pid=$before.backend.id}|ConvertTo-Json -Compress)
        $liveFrontends = @(Get-ChildItem $recoveryData -Filter 'fixture-owned-*.json' | ForEach-Object {
            $identity = Get-Content $_.FullName -Raw | ConvertFrom-Json
            if ($identity.fixtureRole -eq 'frontend' -and (Test-CompanionProcess $identity $recoveryRoot)) { $identity }
        })
        if ($liveFrontends.Count -ne 1) { throw ('Expected one verified frontend after concurrent starts; found '+$liveFrontends.Count+'.') }
        $after = Read-RecoveryRecords
        if ($liveFrontends[0].id -ne $after.frontend.id -or $liveFrontends[0].started -ne $after.frontend.started) { throw 'The surviving frontend does not match the published process identity.' }
        Write-Host 'Concurrent launchers: a single frontend replacement; existing backend/capture preserved; synthetic stale frontend PID event ignored.'

        foreach ($policy in @(@{completed=$true;auto_start=$false},@{completed=$false;auto_start=$true})) {
            $before = Read-RecoveryRecords
            Stop-CompanionProcess $before.backend $recoveryRoot
            Save-CompanionJson (Join-Path $recoveryData 'startup-policy.json') $policy
            Invoke-RecoveryLauncher
            Assert-RecoveryStable $before @('frontend','router') $false
        }
        Write-Host 'Crash recovery respects disabled auto-start and unfinished setup.'

        # Exercise the no-state installation path with the same fixture process
        # adapter. Its placeholder executable is never executed by the adapter.
        $before = Read-RecoveryRecords
        foreach ($name in @('backend','frontend','router')) { Stop-CompanionProcess $before[$name] $recoveryRoot }
        Remove-Item $recoveryRecordFile,$recoveryStateFile
        $fixturePython = Join-Path $recoveryRoot 'Programs\Proxy Transcript\venv\Scripts'
        New-Item -ItemType Directory -Path $fixturePython -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $fixturePython 'python.exe'),'fixture placeholder')
        $previousAppData = $env:LOCALAPPDATA
        try { $env:LOCALAPPDATA = $recoveryRoot; Invoke-RecoveryLauncher }
        finally { $env:LOCALAPPDATA = $previousAppData }
        Assert-RecoveryStable (Read-RecoveryRecords) @('backend','frontend','router') $false
        Write-Host 'Fresh installation keeps capture off until setup is complete.'

        # Legacy direct-port installations also own their new frontend until
        # its identity is persisted. A failed publication must retain the backend.
        $before = Read-RecoveryRecords
        foreach ($name in @('backend','frontend','router')) { Stop-CompanionProcess $before[$name] $recoveryRoot }
        Remove-Item $recoveryRecordFile,$recoveryStateFile
        $directBackend = Start-CompanionBackend $recoveryRoot $recoveryRoot $node 8766
        Wait-CompanionService 'http://127.0.0.1:8766' $directBackend $recoveryRoot -Backend
        Save-CompanionJson $recoveryRecordFile @{backend=$directBackend}
        Save-CompanionJson (Join-Path $recoveryData 'commit-failure.json') @{role='frontend';id=0}
        try {
            Complete-RecoveryLauncher (Start-RecoveryLauncher) $true
            $armed = Join-Path $recoveryData 'commit-failure-armed.json'
            if (-not (Test-Path $armed)) { throw 'Direct frontend publication fault was not reached.' }
            $candidate = Get-Content $armed -Raw | ConvertFrom-Json
            $survivor = & $script:FixtureOwnedLookup $candidate $recoveryRoot
            if ($survivor) { $survivor.Dispose(); throw 'An untracked direct frontend survived publication failure.' }
            if (-not (Test-CompanionProcess $directBackend $recoveryRoot)) { throw 'Direct frontend rollback stopped the healthy backend.' }
        } finally {
            Remove-Item (Join-Path $recoveryData 'commit-failure.json'),(Join-Path $recoveryData 'commit-failure-armed.json') -ErrorAction SilentlyContinue
        }
        Invoke-RecoveryLauncher
        Assert-RecoveryStable @{backend=$directBackend} @('backend')
        Write-Host 'Direct-port frontend publication failure reaped the new process and preserved the healthy capture backend.'

        # The actual updater must wait for the same installation lock. An
        # intentionally invalid package stops it before preparation after release.
        [IO.File]::WriteAllText((Join-Path $recoveryRoot 'package.json'),'{"name":"lock-fixture"}')
        $operation = Enter-CompanionOperation $recoveryRoot
        try {
            $updater = Start-CompanionProcess $shell @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $recoveryScripts 'update-companion.ps1'),'-Root',$recoveryRoot,'-SourceRoot',$recoveryRoot) $recoveryRoot (Join-Path $recoveryData 'updater')
            $script:recoveryLaunchers += ,$updater
            Start-Sleep -Milliseconds 1200
            $updater.Refresh()
            if ($updater.HasExited) { throw 'Updater bypassed the shared installation operation lock.' }
        } finally { $operation.Dispose() }
        Complete-RecoveryLauncher $updater $true
        if ((Get-Content (Join-Path $recoveryData 'updater.err.log') -Raw) -notmatch 'Choose an extracted toolkit release') { throw 'Updater failed before testing the operation lock.' }
        $events = Get-Content (Join-Path $recoveryData 'recovery-events.jsonl') | ForEach-Object { $_ | ConvertFrom-Json }
        if ($events | Where-Object { $_.name -eq 'capture-overlap' }) { throw 'At least two fixture backends captured concurrently.' }
        Write-Host 'Start/update share one operation lock; no concurrent capture activation in any recovery scenario.'
    } catch {
        foreach ($log in @(Get-ChildItem $recoveryData -Recurse -Filter '*.err.log')) {
            $detail = Get-Content $log.FullName -Raw
            if ($detail) { Write-Host ($log.Name+': '+$detail) }
        }
        throw
    } finally {
        foreach ($process in $script:recoveryLaunchers) {
            try { Stop-CompanionProcessHandle $process } finally { $process.Dispose() }
        }
        foreach ($file in @(Get-ChildItem $recoveryData -Filter 'fixture-owned-*.json')) {
            $identity = Get-Content $file.FullName -Raw | ConvertFrom-Json
            Stop-CompanionProcess $identity $recoveryRoot
        }
        Remove-Item -LiteralPath $recoveryRoot -Recurse -Force
    }
}

if ($ImageFixturesOnly) { Test-ImageAcquisition; return }
if ($RetirementFixturesOnly) { Test-RetirementParsing; return }
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Process tree fixtures require Windows; no Windows verification was performed.' }
$clock = [Diagnostics.Stopwatch]::StartNew()
if ($VerifyBaseline) {
    $ErrorActionPreference = 'Continue'
    try { $output = & $shell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -BaselineRevision '7ae7e6991a6cc848334109720fb9ef608bca6999' 2>&1 | Out-String; $baselineExit=$LASTEXITCODE }
    finally { $ErrorActionPreference = 'Stop' }
    if ($baselineExit -eq 0 -or $output -notmatch 'UNVERIFIED_PID_WAS_STOPPED') { throw 'Baseline did not reproduce the expected unverified PID regression.' }
    Write-Host 'Baseline regression reproduced: a legacy PID-only record terminates an unrelated fixture without ownership evidence.'
}
if (-not $BaselineRevision) { Test-ImageAcquisition; Test-RetirementParsing }
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
        $details.executableMatches=((Get-CompanionProcessExecutable $observed) -eq [IO.Path]::GetFullPath([string]$Record.executable))
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
function New-FixtureRecord($Process,[string]$Stage) {
    try{return New-CompanionProcessRecord $Process $root}
    catch{throw ('Fixture identity capture failed at '+$Stage+': '+$_.Exception.Message)}
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
    if (-not $BaselineRevision) {
        $current=Get-Process -Id $PID
        try{
            $currentRecord=New-FixtureRecord $current 'native current process'
            Assert-FixtureIdentity $currentRecord 'native current process'
        }finally{$current.Dispose()}
        Write-Host 'Native current-process image identity captured and verified.'
    }
    $unrelated=Start-Fixture
    $valid=New-FixtureRecord $unrelated 'initial sleeper'
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
    $priorityRecord=New-FixtureRecord $priorityParent 'stale-parent sleeper'
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

    foreach($attempt in 1..4){
        $fresh=Start-Fixture
        $freshRecord=New-FixtureRecord $fresh ('fresh startup '+$attempt)
        Assert-FixtureIdentity $freshRecord ('fresh startup '+$attempt)
        $fresh.Kill();$fresh.WaitForExit()
    }
    Write-Host 'Four consecutive fresh Windows process identities captured and verified.'

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
    $exitedRecord=New-FixtureRecord $exited 'exit-no-op sleeper'
    $exited.Kill();$exited.WaitForExit()
    Save-CompanionJson $recordFile @{backend=$exitedRecord}
    Invoke-Stop
    Assert-Alive $unrelated 'Exited process record affected an unrelated fixture.'

    $owned=Start-Fixture
    $ownedRecord=New-FixtureRecord $owned 'owned-stop sleeper'
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
    $treeRecord=New-FixtureRecord $treeParent 'owned-tree parent'
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

    # Keep the original parent handle open after it exits; a surviving child is
    # still owned and must not escape rollback merely because the parent is gone.
    Remove-Item (Join-Path $root 'tree-0.json'),(Join-Path $root 'tree-1.json'),(Join-Path $root 'tree-2.json')
    $orphanArguments='-NoProfile -ExecutionPolicy Bypass -File "'+$treeScript+'" -Shell "'+$shell+'" -Root "'+$root+'" -Depth 1'
    $exitedParent=Start-Process $shell -ArgumentList $orphanArguments -PassThru -WindowStyle Hidden
    $null=$exitedParent.Handle
    $children+=,$exitedParent
    $null=New-FixtureRecord $exitedParent 'exiting owned parent'
    $childIdentityFile=Join-Path $root 'tree-0.json'
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    while(-not (Test-Path $childIdentityFile)){
        if([DateTime]::UtcNow -gt $deadline){throw 'Exited-parent child did not become ready.'}
        Start-Sleep -Milliseconds 50
    }
    $childIdentity=Get-Content $childIdentityFile -Raw|ConvertFrom-Json
    $orphan=Get-CompanionOwnedProcess $childIdentity $root
    if(-not $orphan){throw 'Exited-parent child identity was not verified.'}
    $children+=,$orphan
    $exitedParent.Kill();$exitedParent.WaitForExit()
    Assert-Alive $orphan 'The exited-parent fixture did not leave a live child.'
    Stop-CompanionProcessHandle $exitedParent
    if(-not $orphan.WaitForExit(10000)){throw 'A live owned child survived rollback after its retained parent exited.'}
    Assert-Alive $unrelated 'Exited-parent cleanup affected an unrelated fixture.'
    Write-Host 'Exited owned parent handle retained: surviving child terminated with verified native CIM parentage.'

    $retired=Start-Fixture
    $retireFile=Join-Path $data 'retire.json'
    Save-CompanionJson $retireFile @($wrongStart,(New-FixtureRecord $retired 'retirement sleeper'))
    function Start-Sleep { }
    try { & (Join-Path $scripts 'retire-companion.ps1') -Record $retireFile -Root $root }
    finally { Remove-Item Function:\Start-Sleep }
    if (-not $retired.WaitForExit(10000)) { throw 'Retirement did not stop its correctly identified fixture.' }
    Assert-Alive $unrelated 'Retirement stopped a fixture with the wrong start time.'

    Test-LauncherRecovery

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
