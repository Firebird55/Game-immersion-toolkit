"""Exercise real owner ACL, DPAPI and reusable key/version reservations on Windows."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='The actual identity adapter is Windows CurrentUser DPAPI')
def test_real_protected_identity_roundtrip_and_version_fences(tmp_path):
    java = shutil.which('keytool')
    if java is None:
        java = 'C:/Program Files/Java/jdk-19/bin/keytool.exe'
    if not Path(java).is_file():
        pytest.skip('The actual JDK keytool is unavailable')
    repository = Path(__file__).resolve().parents[2]
    script = tmp_path / 'signing-proof.ps1'
    identity = tmp_path / 'owned-identity'
    script.write_text(r'''
param($Source,$Identity,$Java)
$ErrorActionPreference='Stop'
. (Join-Path $Source 'scripts/android-build-paths.ps1')
. (Join-Path $Source 'scripts/android-signing.ps1')
$first=Initialize-AndroidSigningIdentity $Identity $Java
$second=Reserve-AndroidSigningVersion $Identity 5
$certificate=$second.record.signing_certificate_sha256
try {
    if($second.password.Length -ne 64){throw 'DPAPI roundtrip failed'}
    $locked=$false
    try {$unexpected=Reserve-AndroidSigningVersion $Identity 6;$unexpected.lock.Dispose()}catch{$locked=$true}
    if(-not $locked){throw 'Concurrent signer reservation escaped the exclusive lock'}
}finally{$second.password=$null;$second.lock.Dispose()}
$duplicate=$false
try {$unexpected=Reserve-AndroidSigningVersion $Identity 5;$unexpected.lock.Dispose()}catch{$duplicate=$true}
if(-not $duplicate){throw 'A duplicate version code was admitted'}
$third=Reserve-AndroidSigningVersion $Identity 6
try {if($third.record.signing_certificate_sha256 -ne $certificate){throw 'Signer changed on reuse'}}
finally{$third.password=$null;$third.lock.Dispose()}
$overwrite=$false
try {Initialize-AndroidSigningIdentity $Identity $Java | Out-Null}catch{$overwrite=$true}
if(-not $overwrite){throw 'Existing owner key could be overwritten'}
$plaintext=[Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes((Join-Path $Identity 'password.dpapi')))
if($plaintext -match '^[A-Za-z0-9+/]{64}$'){throw 'Signing password was written as plaintext'}
$acl=Get-Acl -LiteralPath (Join-Path $Identity 'password.dpapi')
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-1-0'),'Read','Allow'))
Set-Acl -LiteralPath (Join-Path $Identity 'password.dpapi') -AclObject $acl
$broad=$false
try {$unexpected=Reserve-AndroidSigningVersion $Identity 7;$unexpected.lock.Dispose()}catch{$broad=$true}
if(-not $broad){throw 'Broad secret ACL was admitted'}
@{passed=$true;signing_certificate_sha256=$certificate;last_reserved_version_code=6} | ConvertTo-Json
''', encoding='utf8')
    completed = subprocess.run(['pwsh', '-NoProfile', '-File', str(script), str(repository),
        str(identity), str(Path(java).parent.parent)], capture_output=True, text=True, timeout=45)
    assert completed.returncode == 0, completed.stderr[-2000:]
    result = json.loads(completed.stdout)
    assert result['passed'] and len(result['signing_certificate_sha256']) == 64
    assert result['last_reserved_version_code'] == 6
