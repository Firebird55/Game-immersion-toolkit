param([switch]$NoGamePicker, [switch]$Contribute, [switch]$InstructionsOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Write-Host 'Game immersion toolkit: local Windows OCR and verified bilingual game text.'
Write-Host 'Requirements: Windows Snipping Tool, Python 3.12 and Node.js 24 with npm 10+.'
Write-Host 'Game files stay in your own installation; they are never uploaded or bundled.'
Write-Host 'Contributors and AI agents: read AGENTS.md, CONTRIBUTING.md and RELEASE.md.'
Write-Host 'Preserve user data/credentials, commit logical changes, run checks before pushing.'
Write-Host 'Edit shared UI only in Lexirise-shared-components; never edit generated vendor copies.'
Write-Host 'Release with npm run release -- --version <semver>; verify hosted Actions and assets.'
if ($InstructionsOnly) { return }
& (Join-Path $PSScriptRoot 'setup.ps1')
if (-not $NoGamePicker) { & (Join-Path $PSScriptRoot 'select-game-folders.ps1') }
if ($Contribute) { Start-Process -FilePath (Join-Path $projectRoot 'CONTRIBUTING.md') -WindowStyle Hidden }
Write-Host 'Installation complete. Launch Start Proxy Transcript.cmd. Re-run Choose Game Folders.cmd after moving a game.'
