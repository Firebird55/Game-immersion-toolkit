param([Parameter(Mandatory=$true)][string]$SourceArchive,
      [Parameter(Mandatory=$true)][string]$OutputRoot,
      [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$pin = Get-Content (Join-Path $root 'packaging/codecs/flac-reference.json') -Raw | ConvertFrom-Json
& $Python -B (Join-Path $PSScriptRoot 'reference-codec.py') prepare --archive $SourceArchive --output $OutputRoot
if ($LASTEXITCODE -ne 0) { throw 'Exact source/notice preparation failed.' }
$OutputRoot = (Resolve-Path -LiteralPath $OutputRoot).Path
$source = Join-Path $OutputRoot ('upstream/flac-' + $pin.version)
$build = Join-Path $OutputRoot 'build'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installed = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationVersion
$generators = @{17='Visual Studio 17 2022'; 18='Visual Studio 18 2026'}
$generator = $generators[([version]$installed).Major]
if (-not $generator) { throw 'A supported MSVC build-host installation is required.' }
$options = @('-S', $source, '-B', $build, '-G', $generator, '-A', 'x64')
foreach ($item in $pin.cmake.PSObject.Properties) { $options += "-D$($item.Name)=$($item.Value)" }
# CRT stays an explicit native/system prerequisite; no MSVC redistributable is
# copied from a developer installation or silently added to the candidate.
$options += '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL'
$options += '-DCMAKE_SHARED_LINKER_FLAGS_RELEASE=/INCREMENTAL:NO /Brepro'
$options += '-DCMAKE_EXE_LINKER_FLAGS_RELEASE=/INCREMENTAL:NO /Brepro'
& cmake @options
if ($LASTEXITCODE -ne 0) { throw 'Reference codec configuration failed.' }
& cmake --build $build --config Release --target flacapp --parallel 2
if ($LASTEXITCODE -ne 0) { throw 'Reference codec source build failed.' }
$compiler = Get-ChildItem (Join-Path $build 'CMakeFiles') -Recurse -Filter CMakeCCompiler.cmake | Select-Object -First 1
$version = [regex]::Match((Get-Content $compiler.FullName -Raw), 'set\(CMAKE_C_COMPILER_VERSION "([^"]+)"\)').Groups[1].Value
if (-not $version) { throw 'MSVC compiler observation is unavailable.' }
$cmake = (& cmake --version | Select-Object -First 1)
& $Python -B (Join-Path $PSScriptRoot 'reference-codec.py') finish --output $OutputRoot --compiler-version $version --cmake-version $cmake
if ($LASTEXITCODE -ne 0) { throw 'Source kit/output closure failed.' }
