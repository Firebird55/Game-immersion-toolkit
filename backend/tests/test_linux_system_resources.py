"""Ubuntu native origins require signed metadata, exact source and full terms."""
from __future__ import annotations

import copy
import gzip
import importlib.util
import io
import json
import lzma
from pathlib import Path
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packaging/runtime-bundle'))
import linux_system as lib
import linux_system_review as adapter

spec = importlib.util.spec_from_file_location('linux_system_collector', ROOT / 'scripts/build-linux-system-resources.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def tar_bytes(files, *, compression='xz', links=()):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        root = tarfile.TarInfo('.')
        root.type = tarfile.DIRTYPE
        archive.addfile(root)
        for name, data in files.items():
            entry = tarfile.TarInfo('./' + name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        for name, target in links:
            entry = tarfile.TarInfo('./' + name)
            entry.type, entry.linkname = tarfile.SYMTYPE, target
            archive.addfile(entry)
    data = stream.getvalue()
    if compression == 'zst':
        import zstandard
        return zstandard.ZstdCompressor().compress(data)
    return lzma.compress(data)


def deb_bytes(control, files, *, compression='zst', links=()):
    result = b'!<arch>\n'
    for name, data in [('debian-binary', b'2.0\n'),
                       ('control.tar.' + compression, tar_bytes({'control': control.encode()}, compression=compression)),
                       ('data.tar.' + compression, tar_bytes(files, compression=compression, links=links))]:
        header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n'.encode()
        assert len(header) == 60
        result += header + data + (b'\n' if len(data) % 2 else b'')
    return result


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def control_record(package, version='1.2-3', source=None):
    return f'Package: {package}\nVersion: {version}\nArchitecture: amd64\n' + (f'Source: {source}\n' if source else '')


@pytest.mark.parametrize('compression', ['xz', 'zst'])
def test_actual_deb_stream_root_and_links_are_not_extracted(tmp_path, compression):
    elf = b'\x7fELFauthored selected library'
    path = write(tmp_path, 'fixture.deb', deb_bytes(control_record('libfixture1', source='fixture (1.2)'),
        {'usr/lib/libfixture.so.1.2': elf, 'usr/share/doc/libfixture1/copyright': b'Full authored copyright and permission'},
        compression=compression, links=[('usr/lib/libfixture.so.1', 'libfixture.so.1.2'), ('escape', '../../outside')]))
    control, files, notices = lib.deb_evidence(path)
    assert lib.source_identity(control) == ('fixture', '1.2')
    assert files['usr/lib/libfixture.so.1.2'] == lib.sha(elf)
    assert 'usr/lib/libfixture.so.1' not in files and 'escape' not in files
    assert list(notices.values()) == [b'Full authored copyright and permission']
    assert not (tmp_path / 'usr').exists()


@pytest.mark.parametrize('name', ['../escape', '/escape', 'a/../b', 'a\\b', '.'])
def test_deb_member_traversal_is_rejected(tmp_path, name):
    # Construct literal paths; root-directory allowance must not allow a file
    # named '.' or strip arbitrary path traversal into an acceptable spelling.
    data = deb_bytes(control_record('fixture'), {name: b'payload'})
    with pytest.raises(ValueError, match='path'):
        lib.deb_evidence(write(tmp_path, 'bad.deb', data))


def test_control_duplicate_fields_and_ambiguous_sources_fail():
    with pytest.raises(ValueError, match='Duplicate'):
        lib.one_paragraph(b'Package: first\nPackage: second\n')
    with pytest.raises(ValueError, match='source package'):
        lib.source_identity({'Package': 'x', 'Version': '1', 'Source': 'x (1) injected'})
    assert lib.source_identity({'Package': 'x', 'Version': '2'}) == ('x', '2')
    assert lib.source_identity({'Package': 'libx', 'Version': '2+b1', 'Source': 'x (2)'}) == ('x', '2')


def test_signature_requires_exact_allowed_primary_key_and_success(tmp_path, monkeypatch):
    key = write(tmp_path, 'key.gpg', b'authored key fixture')
    signed = write(tmp_path, 'InRelease', b'authored signed release')
    primary = 'A' * 40
    policy = {'keyring': {'sha256': lib.digest(key), 'bytes': key.stat().st_size},
              'signing_keys': [primary], 'codename': 'noble', 'architecture': 'amd64'}
    status = f'[GNUPG:] VALIDSIG {primary} 2026-11-01 1 0 4 0 1 10 01 {primary}\n'
    signed_body = b'Origin: Ubuntu\nLabel: Ubuntu\nSuite: noble\nCodename: noble\nArchitectures: amd64\n'
    observed = []
    def verifier(args, **kwargs):
        observed.append(args)
        (Path(kwargs['cwd']) / 'Release').write_bytes(signed_body)
        return SimpleNamespace(returncode=0, stdout=status.encode())
    monkeypatch.setattr(lib.subprocess, 'run', verifier)
    assert lib.verify_release(signed, key, policy, 'noble')['Origin'] == 'Ubuntu'
    assert observed[0][1:5] == ['--homedir', '.', '--keyring', './archive-keyring.gpg']
    for bad in ['[GNUPG:] GOODSIG A claimed identity\n', status.replace(primary, 'B' * 40)]:
        status = bad
        with pytest.raises(ValueError, match='signature'):
            lib.verify_release(signed, key, policy, 'noble')
    monkeypatch.setattr(lib.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout=b''))
    with pytest.raises(ValueError, match='signature'):
        lib.verify_release(signed, key, policy, 'noble')


def test_metadata_reads_only_indexes_bound_to_signed_release(tmp_path, monkeypatch):
    policy = {'suites': ['noble'], 'components': ['main'], 'architecture': 'amd64', 'source_packages': ['fixture']}
    package = 'Package: libfixture\nVersion: 1\nSource: fixture\nArchitecture: amd64\nSHA256: ' + 'a' * 64 + '\nSize: 8\nFilename: pool/f.deb\n'
    source = 'Package: fixture\nVersion: 1\nChecksums-Sha256:\n ' + 'b' * 64 + ' 8 f.dsc\n'
    index = {}
    for name, body in [('main/binary-amd64/Packages.xz', package), ('main/source/Sources.xz', source)]:
        data = lzma.compress(body.encode())
        write(tmp_path, 'metadata/noble/' + name, data)
        index[name] = f' {lib.sha(data)} {len(data)} {name}\n'
    monkeypatch.setattr(lib, 'verify_release', lambda *a, **k: {'SHA256': ''.join(index.values())})
    binaries, sources = lib.metadata(tmp_path, policy, {'libfixture'})
    assert lib.source_identity(binaries['libfixture', '1']) == ('fixture', '1')
    assert ('fixture', '1') in sources
    (tmp_path / 'metadata/noble/main/source/Sources.xz').write_bytes(lzma.compress(b'Package: attacker\n'))
    with pytest.raises(ValueError, match='bytes differ'):
        lib.metadata(tmp_path, policy, {'libfixture'})


def fixture_closure(tmp_path, monkeypatch):
    policy = {'source_packages': ['fixture', 'base-files']}
    selected, binaries, sources = [], {}, {}
    for package, source in [('libfixture', 'fixture'), ('base-files', 'base-files')]:
        files = {'usr/lib/' + package + '.so': b'\x7fELF' + package.encode(),
                 'usr/share/doc/' + package + '/copyright': b'Exact binary copyright'}
        if package == 'base-files':
            files.update({'usr/share/common-licenses/GPL-3': b'Complete authored GPL fixture',
                          'usr/share/common-licenses/LGPL-2.1': b'Complete authored LGPL fixture'})
        data = deb_bytes(control_record(package, source=source), files)
        filename = 'pool/' + package + '.deb'
        write(tmp_path, 'binary/' + filename, data)
        binaries[package, '1.2-3'] = {'Package': package, 'Version': '1.2-3', 'Architecture': 'amd64',
            'Source': source, 'Filename': filename, 'SHA256': lib.sha(data), 'Size': str(len(data))}
        selected.append({'package': package, 'version': '1.2-3'})
        source_files = {source + '.dsc': b'Exact source recipe',
            source + '.orig.tar.xz': tar_bytes({'preferred-source.c': b'preferred source'}),
            source + '.debian.tar.xz': tar_bytes({'debian/copyright': b'Complete source copyright', 'debian/rules': b'Exact build recipe'})}
        checksums = ''
        for name, value in source_files.items():
            write(tmp_path, 'source/pool/' + name, value)
            checksums += f' {lib.sha(value)} {len(value)} {name}\n'
        sources[source, '1.2-3'] = {'Directory': 'pool', 'Checksums-Sha256': checksums}
    write(tmp_path, 'collection.json', json.dumps({'schema': 'toolkit-ubuntu-system-collection-v1',
        'policy_sha256': lib.policy_digest(policy), 'packages': selected}).encode())
    monkeypatch.setattr(lib, 'metadata', lambda *a, **k: (binaries, sources))
    lib.verify_closure(tmp_path, policy, retain_notices=True)
    return policy, binaries, sources


def test_complete_exact_binary_source_and_full_terms(tmp_path, monkeypatch):
    policy, _, _ = fixture_closure(tmp_path, monkeypatch)
    result = lib.verify_closure(tmp_path, policy)
    assert (result['packages'], result['sources'], result['archives']) == (2, 2, 8)
    assert result['origins'][lib.sha(b'\x7fELFlibfixture')][0]['member'] == 'usr/lib/libfixture.so'


@pytest.mark.parametrize('mutation', ['binary', 'source', 'copyright', 'attribution', 'extra-archive', 'wrong-source-version', 'wrong-binary-control'])
def test_independent_review_refuses_incomplete_or_misattributed_closure(tmp_path, monkeypatch, mutation):
    policy, binaries, sources = fixture_closure(tmp_path, monkeypatch)
    if mutation == 'binary':
        (tmp_path / 'binary/pool/libfixture.deb').write_bytes(b'changed')
    elif mutation == 'source':
        (tmp_path / 'source/pool/fixture.debian.tar.xz').unlink()
    elif mutation == 'copyright':
        next((tmp_path / 'notices').glob('*.txt')).write_bytes(b'short SPDX label')
    elif mutation == 'attribution':
        (tmp_path / 'NOTICE-INDEX.json').write_text('{}')
    elif mutation == 'extra-archive':
        write(tmp_path, 'source/unreviewed.tar.xz', b'unknown')
    elif mutation == 'wrong-source-version':
        binaries['libfixture', '1.2-3']['Source'] = 'fixture (other-version)'
    else:
        binary = binaries['libfixture', '1.2-3']
        data = deb_bytes(control_record('libfixture', 'wrong', 'fixture'), {'usr/lib/libfixture.so': b'\x7fELFlibfixture'})
        write(tmp_path, 'binary/pool/libfixture.deb', data)
        binary.update(SHA256=lib.sha(data), Size=str(len(data)))
    with pytest.raises(ValueError):
        lib.verify_closure(tmp_path, policy)


def test_gpg_failure_blocks_all_three_dependent_review_claims(monkeypatch):
    blocks = []
    value = SimpleNamespace(target='linux-x64', inventory={}, block=lambda *x: blocks.append(x))
    with pytest.raises(ValueError, match='absent'):
        adapter.inspect(value, SimpleNamespace(files={}), lambda *x: True)
    assert {block[0] for block in blocks} == {'native_inputs', 'complete_notices', 'corresponding_sources'}


def test_final_adapter_rejects_a_different_source_snapshot_before_trusting_any_origin(tmp_path):
    prefix = '_internal/' + lib.PREFIX + '/'
    blocks = []
    value = SimpleNamespace(target='linux-x64', inventory={prefix + 'collection.json': {}},
        block=lambda *x: blocks.append(x), origin=lambda *x: pytest.fail('Unverified origin accepted'))
    snapshot = SimpleNamespace(files={name: b'not the reviewed source' for name in lib.OWNED})
    with pytest.raises(ValueError, match='candidate source'):
        adapter.inspect(value, snapshot, lambda data, expected, name: lib.sha(data) == expected)
    assert len(blocks) == 3


def test_final_adapter_records_verified_exact_member_origins_only(tmp_path, monkeypatch):
    prefix = '_internal/' + lib.PREFIX + '/'
    snapshot = SimpleNamespace(files={name: (ROOT / name).read_bytes() for name in lib.OWNED})
    inventory = {}
    for name, data in snapshot.files.items():
        target = prefix + 'recipe/' + name
        write(tmp_path, target, data)
        inventory[target] = {'sha256': lib.sha(data)}
    origins, evidence = [], []
    value = SimpleNamespace(target='linux-x64', root=tmp_path, inventory=inventory,
        block=lambda *x: pytest.fail('Valid authored adapter evidence blocked'),
        origin=lambda *x: origins.append(x), evidence=lambda key, **values: evidence.append((key, values)))
    expected = {'origins': {'a' * 64: [{'package': 'libfixture', 'version': '1',
        'archive_sha256': 'b' * 64, 'member': 'usr/lib/libfixture.so'}]},
        'packages': 1, 'sources': 1, 'notices': 2, 'archives': 4}
    monkeypatch.setattr(lib, 'verify_closure', lambda root, policy, **kwargs: expected)
    adapter.inspect(value, snapshot, lambda data, expected, name: lib.sha(data) == expected)
    assert origins == [('a' * 64, 'Ubuntu libfixture=1 archive:' + 'b' * 64 + ' member:usr/lib/libfixture.so')]
    assert {key for key, _ in evidence} == {'native_inputs', 'complete_notices', 'corresponding_sources'}


def test_build_host_sync_never_runs_outside_explicit_ephemeral_ci(monkeypatch):
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.setattr(collector.subprocess, 'run', lambda *a, **k: pytest.fail('No process may run'))
    with pytest.raises(ValueError, match='ephemeral'):
        collector.synchronize({'x': {'version': '1'}}, {('x', '2'): {}})


def test_supplier_download_refuses_unsigned_host_or_modified_cached_bytes(tmp_path):
    with pytest.raises(ValueError, match='hosts'):
        collector.acquire('https://untrusted.invalid/ubuntu/package', tmp_path)
    expected = lib.sha(b'expected')
    write(tmp_path, expected, b'modified')
    with pytest.raises(ValueError, match='bytes differ'):
        collector.acquire('https://archive.ubuntu.com/ubuntu/pool/fixture', tmp_path, expected=expected, size=8)
