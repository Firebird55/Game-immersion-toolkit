$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot 'start-companion.ps1'
$icon = Join-Path $projectRoot 'assets\proxy-transcript.ico'
$powerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Launcher not found: $launcher"
}
if (-not (Test-Path -LiteralPath $icon)) {
    throw "Icon not found: $icon"
}

$startMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$taskbarDir = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
$startShortcut = Join-Path $startMenuDir 'Proxy Transcript.lnk'
$taskbarShortcut = Join-Path $taskbarDir 'Proxy Transcript.lnk'

New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
New-Item -ItemType Directory -Path $taskbarDir -Force | Out-Null

function New-ProxyShortcut([string]$path) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $powerShell
    $shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`""
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = "$icon,0"
    $shortcut.Description = 'Start the Proxy Transcript companion in Chrome'
    $shortcut.Save()
}

New-ProxyShortcut $startShortcut
New-ProxyShortcut $taskbarShortcut

# Windows 11 may ignore programmatic pin verbs, but invoking one when exposed
# makes the icon appear immediately on systems that still support the verb.
try {
    $shellApplication = New-Object -ComObject Shell.Application
    $folder = $shellApplication.Namespace($startMenuDir)
    $item = $folder.ParseName((Split-Path -Leaf $startShortcut))
    $pinVerb = $item.Verbs() | Where-Object {
        ($_.Name -replace '&', '') -match 'taskbar|taakbalk'
    } | Select-Object -First 1
    if ($pinVerb) {
        $pinVerb.DoIt()
    }
}
catch {
    Write-Verbose "Windows did not expose a taskbar pin verb: $($_.Exception.Message)"
}

Write-Host "Start menu shortcut: $startShortcut"
Write-Host "Taskbar shortcut:   $taskbarShortcut"
