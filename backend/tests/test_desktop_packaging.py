"""Packaging must not publish unreviewed or mutated frozen payloads.

These tests use authored executable headers; they prove archive/gate behavior,
not native runtime loading or an installer UI. Native installer probes are separate.
"""
from importlib.util import module_from_spec, spec_from_file_location
import json
import hashlib
import os
from pathlib import Path
import struct
import tarfile
import zipfile

import pytest

spec = spec_from_file_location('desktop_packaging', Path(__file__).resolve().parents[2] / 'scripts/package-desktop.py')
packaging = module_from_spec(spec)
spec.loader.exec_module(packaging)


def payload(tmp_path, target='windows-x64'):
    root = tmp_path / 'runtime'
    (root / '_internal').mkdir(parents=True)
    (root / 'THIRD_PARTY').mkdir()
    header = bytearray(256)
    if target == 'windows-x64':
        header[:2] = b'MZ'
        struct.pack_into('<I', header, 60, 128)
        header[128:132] = b'PE\0\0'
        struct.pack_into('<H', header, 132, 0x8664)
        executable = 'GameImmersionToolkit.exe'
    elif target == 'linux-x64':
        header[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', header, 18, 62)
        executable = 'GameImmersionToolkit'
    else:
        header[:4] = b'\xcf\xfa\xed\xfe'
        struct.pack_into('<I', header, 4, 0x100000c if target == 'macos-arm64' else 0x1000007)
        executable = 'GameImmersionToolkit'
    (root / executable).write_bytes(header)
    (root / 'LICENSE').write_text('Authored fixture license')
    (root / 'THIRD_PARTY/fixture.txt').write_text('Authored dependency fixture')
    identity = dict(source_commit='a' * 40, version='1.2.3', build_id='test-fixture', profile='runtime-experiment')
    (root / '_internal/runtime-manifest.json').write_text(json.dumps(identity))
    receipt = dict(schema='proxy-runtime-candidate-v1', **identity, r19_complete=False,
        redistribution_review='pending-exact-output', native_acceptance='unavailable',
        files=[dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=packaging.digest(p))
            for p in sorted(root.rglob('*')) if p.is_file()])
    provenance = tmp_path / 'CANDIDATE-PROVENANCE.json'
    provenance.write_text(json.dumps(receipt))
    return root, provenance, receipt


def test_candidate_never_implicitly_becomes_a_release(tmp_path):
    root, _, receipt = payload(tmp_path)
    with pytest.raises(packaging.PackageError, match='Release packaging requires'):
        packaging.validate(root, receipt, 'windows-x64')
    assert packaging.validate(root, receipt, 'windows-x64', candidate=True) is False


@pytest.mark.parametrize('mutation', ['extra', 'changed', 'missing', 'wrong-target', 'identity'])
def test_changed_payload_cannot_enter_an_installer(tmp_path, mutation):
    root, _, receipt = payload(tmp_path)
    target = 'windows-x64'
    if mutation == 'extra':
        (root / 'private.db').write_bytes(b'never package')
    elif mutation == 'changed':
        (root / 'GameImmersionToolkit.exe').write_bytes(b'changed')
    elif mutation == 'missing':
        (root / 'LICENSE').unlink()
    elif mutation == 'identity':
        receipt['source_commit'] = 'b' * 40
    else:
        target = 'linux-x64'
    with pytest.raises((packaging.PackageError, FileNotFoundError)):
        packaging.validate(root, receipt, target, candidate=True)


@pytest.mark.parametrize('target', ['windows-x64', 'linux-x64', 'macos-arm64', 'macos-x64'])
def test_platform_archive_has_native_entry_and_bound_provenance(tmp_path, target):
    root, provenance, _ = payload(tmp_path, target)
    output = tmp_path / 'new output'
    result = packaging.package(root, provenance, target, output, candidate=True)
    assert result['release_eligible'] is False
    assert result['runtime_receipt_sha256'] == packaging.digest(provenance)
    archive = output / result['artifacts'][0]['path']
    if target == 'linux-x64':
        with tarfile.open(archive) as stream:
            names = stream.getnames()
            executable = next(item for item in stream if item.name.endswith('/GameImmersionToolkit'))
            assert executable.mode & 0o111
            assert any(name.endswith('/install.sh') for name in names)
    else:
        with zipfile.ZipFile(archive) as stream:
            names = stream.namelist()
            if target.startswith('macos-'):
                import plistlib
                info = plistlib.loads(stream.read('Game Immersion Toolkit.app/Contents/Info.plist'))
                assert info['CFBundleExecutable'] == 'GameImmersionToolkit'
                assert info['CFBundleVersion'] == '1.2.3'
    assert any(name.endswith('/PROVENANCE.json') for name in names)
    assert not any('site-packages' in name or '.venv' in name for name in names)
    for entry in result['artifacts']:
        assert packaging.digest(output / entry['path']) == entry['sha256']


def test_existing_outputs_and_overlap_preserved(tmp_path):
    root, provenance, _ = payload(tmp_path)
    output = tmp_path / 'existing'
    output.mkdir()
    marker = output / 'keep'
    marker.write_text('retained')
    with pytest.raises(packaging.PackageError, match='previous packages are preserved'):
        packaging.package(root, provenance, 'windows-x64', output, candidate=True)
    assert marker.read_text() == 'retained'
    with pytest.raises(packaging.PackageError, match='overlap'):
        packaging.package(root, provenance, 'windows-x64', root / 'new', candidate=True)


def test_native_links_must_be_inventoried_and_contained(tmp_path):
    root, provenance, receipt = payload(tmp_path, 'macos-arm64')
    link = root / '_internal/native-link'
    try:
        link.symlink_to(Path('..') / 'LICENSE')
    except OSError:
        pytest.skip('Host does not permit creating symbolic links.')
    # Create a native relative target: Windows can store a literal slash in a
    # reparse point without resolving it as a path separator. Inventory the
    # actual link bytes, as the production builder does.
    link_text = os.readlink(link)
    entry = dict(path='_internal/native-link', link=link_text, bytes=len(link_text.encode()),
        sha256=hashlib.sha256(link_text.encode()).hexdigest())
    receipt['files'].append(entry)
    assert packaging.validate(root, receipt, 'macos-arm64', candidate=True) is False
    provenance.write_text(json.dumps(receipt))
    result = packaging.package(root, provenance, 'macos-arm64', tmp_path / 'linked-package', candidate=True)
    with zipfile.ZipFile(tmp_path / 'linked-package' / result['artifacts'][0]['path']) as stream:
        archived = stream.getinfo('Game Immersion Toolkit.app/Contents/MacOS/_internal/native-link')
        assert (archived.external_attr >> 16) & 0o170000 == 0o120000
        assert stream.read(archived) == link_text.encode()
    link.unlink()
    outside = tmp_path / 'outside'
    outside.write_text('must never enter package')
    link.symlink_to(Path('..') / '..' / 'outside')
    link_text = os.readlink(link)
    entry.update(link=link_text, bytes=len(link_text.encode()), sha256=hashlib.sha256(link_text.encode()).hexdigest())
    with pytest.raises(packaging.PackageError, match='symbolic link'):
        packaging.validate(root, receipt, 'macos-arm64', candidate=True)
