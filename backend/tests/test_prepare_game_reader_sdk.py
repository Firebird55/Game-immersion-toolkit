"""Build inputs cannot execute until the exact SDK archive has been verified."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('prepare_reader_sdk', Path(__file__).resolve().parents[2] / 'scripts/prepare-game-reader-sdk.py')
sdk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk)


@pytest.mark.parametrize('kind', ['zip', 'tar'])
def test_expanded_input_matches_exact_supplier_and_detects_changed_file(tmp_path, kind):
    archive = tmp_path / ('sdk.zip' if kind == 'zip' else 'sdk.tar.gz')
    executable = 'dotnet.exe' if kind == 'zip' else 'dotnet'
    content = {executable: b'authored SDK executable', 'sdk/compiler.dll': b'authored compiler'}
    if kind == 'zip':
        with zipfile.ZipFile(archive, 'w') as bundle:
            for name, data in content.items():
                bundle.writestr(name, data)
    else:
        with tarfile.open(archive, 'w:gz') as bundle:
            for name, data in content.items():
                entry = tarfile.TarInfo('./' + name)
                entry.size, entry.mode = len(data), 0o755
                bundle.addfile(entry, io.BytesIO(data))
    pin = {'sha512': hashlib.sha512(archive.read_bytes()).hexdigest(), 'artifact': archive.name}
    output = tmp_path / 'expanded'
    sdk.expand(archive, output)
    assert set(sdk.verifier.verify(archive, output, pin)['files']) == set(content)
    (output / 'sdk/compiler.dll').write_bytes(b'changed')
    with pytest.raises(ValueError, match='missing|differ'):
        sdk.verifier.verify(archive, output, pin)
    with pytest.raises(ValueError, match='fresh SDK'):
        sdk.expand(archive, output)


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'C:/escape', 'a\\escape', 'a/../escape'])
def test_sdk_archive_cannot_escape_output(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr(name, b'bad')
    if '\\' in name:
        archive.write_bytes(archive.read_bytes().replace(name.replace('\\', '/').encode(), name.encode()))
    with pytest.raises(ValueError, match='Unsafe'):
        sdk.expand(archive, tmp_path / 'output')


def test_sdk_tar_link_is_never_followed(tmp_path):
    archive = tmp_path / 'bad.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        entry = tarfile.TarInfo('link')
        entry.type, entry.linkname = tarfile.SYMTYPE, '../outside'
        bundle.addfile(entry)
    with pytest.raises(ValueError, match='links'):
        sdk.expand(archive, tmp_path / 'output')


def test_cached_wrong_sdk_is_rejected_before_network_or_execution(tmp_path, monkeypatch):
    (tmp_path / 'sdk.zip').write_bytes(b'wrong')
    monkeypatch.setattr(sdk.urllib.request, 'urlopen', lambda *_a, **_k: pytest.fail('No acquisition for a corrupt cache'))
    with pytest.raises(ValueError, match='Cached SDK'):
        sdk.acquire(tmp_path, {'artifact': 'sdk.zip', 'sha512': '0' * 128})
