param(
    [Parameter(Mandatory = $true)][string]$InputManifest,
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$OutputRoot,
    [switch]$DiagnosticOnly,
    [switch]$FrontendExperiment,
    [switch]$RuntimeExperiment
)
$ErrorActionPreference = 'Stop'

function Invoke-RuntimeExperimentFreezer {
    param(
        [Parameter(Mandatory = $true)][string]$SelectedPython,
        [Parameter(Mandatory = $true)][string]$EnvironmentHelper,
        [Parameter(Mandatory = $true)][string[]]$FreezerArguments
    )
    # Private pipe only. Do not print selected roots or put them in a receipt.
    $query = @(& $SelectedPython -B $EnvironmentHelper --selected-python $SelectedPython)
    if ($LASTEXITCODE -ne 0 -or $query.Count -ne 1 -or $query[0].Length -gt 200000) {
        throw 'Experimental freezer PATH query failed.'
    }
    try { $environment = $query[0] | ConvertFrom-Json -AsHashtable } catch {
        throw 'Experimental freezer PATH query failed.'
    }
    if ($environment -isnot [System.Collections.IDictionary] -or $environment.Count -ne 2 -or
        -not $environment.Contains('schema') -or -not $environment.Contains('path') -or
        $environment.schema -isnot [string] -or $environment.schema -cne 'proxy-r19-runtime-build-environment-v1' -or
        $environment.path -isnot [string] -or [string]::IsNullOrEmpty($environment.path) -or
        $environment.path.Length -gt 32766 -or $environment.path -match '[\x00-\x1f\x7f"]' -or
        $environment.path.Split(';').Count -gt 5 -or
        @($environment.path.Split(';') | Where-Object { [string]::IsNullOrEmpty($_) }).Count -ne 0) {
        throw 'Experimental freezer PATH query failed.'
    }
    $hadPath = Test-Path Env:PATH
    $previousPath = $env:PATH
    try {
        $env:PATH = $environment.path
        & $SelectedPython -B -m PyInstaller @FreezerArguments
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed; retain quarantined output for inspection.' }
    } finally {
        if ($hadPath) { $env:PATH = $previousPath } else { Remove-Item Env:PATH -ErrorAction Stop }
        if ((Test-Path Env:PATH) -ne $hadPath -or $env:PATH -cne $previousPath) {
            throw 'Experimental freezer parent PATH restoration failed.'
        }
    }
}

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
if ($RuntimeExperiment -and $Inputs.profile -ne 'runtime-experiment') { throw '-RuntimeExperiment requires the runtime-experiment profile.' }
if (@($DiagnosticOnly, $FrontendExperiment, $RuntimeExperiment | Where-Object { $_ }).Count -ne 1) { throw 'Choose exactly one quarantined experimental profile.' }
if ($DoctorExit -ne 0 -and -not (($DiagnosticOnly -or $FrontendExperiment -or $RuntimeExperiment) -and $DoctorExit -eq 2)) {
    throw 'Development prerequisites are unavailable; no build was started.'
}
if ($DoctorExit -ne 0) { Write-Host 'Application doctor unavailable. Exact experimental inputs and hosted probes must establish their own limited scope.' }
$Policy = Join-Path $SourceRoot 'packaging/runtime-bundle/closure.py'
& $Python -B $Policy preflight --inputs $InputManifest --evidence $EvidenceRoot --source $SourceRoot
if ($LASTEXITCODE -ne 0) { throw 'Exact input/source/hash/license/native evidence is incomplete.' }
$PreviousInputs = $env:PROXY_RUNTIME_BUILD_INPUTS
$PreviousEvidence = $env:PROXY_RUNTIME_EVIDENCE_ROOT
try {
    $env:PROXY_RUNTIME_BUILD_INPUTS = $InputManifest
    $env:PROXY_RUNTIME_EVIDENCE_ROOT = $EvidenceRoot
    $freezerArguments = @('--noconfirm', '--clean', '--distpath', (Join-Path $OutputRoot 'quarantine'),
        '--workpath', (Join-Path $OutputRoot 'build'), (Join-Path $SourceRoot 'packaging/runtime-bundle/runtime.spec'))
    if ($RuntimeExperiment) {
        Invoke-RuntimeExperimentFreezer -SelectedPython $Python -EnvironmentHelper (Join-Path $SourceRoot 'packaging/runtime-bundle/build_environment.py') -FreezerArguments $freezerArguments
    } else {
        & $Python -B -m PyInstaller @freezerArguments
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed; retain quarantined output for inspection.' }
    }
    & $Python -B $Policy finalize --inputs $InputManifest --evidence $EvidenceRoot --source $SourceRoot --output (Join-Path $OutputRoot 'quarantine')
    if ($LASTEXITCODE -ne 0) { throw 'Collected candidate failed the private/proprietary artifact gate.' }
    @{ schema = 'proxy-runtime-build-check-v1'; doctor_exit = $DoctorExit; diagnostic_only = [bool]$DiagnosticOnly; r19_complete = $false } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputRoot 'build-check.json') -Encoding UTF8
    Write-Host 'Quarantined candidate built. Exact output redistribution review and Windows 11 25H2 acceptance remain incomplete. No release asset was created.'
} finally {
    $env:PROXY_RUNTIME_BUILD_INPUTS = $PreviousInputs
    $env:PROXY_RUNTIME_EVIDENCE_ROOT = $PreviousEvidence
}
