"""Publication must bind every target to the same source and checked bytes."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import SimpleNamespace

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


@pytest.fixture
def android_release(tmp_path, monkeypatch):
    root = tmp_path / 'android'
    root.mkdir()
    apk = root / 'GameImmersionToolkit-android-release.apk'
    apk.write_bytes(b'authored signed APK fixture')
    apk_hash = assembly.digest(apk)
    certificate = 'd' * 64
    provenance = dict(schema='toolkit-android-candidate-v1', variant='release', source_commit=COMMIT,
        source_dirty=False, version_name=VERSION, apk_sha256=apk_hash, version_code=123,
        application_id=assembly.ANDROID_APPLICATION, signing_certificate_sha256=certificate,
        signing='owner-host-protected-reusable-identity')
    evidence = dict(schema='toolkit-android-physical-release-v1', source_commit=COMMIT,
        installed_apk_sha256=apk_hash, abi='arm64-v8a', api=36,
        checks=dict.fromkeys(assembly.ANDROID_ACCEPTANCE, True))
    (root / 'ANDROID-PROVENANCE.json').write_text(json.dumps(provenance))
    (root / 'ANDROID-ACCEPTANCE.json').write_text(json.dumps(evidence))
    sdk = ('java', 'apksigner.jar', 'aapt2')
    signature = 'Signer #1 certificate SHA-256 digest: ' + certificate + '\n'
    badging = f"package: name='{assembly.ANDROID_APPLICATION}' versionCode='123' versionName='{VERSION}'\n"
    responses = {
        (sdk[0], '-jar', sdk[1], 'verify', '--print-certs', apk): signature,
        (sdk[2], 'dump', 'badging', apk): badging,
    }
    monkeypatch.setattr(assembly.subprocess, 'run',
        lambda command, **_: SimpleNamespace(stdout=responses[tuple(command)]))
    return root, apk, certificate, sdk, provenance, evidence, responses


def test_windows_android_publication_includes_only_selected_binary_targets(tmp_path, android_release):
    source, native, output = releases(tmp_path)
    root, apk, certificate, sdk, *_ = android_release
    count = assembly.assemble(source, native, output, COMMIT, VERSION,
        android=root, certificate=certificate, sdk_commands=sdk)
    assets = assembly.checked_assets(output)
    assert count == len(assets) == 8
    assert sorted(p.name for p in output.glob('DESKTOP-PROVENANCE-*.json')) == ['DESKTOP-PROVENANCE-windows-x64.json']
    assert not list(output.glob('*.dmg')) and not list(output.glob('*.tar.gz'))
    receipt = json.loads((output / 'ANDROID-PROVENANCE.json').read_text())
    assert receipt['release_eligible'] and receipt['physical_device_acceptance'] == 'approved'
    assert receipt['tag'] == 'v' + VERSION and receipt['source_commit'] == COMMIT
    assert receipt['apk']['sha256'] == assembly.digest(apk) == assets[receipt['apk']['path'].casefold()][2]
    assert not (output / 'ANDROID-ACCEPTANCE.json').exists()


def test_zzz_owner_gameplay_prerelease_requires_installation_and_explicit_opt_in(tmp_path, android_release):
    source, native, output = releases(tmp_path)
    root, apk, certificate, sdk, *_ = android_release
    evidence = dict(schema='toolkit-android-physical-install-v1', source_commit=COMMIT,
        installed_apk_sha256=assembly.digest(apk), abi='arm64-v8a', api=36, game='zzz',
        version_code=123, checks={'installed_in_place': True})
    (root / 'ANDROID-ACCEPTANCE.json').write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='gameplay'):
        assembly.assemble(source, native, output, COMMIT, VERSION,
            android=root, certificate=certificate, sdk_commands=sdk)
    assembly.assemble(source, native, output, COMMIT, VERSION,
        android=root, certificate=certificate, sdk_commands=sdk, owner_gameplay_pending=True)
    receipt = json.loads((output / 'ANDROID-PROVENANCE.json').read_text())
    assert not receipt['release_eligible']
    assert receipt['physical_device_acceptance'] == 'installation-verified'
    assert receipt['gameplay_acceptance'] == 'owner-pending' and receipt['game_scope'] == ['zzz']


@pytest.mark.parametrize('failure', ['debug-build', 'dirty-tree', 'wrong-tag', 'mutated-apk',
    'other-installed-apk', 'failed-offline', 'emulator-abi', 'third-party-signer', 'debuggable-manifest'])
def test_windows_android_publication_requires_exact_non_debug_accepted_apk(tmp_path, android_release, failure):
    source, native, output = releases(tmp_path)
    root, apk, certificate, sdk, provenance, evidence, responses = android_release
    if failure == 'debug-build': provenance['variant'] = 'ownerCandidate'
    if failure == 'dirty-tree': provenance['source_dirty'] = True
    if failure == 'wrong-tag': provenance['version_name'] = '1.2.2'
    if failure == 'mutated-apk': apk.write_bytes(b'changed')
    if failure == 'other-installed-apk': evidence['installed_apk_sha256'] = 'b' * 64
    if failure == 'failed-offline': evidence['checks']['offline_audio_restart'] = False
    if failure == 'emulator-abi': evidence['abi'] = 'x86_64'
    if failure == 'third-party-signer':
        key = next(key for key in responses if key[0] == sdk[0])
        responses[key] = 'Signer #1 certificate SHA-256 digest: ' + 'c' * 64 + '\n'
    if failure == 'debuggable-manifest':
        key = next(key for key in responses if key[0] == sdk[2])
        responses[key] += 'application-debuggable\n'
    (root / 'ANDROID-PROVENANCE.json').write_text(json.dumps(provenance))
    (root / 'ANDROID-ACCEPTANCE.json').write_text(json.dumps(evidence))
    with pytest.raises(ValueError):
        assembly.assemble(source, native, output, COMMIT, VERSION,
            android=root, certificate=certificate, sdk_commands=sdk)
    assert not output.exists()
