param([Parameter(Mandatory=$true)][string]$InputRoot,
      [string]$OutputRoot = 'C:\r19-game-codec-replay',
      [string]$CMakeRoot = 'C:\r19-build-tools\cmake-4.4.5',
      [Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference = 'Stop'
function Get-ReplayExecutables([string]$PinnedCMakeRoot, [string]$PythonPath) {
    if (-not [IO.Path]::IsPathFullyQualified($PinnedCMakeRoot) -or
        -not [IO.Path]::IsPathFullyQualified($PythonPath)) {
        throw 'Explicit absolute build-tool paths are required; ambient lookup is disabled.'
    }
    $selected = [ordered]@{CMake=(Join-Path $PinnedCMakeRoot 'cmake-4.4.5-windows-x86_64/bin/cmake.exe'); Python=$PythonPath}
    foreach ($name in @('CMake','Python')) {
        $item = Get-Item -LiteralPath ($selected[$name]) -ErrorAction Stop
        if ($item.PSIsContainer -or $item.Extension -ne '.exe' -or
            ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'A single regular explicit build-tool executable is required.'
        }
        $selected[$name] = $item.FullName
    }
    return [pscustomobject]$selected
}
function Get-NumericToolObservation([string]$CMakePath, [string]$CompilerPath) {
    $process = [Diagnostics.Process]::new()
    $started = $false
    try {
        $start = [Diagnostics.ProcessStartInfo]::new()
        $start.FileName = $CMakePath
        $start.ArgumentList.Add('--version')
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $start.Environment.Clear()
        foreach ($name in @('SystemRoot','WINDIR','TEMP','TMP')) {
            $value = [Environment]::GetEnvironmentVariable($name, 'Process')
            if ($null -ne $value) { $start.Environment[$name] = $value }
        }
        $start.Environment['PATH'] = (Join-Path $env:SystemRoot 'System32')
        $process.StartInfo = $start
        $started = $process.Start()
        if (-not $started -or -not $process.WaitForExit(10000)) { throw 'Bounded version probe failed.' }
        # Read only bounded native output after exit. A full pipe times out
        # above instead of accumulating an unbounded line or hidden stderr.
        $buffer = [char[]]::new(4097)
        $stdoutTask = $process.StandardOutput.ReadBlockAsync($buffer, 0, $buffer.Length)
        if (-not $stdoutTask.Wait(2000)) { throw 'Bounded version probe failed.' }
        $count = $stdoutTask.GetAwaiter().GetResult()
        $errorBuffer = [char[]]::new(4097)
        $stderrTask = $process.StandardError.ReadBlockAsync($errorBuffer, 0, $errorBuffer.Length)
        if (-not $stderrTask.Wait(2000)) { throw 'Bounded version probe failed.' }
        $errorCount = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0 -or $count -ge 4097 -or $errorCount -ge 4097) { throw 'Bounded version probe failed.' }
        $first = ([string]::new($buffer, 0, $count).Split("`n"))[0].TrimEnd("`r")
        if ($first -notmatch '^cmake version ([0-9]+\.[0-9]+\.[0-9]+)$') { throw 'Non-numeric version probe result.' }
        $cmakeNumeric = $Matches[1]
        $resource = [Diagnostics.FileVersionInfo]::GetVersionInfo($CompilerPath)
        $fileNumeric = @($resource.FileMajorPart, $resource.FileMinorPart, $resource.FileBuildPart, $resource.FilePrivatePart) -join '.'
        $productNumeric = @($resource.ProductMajorPart, $resource.ProductMinorPart, $resource.ProductBuildPart, $resource.ProductPrivatePart) -join '.'
        return [ordered]@{
            cmake = @{version=$cmakeNumeric; bytes=(Get-Item -LiteralPath $CMakePath).Length;
                sha256=(Get-FileHash -LiteralPath $CMakePath -Algorithm SHA256).Hash.ToLowerInvariant()}
            cl = @{file_version=$fileNumeric; product_version=$productNumeric; bytes=(Get-Item -LiteralPath $CompilerPath).Length;
                sha256=(Get-FileHash -LiteralPath $CompilerPath -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
    } catch {
        throw 'Reviewed numeric tool-version observation failed.'
    } finally {
        if ($started -and -not $process.HasExited) {
            try { $process.Kill($true); $null = $process.WaitForExit(5000) } catch { }
        }
        $process.Dispose()
    }
}
function Get-CompilerEnvironment([string]$ActivationRoot, [string]$VcvarsPath,
    [string]$SdkVersion, [string]$ToolsetVersion) {
    if (-not [IO.Path]::IsPathFullyQualified($ActivationRoot) -or
        -not [IO.Path]::IsPathFullyQualified($VcvarsPath) -or
        $VcvarsPath -match '["%!^&|<>\r\n]' -or $ActivationRoot -match '["%!^&|<>\r\n]' -or
        $SdkVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' -or
        $ToolsetVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
        throw 'Exact safe compiler activation inputs are required.'
    }
    $activation = Join-Path $ActivationRoot 'activation.cmd'
    $privateActivationLog = Join-Path $ActivationRoot 'PRIVATE-ACTIVATION.log'
    $privateShellLog = Join-Path $ActivationRoot 'PRIVATE-ACTIVATION-CMD.log'
    if (Test-Path -LiteralPath $activation) { throw 'Compiler activation script must be fresh.' }
    $vcvars = Get-Item -LiteralPath $VcvarsPath -ErrorAction Stop
    if ($vcvars.PSIsContainer -or $vcvars.Extension -ne '.bat' -or
        ($vcvars.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Exact compiler activation batch is unavailable.' }
    $lines = @('@echo off', 'set "ERRORLEVEL="',
        ('call "' + $vcvars.FullName + '" x64 ' + $SdkVersion + ' -vcvars_ver=' + $ToolsetVersion +
            ' > "' + $privateActivationLog + '" 2>&1'),
        'if not "%errorlevel%"=="0" exit /b %errorlevel%', 'set')
    [IO.File]::WriteAllLines($activation, $lines, [Text.UTF8Encoding]::new($false))
    $PSNativeCommandUseErrorActionPreference = $false
    $rows = & $env:ComSpec /d /q /c $activation 2>> $privateShellLog
    $activationExit = [long]$LASTEXITCODE
    if ($activationExit -ne 0) { throw ('Exact compiler/SDK activation failed; exit code ' + $activationExit + '.') }
    $selected = [ordered]@{}
    foreach ($line in $rows) {
        if ($line -match '^([^=]+)=(.*)$' -and $Matches[1] -in @('INCLUDE','LIB','VCToolsInstallDir','WindowsSdkDir','WindowsSDKVersion')) {
            $selected[$Matches[1]] = $Matches[2]
        }
    }
    return $selected
}
function Get-CompilerSearchObservation(
    [ValidateSet('INCLUDE','LIB')][string]$Kind, [string]$Value,
    [string[]]$AllowedRoots, [System.Collections.IDictionary]$ComponentRoots) {
    # These are diagnostic roles, not an additional search-root allowlist.
    $roles = @('msvc-include','msvc-atlmfc-include','sdk-include','netfx-include',
        'msvc-lib-x64','msvc-atlmfc-lib-x64','sdk-ucrt-lib-x64','sdk-um-lib-x64',
        'netfx-lib-x64','vc-auxiliary-include','netfx-other','sdk-other','msvc-other')
    $entries = [Collections.Generic.List[object]]::new()
    $state = 'checked'
    if (-not $Value) { $state = 'unavailable' }
    elseif ($Value.Length -gt 32767) { $state = 'value-limit' }
    else {
        $parts = $Value.TrimEnd(';').Split(';')
        if ($parts.Count -gt 64) { $state = 'entry-limit' }
        foreach ($entry in ($parts | Select-Object -First 64)) {
            $role = 'unclassified'; $exists = $null; $disposition = 'invalid-entry'
            if (-not $entry) { $disposition = 'empty-entry' }
            else {
                try {
                    if ([IO.Path]::IsPathFullyQualified($entry)) {
                        $full = [IO.Path]::GetFullPath($entry).TrimEnd('\')
                        foreach ($name in $roles) {
                            if (-not $ComponentRoots.Contains($name)) { continue }
                            $base = [IO.Path]::GetFullPath($ComponentRoots[$name]).TrimEnd('\')
                            if ($full.Equals($base, [StringComparison]::OrdinalIgnoreCase) -or
                                $full.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) {
                                $role = $name; break
                            }
                        }
                        $allowed = $false
                        foreach ($base in $AllowedRoots) {
                            $canonical = [IO.Path]::GetFullPath($base).TrimEnd('\')
                            if ($full.Equals($canonical, [StringComparison]::OrdinalIgnoreCase) -or
                                $full.StartsWith($canonical + '\', [StringComparison]::OrdinalIgnoreCase)) { $allowed = $true }
                        }
                        $exists = [bool](Test-Path -LiteralPath $full -PathType Container -ErrorAction Stop)
                        $disposition = if (-not $allowed) { 'outside-declared-roots' }
                            elseif (-not $exists) { 'missing-directory' } else { 'accepted' }
                    }
                } catch {
                    # No exception message, supplied path or path fingerprint is public.
                    $role = 'unclassified'; $exists = $null; $disposition = 'inspection-error'
                }
            }
            $entries.Add([ordered]@{component_role=$role; exists=$exists; disposition=$disposition})
        }
    }
    return [ordered]@{kind=$Kind; state=$state; entry_count=$entries.Count; entries=@($entries.ToArray())}
}
function Write-CompilerSearchFailure([string]$Destination, [string]$InputManifest,
    [string]$SourceCommit, [object[]]$Observations) {
    try {
        if (Test-Path -LiteralPath $Destination) { throw 'fresh-output' }
        if ($SourceCommit -cnotmatch '^[a-f0-9]{40}$' -or $Observations.Count -ne 2) { throw 'identity' }
        $roles = @('unclassified','msvc-include','msvc-atlmfc-include','sdk-include','netfx-include',
            'msvc-lib-x64','msvc-atlmfc-lib-x64','sdk-ucrt-lib-x64','sdk-um-lib-x64',
            'netfx-lib-x64','vc-auxiliary-include','netfx-other','sdk-other','msvc-other')
        $paths = @(); $failed = $false; $seen = @{}
        foreach ($item in $Observations) {
            if ($item.kind -isnot [string] -or $item.kind -cnotin @('INCLUDE','LIB') -or $seen.ContainsKey($item.kind) -or
                $item.state -isnot [string] -or $item.state -cnotin @('checked','unavailable','value-limit','entry-limit') -or
                $item.entry_count -isnot [int] -or $item.entry_count -lt 0 -or $item.entry_count -gt 64 -or
                @($item.entries).Count -ne $item.entry_count -or
                ($item.state -eq 'checked' -and $item.entry_count -eq 0) -or
                ($item.state -in @('unavailable','value-limit') -and $item.entry_count -ne 0) -or
                ($item.state -eq 'entry-limit' -and $item.entry_count -ne 64)) { throw 'observation' }
            $seen[$item.kind] = $true
            if ($item.state -ne 'checked') { $failed = $true }
            $entries = @()
            foreach ($entry in $item.entries) {
                if ($entry.component_role -isnot [string] -or $entry.component_role -cnotin $roles -or
                    ($null -ne $entry.exists -and $entry.exists -isnot [bool]) -or
                    $entry.disposition -isnot [string] -or $entry.disposition -cnotin @('accepted','outside-declared-roots','missing-directory',
                        'empty-entry','invalid-entry','inspection-error') -or
                    ($entry.disposition -eq 'accepted' -and $entry.exists -ne $true) -or
                    ($entry.disposition -eq 'missing-directory' -and $entry.exists -ne $false)) { throw 'entry' }
                if ($entry.disposition -ne 'accepted') { $failed = $true }
                $entries += [ordered]@{component_role=$entry.component_role; exists=$entry.exists; disposition=$entry.disposition}
            }
            # Rebuild a fixed projection; arbitrary object fields are never serialized.
            $paths += [ordered]@{kind=$item.kind; state=$item.state; entry_count=$item.entry_count; entries=@($entries)}
        }
        if (-not $failed) { throw 'no-failure' }
        $manifest = Get-Item -LiteralPath $InputManifest -ErrorAction Stop
        if ($manifest.PSIsContainer -or $manifest.Length -le 0 -or $manifest.Length -gt 1048576 -or
            ($manifest.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'manifest' }
        $report = [ordered]@{
            schema='proxy-r19-game-codec-replay-toolchain-preflight-failure-v1'; status='failed'
            phase='preflight-compiler-search-path'; source_commit=$SourceCommit
            input_manifest=@{path='packaging/codecs/ffmpeg-opus-replay.json'; bytes=$manifest.Length
                sha256=(Get-FileHash -LiteralPath $InputManifest -Algorithm SHA256).Hash.ToLowerInvariant()}
            search_paths=@($paths); raw_log_published=$false; native_codec_built=$false; native_codec_executed=$false
            runtime_collection_allowed=$false; production_execution_allowed=$false; source_delivery_approved=$false
            native_windows_11_acceptance='unavailable'; installer='not-built'; r19_complete=$false
        }
        $json = $report | ConvertTo-Json -Depth 7
        New-Item -ItemType Directory -Path $Destination -ErrorAction Stop | Out-Null
        [IO.File]::WriteAllText((Join-Path $Destination 'FAILED-STAGE.json'), $json + "`n", [Text.UTF8Encoding]::new($false))
    } catch {
        throw 'Safe compiler search-path failure receipt could not be recorded.'
    }
}
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
if (Test-Path -LiteralPath $OutputRoot) { throw 'Quarantine output must be fresh; existing work is preserved.' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$instances = @((& $vswhere -products '*' -version '[18.0,19.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json) | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $instances.Count -ne 1) { throw 'Exactly one supported VS18 instance is required.' }
$instance = $instances[0]
$toolset = Join-Path $instance.installationPath ('VC/Tools/MSVC/' + $pin.host.toolset_directory)
$sdk = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$compiler = Join-Path $toolset 'bin/Hostx64/x64/cl.exe'
$executables = Get-ReplayExecutables -PinnedCMakeRoot $CMakeRoot -PythonPath $Python
$cmake = $executables.CMake
$pythonExe = $executables.Python
$tar = Join-Path $env:SystemRoot 'System32/tar.exe'
& $pythonExe -I -B (Join-Path $PSScriptRoot 'pinned-build-cmake.py') verify --root $CMakeRoot | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Pinned isolated CMake input verification failed before native execution.' }
$observedTools = Get-NumericToolObservation -CMakePath $cmake -CompilerPath $compiler
if ($observedTools.cmake.version -ne $pin.host.cmake_version -or
    $observedTools.cl.file_version -ne $pin.host.compiler_version) {
    # This failure-only path creates a fresh quarantine and immediately exits;
    # it never pre-creates a successful build's source-preparation destination.
    $PSNativeCommandUseErrorActionPreference = $false
    $observedTools | ConvertTo-Json -Depth 4 | & $pythonExe -I -B (Join-Path $PSScriptRoot 'replay-game-codec.py') `
        preflight-failure --output $OutputRoot > $null 2> $null
    if ($LASTEXITCODE -ne 0) { throw 'Numeric preflight failure receipt could not be recorded.' }
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
$variables = Get-CompilerEnvironment -ActivationRoot $profileRoot -VcvarsPath $vcvars `
    -SdkVersion $pin.host.sdk_version -ToolsetVersion $pin.host.toolset_directory
foreach ($name in $variables.Keys) {
    [Environment]::SetEnvironmentVariable($name, $variables[$name], 'Process')
}
if ($env:WindowsSDKVersion.TrimEnd('\') -ne $pin.host.sdk_version -or
    $env:VCToolsInstallDir.TrimEnd('\') -ne $toolset.TrimEnd('\')) { throw 'Activated toolchain identity differs.' }
$netfx = Join-Path ${env:ProgramFiles(x86)} ('Windows Kits/NETFXSDK/' + $pin.host.netfx_sdk_headers)
$headerRoots = @((Join-Path $toolset 'include'), (Join-Path $toolset 'atlmfc/include'),
    (Join-Path $sdk ('Include/' + $pin.host.sdk_version)), (Join-Path $netfx 'Include/um'))
$libraryRoots = @((Join-Path $toolset 'lib/x64'), (Join-Path $toolset 'atlmfc/lib/x64'),
    (Join-Path $sdk ('Lib/' + $pin.host.sdk_version + '/ucrt/x64')),
    (Join-Path $sdk ('Lib/' + $pin.host.sdk_version + '/um/x64')), (Join-Path $netfx 'Lib/um/x64'))
$componentRoots = [ordered]@{
    'msvc-include'=$headerRoots[0]; 'msvc-atlmfc-include'=$headerRoots[1]
    'sdk-include'=$headerRoots[2]; 'netfx-include'=$headerRoots[3]
    'msvc-lib-x64'=$libraryRoots[0]; 'msvc-atlmfc-lib-x64'=$libraryRoots[1]
    'sdk-ucrt-lib-x64'=$libraryRoots[2]; 'sdk-um-lib-x64'=$libraryRoots[3]; 'netfx-lib-x64'=$libraryRoots[4]
    # Additional classification roots are diagnostic only; they remain rejected.
    'vc-auxiliary-include'=(Join-Path $instance.installationPath 'VC/Auxiliary/VS/include')
    'netfx-other'=(Split-Path $netfx); 'sdk-other'=$sdk
    'msvc-other'=(Join-Path $instance.installationPath 'VC/Tools/MSVC')
}
$searchObservations = @(
    (Get-CompilerSearchObservation 'INCLUDE' $env:INCLUDE $headerRoots $componentRoots)
    (Get-CompilerSearchObservation 'LIB' $env:LIB $libraryRoots $componentRoots)
)
if (@($searchObservations | Where-Object { $_.state -ne 'checked' -or
    @($_.entries | Where-Object { $_.disposition -ne 'accepted' }).Count -gt 0 }).Count -gt 0) {
    Write-CompilerSearchFailure -Destination $OutputRoot -InputManifest (Join-Path $root 'packaging/codecs/ffmpeg-opus-replay.json') `
        -SourceCommit $env:GITHUB_SHA -Observations $searchObservations
    throw 'Activated compiler search path escapes selected and recorded input roots.'
}
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
    '-DCMAKE_DISABLE_FIND_PACKAGE_Git=TRUE',
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
Invoke-Build 'observe-and-package' $pythonExe @('-I', '-B', (Join-Path $PSScriptRoot 'replay-game-codec.py'),
    'finish', '--output', $OutputRoot, '--cmake-root', $CMakeRoot)
