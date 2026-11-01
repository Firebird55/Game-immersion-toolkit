param(
    [ValidateSet('probe','nte','endfield')][string]$Kind='probe',
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [Parameter(Mandatory=$true)][string]$Dotnet,
    [string]$ExpectedSdkVersion='10.0.403',
    [ValidateSet('win-x64','linux-x64','osx-arm64')][string]$RuntimeIdentifier='win-x64',
    [string]$Python='python',
    [switch]$BlockedQuarantine,
    [string]$PreparedRoot,
    [string]$BaseRef
)
$ErrorActionPreference='Stop'
if (($Kind -eq 'endfield') -ne [bool]$BlockedQuarantine) { throw 'Endfield can only be prebuilt in explicit unpublished quarantine; other owned helpers cannot use that profile.' }
$hostArchitecture=[Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString().ToLowerInvariant()
$hostOS=if($IsWindows){'win'}elseif($IsMacOS){'osx'}elseif($IsLinux){'linux'}else{'unsupported'}
if ($RuntimeIdentifier -ne ($hostOS+'-'+$hostArchitecture)) { throw 'Publish each helper on its matching native OS/architecture build host.' }
$platform=if($RuntimeIdentifier -eq 'osx-arm64'){'darwin-arm64'}else{$RuntimeIdentifier}
$extension=if($IsWindows){'.exe'}else{''}
$nativeFiles=if($IsWindows){@('hostfxr.dll','hostpolicy.dll','coreclr.dll')}elseif($IsMacOS){@('libhostfxr.dylib','libhostpolicy.dylib','libcoreclr.dylib')}else{@('libhostfxr.so','libhostpolicy.so','libcoreclr.so')}
if($Kind -eq 'endfield' -and $RuntimeIdentifier -ne 'win-x64'){throw 'The retired compiled Endfield experiment has no non-Windows resource contract; normal Endfield uses its Python reader.'}
$SourceRoot=Split-Path -Parent $PSScriptRoot
$PolicyRoot=Join-Path $SourceRoot 'packaging/game-readers'
$Pins=Get-Content -LiteralPath (Join-Path $PolicyRoot 'inputs.json') -Raw | ConvertFrom-Json
$selection=$Pins.targets.$RuntimeIdentifier
if(-not $selection){throw 'Missing exact native helper build inputs.'}
$sdkPin=$selection.sdk
$runtimePackages=@($selection.packages)
$upstreamInputs=$null
if($Kind -eq 'endfield') {
    $blocked=Get-Content -LiteralPath (Join-Path $PolicyRoot 'blocked-inputs.json') -Raw | ConvertFrom-Json
    $runtimePackages+=@($blocked.endfield.package)
}
if ($ExpectedSdkVersion -ne '10.0.403' -or $sdkPin.version -ne '10.0.403' -or $Pins.runtime_version -ne '10.0.14') { throw 'The exact reviewed SDK/runtime/RID selection changed.' }
function Assert-NoLinks([string]$Path) {
    $current=[IO.Path]::GetFullPath($Path)
    while ($current) {
        if ((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Helper inputs and outputs cannot use reparse points.' }
        $parent=[IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }; $current=$parent
    }
}
# Check the caller's raw path ancestry before Resolve-Path can erase a junction.
Assert-NoLinks $OutputRoot; Assert-NoLinks $EvidenceRoot; Assert-NoLinks $Dotnet
if($Kind -eq 'endfield') {
    if(-not $PreparedRoot) {throw 'Private Endfield source preparation is required.'}
    Assert-NoLinks $PreparedRoot
    $PreparedRoot=(Resolve-Path -LiteralPath $PreparedRoot).Path
    $selected=Get-Content -LiteralPath (Join-Path $SourceRoot 'scripts/endfield-reader-sources.json') -Raw | ConvertFrom-Json
    $upstreamInputs=[ordered]@{}
    foreach($item in $selected.files.PSObject.Properties) {
        $path=Join-Path $PreparedRoot ('source/'+$item.Name.Replace('AnimeStudio.Endfield/',''))
        Assert-NoLinks $path
        if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value){throw 'A selected private Endfield source differs from its pin.'}
        $upstreamInputs[$item.Name]=$item.Value
    }
    $actual=@(Get-ChildItem -LiteralPath (Join-Path $PreparedRoot 'source') -File -Recurse -Force)
    if($actual.Count -ne @($selected.files.PSObject.Properties).Count){throw 'The private Endfield subset contains an unlisted source.'}
    foreach($path in Get-ChildItem -LiteralPath $PreparedRoot -Recurse -Force){Assert-NoLinks $path.FullName}
    if((Get-FileHash -LiteralPath (Join-Path $PreparedRoot 'upstream-LICENSE.txt') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $blocked.endfield.license_sha256){throw 'Endfield notice differs from its exact source pin.'}
}
$Dotnet=(Resolve-Path -LiteralPath $Dotnet).Path
$EvidenceRoot=(Resolve-Path -LiteralPath $EvidenceRoot).Path
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw 'Choose a new helper output directory; existing candidates are retained.' }
Write-Host 'Checking build-host prerequisites before preparing the reader...'
if($BaseRef) { & npm --prefix $SourceRoot run dev:doctor -- --base $BaseRef }
else { & npm --prefix $SourceRoot run dev:doctor }
$doctorExit=$LASTEXITCODE
if ($doctorExit -notin @(0,2)) { throw 'Development preflight is invalid. No helper build was started.' }
Write-Host 'Verifying the exact SDK archive and expanded files...'
$archive=Join-Path $EvidenceRoot $sdkPin.artifact
if (-not (Test-Path -LiteralPath $archive) -or (Get-FileHash -LiteralPath $archive -Algorithm SHA512).Hash.ToLowerInvariant() -ne $sdkPin.sha512) { throw 'The exact official SDK archive is missing or has the wrong SHA-512.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
function Stream-Sha256($Stream) {
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Stream))).Replace('-','').ToLowerInvariant() } finally {$algorithm.Dispose()}
}
function Build-DiagnosticCodes([string]$Log) {
    # Never expose source excerpts, constant values or raw compiler messages.
    $codes=[regex]::Matches([IO.File]::ReadAllText($Log),'\berror\s+([A-Z]+\d+)') | ForEach-Object {$_.Groups[1].Value} | Sort-Object -Unique
    if($codes){Write-Host ('Private build diagnostic codes: '+($codes -join ','))}
}
function Assert-PortableLock($Value) {
    if($Value -is [string]) {
        if($Value -notmatch '^[A-Za-z0-9_.+/\[\](), *=\-]+$' -or $Value.StartsWith('/') -or $Value -match '(^|/)\.\.?(/|$)') { throw 'The restore lock contains a nonportable path or value.' }
    } elseif($Value -is [Collections.IDictionary]) {
        foreach($key in $Value.Keys) { Assert-PortableLock ([string]$key); Assert-PortableLock $Value[$key] }
    } elseif($Value -is [Collections.IEnumerable]) {
        foreach($item in $Value) { Assert-PortableLock $item }
    } elseif($null -ne $Value -and $Value -isnot [ValueType]) { throw 'The restore lock contains an unsupported value.' }
}
$sdkRoot=Split-Path -Parent $Dotnet
$sdkInventory=Join-Path $EvidenceRoot ('verified-sdk-'+[guid]::NewGuid().ToString('N')+'.json')
& $Python (Join-Path $PSScriptRoot 'verify-dotnet-sdk.py') --archive $archive --sdk-root $sdkRoot --pins (Join-Path $PolicyRoot 'inputs.json') --rid $RuntimeIdentifier --output $sdkInventory
if($LASTEXITCODE -ne 0){throw 'The expanded SDK differs from its exact archive; no build was started.'}
$verifiedSdk=Get-Content -LiteralPath $sdkInventory -Raw | ConvertFrom-Json -AsHashtable
$sdkFiles=$verifiedSdk.files
$sdkEntry=$verifiedSdk.dotnet
if((Get-FileHash -LiteralPath $Dotnet -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sdkFiles[$sdkEntry]){throw 'The selected dotnet executable is not the verified SDK archive executable.'}
$actualSource=(& git -C $SourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualSource -notmatch '^[0-9a-f]{40}$') { throw 'An exact source commit is required.' }
$sourceDirty=-not [string]::IsNullOrWhiteSpace((& git -C $SourceRoot status --porcelain | Out-String))
Write-Host 'SDK verified. Restoring pinned build packages and publishing the self-contained reader...'
$saved=@{}
foreach ($name in @('NUGET_PACKAGES','DOTNET_CLI_HOME','DOTNET_CLI_TELEMETRY_OPTOUT','DOTNET_SKIP_FIRST_TIME_EXPERIENCE','DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE','DOTNET_MULTILEVEL_LOOKUP')) { $saved[$name]=[Environment]::GetEnvironmentVariable($name) }
$feed=Join-Path $EvidenceRoot 'nuget-feed'
$intermediate=Join-Path $EvidenceRoot ('helper-build-'+$Kind+'-'+[guid]::NewGuid().ToString('N'))
$target=Join-Path $OutputRoot $Kind
$entry=if($Kind -eq 'probe'){'ToolkitReaderProbe'}elseif($Kind -eq 'nte'){'NteReader'}else{'EndfieldReader'}
$project=Join-Path $SourceRoot ('scripts/game-readers/'+$entry+'.csproj')
$ownedSource=Join-Path $SourceRoot ('scripts/game-readers/'+$entry+'.cs')
$sourcePaths=@($project,$ownedSource,(Join-Path $PolicyRoot 'inputs.json'),(Join-Path $PolicyRoot 'global.json'),(Join-Path $PSScriptRoot 'verify-dotnet-sdk.py'),$PSCommandPath)
if($Kind -eq 'endfield'){$sourcePaths+=@((Join-Path $PolicyRoot 'blocked-inputs.json'),(Join-Path $SourceRoot 'scripts/endfield-reader-sources.json'))}
$sourceInputs=[ordered]@{}
foreach($path in $sourcePaths) { $sourceInputs[[IO.Path]::GetRelativePath($SourceRoot,$path).Replace('\','/')]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
try {
    $env:NUGET_PACKAGES=Join-Path $EvidenceRoot 'nuget-cache'
    $env:DOTNET_CLI_HOME=Join-Path $EvidenceRoot 'cli-home'
    $env:DOTNET_CLI_TELEMETRY_OPTOUT='1'; $env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1'
    $env:DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='1'; $env:DOTNET_MULTILEVEL_LOOKUP='0'
    Push-Location -LiteralPath $PolicyRoot
    try { $version=(& $Dotnet --version).Trim(); if($LASTEXITCODE -ne 0 -or $version -ne $ExpectedSdkVersion) { throw 'The selected build-host SDK does not match its exact pin.' } }
    finally { Pop-Location }
    New-Item -ItemType Directory -Path $feed,$intermediate -Force | Out-Null
    foreach ($package in $runtimePackages) {
        $path=Join-Path $feed $package.artifact
        Assert-NoLinks $path
        if (-not (Test-Path -LiteralPath $path)) {
            # Explicit BUILD-HOST acquisition only. End-user execution never
            # invokes this script, dotnet restore, NuGet or any source compiler.
            Invoke-WebRequest -Uri $package.source -OutFile ($path+'.pending')
            Move-Item -LiteralPath ($path+'.pending') -Destination $path
        }
        $stream=[IO.File]::OpenRead($path); $algorithm=[Security.Cryptography.SHA512]::Create()
        try { $hash=[Convert]::ToBase64String($algorithm.ComputeHash($stream)) } finally { $stream.Dispose(); $algorithm.Dispose() }
        if ($hash -ne $package.sha512_base64) { throw 'A pinned runtime/apphost NuGet package failed SHA-512 verification.' }
    }
    $config=Join-Path $intermediate 'NuGet.Config'
    $escaped=[Security.SecurityElement]::Escape($feed)
    [IO.File]::WriteAllText($config, '<configuration><packageSources><clear/><add key="pinned-local" value="'+$escaped+'"/></packageSources></configuration>', [Text.UTF8Encoding]::new($false))
    $obj=Join-Path $intermediate 'obj'
    $bin=Join-Path $intermediate 'bin'
    $lock=Join-Path $intermediate 'packages.lock.json'
    # These owned console projects reference only Microsoft.NETCore.App. The
    # SDK otherwise prefetches optional desktop/web packs for possible transitive
    # references; keep the offline feed closed to the two reviewed packages.
    # https://learn.microsoft.com/dotnet/core/project-sdk/msbuild-props#disabletransitiveframeworkreferencedownloads
    # Keep ordinary compile output out of the checkout and avoid a shared
    # VBCSCompiler process surviving this owned build-host invocation.
    $properties=@('-p:RuntimeFrameworkVersion=10.0.14','-p:TargetLatestRuntimePatch=false','-p:SelfContained=true','-p:UseAppHost=true','-p:DisableTransitiveFrameworkReferenceDownloads=true','-p:UseSharedCompilation=false','-p:NuGetAudit=false',('-p:BaseIntermediateOutputPath='+$obj+'/'),('-p:BaseOutputPath='+$bin+'/'),('-p:NuGetLockFilePath='+$lock),'-p:RestorePackagesWithLockFile=true')
    if($Kind -eq 'endfield'){$properties+=('-p:EndfieldSource='+(Join-Path $PreparedRoot 'source'))}
    Push-Location -LiteralPath $PolicyRoot
    try {
        & $Dotnet restore $project --runtime $RuntimeIdentifier --configfile $config @properties --nologo > (Join-Path $intermediate 'restore.log') 2>&1
        if ($LASTEXITCODE -ne 0) { Build-DiagnosticCodes (Join-Path $intermediate 'restore.log'); throw 'Offline pinned helper restore failed; no implicit source feed is allowed.' }
        & $Dotnet restore $project --runtime $RuntimeIdentifier --configfile $config @properties --locked-mode --nologo > (Join-Path $intermediate 'locked-restore.log') 2>&1
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $lock)) { throw 'The exact helper restore lock could not be replayed.' }
        & $Dotnet publish $project --no-restore --runtime $RuntimeIdentifier --self-contained true -c Release -o $target @properties '-p:PublishSingleFile=false' '-p:PublishTrimmed=false' '-p:DebugType=None' '-p:DebugSymbols=false' '-p:ContinuousIntegrationBuild=true' --nologo > (Join-Path $intermediate 'publish.log') 2>&1
        if ($LASTEXITCODE -ne 0) { Build-DiagnosticCodes (Join-Path $intermediate 'publish.log'); throw 'Self-contained helper publication failed; quarantined output is retained.' }
    } finally { Pop-Location }
    $ownedFiles=@($extension,'.dll','.runtimeconfig.json','.deps.json') | ForEach-Object {$entry+$_}
    foreach($required in (@($ownedFiles)+@('System.Private.CoreLib.dll')+$nativeFiles)) {
        if(-not (Test-Path -LiteralPath (Join-Path $target $required))) { throw 'A required self-contained runtime file is missing.' }
    }
    $runtime=Get-Content -LiteralPath (Join-Path $target ($entry+'.runtimeconfig.json')) -Raw | ConvertFrom-Json
    if (@($runtime.runtimeOptions.includedFrameworks | Where-Object {$_.name -eq 'Microsoft.NETCore.App' -and $_.version -eq '10.0.14'}).Count -ne 1 -or $runtime.runtimeOptions.framework -or $runtime.runtimeOptions.frameworks) { throw 'The helper unexpectedly depends on a machine-installed shared framework.' }
    if($Kind -eq 'probe') { [IO.File]::WriteAllText((Join-Path $target 'probe-resource.txt'), "R19 authored self-contained reader probe.`n", [Text.UTF8Encoding]::new($false)) }
    # Retain the exact replayed lock only after checking every JSON key/value
    # excludes absolute/private paths. project.assets.json is never collected.
    Assert-PortableLock (Get-Content -LiteralPath $lock -Raw | ConvertFrom-Json -AsHashtable)
    Copy-Item -LiteralPath $lock -Destination (Join-Path $target 'restore-lock.json')
    $notices=Join-Path $target 'notices'; New-Item -ItemType Directory -Path $notices | Out-Null
    Copy-Item -LiteralPath (Join-Path $SourceRoot 'LICENSE') -Destination (Join-Path $notices 'PROJECT-LICENSE.txt')
    if($Kind -eq 'endfield'){Copy-Item -LiteralPath (Join-Path $PreparedRoot 'upstream-LICENSE.txt') -Destination (Join-Path $notices 'ENDFIELDSTUDIO-LICENSE.txt')}
    foreach ($name in @('LICENSE.txt','ThirdPartyNotices.txt')) {
        $matching=@($sdkFiles.Keys | Where-Object {$_ -notmatch '/' -and $_ -ieq $name})
        if($matching.Count -ne 1) { throw 'The original SDK archive must contain one full license and third-party notice.' }
        $path=Join-Path $sdkRoot $matching[0]
        Assert-NoLinks $path
        if(-not (Test-Path -LiteralPath $path)) { throw 'The provisioned SDK full license/third-party notices are missing.' }
        Copy-Item -LiteralPath $path -Destination (Join-Path $notices ('sdk-'+$name))
    }
    $packageFiles=[ordered]@{}
    foreach($package in $runtimePackages) {
        $zip=[IO.Compression.ZipFile]::OpenRead((Join-Path $feed $package.artifact))
        try {
            $found=0
            foreach($member in $zip.Entries) {
                if(-not $member.FullName.EndsWith('/')) {
                    $stream=$member.Open(); try {$memberHash=Stream-Sha256 $stream} finally {$stream.Dispose()}
                    $packageFiles[$package.name+'/'+$member.FullName]=$memberHash
                }
                if($member.FullName -match '(?i)(^|/)(LICENSE[^/]*|COPYING[^/]*|NOTICE[^/]*|THIRD[-_]?PARTY[-_]?NOTICES[^/]*)$') {
                    if($member.FullName.Contains('..') -or $member.FullName.Contains('\')) { throw 'Unsafe package notice path.' }
                    $destination=Join-Path $notices ($package.name+'/'+$member.FullName)
                    New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
                    [IO.Compression.ZipFileExtensions]::ExtractToFile($member,$destination,$false); $found++
                }
            }
            if($found -eq 0) { throw 'A runtime/apphost package has no complete retained notice evidence.' }
        } finally { $zip.Dispose() }
    }
    foreach($path in $sourcePaths) {if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceInputs[[IO.Path]::GetRelativePath($SourceRoot,$path).Replace('\','/')]) {throw 'Helper source changed during publication.'}}
    if((& git -C $SourceRoot rev-parse HEAD).Trim() -ne $actualSource) {throw 'The source commit changed during helper publication.'}
    if($Kind -eq 'endfield') {
        foreach($item in $selected.files.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $PreparedRoot ('source/'+$item.Name.Replace('AnimeStudio.Endfield/',''))) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value){throw 'A selected upstream source changed during private publication.'}}
    }
    $receipt=[ordered]@{schema='proxy-dotnet-helper-build-receipt-v1';source_commit=$actualSource;source_dirty=$sourceDirty;source_inputs=$sourceInputs;sdk=$sdkPin;sdk_version=$version;runtime_version='10.0.14';sdk_installed_files=$sdkFiles;runtime_packages=$runtimePackages;runtime_package_files=$packageFiles;restore_lock_sha256=(Get-FileHash -LiteralPath $lock -Algorithm SHA256).Hash.ToLowerInvariant();dotnet_executable_sha256=(Get-FileHash -LiteralPath $Dotnet -Algorithm SHA256).Hash.ToLowerInvariant()}
    if($Kind -eq 'endfield'){$receipt.upstream_source_inputs=$upstreamInputs}
    [IO.File]::WriteAllText((Join-Path $target 'build-receipt.json'),(ConvertTo-Json -InputObject $receipt -Depth 20)+"`n",[Text.UTF8Encoding]::new($false))
    # Every shipped framework/native file must match an exact pinned package
    # member. The owned assembly/apphost/config and notices have separate owners.
    foreach($path in @(Get-ChildItem -LiteralPath $target -File)) {
        if($path.Name -in (@($ownedFiles)+@('probe-resource.txt','build-receipt.json','restore-lock.json'))) {continue}
        $hash=(Get-FileHash -LiteralPath $path.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if(-not @($packageFiles.Values | Where-Object {$_ -eq $hash}).Count) {throw 'A collected runtime file is not part of either pinned runtime/apphost package.'}
    }
    $files=[ordered]@{}
    foreach($path in @(Get-ChildItem -LiteralPath $target -Recurse -File | Sort-Object FullName)) {
        Assert-NoLinks $path.FullName
        $name=[IO.Path]::GetRelativePath($target,$path.FullName).Replace('\','/')
        if($name -match '(?i)\.(pdb|cs|dpapi|db|onnx|pak|pck|wem|bnk)$' -or $name -match '(?i)(^|/)(UEExtractor|oodle|Keys\.cs)' -or $name -match '(^|/)\.\.?(/|$)') { throw 'Unreviewed/private content reached the owned helper output.' }
        $files[$name]=[ordered]@{bytes=$path.Length;sha256=(Get-FileHash -LiteralPath $path.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $canonicalFiles=[ordered]@{}
    [string[]]$orderedNames=@($files.Keys); [Array]::Sort($orderedNames,[StringComparer]::Ordinal)
    foreach($name in $orderedNames) { $canonicalFiles[$name]=[ordered]@{bytes=$files[$name].bytes;sha256=$files[$name].sha256} }
    $json=ConvertTo-Json -InputObject $canonicalFiles -Depth 8 -Compress
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try {$buildId=([BitConverter]::ToString($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($json)))).Replace('-','').ToLowerInvariant()} finally {$algorithm.Dispose()}
    $manifest=[ordered]@{schema='proxy-prebuilt-dotnet-reader-v1';kind=$Kind;entry=($entry+$extension);platform=$platform;sdk_version=$version;runtime_version='10.0.14';source_commit=$actualSource;source_dirty=$sourceDirty;purpose=$(if($Kind -eq 'probe'){'authored-probe-only'}else{'owned-bridge-only'});source_inputs=$sourceInputs;build_id=$buildId;files=$canonicalFiles;sdk_archive=$sdkPin;runtime_packages=$runtimePackages;restore_lock_sha256=(Get-FileHash -LiteralPath $lock -Algorithm SHA256).Hash.ToLowerInvariant();dotnet_executable_sha256=(Get-FileHash -LiteralPath $Dotnet -Algorithm SHA256).Hash.ToLowerInvariant();redistribution_review='pending-exact-output';game_reader_acceptance='not-established';r19_complete=$false;doctor_exit=$doctorExit}
    $manifestName='helper-manifest.json'
    if($Kind -eq 'endfield') {
        $manifest.schema='proxy-blocked-game-helper-v1';$manifest.purpose='blocked-private-game-reader'
        $manifest.Remove('entry');$manifest.runtime_entrypoints=@();$manifest.runtime_collection_allowed=$false
        $manifest.upstream_source_inputs=$upstreamInputs;$manifest.gate=$blocked.endfield.gate
        $manifestName='blocked-manifest.json'
    }
    [IO.File]::WriteAllText((Join-Path $target $manifestName),(ConvertTo-Json -InputObject $manifest -Depth 20)+"`n",[Text.UTF8Encoding]::new($false))
    Write-Host ('Self-contained owned helper created for '+$platform+'; final resource review and native candidate acceptance remain pending.')
} finally {
    foreach($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name,$saved[$name]) }
}
