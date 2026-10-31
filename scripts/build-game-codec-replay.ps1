param([Parameter(Mandatory=$true)][string]$InputRoot,
      [string]$OutputRoot = 'C:\r19-game-codec-replay',
      [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$pin = Get-Content (Join-Path $root 'packaging/codecs/ffmpeg-opus-replay.json') -Raw | ConvertFrom-Json
# This is build-host orchestration under the project LICENSE, not one of the
# three additionally GPL-licensed Xiph FLAC recipe files. No runtime collection.
if (-not $IsWindows -or $env:ImageVersion -ne $pin.host.image_version -or $env:ImageOS -notmatch '^[a-z0-9-]+$') {
    throw 'Exact reviewed hosted image unavailable; no moving-image substitution.'
}
if ([IO.Path]::GetFullPath($OutputRoot) -ne 'C:\r19-game-codec-replay') {
    throw 'The experimental configure prefix is fixed; use the isolated hosted job.'
}
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$instances = @((& $vswhere -products '*' -version '[18.0,19.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json) | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $instances.Count -ne 1) { throw 'Exactly one supported VS18 instance is required.' }
$instance = $instances[0]
$toolset = Join-Path $instance.installationPath ('VC/Tools/MSVC/' + $pin.host.toolset_directory)
$sdk = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$compiler = Join-Path $toolset 'bin/Hostx64/x64/cl.exe'
$cmake = (Get-Command cmake -CommandType Application).Source
$pythonExe = (Get-Command $Python -CommandType Application).Source
$tar = Join-Path $env:SystemRoot 'System32/tar.exe'
$cmakeVersion = (& $cmake --version | Select-Object -First 1)
if ($cmakeVersion -ne ('cmake version ' + $pin.host.cmake_version) -or
    [Diagnostics.FileVersionInfo]::GetVersionInfo($compiler).FileVersion.Trim() -ne $pin.host.compiler_version) {
    throw 'Actual compiler or CMake differs from the reviewed build-host tuple.'
}
# Build processes get an allowlisted environment rather than arbitrary MSBuild
# properties, compiler search paths or shell-startup files from the runner.
$retained = [ordered]@{}
foreach ($name in @('SystemRoot','WINDIR','ComSpec','ProgramFiles','ProgramFiles(x86)','ProgramW6432',
    'SystemDrive','OS','PATHEXT','PROCESSOR_ARCHITECTURE','PROCESSOR_IDENTIFIER','NUMBER_OF_PROCESSORS',
    'ImageOS','ImageVersion','GITHUB_SHA','GITHUB_STEP_SUMMARY')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Process')
    if ($null -ne $value) { $retained[$name] = $value }
}
foreach ($name in @([Environment]::GetEnvironmentVariables('Process').Keys)) {
    [Environment]::SetEnvironmentVariable($name, $null, 'Process')
}
foreach ($name in $retained.Keys) { [Environment]::SetEnvironmentVariable($name, $retained[$name], 'Process') }
$profileRoot = 'C:\r19-game-codec-empty-profile'
if (Test-Path -LiteralPath $profileRoot) { throw 'Isolated build profile must be fresh.' }
foreach ($directory in @($profileRoot, "$profileRoot\AppData\Roaming", "$profileRoot\AppData\Local", "$profileRoot\Temp", "$profileRoot\MSBuild")) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
$env:USERPROFILE = $profileRoot
$env:APPDATA = "$profileRoot\AppData\Roaming"
$env:LOCALAPPDATA = "$profileRoot\AppData\Local"
$env:TEMP = "$profileRoot\Temp"
$env:TMP = "$profileRoot\Temp"
$env:UserRootDir = "$profileRoot\MSBuild\"
$env:MSBuildUserExtensionsPath = "$profileRoot\MSBuild\"
$env:ImportDirectoryBuildProps = 'false'
$env:ImportDirectoryBuildTargets = 'false'
$env:ImportUserLocationsByWildcardBeforeMicrosoftCommonProps = 'false'
$env:ImportUserLocationsByWildcardAfterMicrosoftCommonProps = 'false'
$env:ImportUserLocationsByWildcardBeforeMicrosoftCppDefaultProps = 'false'
$env:ImportUserLocationsByWildcardAfterMicrosoftCppDefaultProps = 'false'
$env:PATH = (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot
# No inherited INCLUDE/LIB/LIBPATH, HOME, ENV/BASH_ENV or pkg-config override.
# Import only the explicitly selected compiler/SDK environment, never stdout it.
$vcvars = Join-Path $instance.installationPath 'VC/Auxiliary/Build/vcvarsall.bat'
$command = '"' + $vcvars + '" x64 ' + $pin.host.sdk_version + ' -vcvars_ver=' + $pin.host.toolset_directory + ' >nul && set'
$variables = & $env:ComSpec /d /s /c ('"' + $command + '"')
if ($LASTEXITCODE -ne 0) { throw 'Exact compiler/SDK activation failed.' }
foreach ($line in $variables) {
    if ($line -match '^([^=]+)=(.*)$' -and $Matches[1] -in @('INCLUDE','LIB','VCToolsInstallDir','WindowsSdkDir','WindowsSDKVersion')) {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
if ($env:WindowsSDKVersion.TrimEnd('\') -ne $pin.host.sdk_version -or
    $env:VCToolsInstallDir.TrimEnd('\') -ne $toolset.TrimEnd('\')) { throw 'Activated toolchain identity differs.' }
$netfx = Join-Path ${env:ProgramFiles(x86)} ('Windows Kits/NETFXSDK/' + $pin.host.netfx_sdk_headers)
$headerRoots = @((Join-Path $toolset 'include'), (Join-Path $toolset 'atlmfc/include'),
    (Join-Path $sdk ('Include/' + $pin.host.sdk_version)), (Join-Path $netfx 'Include/um'))
$libraryRoots = @((Join-Path $toolset 'lib/x64'), (Join-Path $toolset 'atlmfc/lib/x64'),
    (Join-Path $sdk ('Lib/' + $pin.host.sdk_version + '/ucrt/x64')),
    (Join-Path $sdk ('Lib/' + $pin.host.sdk_version + '/um/x64')), (Join-Path $netfx 'Lib/um/x64'))
function Assert-SearchPath([string]$Value, [string[]]$AllowedRoots) {
    if (-not $Value) { throw 'Compiler header/library search path is unavailable.' }
    foreach ($entry in $Value.TrimEnd(';').Split(';')) {
        if (-not $entry) { throw 'An empty compiler search entry would permit ambient input.' }
        $full = [IO.Path]::GetFullPath($entry).TrimEnd('\')
        $allowed = $false
        foreach ($base in $AllowedRoots) {
            $canonical = [IO.Path]::GetFullPath($base).TrimEnd('\')
            if ($full -eq $canonical -or $full.StartsWith($canonical + '\', [StringComparison]::OrdinalIgnoreCase)) { $allowed = $true }
        }
        if (-not $allowed -or -not (Test-Path -LiteralPath $full -PathType Container)) {
            throw 'Activated compiler search path escapes selected and recorded input roots.'
        }
    }
}
Assert-SearchPath $env:INCLUDE $headerRoots
Assert-SearchPath $env:LIB $libraryRoots
& $pythonExe -I -B (Join-Path $PSScriptRoot 'replay-game-codec.py') prepare --input-root $InputRoot --output $OutputRoot
if ($LASTEXITCODE -ne 0) { throw 'Exact source/tool hash and source-only preparation failed.' }
$privateLog = Join-Path $OutputRoot 'PRIVATE-BUILD.log'
function Invoke-Build(
    [ValidateSet('extract-msys-base','extract-make','extract-nasm','extract-pkgconf',
        'check-shell','check-make','check-nasm','check-pkgconf','configure-opus',
        'build-opus','install-opus','configure-ffmpeg','clean-ffmpeg','build-ffmpeg',
        'install-ffmpeg','compile-probe','observe-and-package')][string]$Phase,
    [string]$Executable, [string[]]$Arguments) {
    $offset = if (Test-Path -LiteralPath $privateLog) { (Get-Item -LiteralPath $privateLog).Length } else { 0 }
    $PSNativeCommandUseErrorActionPreference = $false
    & $Executable @Arguments >> $privateLog 2>&1
    $commandExit = [long]$LASTEXITCODE
    if ($commandExit -ne 0) {
        # The classifier emits no log text, paths, arguments or passing receipt.
        # Its own diagnostics also stay private if receipt generation fails.
        & $pythonExe -I -B (Join-Path $PSScriptRoot 'replay-game-codec.py') failure --output $OutputRoot `
            --phase $Phase --exit-code $commandExit --log $privateLog --log-offset $offset `
            >> (Join-Path $OutputRoot 'PRIVATE-DIAGNOSIS.log') 2>&1
        throw ('Quarantined build phase failed: ' + $Phase + '; exit code ' + $commandExit + '.')
    }
}
$toolsRoot = Join-Path $OutputRoot 'tools'
New-Item -ItemType Directory -Path $toolsRoot | Out-Null
Invoke-Build 'extract-msys-base' $tar @('-xf', (Join-Path $InputRoot $pin.build_tools[0].filename), '-C', $toolsRoot)
$msys = Join-Path $toolsRoot 'msys64'
$packagePhases = @{'make-4.4.1-3-x86_64.pkg.tar.zst'='extract-make';
    'nasm-3.02-1-x86_64.pkg.tar.zst'='extract-nasm'; 'pkgconf-3.0.9-1-x86_64.pkg.tar.zst'='extract-pkgconf'}
foreach ($package in @($pin.build_tools | Select-Object -Skip 1)) {
    Invoke-Build ($packagePhases[$package.filename]) $tar @('-xf', (Join-Path $InputRoot $package.filename), '-C', $msys,
        '--exclude=.BUILDINFO', '--exclude=.PKGINFO', '--exclude=.MTREE', '--exclude=.INSTALL')
}
$env:PATH = @((Join-Path $toolset 'bin/Hostx64/x64'), (Join-Path $sdk ('bin/' + $pin.host.sdk_version + '/x64')),
    (Split-Path $cmake), (Join-Path $msys 'usr/bin'), (Join-Path $env:SystemRoot 'System32'), $env:SystemRoot) -join ';'
foreach ($name in @('CL','_CL_','LINK','_LINK_','CC','CXX','AR','CFLAGS','CXXFLAGS','CPPFLAGS','LDFLAGS',
    'LIBPATH','MAKEFLAGS','MFLAGS','CMAKE_PREFIX_PATH','CMAKE_TOOLCHAIN_FILE','PKG_CONFIG_PATH','PKG_CONFIG_SYSROOT_DIR',
    'MSYS2_ARG_CONV_EXCL')) {
    [Environment]::SetEnvironmentVariable($name, $null, 'Process')
}
$env:MSYSTEM = 'MSYS'
$env:MSYS2_PATH_TYPE = 'strict'
$opusPrefix = Join-Path $OutputRoot 'out/opus-vs-64'
$env:PKG_CONFIG_LIBDIR = '/c/r19-game-codec-replay/out/opus-vs-64/lib/pkgconfig'
$sh = Join-Path $msys 'usr/bin/sh.exe'
$bash = Join-Path $msys 'usr/bin/bash.exe'
$make = Join-Path $msys 'usr/bin/make.exe'
$nasm = Join-Path $msys 'usr/bin/nasm.exe'
$pkgconf = Join-Path $msys 'usr/bin/pkgconf.exe'
Invoke-Build 'check-shell' $sh @('--version')
Invoke-Build 'check-make' $make @('--version')
Invoke-Build 'check-nasm' $nasm @('-v')
Invoke-Build 'check-pkgconf' $pkgconf @('--version')
# Identity includes exact host headers/static libraries and all isolated MSYS
# tool bytes, not just self-reported versions. No machine paths are published.
$toolRoots = [ordered]@{
    'msvc-bin' = (Join-Path $toolset 'bin/Hostx64/x64')
    'msvc-include' = (Join-Path $toolset 'include')
    'msvc-lib-x64' = (Join-Path $toolset 'lib/x64')
    'sdk-bin-x64' = (Join-Path $sdk ('bin/' + $pin.host.sdk_version + '/x64'))
    'sdk-include' = (Join-Path $sdk ('Include/' + $pin.host.sdk_version))
    'sdk-ucrt-x64' = (Join-Path $sdk ('Lib/' + $pin.host.sdk_version + '/ucrt/x64'))
    'sdk-um-x64' = (Join-Path $sdk ('Lib/' + $pin.host.sdk_version + '/um/x64'))
    'cmake' = (Split-Path (Split-Path $cmake))
    'msbuild' = (Join-Path $instance.installationPath 'MSBuild')
    'vc-auxiliary' = (Join-Path $instance.installationPath 'VC/Auxiliary')
    'isolated-msys-bin' = (Join-Path $msys 'usr/bin')
}
foreach ($entry in ([ordered]@{'msvc-atlmfc-include'=(Join-Path $toolset 'atlmfc/include');
    'msvc-atlmfc-lib-x64'=(Join-Path $toolset 'atlmfc/lib/x64');
    'netfx-sdk-include'=(Join-Path $netfx 'Include/um'); 'netfx-sdk-lib-x64'=(Join-Path $netfx 'Lib/um/x64')}).GetEnumerator()) {
    if (Test-Path -LiteralPath $entry.Value -PathType Container) { $toolRoots[$entry.Key] = $entry.Value }
}
function Write-ToolIdentity([string]$Destination) {
    $trees = [ordered]@{}
    foreach ($label in $toolRoots.Keys) {
        $base = $toolRoots[$label]
        if (-not (Test-Path -LiteralPath $base -PathType Container)) { throw 'An exact tool/header/library tree is unavailable.' }
        $files = [ordered]@{}
        $entries = @(Get-Item -LiteralPath $base -Force) + @(Get-ChildItem -LiteralPath $base -Force -Recurse)
        foreach ($file in @($entries | Sort-Object FullName)) {
            if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Tool tree contains an unresolved reparse point.' }
            if ($file.PSIsContainer) { continue }
            $relative = [IO.Path]::GetRelativePath($base, $file.FullName).Replace('\','/')
            $files[$relative] = @{bytes=$file.Length; sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
        $trees[$label] = $files
    }
    $individual = [ordered]@{}
    foreach ($entry in ([ordered]@{'windows-tar'=$tar; 'vswhere'=$vswhere; 'cmd'=$env:ComSpec; 'python'=$pythonExe}).GetEnumerator()) {
        $item = Get-Item -LiteralPath $entry.Value
        $individual[$entry.Key] = @{bytes=$item.Length; sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $value = [ordered]@{image_os=$env:ImageOS; image_version=$env:ImageVersion; compiler=$pin.host.compiler_version;
        visual_studio_version=$instance.installationVersion; toolset=$pin.host.toolset_directory;
        sdk=$pin.host.sdk_version; cmake=$pin.host.cmake_version; trees=$trees; individual=$individual}
    $value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Destination -Encoding utf8NoBOM
}
Write-ToolIdentity (Join-Path $OutputRoot 'BUILD-TOOLS.json')
$opusSource = Join-Path $OutputRoot 'upstream/opus-1.6.1'
$opusBuild = Join-Path $OutputRoot 'opus-build'
$globals = 'UserRootDir=' + $env:UserRootDir.Replace('\','/') + ';ImportDirectoryBuildProps=false;ImportDirectoryBuildTargets=false'
# Original upstream Opus commands, with the declared generator/SDK/path control.
Invoke-Build 'configure-opus' $cmake @('-S', $opusSource, '-B', $opusBuild, '-G', $pin.host.generator,
    '-A', 'x64', '-T', ('version=' + $pin.host.toolset_directory),
    ('-DCMAKE_GENERATOR_INSTANCE=' + $instance.installationPath), ('-DCMAKE_SYSTEM_VERSION=' + $pin.host.sdk_version),
    '-DOPUS_STATIC_RUNTIME=ON', ('-DCMAKE_INSTALL_PREFIX=' + $opusPrefix.Replace('\','/')),
    ('-DCMAKE_VS_GLOBALS=' + $globals),
    '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF', '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF')
Invoke-Build 'build-opus' $cmake @('--build', $opusBuild, '--config', 'Release', '--parallel', '2')
Invoke-Build 'install-opus' $cmake @('--install', $opusBuild, '--config', 'Release')
$options = @(Get-Content (Join-Path $OutputRoot 'ORIGINAL-OPTIONS.json') -Raw | ConvertFrom-Json)
$ffmpegBuild = Join-Path $OutputRoot 'ffmpeg-build'
New-Item -ItemType Directory -Path $ffmpegBuild | Out-Null
Push-Location $ffmpegBuild
try {
    # Original option bytes are not rewritten. No GPL/version3/nonfree additions,
    # no CLI/file protocol enabling and no prebuilt codec substitution.
    Invoke-Build 'configure-ffmpeg' $sh (@('/c/r19-game-codec-replay/upstream/ffmpeg-9.0.2/configure') + $options + @(
        '--target-os=win64', '--toolchain=msvc', '--arch=x86_64', '--prefix=/c/r19-game-codec-replay/out/ffmpeg-vs-64'))
    Invoke-Build 'clean-ffmpeg' $make @('clean')
    Invoke-Build 'build-ffmpeg' $make @('-j2')
    Invoke-Build 'install-ffmpeg' $make @('install')
} finally { Pop-Location }
$candidate = Join-Path $OutputRoot 'candidate'
New-Item -ItemType Directory -Path $candidate | Out-Null
Copy-Item (Join-Path $OutputRoot 'out/ffmpeg-vs-64/bin/*.dll') -Destination $candidate
foreach ($notice in $pin.notices) {
    $component = @($pin.sources | Where-Object component -eq $notice.component)[0]
    $noticeTarget = Join-Path $candidate ('notices/' + $notice.component + '/' + $notice.path)
    New-Item -ItemType Directory -Path (Split-Path $noticeTarget) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $OutputRoot ('upstream/' + $component.root + '/' + $notice.path)) -Destination $noticeTarget
}
$ffmpegPrefix = Join-Path $OutputRoot 'out/ffmpeg-vs-64'
$probe = Join-Path $root 'scripts/fixtures/game-codec-replay.c'
Push-Location $candidate
try {
    Invoke-Build 'compile-probe' $compiler @('/nologo', '/O2', '/MT', '/utf-8', ('/I' + (Join-Path $ffmpegPrefix 'include')),
        ('/I' + (Join-Path $opusPrefix 'include')), $probe, '/Fe:game-codec-probe.exe', '/link',
        # Original MSVC Makefile installs suffixed import libraries beside DLLs.
        ('/LIBPATH:' + (Join-Path $ffmpegPrefix 'bin')), ('/LIBPATH:' + (Join-Path $opusPrefix 'lib')),
        'avcodec-vgmstream.lib', 'avformat-vgmstream.lib', 'avutil-vgmstream.lib', 'swresample-vgmstream.lib', 'opus.lib')
    Remove-Item -LiteralPath 'game-codec-replay.obj'
} finally { Pop-Location }
Write-ToolIdentity (Join-Path $OutputRoot 'BUILD-TOOLS-AFTER.json')
Invoke-Build 'observe-and-package' $pythonExe @('-I', '-B', (Join-Path $PSScriptRoot 'replay-game-codec.py'), 'finish', '--output', $OutputRoot)
