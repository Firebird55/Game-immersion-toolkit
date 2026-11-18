"""Run real hosted acquisition commands in an empty workspace, without HTTP."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request

import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('kind',['zstandard','crypto'])
def test_actual_hosted_software_callers_create_cold_cache_and_keep_pin_verification(tmp_path,monkeypatch,kind):
    lines=(ROOT/'.github/workflows/android-shared-core.yml').read_text().splitlines()
    commands=[re.fullmatch(r'\s+python -c "(.+)"',line)[1] for line in lines if 'm.acquire(' in line]
    assert len(commands)==2
    command=next(value for value in commands if ('android-zstandard' if kind=='zstandard' else 'android-crypto-source') in value)
    scripts=tmp_path/'scripts';scripts.mkdir()
    shutil.copyfile(ROOT/'scripts/build-android-python-dependencies.py',scripts/'build-android-python-dependencies.py')
    policy=tmp_path/'packaging/android';policy.mkdir(parents=True)
    raw=b'Authored software source fixture; not a real dependency acquisition.'
    pin={'source':'https://software.invalid/original','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    name='zstandard-native.json' if kind=='zstandard' else 'publisher-crypto-native.json'
    (policy/name).write_text(json.dumps(pin if kind=='zstandard' else {'source':pin}))
    cache=tmp_path/'output'/('android-zstandard' if kind=='zstandard' else 'android-crypto-source')
    archive=cache/('zstandard-0.25.0.tar.gz' if kind=='zstandard' else 'pycryptodome-3.24.1.tar.gz')
    calls=[]
    def fetch(url,*,timeout):
        assert url==pin['source'] and timeout==60
        assert cache.is_dir(),'The actual workflow must create its owned directory before any transfer.'
        calls.append(url);return io.BytesIO(raw)
    monkeypatch.setattr(urllib.request,'urlopen',fetch)
    monkeypatch.chdir(tmp_path)
    assert not cache.exists()
    exec(compile(command,'actual-hosted-command','exec'),{'__name__':'authored_workflow'})
    assert archive.read_bytes()==raw and len(calls)==1
    exec(compile(command,'actual-hosted-command','exec'),{'__name__':'authored_workflow'})
    assert len(calls)==1,'Verified warm inputs must not be acquired again.'
    archive.write_bytes(b'changed software')
    with pytest.raises(ValueError,match='checksum mismatch'):
        exec(compile(command,'actual-hosted-command','exec'),{'__name__':'authored_workflow'})
    assert len(calls)==1,'A changed cached input must be rejected, never silently replaced.'


@pytest.mark.skipif(sys.platform != 'win32', reason='The hosted supplier alias is a Windows junction')
def test_actual_zstandard_workflow_uses_verified_physical_ndk_and_keeps_private_link_guard(tmp_path):
    lines=(ROOT/'.github/workflows/android-shared-core.yml').read_text().splitlines()
    start=next(i for i,line in enumerate(lines) if '- name: Build reviewed Zstandard ABIs' in line)
    end=next(i for i in range(start+1,len(lines)) if lines[i].startswith('      - name:'))
    actual='\n'.join(line.removeprefix('          ') for line in lines[start+2:end])
    script=r'''
$ErrorActionPreference='Stop'
Set-Location $env:TOOLKIT_WORKFLOW_ROOT
$sdk=Join-Path $env:TOOLKIT_FIXTURE_ROOT 'physical-sdk'
$alias=Join-Path $env:TOOLKIT_FIXTURE_ROOT 'runner-sdk-alias'
$original=Join-Path $sdk 'ndk/27.3.13750724'
New-Item -ItemType Directory -Path (Join-Path $original 'toolchains/llvm/prebuilt/windows-x86_64/bin') -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $original 'source.properties'),'Pkg.Revision=27.3.13750724')
[IO.File]::WriteAllText((Join-Path $original 'toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe'),'authored compiler bytes; never executed')
New-Item -ItemType Junction -Path $alias -Target $sdk | Out-Null
$env:ANDROID_HOME=$alias
$global:LASTEXITCODE=0
$script:compilerCalls=0
function python {
    if($args[0] -eq 'scripts/build-android-zstandard.py') {
        $script:compilerCalls++
        $position=[array]::IndexOf($args,'--ndk-root')
        if($position -lt 0 -or $args[$position+1] -ne $original){throw 'Workflow passed an installed alias into the guarded compiler.'}
        Assert-AndroidNoLinks $args[$position+1]
    }
    $global:LASTEXITCODE=0
}
try {
    Invoke-Expression $env:TOOLKIT_ACTUAL_WORKFLOW_STEP
    if($script:compilerCalls -ne 1){throw 'The actual guarded compiler call was not exercised.'}
    $rejected=$false
    try {Assert-AndroidNoLinks (Join-Path $alias 'mutable-output')} catch {$rejected=$true}
    if(-not $rejected){throw 'A writable alias incorrectly became admissible.'}
} finally {
    if((Get-Item -LiteralPath $alias).ResolveLinkTarget($true).FullName -ne $sdk){throw 'Unexpected junction cleanup target.'}
    Remove-Item -LiteralPath $alias -Force
}
'''
    result=subprocess.run([shutil.which('pwsh'),'-NoProfile','-NonInteractive','-Command',script],
        env={**os.environ,'TOOLKIT_FIXTURE_ROOT':str(tmp_path),'TOOLKIT_WORKFLOW_ROOT':str(ROOT),
             'TOOLKIT_ACTUAL_WORKFLOW_STEP':actual},capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
