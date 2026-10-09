$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$installDir = Join-Path $env:LOCALAPPDATA 'Programs\Proxy Transcript'
$venvDir = Join-Path $installDir 'venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
New-Item -ItemType Directory -Path $installDir -Force | Out-Null

$pythonCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    'C:\Python312\python.exe',
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
$basePython = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $basePython) { throw 'Python 3.12 was not found.' }

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $basePython -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

& $venvPython -m pip install --disable-pip-version-check --timeout 120 --retries 8 -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

# The Python oneocr package expects the native OCR files from Windows Snipping
# Tool in the current user's profile. Without them capture starts but fails as
# soon as a game window appears, so verify them during setup.
$snippingTool = Get-AppxPackage -Name Microsoft.ScreenSketch | Select-Object -First 1
if (-not $snippingTool) { throw 'Windows Snipping Tool is required for OCR.' }
$ocrSource = Join-Path $snippingTool.InstallLocation 'SnippingTool'
$ocrTarget = Join-Path $env:USERPROFILE '.config\oneocr'
New-Item -ItemType Directory -Path $ocrTarget -Force | Out-Null
foreach ($name in @('oneocr.dll', 'oneocr.onemodel', 'onnxruntime.dll')) {
    $source = Join-Path $ocrSource $name
    if (-not (Test-Path -LiteralPath $source)) { throw "Windows Snipping Tool OCR file is missing: $name" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $ocrTarget $name) -Force
}
& $venvPython -c 'from oneocr import OcrEngine; OcrEngine()'
if ($LASTEXITCODE -ne 0) { throw 'Native OCR initialization failed.' }


$vinext = Join-Path $projectRoot 'node_modules\vinext\dist\cli.js'
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Install Node.js 24 LTS (including npm), then run setup again.' }
$npmMajor = [int]((& npm --version).Split('.')[0])
if ($npmMajor -lt 10) { throw 'npm 10 or newer is required. Install current Node.js LTS or run npm install -g npm@11, then retry.' }
& npm ci
if ($LASTEXITCODE -ne 0) { throw 'Locked frontend dependency installation failed.' }

$wasRunning = $false
try {
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:3000/' -UseBasicParsing -TimeoutSec 2
    $wasRunning = $response.StatusCode -eq 200
} catch { }
if ($wasRunning) {
    & (Join-Path $PSScriptRoot 'stop-companion.ps1')
    Start-Sleep -Seconds 1
}

& node $vinext build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'data\textmaps\zh_base.json'))) {
    & $venvPython -m scripts.download_textmaps
    if ($LASTEXITCODE -ne 0) { throw 'TextMap download failed.' }
}

& (Join-Path $PSScriptRoot 'install-shortcuts.ps1')
if ($wasRunning) { & (Join-Path $PSScriptRoot 'start-companion.ps1') -NoBrowser }
Write-Host 'Proxy Transcript is ready. Launch it from Start or the taskbar.'
