param([Parameter(Mandatory = $true)][string]$OutputRoot)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $root) { throw 'Choose a fresh compiler output directory.' }
$cursor = [IO.DirectoryInfo]$root
while ($null -ne $cursor) {
    if ($cursor.Exists -and ($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Compiler paths cannot traverse reparse points.' }
    $cursor = $cursor.Parent
}
$pins = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../packaging/codecs/audio-runtime.json') -Raw | ConvertFrom-Json
$compiler = $pins.windows_build_toolchain
New-Item -ItemType Directory -Path $root | Out-Null
$archive = Join-Path $root 'compiler.7z.exe'
Invoke-WebRequest -Uri $compiler.url -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $compiler.sha256) { throw 'Compiler archive checksum differs.' }
$process = Start-Process -FilePath $archive -ArgumentList @('-y', ('-o"' + $root + '"')) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath (Join-Path $root 'w64devkit/bin/gcc.exe'))) { throw 'Verified compiler extraction failed.' }
Write-Output 'Verified build-only w64devkit is ready. It is not an application dependency.'
