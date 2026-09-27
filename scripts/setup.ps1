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

& $venvPython -m pip install --disable-pip-version-check --timeout 120 --retries 8 -r requirements.txt
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

$vadTarget = Join-Path $projectRoot 'assets\fireredvad'
$vadSource = 'https://raw.githubusercontent.com/FireRedTeam/FireRedVAD/c30ec49e8cc69642b0ee65362eba11b9d11c6e54/pretrained_models/onnx_models'
$vadFiles = @{
    'cmvn.ark' = 'C87F6F13EDF0F0EC7535DDFC9CC3387D9268CB234B70182D566C5E2EDF3CA473'
    'fireredvad_vad.onnx' = 'A226E68E695548754A9AB5480A55BBCB8522AA69111CB97E4F093DDCE63AD5DC'
}
New-Item -ItemType Directory -Path $vadTarget -Force | Out-Null
foreach ($name in $vadFiles.Keys) {
    $destination = Join-Path $vadTarget $name
    if (-not (Test-Path -LiteralPath $destination) -or
        (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $vadFiles[$name]) {
        Invoke-WebRequest -Uri "$vadSource/$name" -OutFile $destination -TimeoutSec 60
    }
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $vadFiles[$name]) {
        throw "FireRedVAD model verification failed: $name"
    }
}
& $venvPython -c 'from backend.firered_vad import FireRedVad; FireRedVad()'
if ($LASTEXITCODE -ne 0) { throw 'Voice validation model initialization failed.' }

$vinext = Join-Path $projectRoot 'node_modules\vinext\dist\cli.js'
if (-not (Test-Path -LiteralPath $vinext)) {
    throw 'Node packages are missing. Restore node_modules from the source ZIP before building.'
}

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
