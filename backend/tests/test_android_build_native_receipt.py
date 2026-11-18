"""Execute the actual PowerShell post-assembly stage with composite receipts."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def native_stage(tmp_path):
    shell=shutil.which('pwsh')
    if not shell:pytest.skip('PowerShell 7 is required for the actual Windows build stage')
    base={'schema':'toolkit-android-python-wheels-v1','policy_sha256':'a'*64,'native':{},'rapidfuzz_native':{}}
    audit={'native_files':{}}
    for abi in ('arm64-v8a','x86_64'):
        base['native'][abi]={'native_sha256':'b'*64}
        base['rapidfuzz_native'][abi]={'modules':{name:{'sha256':'c'*64} for name in (
            'rapidfuzz/utils_cpp.so','rapidfuzz/fuzz_cpp.so','rapidfuzz/process_cpp_impl.so',
            'rapidfuzz/distance/_initialize_cpp.so','rapidfuzz/distance/metrics_cpp.so')}}
        prefix='assets/chaquopy/requirements-'+abi+'.imy/'
        audit['native_files'][prefix+'pydantic_core/_pydantic_core.so']={'sha256':'b'*64}
        for name in base['rapidfuzz_native'][abi]['modules']:audit['native_files'][prefix+name]={'sha256':'c'*64}
    composite={'schema':'toolkit-android-runtime-wheels-v2','base_receipt_sha256':''}
    def publish():
        raw=json.dumps(base).encode();(tmp_path/'python-base-wheels-receipt.json').write_bytes(raw)
        composite['base_receipt_sha256']=hashlib.sha256(raw).hexdigest()
        (tmp_path/'python-wheels-receipt.json').write_text(json.dumps(composite))
        (tmp_path/'audit.json').write_text(json.dumps(audit))
    script=tmp_path/'actual-stage.ps1'
    script.write_text(r'''
param([string]$Repository,[string]$Wheelhouse)
$ErrorActionPreference='Stop'
. (Join-Path $Repository 'scripts/android-build-paths.ps1')
$errors=$null;$tokens=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $Repository 'scripts/build-android-app.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Build script syntax error'}
$functions=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Read-AndroidBoundBaseReceipt'},$true))
if($functions.Count -ne 1){throw 'Missing actual bound-receipt stage'}
Invoke-Expression $functions[0].Extent.Text
$receipt=Get-Content -LiteralPath (Join-Path $Wheelhouse 'python-wheels-receipt.json') -Raw | ConvertFrom-Json
$nativeAudit=Get-Content -LiteralPath (Join-Path $Wheelhouse 'audit.json') -Raw | ConvertFrom-Json
$policyHash='a'*64;$policy=[pscustomobject]@{abis=@('arm64-v8a','x86_64')}
$baseReceipt=Read-AndroidBoundBaseReceipt $Wheelhouse $receipt $policyHash
$loops=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.ForEachStatementAst] -and $n.Variable.VariablePath.UserPath -eq 'abi'},$true))
if($loops.Count -ne 1){throw 'Missing actual APK native hash stage'}
Invoke-Expression $loops[0].Extent.Text
Write-Output 'actual-native-hash-stage-passed'
''')
    def run():return subprocess.run([shell,'-NoProfile','-File',str(script),str(ROOT),str(tmp_path)],capture_output=True,text=True,timeout=30)
    publish();return base,composite,audit,tmp_path,publish,run


def test_v2_composite_without_top_level_native_fields_uses_its_exact_preserved_base(native_stage):
    base,composite,audit,path,publish,run=native_stage
    assert 'native' not in composite and 'rapidfuzz_native' not in composite
    result=run()
    assert result.returncode==0,result.stderr
    assert 'actual-native-hash-stage-passed' in result.stdout


@pytest.mark.parametrize('change',['changed-bytes','missing','base-schema','base-policy','composite-schema','missing-binding','core-hash','missing-rapid','rapid-hash'])
def test_actual_post_assembly_stage_rejects_changed_missing_or_foreign_receipts_and_apk_bytes(native_stage,change):
    base,composite,audit,path,publish,run=native_stage
    if change=='base-schema':base['schema']='unbound-base-v0'
    elif change=='base-policy':base['policy_sha256']='f'*64
    elif change=='composite-schema':composite['schema']='unverified-runtime-v0'
    elif change=='core-hash':next(v for k,v in audit['native_files'].items() if '/pydantic_core/' in k)['sha256']='f'*64
    elif change=='missing-rapid':audit['native_files'].pop(next(k for k in audit['native_files'] if '/rapidfuzz/' in k))
    elif change=='rapid-hash':next(v for k,v in audit['native_files'].items() if '/rapidfuzz/' in k)['sha256']='f'*64
    publish()
    if change=='changed-bytes':
        target=path/'python-base-wheels-receipt.json';target.write_bytes(target.read_bytes()+b'\n')
    elif change=='missing':(path/'python-base-wheels-receipt.json').unlink()
    elif change=='missing-binding':
        composite.pop('base_receipt_sha256');(path/'python-wheels-receipt.json').write_text(json.dumps(composite))
    result=run()
    assert result.returncode!=0,'A changed receipt or native APK byte identity was accepted'
    assert 'actual-native-hash-stage-passed' not in result.stdout


@pytest.mark.parametrize('change', [None, 'older-source', 'older-version', 'missing-source', 'missing-version'])
def test_release_build_binds_input_and_packaged_frontend_to_the_exact_tag(tmp_path, change):
    shell = shutil.which('pwsh')
    if not shell:
        pytest.skip('PowerShell 7 is required for the actual Android release stage')
    script = tmp_path / 'actual-frontend-stage.ps1'
    script.write_text(r'''
param([string]$Builder,[string]$Manifest)
$ErrorActionPreference='Stop'
$errors=$null;$tokens=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Builder,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Invalid release builder syntax'}
$functions=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Assert-AndroidReleaseFrontend'},$true))
$binding=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Assert-AndroidReleaseFrontend'},$true))
if($functions.Count -ne 1 -or $binding.Count -ne 2 -or
        $binding[0].Extent.Text -ne 'Assert-AndroidReleaseFrontend $frontendManifest $head $version' -or
        $binding[1].Extent.Text -ne 'Assert-AndroidReleaseFrontend $nativeAudit.frontend $head $version') {
    throw 'The release requires both exact frontend bindings'
}
Invoke-Expression $functions[0].Extent.Text
Assert-AndroidReleaseFrontend (Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json) ('a'*40) '1.2.3'
Write-Output 'release-frontend-bound'
''', encoding='utf8')
    frontend = {'source_commit': 'a' * 40, 'version': '1.2.3'}
    if change == 'older-source':
        frontend['source_commit'] = 'b' * 40
    elif change == 'older-version':
        frontend['version'] = '1.2.2'
    elif change == 'missing-source':
        del frontend['source_commit']
    elif change == 'missing-version':
        del frontend['version']
    manifest = tmp_path / 'desktop-manifest.json'
    manifest.write_text(json.dumps(frontend), encoding='utf8')
    output = subprocess.run([shell, '-NoProfile', '-File', str(script), str(ROOT / 'scripts/build-android-app.ps1'),
                             str(manifest)], capture_output=True, text=True, timeout=30)
    if change is None:
        assert output.returncode == 0, output.stderr
        assert 'release-frontend-bound' in output.stdout
    else:
        assert output.returncode != 0
        assert 'frontend must match the exact tagged source and version' in output.stderr
        assert 'release-frontend-bound' not in output.stdout
