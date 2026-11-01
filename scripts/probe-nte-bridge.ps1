param([Parameter(Mandatory=$true)][string]$HelperRoot,
      [Parameter(Mandatory=$true)][string]$Dotnet,
      [Parameter(Mandatory=$true)][string]$EvidenceRoot)
$ErrorActionPreference='Stop'
$SourceRoot=Split-Path -Parent $PSScriptRoot
$reportPath=Join-Path $SourceRoot 'output/checks/r19-nte-bridge.json'
Remove-Item -LiteralPath $reportPath -Force -ErrorAction SilentlyContinue
$temporary=Join-Path $env:RUNNER_TEMP ('R19 NTE fixture space 漢字 '+[guid]::NewGuid())
$owned=[Collections.Generic.List[Diagnostics.Process]]::new()
$saved=@{}; foreach($name in @('PATH','DOTNET_ROOT','DOTNET_CLI_HOME','NUGET_PACKAGES')) {$saved[$name]=[Environment]::GetEnvironmentVariable($name)}
function Snapshot([string]$root) {
    return @(Get-ChildItem -LiteralPath $root -Recurse -Force | Sort-Object FullName | ForEach-Object {
        $name=[IO.Path]::GetRelativePath($root,$_.FullName).Replace('\','/')
        if($_.PSIsContainer){'directory:'+$name}else{'file:'+$name+':'+(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
    }) -join ','
}
function Invoke-Bridge([string[]]$Arguments,[string]$Request='{}') {
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName=Join-Path $script:application 'NteReader.exe'
    foreach($arg in $Arguments){$info.ArgumentList.Add($arg)}
    $info.WorkingDirectory=$temporary; $info.UseShellExecute=$false
    $info.RedirectStandardInput=$true; $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
    $info.StandardInputEncoding=[Text.UTF8Encoding]::new($false)
    $info.Environment.Clear()
    foreach($name in @('SystemRoot','WINDIR','TEMP','TMP')) {if([Environment]::GetEnvironmentVariable($name)){$info.Environment[$name]=[Environment]::GetEnvironmentVariable($name)}}
    $info.Environment['PATH']="$env:WINDIR/System32;$env:WINDIR"
    $info.Environment['DOTNET_ROOT']=Join-Path $temporary 'absent-system-dotnet'
    $info.Environment['DOTNET_MULTILEVEL_LOOKUP']='0'
    $process=[Diagnostics.Process]::Start($info); $owned.Add($process)
    $stdout=$process.StandardOutput.ReadToEndAsync(); $stderr=$process.StandardError.ReadToEndAsync()
    $process.StandardInput.WriteLine($Request); $process.StandardInput.Close()
    if(-not $process.WaitForExit(20000)){throw 'NTE bridge exceeded its owned process deadline.'}
    return @{code=$process.ExitCode;stdout=$stdout.GetAwaiter().GetResult();stderr=$stderr.GetAwaiter().GetResult()}
}
function Require-Code($result,[int]$expected) {if($result.code -ne $expected){throw 'NTE bridge fixture returned an unexpected exit code.'}}
function Request([string]$voice='Chinese') {return @{archive_metadata=('0x'+('0'*64));voice_language=$voice;locales=@('en','zh-CN','zh-Hant','ja','ko')}}
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $HelperRoot=(Resolve-Path -LiteralPath $HelperRoot).Path
    $Dotnet=(Resolve-Path -LiteralPath $Dotnet).Path
    $manifest=Get-Content -LiteralPath (Join-Path $HelperRoot 'helper-manifest.json') -Raw | ConvertFrom-Json
    if($manifest.kind -ne 'nte' -or $manifest.purpose -ne 'owned-bridge-only' -or $manifest.source_commit -ne $env:GITHUB_SHA -or $manifest.source_dirty -ne $false){throw 'Only a matching clean owned NTE bridge may enter this fixture.'}
    foreach($item in $manifest.files.PSObject.Properties){
        $path=Join-Path $HelperRoot $item.Name
        if((Get-Item -LiteralPath $path).Length -ne $item.Value.bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value.sha256){throw 'Owned NTE helper bytes differ from the build receipt.'}
    }
    $sdk=Split-Path $Dotnet
    $receipt=Get-Content -LiteralPath (Join-Path $HelperRoot 'build-receipt.json') -Raw | ConvertFrom-Json
    foreach($name in @('dotnet.exe','sdk/10.0.403/Roslyn/bincore/csc.dll','sdk/10.0.403/Microsoft.Build.dll')){
        if((Get-FileHash -LiteralPath (Join-Path $sdk $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $receipt.sdk_installed_files.$name){throw 'Fixture compiler differs from the verified SDK build input.'}
    }
    $env:DOTNET_ROOT=$sdk; $env:DOTNET_CLI_HOME=Join-Path $temporary 'cli'; $env:NUGET_PACKAGES=Join-Path $temporary 'packages'
    $config=Join-Path $temporary 'NuGet.Config'
    [IO.File]::WriteAllText($config,'<configuration><packageSources><clear/></packageSources></configuration>')
    $fixtures=Join-Path $SourceRoot 'packaging/game-readers/fixtures'
    $fixtureInputs=[ordered]@{}
    foreach($file in Get-ChildItem -LiteralPath $fixtures -File){$fixtureInputs[$file.Name]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    foreach($kind in @('Cue','Unreal')){
        $target=Join-Path $temporary ('compiled-'+$kind)
        $props=@('-p:DisableTransitiveFrameworkReferenceDownloads=true','-p:UseSharedCompilation=false','-p:NuGetAudit=false',('-p:BaseIntermediateOutputPath='+$temporary+'/'+$kind+'-obj/'),('-p:BaseOutputPath='+$temporary+'/'+$kind+'-bin/'),('-p:FixtureCueAssembly='+$temporary+'/compiled-Cue/CUE4Parse.dll'))
        & $Dotnet restore (Join-Path $fixtures ($kind+'Fixture.csproj')) --configfile $config @props --nologo > (Join-Path $temporary ($kind+'-restore.log')) 2>&1
        if($LASTEXITCODE -ne 0){throw 'Authored NTE fixture offline restore failed.'}
        & $Dotnet build (Join-Path $fixtures ($kind+'Fixture.csproj')) --no-restore -c Release -o $target @props '-p:DebugType=None' --nologo > (Join-Path $temporary ($kind+'-build.log')) 2>&1
        if($LASTEXITCODE -ne 0){throw 'Authored NTE reflection fixture did not compile; private logs remain on the build host.'}
    }
    $application=Join-Path $temporary 'Immutable app 漢字'
    $tools=Join-Path $temporary 'Authored tools'; $install=Join-Path $temporary 'Authored install'
    Copy-Item -LiteralPath $HelperRoot -Destination $application -Recurse
    New-Item -ItemType Directory -Path $tools,$install | Out-Null
    Copy-Item -LiteralPath (Join-Path $temporary 'compiled-Cue/CUE4Parse.dll'),(Join-Path $temporary 'compiled-Unreal/UEExtractor.dll') -Destination $tools
    [IO.File]::WriteAllText((Join-Path $install 'owned-fixture.json'),'[invalid]')
    $env:PATH="$env:WINDIR/System32;$env:WINDIR"
    $env:DOTNET_ROOT=Join-Path $temporary 'absent-system-dotnet'
    if(Get-Command dotnet,csc,msbuild,node,npm -ErrorAction SilentlyContinue){throw 'Developer tools remain discoverable.'}
    $identity=Invoke-Bridge @('--runtime-identity'); Require-Code $identity 0
    $identity=$identity.stdout | ConvertFrom-Json
    if($identity.runtime_version -ne '10.0.14' -or $identity.runtime_origin -ne 'app-local' -or $identity.corelib_sha256 -ne $manifest.files.'System.Private.CoreLib.dll'.sha256 -or $identity.game_execution_approved -ne $false){throw 'NTE app-local runtime identity differs.'}
    $request=Request
    Require-Code (Invoke-Bridge @('inventory',$install,$tools,(Join-Path $temporary 'bad-marker')) ($request | ConvertTo-Json -Compress)) 1
    [IO.File]::WriteAllText((Join-Path $install 'owned-fixture.json'),'{'+'"schema":"proxy-owned-nte-fixture-v1","localization_version":3}')
    $before=@{}; foreach($root in @($application,$tools,$install)){$before[$root]=Snapshot $root;Get-ChildItem -LiteralPath $root -File -Recurse | ForEach-Object {$_.IsReadOnly=$true}}
    $inventory=Join-Path $temporary 'inventory'
    Require-Code (Invoke-Bridge @('inventory',$install,$tools,$inventory) ($request | ConvertTo-Json -Compress)) 0
    if(@(Get-Content -LiteralPath (Join-Path $inventory 'inventory.json') -Raw | ConvertFrom-Json).Count -lt 100){throw 'Reflection inventory did not enumerate the authored provider.'}
    $texts=@{'en'='Owned NTE fixture';'zh-CN'='中文测试';'zh-Hant'='中文測試';'ja'='日本語テスト';'ko'='한국어 테스트'}
    foreach($voice in @('Chinese','English','Japanese','Korean')){
        $request=Request $voice; $destination=Join-Path $temporary ('index-'+$voice)
        Require-Code (Invoke-Bridge @('index',$install,$tools,$destination) ($request | ConvertTo-Json -Compress)) 0
        $rows=Get-Content -LiteralPath (Join-Path $destination 'localization.json') -Raw | ConvertFrom-Json
        foreach($locale in $texts.Keys){if(@($rows.$locale).Count -ne 1 -or $rows.$locale[0].value -ne $texts[$locale] -or $rows.$locale[0].key -ne 'owned01'){throw 'Actual NTE bridge changed the authored locale/identity.'}}
        if(@(Get-Content -LiteralPath (Join-Path $destination 'media.json') -Raw | ConvertFrom-Json).Count -ne 2 -or -not (Test-Path -LiteralPath (Join-Path $destination 'banks/Play_Vo_owned01.bnk'))){throw 'Actual NTE bridge lost authored bank/media bindings.'}
        $subtitles=Get-Content -LiteralPath (Join-Path $destination 'cinema-subtitles.json') -Raw | ConvertFrom-Json
        if(-not $subtitles.'HT/Content/SrtFile/FFMpeg/Story/owned.srt'.Contains('Owned subtitle')){throw 'Actual NTE bridge lost the authored cinematic subtitle.'}
        $request.depot="HT/Content/WwiseAudio/Media/$voice/42.wem"
        $single=Join-Path $temporary ('voice-'+$voice)
        Require-Code (Invoke-Bridge @('voice',$install,$tools,$single) ($request | ConvertTo-Json -Compress)) 0
        if([Convert]::ToHexString([IO.File]::ReadAllBytes((Join-Path $single 'voice.wem'))) -ne [Convert]::ToHexString([byte[]](0..255))){throw 'Actual NTE single voice bytes differ.'}
        $request.depots=@("HT/Content/WwiseAudio/Media/$voice/42.wem","HT/Content/WwiseAudio/Media/$voice/43.wem")
        $batch=Join-Path $temporary ('voices-'+$voice)
        Require-Code (Invoke-Bridge @('voices',$install,$tools,$batch) ($request | ConvertTo-Json -Compress)) 0
        if([Convert]::ToHexString([IO.File]::ReadAllBytes((Join-Path $batch '1.wem'))) -ne [Convert]::ToHexString([byte[]](255..0))){throw 'Actual NTE batch voice bytes differ.'}
    }
    foreach($destination in @($install,$tools,$application)) {Require-Code (Invoke-Bridge @('inventory',$install,$tools,$destination) ((Request) | ConvertTo-Json -Compress)) 1}
    $request=Request; $request.depot='../escape.wem'
    Require-Code (Invoke-Bridge @('voice',$install,$tools,(Join-Path $temporary 'bad-depot')) ($request | ConvertTo-Json -Compress)) 1
    $broken=Join-Path $temporary 'Missing dependency'; New-Item -ItemType Directory -Path $broken | Out-Null
    Copy-Item -LiteralPath (Join-Path $tools 'UEExtractor.dll') -Destination $broken
    Require-Code (Invoke-Bridge @('inventory',$install,$broken,(Join-Path $temporary 'missing-dependency')) ((Request) | ConvertTo-Json -Compress)) 1
    foreach($root in @($application,$tools,$install)){if((Snapshot $root) -cne $before[$root]){throw 'NTE bridge wrote to an immutable application, tool or install tree.'}}
    $unsupported=Join-Path $temporary 'Unsupported format'; New-Item -ItemType Directory -Path $unsupported | Out-Null
    [IO.File]::WriteAllText((Join-Path $unsupported 'owned-fixture.json'),'{'+'"schema":"proxy-owned-nte-fixture-v1","localization_version":4}')
    Require-Code (Invoke-Bridge @('index',$unsupported,$tools,(Join-Path $temporary 'unsupported-output')) ((Request) | ConvertTo-Json -Compress)) 3
    $report=@{schema='proxy-r19-nte-bridge-v1';source_commit=$env:GITHUB_SHA;source_dirty=$false;status='passed';helper_manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $application 'helper-manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant();fixture_inputs=$fixtureInputs;runtime_identity=$identity;actions=@('inventory','index','voice','voices');voice_languages=@('Chinese','English','Japanese','Korean');text_locales=@('en','zh-CN','zh-Hant','ja','ko');upstream_dependency='authored stand-ins; no actual UEExtractor/CUE4Parse/Oodle';immutable_trees='unchanged';developer_environment='cleared';malformed_and_missing_dependency='rejected';unsupported_localization='exit-3';real_games_accessed=$false;real_accounts_accessed=$false;native_windows_11_acceptance='unavailable';game_reader_acceptance='not-established';redistribution_review='pending-exact-output';installer='not-built';r19_complete=$false}
} finally {
    foreach($process in $owned){if(-not $process.HasExited){$process.Kill($true)};if(-not $process.WaitForExit(10000)){throw 'Owned NTE bridge process did not stop.'};$process.Dispose()}
    foreach($name in $saved.Keys){[Environment]::SetEnvironmentVariable($name,$saved[$name])}
    Get-ChildItem -LiteralPath $temporary -File -Recurse -Force | ForEach-Object {$_.IsReadOnly=$false}
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
New-Item -ItemType Directory -Path (Split-Path $reportPath) -Force | Out-Null
$report.owned_cleanup='passed';$report | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $reportPath -Encoding utf8
