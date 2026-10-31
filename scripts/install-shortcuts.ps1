$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$launcherSource = Join-Path $projectRoot 'launcher\ProxyTranscriptLauncher.cs'
$icon = Join-Path $projectRoot 'assets\proxy-transcript.ico'
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\Proxy Transcript'
$launcher = Join-Path $installDir 'ProxyTranscriptLauncher.exe'
$projectPointer = Join-Path $installDir 'project-path.txt'

if (-not (Test-Path -LiteralPath $launcherSource)) {
    throw "Launcher source not found: $launcherSource"
}
if (-not (Test-Path -LiteralPath $icon)) {
    throw "Icon not found: $icon"
}

$compilerCandidates = @(
    (Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:SystemRoot 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) {
    throw 'The Windows C# compiler was not found.'
}

New-Item -ItemType Directory -Path $installDir -Force | Out-Null

$needsBuild = -not (Test-Path -LiteralPath $launcher) -or
    (Get-Item -LiteralPath $launcherSource).LastWriteTimeUtc -gt (Get-Item -LiteralPath $launcher).LastWriteTimeUtc -or
    (Get-Item -LiteralPath $icon).LastWriteTimeUtc -gt (Get-Item -LiteralPath $launcher).LastWriteTimeUtc

if ($needsBuild) {
    & $compiler /nologo /target:winexe /optimize+ /win32icon:"$icon" /out:"$launcher" "$launcherSource"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $launcher)) {
        throw 'Failed to build ProxyTranscriptLauncher.exe.'
    }
}

Set-Content -LiteralPath $projectPointer -Value $projectRoot -Encoding UTF8

$startMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$startShortcut = Join-Path $startMenuDir 'Game Immersion Toolkit.lnk'

New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null

function New-ProxyShortcut([string]$path) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $launcher
    $shortcut.Arguments = ''
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = "$icon,0"
    $shortcut.Description = 'Start Game Immersion Toolkit'
    $shortcut.Save()
}

New-ProxyShortcut $startShortcut

Write-Host "Start menu shortcut: $startShortcut"
Write-Host 'The taskbar pin is managed by Windows and is not written directly into its internal pinned-items folder.'
