param(
    [Parameter(Mandatory = $true)][string]$InputManifest,
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$OutputRoot,
    [switch]$DiagnosticOnly,
    [switch]$FrontendExperiment
)
$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $SourceRoot 'output/runtime-bundle' }
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitProcess) {
    throw 'Build on Windows x64. macOS/Linux cannot establish a Windows bundle.'
}
$InputManifest = (Resolve-Path -LiteralPath $InputManifest).Path
$EvidenceRoot = (Resolve-Path -LiteralPath $EvidenceRoot).Path
$Python = (Resolve-Path -LiteralPath $Python).Path
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw 'Choose a new empty output path; existing candidates are preserved.' }
# Never prepare/install implicitly: the build operator provisions the reviewed
# interpreter and exact packaging wheels before invoking this script.
& npm --prefix $SourceRoot run dev:doctor -- --base upstream/main
$DoctorExit = $LASTEXITCODE
$Inputs = Get-Content -LiteralPath $InputManifest -Raw | ConvertFrom-Json
if ($DiagnosticOnly -and $Inputs.profile -ne 'diagnostic') { throw '-DiagnosticOnly requires the diagnostic profile.' }
if ($FrontendExperiment -and $Inputs.profile -ne 'frontend-experiment') { throw '-FrontendExperiment requires the frontend-experiment profile.' }
if ($DiagnosticOnly -and $FrontendExperiment) { throw 'Choose one quarantined experimental profile.' }
if ($DoctorExit -ne 0 -and -not (($DiagnosticOnly -or $FrontendExperiment) -and $DoctorExit -eq 2)) {
    throw 'Development prerequisites are unavailable; no build was started.'
}
if ($DoctorExit -ne 0) { Write-Host 'Application doctor unavailable. Only the separately validated diagnostic/frontend subset may proceed.' }
$Policy = Join-Path $SourceRoot 'packaging/runtime-bundle/closure.py'
& $Python -B $Policy preflight --inputs $InputManifest --evidence $EvidenceRoot --source $SourceRoot
if ($LASTEXITCODE -ne 0) { throw 'Exact input/source/hash/license/native evidence is incomplete.' }
$PreviousInputs = $env:PROXY_RUNTIME_BUILD_INPUTS
$PreviousEvidence = $env:PROXY_RUNTIME_EVIDENCE_ROOT
try {
    $env:PROXY_RUNTIME_BUILD_INPUTS = $InputManifest
    $env:PROXY_RUNTIME_EVIDENCE_ROOT = $EvidenceRoot
    & $Python -B -m PyInstaller --noconfirm --clean --distpath (Join-Path $OutputRoot 'quarantine') --workpath (Join-Path $OutputRoot 'build') (Join-Path $SourceRoot 'packaging/runtime-bundle/runtime.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed; retain quarantined output for inspection.' }
    & $Python -B $Policy finalize --inputs $InputManifest --evidence $EvidenceRoot --source $SourceRoot --output (Join-Path $OutputRoot 'quarantine')
    if ($LASTEXITCODE -ne 0) { throw 'Collected candidate failed the private/proprietary artifact gate.' }
    @{ schema = 'proxy-runtime-build-check-v1'; doctor_exit = $DoctorExit; diagnostic_only = [bool]$DiagnosticOnly; r19_complete = $false } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputRoot 'build-check.json') -Encoding UTF8
    Write-Host 'Quarantined candidate built. Exact output redistribution review and Windows 11 25H2 acceptance remain incomplete. No release asset was created.'
} finally {
    $env:PROXY_RUNTIME_BUILD_INPUTS = $PreviousInputs
    $env:PROXY_RUNTIME_EVIDENCE_ROOT = $PreviousEvidence
}
