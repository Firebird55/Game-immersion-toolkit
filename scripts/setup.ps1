$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe')) {
    python -m venv .venv
}

& '.\.venv\Scripts\python.exe' -m pip install --disable-pip-version-check -r requirements.txt
npm install
npm run build
& '.\.venv\Scripts\python.exe' -m scripts.download_textmaps
& (Join-Path $PSScriptRoot 'install-shortcuts.ps1')

Write-Host ''
Write-Host 'Proxy Transcript is ready. Launch it from Start or the taskbar.'
