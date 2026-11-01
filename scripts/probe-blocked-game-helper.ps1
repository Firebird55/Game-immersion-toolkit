param([Parameter(Mandatory=$true)][ValidateSet('endfield','pragmata')][string]$Kind,
      [Parameter(Mandatory=$true)][string]$HelperRoot,
      [Parameter(Mandatory=$true)][string]$FixtureRoot)
$ErrorActionPreference='Stop'
$reportPath=Join-Path $env:GITHUB_WORKSPACE ('output/checks/r19-blocked-'+$Kind+'.json')
Remove-Item -LiteralPath $reportPath -Force -ErrorAction SilentlyContinue
$temporary=Join-Path $env:RUNNER_TEMP ('R19 blocked helper space 漢字 '+[guid]::NewGuid())
$owned=[Collections.Generic.List[Diagnostics.Process]]::new()
function Snapshot([string]$root){return @(Get-ChildItem -LiteralPath $root -Recurse -Force | Sort-Object FullName | ForEach-Object {$name=[IO.Path]::GetRelativePath($root,$_.FullName).Replace('\','/');if($_.PSIsContainer){'directory:'+$name}else{'file:'+$name+':'+(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}}) -join ','}
function Invoke-Owned([string[]]$Arguments,[string]$Request='{}'){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=Join-Path $script:app $(if($Kind -eq 'endfield'){'EndfieldReader.exe'}else{'Toolkit.REE.Selective.exe'})
    foreach($arg in $Arguments){$info.ArgumentList.Add($arg)}
    $info.WorkingDirectory=$temporary;$info.UseShellExecute=$false
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $info.Environment.Clear()
    foreach($name in @('SystemRoot','WINDIR','TEMP','TMP')){if([Environment]::GetEnvironmentVariable($name)){$info.Environment[$name]=[Environment]::GetEnvironmentVariable($name)}}
    $info.Environment['PATH']="$env:WINDIR/System32;$env:WINDIR"
    $info.Environment['DOTNET_ROOT']=Join-Path $temporary 'absent-dotnet'
    $info.Environment['DOTNET_MULTILEVEL_LOOKUP']='0'
    $info.Environment['PROXY_TRANSCRIPT_REE_PROJECTS']=Join-Path $script:fixture 'projects'
    $process=[Diagnostics.Process]::Start($info);$owned.Add($process)
    $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
    $process.StandardInput.WriteLine($Request);$process.StandardInput.Close()
    if(-not $process.WaitForExit(30000)){throw 'Private helper exceeded its owned deadline.'}
    return @{code=$process.ExitCode;stdout=$stdout.GetAwaiter().GetResult();stderr=$stderr.GetAwaiter().GetResult()}
}
New-Item -ItemType Directory -Path $temporary | Out-Null
try{
    $manifestPath=Join-Path $HelperRoot 'blocked-manifest.json'
    $manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if($manifest.schema -ne 'proxy-blocked-game-helper-v1' -or $manifest.kind -ne $Kind -or $manifest.source_commit -ne $env:GITHUB_SHA -or $manifest.source_dirty -ne $false -or $manifest.runtime_collection_allowed -ne $false -or @($manifest.runtime_entrypoints).Count -ne 0){throw 'Only a matching explicitly blocked private helper may enter this probe.'}
    foreach($root in @($HelperRoot,$FixtureRoot)){
        $path=[IO.Path]::GetFullPath($root)
        while($path){if((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Private helper inputs cannot follow reparse points.'};$path=[IO.Path]::GetDirectoryName($path)}
        if(@(Get-ChildItem -LiteralPath $root -Recurse -Force | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'Private helper inputs contain reparse points.'}
    }
    foreach($item in $manifest.files.PSObject.Properties){$file=Get-Item -LiteralPath (Join-Path $HelperRoot $item.Name);if($file.Length -ne $item.Value.bytes -or (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value.sha256){throw 'Private helper bytes differ from the blocked inventory.'}}
    if(@(Get-ChildItem -LiteralPath $HelperRoot -File -Recurse).Count -ne @($manifest.files.PSObject.Properties).Count+1){throw 'Private helper contains unlisted files.'}
    $app=Join-Path $temporary 'Immutable reader 漢字';$fixture=Join-Path $temporary 'Owned input 漢字'
    Copy-Item -LiteralPath $HelperRoot -Destination $app -Recurse
    Copy-Item -LiteralPath $FixtureRoot -Destination $fixture -Recurse
    $beforeApp=Snapshot $app;$beforeFixture=Snapshot $fixture
    foreach($root in @($app,$fixture)){Get-ChildItem -LiteralPath $root -File -Recurse | ForEach-Object {$_.IsReadOnly=$true}}
    $identity=$null
    if($Kind -eq 'endfield'){
        $result=Invoke-Owned @('--runtime-identity')
        if($result.code -ne 0){throw 'Blocked Endfield app-local runtime could not start.'}
        $identity=$result.stdout | ConvertFrom-Json
        if($identity.runtime_origin -ne 'app-local' -or $identity.runtime_version -ne '10.0.14' -or $identity.game_execution_approved -ne $false -or $identity.corelib_sha256 -ne $manifest.files.'System.Private.CoreLib.dll'.sha256 -or $identity.hashing_sha256 -ne $manifest.files.'System.IO.Hashing.dll'.sha256){throw 'Blocked Endfield runtime/package identity differs.'}
        foreach($voice in @('chinese','english','japanese','korean')){
            $result=Invoke-Owned @('inventory',(Join-Path $fixture 'endfield/StreamingAssets')) (@{language=$voice} | ConvertTo-Json -Compress)
            if($result.code -ne 0 -or $result.stdout.Trim() -ne '[]'){throw 'Blocked Endfield missing-pack fixture did not remain empty.'}
        }
        $result=Invoke-Owned @('voice',(Join-Path $fixture 'endfield/StreamingAssets')) '{"language":"english","block":0,"chunk":"owned","file_hash":"0","file_id":"0"}'
        if($result.code -eq 0){throw 'Blocked Endfield invented an absent voice.'}
        $result=Invoke-Owned @('inventory',(Join-Path $fixture 'endfield/StreamingAssets')) '{}'
        if($result.code -eq 0){throw 'Blocked Endfield accepted an incomplete request.'}
        $scope='actual selected reader; app-local runtime and hashing; empty-pack/malformed-input probes only'
    }else{
        $binary=[IO.File]::ReadAllBytes((Join-Path $app 'Toolkit.REE.Selective.exe'));$pe=[BitConverter]::ToInt32($binary,60)
        if([BitConverter]::ToUInt16($binary,$pe+4) -ne 0x14c -or [BitConverter]::ToUInt16($binary,$pe+24) -ne 0x10b){throw 'Selective reader is not its declared x86 image.'}
        $output=Join-Path $temporary 'selected-output'
        $result=Invoke-Owned @('Owned',(Join-Path $fixture 'owned.pak'),$output)
        if($result.code -ne 0){
            # Exception class/method names are useful without disclosing input,
            # paths, source excerpts, messages or embedded constants.
            $types=[regex]::Matches($result.stderr,'\b[A-Za-z][A-Za-z0-9_.]+Exception\b') | ForEach-Object {$_.Value} | Sort-Object -Unique
            $frames=[regex]::Matches($result.stderr,'\bat ([A-Za-z][A-Za-z0-9_+.`]+)\(') | ForEach-Object {$_.Groups[1].Value} | Select-Object -First 12
            Write-Host (@{exit_code=$result.code;exception_types=@($types);methods=@($frames)} | ConvertTo-Json -Compress)
            throw 'Precompiled selective reader did not extract the authored PAK.'
        }
        $expected=Get-Content -LiteralPath (Join-Path $fixture 'expected.json') -Raw | ConvertFrom-Json
        if((Get-FileHash -LiteralPath (Join-Path $output $expected.selected) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.selected_sha256 -or (Test-Path -LiteralPath (Join-Path $output $expected.unselected)) -or @(Get-ChildItem -LiteralPath $output -File -Recurse).Count -ne 1){throw 'Precompiled selective reader lost bytes or extracted an unrequested asset.'}
        $result=Invoke-Owned @('Owned',(Join-Path $fixture 'oversized.pak'),(Join-Path $temporary 'oversized-output'))
        if($result.code -eq 0){throw 'Precompiled selective reader accepted an oversized table.'}
        $scope='actual selective x86 reader; authored uncompressed PAK selection and oversized-table rejection only'
    }
    if((Snapshot $app) -cne $beforeApp -or (Snapshot $fixture) -cne $beforeFixture){throw 'Private helper wrote to immutable application or authored input trees.'}
    $report=@{schema='proxy-r19-blocked-game-helper-probe-v1';source_commit=$env:GITHUB_SHA;source_dirty=$false;kind=$Kind;status='passed';scope=$scope;runtime_identity=$identity;manifest_sha256=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant();platform=$manifest.platform;files=@($manifest.files.PSObject.Properties).Count;developer_environment='cleared; no inherited loader/account variables';immutable_trees='unchanged';runtime_collection_allowed=$false;game_execution_approved=$false;unreviewed_source_material_in_private_binary=$true;embedded_constants_review='open';redistribution_review='not-established';native_windows_11_acceptance='unavailable';real_games_accessed=$false;real_accounts_accessed=$false;installer='not-built';r19_complete=$false}
}finally{
    foreach($process in $owned){if(-not $process.HasExited){$process.Kill($true)};if(-not $process.WaitForExit(10000)){throw 'Owned private helper process did not stop.'};$process.Dispose()}
    Get-ChildItem -LiteralPath $temporary -File -Recurse -Force | ForEach-Object {$_.IsReadOnly=$false}
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
New-Item -ItemType Directory -Path (Split-Path $reportPath) -Force | Out-Null
$report.owned_cleanup='passed';$report | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $reportPath -Encoding utf8
