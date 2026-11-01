"""Exact supplier preparation, internal links and native target identity."""
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packaging/runtime-bundle'))
import python_supplier as supplier

spec = spec_from_file_location('prepare_python', ROOT / 'scripts/prepare-desktop-python.py')
prepare = module_from_spec(spec)
spec.loader.exec_module(prepare)


def archive_fixture(tmp_path, *, target='linux-x64', extra=None):
    archive = tmp_path / 'python-fixture.tar.gz'
    executable = 'python.exe' if target == 'windows-x64' else 'bin/python3.12'
    native = 'python312.dll' if target == 'windows-x64' else 'lib/libpython3.12.so.1.0'
    files = {executable: b'authored executable fixture', native: b'authored native fixture',
             'LICENSE.txt': b'authored license fixture'}
    with tarfile.open(archive, 'w:gz') as output:
        for name, data in files.items():
            member = tarfile.TarInfo('python/' + name)
            member.size = len(data)
            member.mode = 0o755 if name == executable else 0o644
            output.addfile(member, io.BytesIO(data))
        if target != 'windows-x64':
            link = tarfile.TarInfo('python/bin/python3')
            link.type = tarfile.SYMTYPE
            link.linkname = 'python3.12'
            output.addfile(link)
        for member, data in extra or []:
            member.size = len(data) if data is not None else 0
            output.addfile(member, io.BytesIO(data) if data is not None else None)
    return archive, {'target': target, 'sha256': supplier.digest(archive),
        'bytes': archive.stat().st_size, 'required_files': [executable, native, 'LICENSE.txt']}


def symlink(name, destination):
    member = tarfile.TarInfo(name)
    member.type = tarfile.SYMTYPE
    member.linkname = destination
    return member, None


@pytest.mark.parametrize('extra', [
    [(tarfile.TarInfo('python/../escape'), b'escape')],
    [(tarfile.TarInfo('/absolute'), b'escape')],
    [(tarfile.TarInfo('python/bin/python3.12'), b'duplicate')],
    [symlink('python/bin/outside', '../../../outside')],
    [symlink('python/bin/outside', '/usr/bin/python3')],
    [symlink('python/bin/broken', 'missing')],
    [symlink('python/bin/cycle1', 'cycle2'), symlink('python/bin/cycle2', 'cycle1')],
    [symlink('python/linked', 'bin/python3.12'), (tarfile.TarInfo('python/linked/file'), b'write through link')],
])
def test_archive_rejects_unsafe_graph_before_output_creation(tmp_path, extra):
    archive, pin = archive_fixture(tmp_path, extra=extra)
    output = tmp_path / 'output'
    with pytest.raises(ValueError):
        supplier.extract(archive, output, pin)
    assert not output.exists()


def test_hardlinks_and_devices_are_rejected(tmp_path):
    for number, kind in enumerate((tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE)):
        case = tmp_path / str(number)
        case.mkdir()
        member = tarfile.TarInfo('python/special')
        member.type = kind
        member.linkname = 'python/bin/python3.12'
        archive, pin = archive_fixture(case, extra=[(member, None)])
        with pytest.raises(ValueError, match='unsupported links or special'):
            supplier.archive_plan(archive, pin)


def test_linux_case_distinct_paths_are_not_windows_aliases(tmp_path):
    extra = [(tarfile.TarInfo('python/share/terminfo/A'), b'A'),
             (tarfile.TarInfo('python/share/terminfo/a'), b'a')]
    archive, pin = archive_fixture(tmp_path, extra=extra)
    assert len(supplier.archive_plan(archive, pin)) == 6
    pin['target'] = 'macos-arm64'
    with pytest.raises(ValueError, match='aliases'):
        supplier.archive_plan(archive, pin)


def test_exact_windows_extraction_and_tamper_detection(tmp_path, monkeypatch):
    archive, pin = archive_fixture(tmp_path, target='windows-x64')
    monkeypatch.setattr(supplier, 'host_target', lambda: 'windows-x64')
    root = tmp_path / 'fresh'
    observed = supplier.extract(archive, root, pin)
    assert len(observed) == 3
    (root / 'python/python312.dll').write_bytes(b'changed')
    with pytest.raises(ValueError, match='differs from the supplier archive'):
        supplier.verify_installed(archive, root / 'python', pin)
    with pytest.raises(ValueError, match='existing files are preserved'):
        supplier.extract(archive, root, pin)
    assert (root / 'python/python312.dll').read_bytes() == b'changed'


@pytest.mark.skipif(os.name == 'nt', reason='Real POSIX link extraction runs on native hosted targets.')
def test_posix_links_and_permissions_are_preserved_and_verified(tmp_path, monkeypatch):
    archive, pin = archive_fixture(tmp_path)
    monkeypatch.setattr(supplier, 'host_target', lambda: 'linux-x64')
    root = tmp_path / 'fresh'
    observed = supplier.extract(archive, root, pin)
    link = root / 'python/bin/python3'
    assert link.is_symlink() and os.readlink(link) == 'python3.12'
    assert (root / 'python/bin/python3.12').stat().st_mode & 0o111 == 0o111
    assert next(item for item in observed if item['path'] == 'bin/python3')['link'] == 'python3.12'
    link.unlink()
    link.symlink_to('../lib/libpython3.12.so.1.0')
    with pytest.raises(ValueError, match='symbolic link differs'):
        supplier.verify_installed(archive, root / 'python', pin)


def test_changed_archive_and_wrong_native_target_produce_no_output(tmp_path, monkeypatch):
    archive, pin = archive_fixture(tmp_path)
    output = tmp_path / 'output'
    monkeypatch.setattr(supplier, 'host_target', lambda: 'windows-x64')
    with pytest.raises(ValueError, match='native target'):
        supplier.extract(archive, output, pin)
    archive.write_bytes(b'changed archive')
    with pytest.raises(ValueError, match='exact observed pin'):
        supplier.extract(archive, output, pin)
    assert not output.exists()


def test_wheel_install_changes_only_build_paths(tmp_path, monkeypatch):
    extra = [(tarfile.TarInfo('python/Lib/site-packages/pip/__init__.py'), b'original pip')]
    archive, pin = archive_fixture(tmp_path, target='windows-x64', extra=extra)
    monkeypatch.setattr(supplier, 'host_target', lambda: 'windows-x64')
    root = tmp_path / 'fresh'
    supplier.extract(archive, root, pin)
    (root / 'python/Lib/site-packages/pip/__init__.py').write_bytes(b'updated build dependency')
    assert len(supplier.verify_installed(archive, root / 'python', pin)) == 3
    with pytest.raises(ValueError, match='differs'):
        supplier.verify_installed(archive, root / 'python', pin, include_build_files=True)


def test_download_retries_are_bounded_and_pins_are_checked(tmp_path, monkeypatch):
    attempts = []
    data = b'authored archive fixture'
    pin = {'archive': 'fixture.tar.gz', 'url': 'https://invalid.example/fixture',
           'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def download(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.URLError('authored transient outage')
        result = io.BytesIO(data)
        result.url = pin['url']
        return result

    monkeypatch.setattr(prepare.urllib.request, 'urlopen', download)
    monkeypatch.setattr(prepare.time, 'sleep', lambda _: None)
    result = prepare.acquire(pin, tmp_path / 'cache')
    assert result.read_bytes() == data and len(attempts) == 2
    prepare.acquire(pin, result.parent)
    assert len(attempts) == 2
    result.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Cached Python archive'):
        prepare.acquire(pin, result.parent)
    assert len(attempts) == 2


def test_persistent_network_failure_stops_after_three_attempts(tmp_path, monkeypatch):
    attempts = []

    def unavailable(*args, **kwargs):
        attempts.append(1)
        raise urllib.error.URLError('authored outage')

    monkeypatch.setattr(prepare.urllib.request, 'urlopen', unavailable)
    monkeypatch.setattr(prepare.time, 'sleep', lambda _: None)
    with pytest.raises(urllib.error.URLError):
        prepare.acquire({'archive': 'fixture.tar.gz', 'url': 'https://invalid.example/fixture',
            'bytes': 1, 'sha256': '0' * 64}, tmp_path)
    assert len(attempts) == 3
    assert list(tmp_path.iterdir()) == []


def test_github_outputs_bind_explicit_interpreter_and_archive(tmp_path, monkeypatch):
    outputs = {key: str(tmp_path / key) for key in ('python', 'python_prefix', 'python_archive')}
    output_file, path_file = tmp_path / 'GITHUB_OUTPUT', tmp_path / 'GITHUB_PATH'
    monkeypatch.setattr(prepare, 'host_target', lambda: 'windows-x64')
    prepare.emit_github(outputs, output_file, path_file)
    assert dict(line.split('=', 1) for line in output_file.read_text().splitlines()) == outputs
    assert path_file.read_text().splitlines() == [str(tmp_path), str(tmp_path / 'python_prefix/Scripts')]
    with pytest.raises(ValueError, match='newlines'):
        prepare.emit_github({**outputs, 'python': 'injected\nOUTPUT=other'}, output_file, path_file)


def test_pins_match_native_release_asset_metadata():
    for target in supplier.PIN_FILES:
        pin = supplier.load_pin(target)
        assert pin['github_release_id'] == 424411241
        assert pin['source_commit'] == 'fa506e0858ac9f2cc5b289c137b888a2aa24d1ee'
        assert pin['version'] == '3.12.16' and pin['github_asset_id'] > 0
    assert supplier.load_pin('macos-arm64')['sha256'] == 'fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e'
