"""Build-host SDK verification: exact bytes and closed ZIP/TAR inventories."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tarfile
import zipfile

import pytest


def verifier():
    source = Path(__file__).resolve().parents[2] / 'scripts/verify-dotnet-sdk.py'
    specification = importlib.util.spec_from_file_location('verify_dotnet_sdk', source)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def fixture(tmp_path, kind='tar', extra=None):
    root = tmp_path / 'sdk'; root.mkdir()
    executable = 'dotnet.exe' if kind == 'zip' else 'dotnet'
    files = {executable: b'authored SDK launcher', 'sdk/10.0.403/compiler.dll': b'authored compiler'}
    archive = tmp_path / ('sdk.zip' if kind == 'zip' else 'sdk.tar.gz')
    if kind == 'zip':
        with zipfile.ZipFile(archive, 'w') as stream:
            for name, data in files.items(): stream.writestr(name, data)
            if extra: stream.writestr(*extra)
    else:
        with tarfile.open(archive, 'w:gz') as stream:
            for name, data in files.items():
                member = tarfile.TarInfo('./' + name); member.size = len(data)
                stream.addfile(member, io.BytesIO(data))
            if extra:
                member, data = extra
                stream.addfile(member, io.BytesIO(data) if data is not None else None)
    for name, data in files.items():
        destination = root / name; destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    (root / executable).chmod(0o755)
    specification = {'artifact': archive.name, 'sha512': hashlib.sha512(archive.read_bytes()).hexdigest()}
    return archive, root, specification


@pytest.mark.parametrize('kind', ['zip', 'tar'])
def test_exact_expanded_archive_is_verified_without_running_or_extracting_it(tmp_path, kind):
    archive, root, specification = fixture(tmp_path, kind)
    result = verifier().verify(archive, root, specification)
    assert result['dotnet'] == ('dotnet.exe' if kind == 'zip' else 'dotnet')
    assert result['files'] == {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('kind', ['zip', 'tar'])
@pytest.mark.parametrize('fault', ['archive', 'changed', 'missing', 'extra-file', 'extra-directory'])
def test_mutated_or_extended_sdk_is_rejected(tmp_path, kind, fault):
    archive, root, specification = fixture(tmp_path, kind)
    member = root / 'sdk/10.0.403/compiler.dll'
    if fault == 'archive': specification['sha512'] = '0' * 128
    elif fault == 'changed': member.write_bytes(b'x' * member.stat().st_size)
    elif fault == 'missing': member.unlink()
    elif fault == 'extra-file': (root / 'injected.dll').write_bytes(b'injected')
    else: (root / 'empty').mkdir()
    with pytest.raises(ValueError): verifier().verify(archive, root, specification)


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'C:/absolute', 'sdk/../outside', 'sdk\\outside', 'DOTNET.EXE'])
def test_zip_path_traversal_and_case_aliases_are_rejected(tmp_path, name):
    archive, root, specification = fixture(tmp_path, 'zip', (name, b'unrequested'))
    with pytest.raises(ValueError): verifier().verify(archive, root, specification)


@pytest.mark.parametrize('member_type', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_tar_links_and_special_members_are_rejected(tmp_path, member_type):
    member = tarfile.TarInfo('indirect'); member.type = member_type; member.linkname = 'dotnet'
    archive, root, specification = fixture(tmp_path, extra=(member, None))
    with pytest.raises(ValueError, match='links and special'):
        verifier().verify(archive, root, specification)


def test_expanded_directory_link_is_rejected(tmp_path):
    archive, root, specification = fixture(tmp_path)
    outside = tmp_path / 'outside'; outside.mkdir()
    try: (root / 'indirect').symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip('Directory links are unavailable on this host')
    with pytest.raises(ValueError, match='links or reparse'):
        verifier().verify(archive, root, specification)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable permission contract')
def test_sdk_apphost_must_remain_executable(tmp_path):
    archive, root, specification = fixture(tmp_path)
    (root / 'dotnet').chmod(0o644)
    with pytest.raises(ValueError, match='executable'):
        verifier().verify(archive, root, specification)
