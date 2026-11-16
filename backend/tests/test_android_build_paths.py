"""Installed tool aliases must not become an exception for writable roots."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='The supplier alias regression is a Windows junction')
def test_real_supplier_junction_and_ancestor_alias_resolve_without_weakening_owned_roots(tmp_path):
    powershell = shutil.which('pwsh')
    if not powershell:
        pytest.fail('PowerShell 7.2 or later is required for Android Windows build-path acceptance')
    helper = Path(__file__).resolve().parents[2] / 'scripts/android-build-paths.ps1'
    script = r'''
$ErrorActionPreference='Stop'
. $env:TOOLKIT_ANDROID_PATH_HELPER
$physical=Join-Path $env:TOOLKIT_ANDROID_PATH_ROOT 'supplier with spaces'
$alias=Join-Path $env:TOOLKIT_ANDROID_PATH_ROOT 'installed-alias'
New-Item -ItemType Directory -Path (Join-Path $physical 'bin') -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $physical 'proof.bin'),'authored supplier identity')
[IO.File]::WriteAllText((Join-Path $physical 'bin/python.exe'),'authored non-executable tool fixture')
New-Item -ItemType Junction -Path $alias -Target $physical | Out-Null
try {
    $resolved=Resolve-AndroidSupplierPath $alias 'Authored SDK' @('proof.bin')
    if($resolved -ne $physical){throw 'The supplier root did not resolve physically.'}
    $program=Resolve-AndroidSupplierPath (Join-Path $alias 'bin/python.exe') 'Authored Python' @('')
    if($program -ne (Join-Path $physical 'bin/python.exe')){throw 'The ancestor alias survived.'}
    Assert-AndroidNoLinks $resolved
    $rejected=$false
    try {Assert-AndroidNoLinks (Join-Path $alias 'writable-output')} catch {$rejected=$true}
    if(-not $rejected){throw 'A writable-root alias was incorrectly accepted.'}
    if([IO.File]::ReadAllText((Join-Path $physical 'proof.bin')) -ne 'authored supplier identity'){throw 'Supplier bytes changed.'}
} finally {
    $target=(Get-Item -LiteralPath $alias -Force).ResolveLinkTarget($true).FullName
    if($target -ne $physical){throw 'Unexpected junction cleanup target.'}
    Remove-Item -LiteralPath $alias -Force
}
'''
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', script],
        env={**os.environ, 'TOOLKIT_ANDROID_PATH_ROOT': str(tmp_path), 'TOOLKIT_ANDROID_PATH_HELPER': str(helper)},
        text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
