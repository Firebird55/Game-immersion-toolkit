"""Exercise the real bounded hash build call without starting Gradle or NDK."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('compiler_status', [0, 1])
def test_actual_powershell_hash_stage_passes_explicit_pinned_inputs_and_stops_on_failure(tmp_path, compiler_status):
    shell=shutil.which('pwsh')
    if not shell: pytest.skip('PowerShell 7 is required for the actual assembly stage')
    script=r'''
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $env:TOOLKIT_SOURCE 'scripts/build-android-app.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Actual assembly script failed to parse'}
$parameter=@($ast.ParamBlock.Parameters | Where-Object {$_.Name.VariablePath.UserPath -eq 'PublisherHashSourceArchive'})
if($parameter.Count -ne 1 -or $parameter[0].Extent.Text -notmatch 'Mandatory=\$true'){throw 'Original hash supplier must be explicit and mandatory'}
$BuildRoot=Join-Path $env:TOOLKIT_TEST 'private build'
$PublisherHashSourceArchive=Join-Path $env:TOOLKIT_TEST 'original xxhash.tar.gz'
$SdkRoot=Join-Path $env:TOOLKIT_TEST 'physical SDK'
$NdkArchive=Join-Path $env:TOOLKIT_TEST 'original ndk.zip'
$fixtureScripts=Join-Path $env:TOOLKIT_SOURCE 'scripts'
$Python='Invoke-AuthoredPython';$script:called=0
function Invoke-AuthoredPython {
  $script:called++
  $expected=@((Join-Path $fixtureScripts 'build-android-publisher-hash.py'),'--work-dir',(Join-Path $BuildRoot 'publisher-hash'),
    '--source',$PublisherHashSourceArchive,'--ndk',(Join-Path $SdkRoot 'ndk/27.3.13750724'),'--ndk-archive',$NdkArchive)
  if($args.Count -ne $expected.Count){throw 'Actual hash builder arguments missing'}
  for($i=0;$i -lt $expected.Count;$i++){if($args[$i] -ne $expected[$i]){throw 'Actual hash build supplier/ABI arguments changed'}}
  $global:LASTEXITCODE=[int]$env:TOOLKIT_COMPILER_STATUS
  Write-Output 'actual-authored-compiler-invoked'
}
$source=$ast.Extent.Text
$start=$source.IndexOf('$hashRoot=')
$end=$source.IndexOf('$env:ANDROID_CRYPTO_FIXTURES=', $start)
if($start -lt 0 -or $end -le $start){throw 'Actual hash build stage missing'}
# Dynamic evaluation has no script path. Bind only that automatic variable to
# the real maintained script directory; execute all stage statements unchanged.
Invoke-Expression $source.Substring($start,$end-$start).Replace('$PSScriptRoot','$fixtureScripts')
if($script:called -ne 1 -or $env:ANDROID_PUBLISHER_HASH -ne (Join-Path $BuildRoot 'publisher-hash')){throw 'Actual hash output not handed to Gradle'}
Write-Output 'actual-hash-build-handoff-passed'
'''
    result=subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=30,
        env={**os.environ,'TOOLKIT_SOURCE':str(ROOT),'TOOLKIT_TEST':str(tmp_path),'TOOLKIT_COMPILER_STATUS':str(compiler_status)})
    assert 'actual-authored-compiler-invoked' in result.stdout,result.stdout+result.stderr
    if compiler_status:
        assert result.returncode!=0 and 'actual-hash-build-handoff-passed' not in result.stdout
        assert 'authenticated publisher hash software build failed' in result.stderr
    else:
        assert result.returncode==0,result.stdout+result.stderr
        assert 'actual-hash-build-handoff-passed' in result.stdout


def test_every_committed_workflow_build_caller_supplies_the_pinned_hash_archive():
    calls=[]
    for path in (ROOT/'.github/workflows').glob('*.yml'):
        calls.extend(line for line in path.read_text().splitlines() if './scripts/build-android-app.ps1 ' in line)
    assert calls and all('-PublisherHashSourceArchive ' in line for line in calls)

