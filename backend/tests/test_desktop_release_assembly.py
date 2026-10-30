"""Publication must bind every target to the same source and checked bytes."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

spec = spec_from_file_location('assemble_desktop_release', Path(__file__).resolve().parents[2] / 'scripts/assemble-desktop-release.py')
assembly = module_from_spec(spec)
spec.loader.exec_module(assembly)
COMMIT = 'a' * 40
VERSION = '1.2.3'


def checksums(root):
    (root / 'SHA256SUMS').write_text(''.join(assembly.digest(p) + '  ' + p.name + '\n'
        for p in sorted(root.iterdir()) if p.name != 'SHA256SUMS'))


def releases(tmp_path):
    source, native = tmp_path / 'source', tmp_path / 'native'
    source.mkdir()
    (source / 'PROVENANCE.json').write_text(json.dumps(dict(sourceCommit=COMMIT, version=VERSION, repository=assembly.REPOSITORY)))
    (source / 'source.zip').write_bytes(b'authored archive fixture')
    checksums(source)
    for target in assembly.TARGETS:
        root = native / ('tested-desktop-' + target)
        root.mkdir(parents=True)
        prefix = 'Game-immersion-toolkit-' + VERSION + '-' + target
        suffixes = ['-runtime.zip'] + (['.zip', '-Setup.exe'] if target == 'windows-x64' else
            ['.tar.gz'] if target == 'linux-x64' else ['.zip', '.dmg'])
        entries = []
        for suffix in suffixes:
            path = root / (prefix + suffix)
            path.write_bytes(('authored fixture for ' + path.name).encode())
            entries.append(dict(path=path.name, sha256=assembly.digest(path), bytes=path.stat().st_size))
        receipt = dict(schema='proxy-desktop-distribution-v1', repository=assembly.REPOSITORY,
            tag='v' + VERSION, target=target, version=VERSION, source_commit=COMMIT, release_eligible=True,
            candidate=False, signing='unsigned', native_acceptance='approved', artifacts=entries,
            update_artifact=prefix + '-runtime.zip')
        (root / ('DESKTOP-PROVENANCE-' + target + '.json')).write_text(json.dumps(receipt))
        checksums(root)
    return source, native, tmp_path / 'published'


def test_complete_unsigned_release_combines_all_targets_and_sums(tmp_path):
    source, native, output = releases(tmp_path)
    count = assembly.assemble(source, native, output, COMMIT, VERSION)
    assert len(assembly.checked_assets(output)) == count == 13
    assert len(list(output.glob('DESKTOP-PROVENANCE-*.json'))) == 3
    assert list(output.glob('*-Setup.exe')) and list(output.glob('*.dmg')) and list(output.glob('*.tar.gz'))


@pytest.mark.parametrize('change', ['candidate', 'unverified', 'other-head', 'wrong-target', 'extra', 'changed', 'missing-installer', 'missing-target', 'checksum-escape', 'duplicate'])
def test_incomplete_or_mutated_native_release_never_creates_publication_output(tmp_path, change):
    source, native, output = releases(tmp_path)
    root = native / 'tested-desktop-windows-x64'
    receipt_path = root / 'DESKTOP-PROVENANCE-windows-x64.json'
    receipt = json.loads(receipt_path.read_text())
    if change == 'candidate': receipt['candidate'] = True
    elif change == 'unverified': receipt['native_acceptance'] = 'unavailable'
    elif change == 'other-head': receipt['source_commit'] = 'b' * 40
    elif change == 'wrong-target': receipt['target'] = 'linux-x64'
    elif change == 'extra': (root / 'unchecked.txt').write_text('never publish')
    elif change == 'changed': next(root.glob('*.exe')).write_bytes(b'tampered')
    elif change == 'missing-installer':
        path = next(root.glob('*.exe'))
        receipt['artifacts'] = [item for item in receipt['artifacts'] if item['path'] != path.name]
        path.unlink()
    elif change == 'missing-target': root.rename(root.with_name('missing-windows'))
    elif change == 'checksum-escape':
        with (root / 'SHA256SUMS').open('a') as stream: stream.write('a' * 64 + '  ../outside.zip\n')
    elif change == 'duplicate': receipt['artifacts'].append(receipt['artifacts'][0])
    if change not in {'extra', 'changed', 'missing-target', 'checksum-escape'}:
        receipt_path.write_text(json.dumps(receipt))
        checksums(root)
    with pytest.raises((ValueError, OSError)):
        assembly.assemble(source, native, output, COMMIT, VERSION)
    assert not output.exists()


def test_source_commit_and_unchecked_source_files_are_also_rejected(tmp_path):
    source, native, output = releases(tmp_path)
    with pytest.raises(ValueError, match='provenance'):
        assembly.assemble(source, native, output, 'b' * 40, VERSION)
    (source / 'private.txt').write_text('never publish')
    with pytest.raises(ValueError, match='unchecked'):
        assembly.assemble(source, native, output, COMMIT, VERSION)
    assert not output.exists()
