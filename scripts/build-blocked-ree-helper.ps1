param([Parameter(Mandatory=$true)][string]$PreparedRoot,
      [Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference='Stop'
if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT){throw 'The private selective reader build requires Windows.'}
function No-Links([string]$path){
    while($path){if((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Private reader inputs cannot follow links/reparse points.'};$path=[IO.Path]::GetDirectoryName($path)}
}
No-Links ([IO.Path]::GetFullPath($PreparedRoot));No-Links ([IO.Path]::GetFullPath($OutputRoot))
$PreparedRoot=(Resolve-Path -LiteralPath $PreparedRoot).Path
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
if(Test-Path -LiteralPath $OutputRoot){throw 'Choose a new private reader output; existing artifacts are preserved.'}
$SourceRoot=Split-Path -Parent $PSScriptRoot
$prepared=Get-Content -LiteralPath (Join-Path $PreparedRoot 'prepared-inputs.json') -Raw | ConvertFrom-Json
if($prepared.schema -ne 'proxy-blocked-helper-preparation-v1' -or $prepared.kind -ne 'pragmata' -or $prepared.runtime_collection_allowed -ne $false){throw 'Only separately blocked selective-reader inputs may enter this build.'}
$sources=@(Get-ChildItem -LiteralPath (Join-Path $PreparedRoot 'source') -File -Recurse)
if($sources.Count -ne 17 -or @($prepared.prepared_sources.PSObject.Properties).Count -ne 17){throw 'The selected reader source set differs.'}
foreach($path in Get-ChildItem -LiteralPath $PreparedRoot -Recurse -Force){No-Links $path.FullName}
foreach($item in $prepared.prepared_sources.PSObject.Properties){
    $file=Join-Path $PreparedRoot ('source/'+$item.Name)
    if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value){throw 'A prepared selective-reader source changed before compilation.'}
}
$compiler=Join-Path $env:WINDIR 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
if(-not(Test-Path -LiteralPath $compiler)){throw 'The BUILD HOST needs its Windows Framework compiler; no end-user compiler is used.'}
$signature=Get-AuthenticodeSignature -LiteralPath $compiler
if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft'){throw 'The build-host Framework compiler publisher could not be verified.'}
$commit=(& git -C $SourceRoot rev-parse HEAD).Trim()
$dirty=-not [string]::IsNullOrWhiteSpace((& git -C $SourceRoot status --porcelain | Out-String))
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
foreach($name in @('Zstandard.Net.dll','System.Buffers.dll','libzstd.dll','REE.Unpacker.exe.config')){
    $path=Join-Path $PreparedRoot $name
    if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $prepared.source_inputs.('runtime/'+$name)){throw 'A selective-reader reference/native binary differs.'}
    $destination=if($name -eq 'REE.Unpacker.exe.config'){Join-Path $OutputRoot 'Toolkit.REE.Selective.exe.config'}else{Join-Path $OutputRoot $name}
    Copy-Item -LiteralPath $path -Destination $destination
}
$binary=Join-Path $OutputRoot 'Toolkit.REE.Selective.exe'
$arguments=@('/nologo','/target:exe','/platform:x86','/optimize+','/debug-',('/out:'+$binary),'/reference:System.Numerics.dll',('/reference:'+(Join-Path $OutputRoot 'Zstandard.Net.dll')),('/reference:'+(Join-Path $OutputRoot 'System.Buffers.dll')))+@($sources.FullName)
& $compiler @arguments > (Join-Path $PreparedRoot 'compiler-private.log') 2>&1
if($LASTEXITCODE -ne 0 -or -not(Test-Path -LiteralPath $binary)){
    $codes=[regex]::Matches([IO.File]::ReadAllText((Join-Path $PreparedRoot 'compiler-private.log')),'\berror\s+([A-Z]+\d+)') | ForEach-Object {$_.Groups[1].Value} | Sort-Object -Unique
    if($codes){Write-Host ('Private build diagnostic codes: '+($codes -join ','))}
    throw 'Private selective-reader compilation failed; no runtime artifact was approved.'
}
$notice=Join-Path $OutputRoot 'notices';New-Item -ItemType Directory -Path $notice | Out-Null
Copy-Item -LiteralPath (Join-Path $PreparedRoot 'upstream-README.md') -Destination $notice
Copy-Item -LiteralPath (Join-Path $SourceRoot 'LICENSE') -Destination (Join-Path $notice 'TOOLKIT-LICENSE.txt')
$files=[ordered]@{}
foreach($path in Get-ChildItem -LiteralPath $OutputRoot -File -Recurse | Sort-Object FullName){
    $files[[IO.Path]::GetRelativePath($OutputRoot,$path.FullName).Replace('\','/')]=@{bytes=$path.Length;sha256=(Get-FileHash -LiteralPath $path.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
foreach($item in $prepared.prepared_sources.PSObject.Properties){if((Get-FileHash -LiteralPath (Join-Path $PreparedRoot ('source/'+$item.Name)) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value){throw 'A selected source changed during private compilation.'}}
if((& git -C $SourceRoot rev-parse HEAD).Trim() -ne $commit){throw 'Source commit changed during compilation.'}
$owned=@{}
foreach($name in @('scripts/build-blocked-ree-helper.ps1','scripts/prepare-blocked-game-helper.py','backend/ree_extractor.py','packaging/game-readers/blocked-inputs.json')){$owned[$name]=(Get-FileHash -LiteralPath (Join-Path $SourceRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()}
$manifest=@{schema='proxy-blocked-game-helper-v1';kind='pragmata';purpose='blocked-private-game-reader';platform='win-x86';source_commit=$commit;source_dirty=$dirty;source_inputs=$prepared.source_inputs;prepared_sources=$prepared.prepared_sources;owned_source_inputs=$owned;files=$files;compiler_sha256=(Get-FileHash -LiteralPath $compiler -Algorithm SHA256).Hash.ToLowerInvariant();compiler_version=(Get-Item -LiteralPath $compiler).VersionInfo.FileVersion;compiler_publisher='verified Microsoft Authenticode';gate=$prepared.gate;runtime_collection_allowed=$false;runtime_entrypoints=@();redistribution_review='not-established';native_windows_11_acceptance='unavailable';r19_complete=$false}
[IO.File]::WriteAllText((Join-Path $OutputRoot 'blocked-manifest.json'),($manifest | ConvertTo-Json -Depth 20)+"`n",[Text.UTF8Encoding]::new($false))
Write-Host 'Selective x86 reader precompiled in private quarantine. Runtime collection and game acceptance remain blocked.'
