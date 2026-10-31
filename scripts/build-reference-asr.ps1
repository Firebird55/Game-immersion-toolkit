param([Parameter(Mandatory=$true)][string]$InputRoot,
      [Parameter(Mandatory=$true)][string]$OutputRoot,
      [Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$CMakeRoot)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$pin = Get-Content (Join-Path $root 'packaging/asr/sherpa-reference.json') -Raw | ConvertFrom-Json
if (-not $IsWindows) { throw 'The separate ASR source experiment requires a Windows build host.' }
if (Test-Path -LiteralPath $OutputRoot) { throw 'Choose a fresh private ASR output directory.' }
$Python = (Resolve-Path -LiteralPath $Python).Path
$InputRoot = (Resolve-Path -LiteralPath $InputRoot).Path
$CMakeRoot = (Resolve-Path -LiteralPath $CMakeRoot).ProviderPath
$cmakePin = Get-Content (Join-Path $root $pin.cmake_build_tool_policy) -Raw | ConvertFrom-Json
& $Python -I -B (Join-Path $PSScriptRoot 'pinned-build-cmake.py') verify --root $CMakeRoot
if ($LASTEXITCODE -ne 0) { throw 'The explicit isolated CMake archive/tree verification failed.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$instances = @((& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json) | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $instances.Count -ne 1) { throw 'An explicit VS2026 build-host toolchain is required.' }
$vsRoot = $instances[0].installationPath
if (([version]$instances[0].installationVersion).Major -ne 18) { throw 'The required VS major version is unavailable.' }
$cmakePayload = Join-Path $CMakeRoot $cmakePin.archive.root
$cmakeExecutable = Join-Path $cmakePayload 'bin/cmake.exe'
if (-not (Test-Path -LiteralPath $cmakeExecutable -PathType Leaf)) {
  throw 'The exact isolated CMake executable is required; installed alternatives are not accepted.'
}
$sdk = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$toolRoots = @{
  vc = Join-Path $vsRoot ('VC/Tools/MSVC/' + $pin.toolchain.vc_tools_version)
  msbuild = Join-Path $vsRoot 'MSBuild'
  'vc-auxiliary' = Join-Path $vsRoot 'VC/Auxiliary'
  'sdk-include' = Join-Path $sdk ('Include/' + $pin.toolchain.windows_sdk_version)
  'sdk-lib' = Join-Path $sdk ('Lib/' + $pin.toolchain.windows_sdk_version)
  'sdk-bin' = Join-Path $sdk ('bin/' + $pin.toolchain.windows_sdk_version)
  cmake = $cmakePayload
  python = Split-Path $Python
}
$netfx = Join-Path ${env:ProgramFiles(x86)} ('Windows Kits/NETFXSDK/' + $pin.toolchain.netfx_sdk_version)
foreach ($entry in @{ 'netfx-include' = (Join-Path $netfx 'Include/um');
                      'netfx-lib' = (Join-Path $netfx 'Lib/um/x64') }.GetEnumerator()) {
  if (Test-Path -LiteralPath $entry.Value -PathType Container) { $toolRoots[$entry.Key] = $entry.Value }
}
foreach ($label in @($toolRoots.Keys)) {
  $path = $toolRoots[$label]
  if ($path -isnot [string] -or [string]::IsNullOrWhiteSpace($path) -or
      -not (Test-Path -LiteralPath $path -PathType Container)) {
    throw 'Every explicit tool root must be one existing directory.'
  }
  $resolved = @(Resolve-Path -LiteralPath $path)
  if ($resolved.Count -ne 1 -or $resolved[0].Provider.Name -ne 'FileSystem') {
    throw 'Every explicit tool root must resolve to one filesystem directory.'
  }
  $toolRoots[$label] = $resolved[0].ProviderPath
}
# Every executable/tool remains build-host-only. Version constraints are followed
# by exact per-run file seals, not treated as immutable supplier approval.
$env:PYTHONDONTWRITEBYTECODE = '1'
& $Python -I -B (Join-Path $PSScriptRoot 'reference-asr.py') prepare --inputs $InputRoot --output $OutputRoot
if ($LASTEXITCODE -ne 0) { throw 'Exact source/dependency/notice preparation failed.' }
$OutputRoot = (Resolve-Path -LiteralPath $OutputRoot).Path
$rootsFile = Join-Path $OutputRoot 'PRIVATE-TOOL-ROOTS.json'
$toolRoots | ConvertTo-Json | Set-Content -LiteralPath $rootsFile -Encoding utf8NoBOM
& $Python -I -B (Join-Path $PSScriptRoot 'reference-asr.py') build --output $OutputRoot --inputs $InputRoot --tool-roots $rootsFile --vs-root $vsRoot --cmake-root $CMakeRoot
if ($LASTEXITCODE -ne 0) { throw 'The private ASR source build/probe failed; inspect only its owned private output.' }
