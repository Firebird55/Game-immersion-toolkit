import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

from backend.android_zzz_catalogue import IDENTITY

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt(raw):
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def test_reviewed_asset_pin_matches_both_runtime_hosts():
    tool = load('android-zzz-catalogue-assets')
    pin = json.loads((ROOT / tool.PIN).read_bytes())
    java = ROOT / 'packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit/ZzzCatalogueWorker.java'
    assert pin['manifest_sha256'] == IDENTITY
    assert f'IDENTITY = "{IDENTITY}";' in java.read_text(encoding='utf-8')


@pytest.fixture
def authored(tmp_path, monkeypatch):
    tool = load('android-zzz-catalogue-assets')
    repository = tmp_path / 'repo'
    pin = repository / tool.PIN
    pin.parent.mkdir(parents=True)
    assets = tmp_path / 'software'
    sources = assets / 'sources'
    sources.mkdir(parents=True)
    runtime = {'authored.mjs': b'export const authored = 1;', 'catalogue-host.js': b'// host',
               'catalogue-worker.mjs': b'// worker'}
    originals = {'LICENSE': b'Authored terms for the fixture only.', 'source.tar.gz': b'Authored source bytes.'}
    for name, raw in runtime.items():
        (assets / name).write_bytes(raw)
    for name, raw in originals.items():
        (sources / name).write_bytes(raw)
    manifest = dict(schema='toolkit-android-zzz-catalogue-assets-v1', modules={'authored.mjs': receipt(runtime['authored.mjs'])},
                    host=receipt(runtime['catalogue-host.js']), worker=receipt(runtime['catalogue-worker.mjs']),
                    sources={name:receipt(raw) for name, raw in originals.items()})
    raw = json.dumps(manifest).encode()
    (assets / 'manifest.json').write_bytes(raw)
    monkeypatch.setattr(tool, 'OWNED_SOURCES', {'authored.mjs': 'authored.mjs'})
    monkeypatch.setattr(tool, 'OWNED_RECIPES', {'LICENSE': 'LICENSE'})
    (repository / 'authored.mjs').write_bytes(runtime['authored.mjs'])
    (repository / 'LICENSE').write_bytes(originals['LICENSE'])
    source = tmp_path / 'reference.bundle'
    with zipfile.ZipFile(source, 'x') as archive:
        for name, raw in sorted(originals.items()):
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    pin.write_text(json.dumps(dict(schema='toolkit-android-zzz-catalogue-pin-v1',
                                  manifest_sha256=receipt((assets / 'manifest.json').read_bytes())['sha256'],
                                  corresponding_source_bundle_sha256=receipt(source.read_bytes())['sha256'],
                                  modules=1, sources=2)))
    return tool, repository, assets


def test_authenticated_assembly_is_reusable_and_rejects_stale_owned_source(tmp_path, authored):
    tool, repository, assets = authored
    destination = tmp_path / 'stage'
    proof = tool.assemble(assets, destination, repository)
    assert proof == tool.assemble(assets, destination, repository)
    assert proof['present'] and proof['runtime_files'] == 4 and proof['source_files'] == 2
    assert not list(tmp_path.glob('zzz-catalogue-*'))
    (repository / 'authored.mjs').write_bytes(b'changed repo source')
    with pytest.raises(ValueError, match='software member differs'):
        tool.assemble(assets, destination, repository)


@pytest.mark.parametrize('changed', ['manifest.json', 'authored.mjs', 'sources.bundle', 'missing', 'extra', 'duplicate'])
def test_packaged_component_checks_the_exact_apk_namespace(tmp_path, authored, changed):
    tool, repository, assets = authored
    package = tmp_path / 'stage'
    proof = tool.assemble(assets, package, repository)
    archive_path = tmp_path / 'candidate.apk'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('assets/other-authorized.json', '{}')
        assert tool.verify_apk(archive, repository) == {'present': False}
        for path in package.iterdir():
            if changed == 'missing' and path.name == 'sources.bundle':
                continue
            archive.writestr(tool.NAMESPACE + path.name, b'changed' if changed == path.name else path.read_bytes())
        if changed == 'duplicate':
            assert tool.verify_apk(archive, repository) == proof
        if changed == 'extra':
            archive.writestr(tool.NAMESPACE + 'other.mjs', b'extra')
        if changed == 'duplicate':
            with pytest.warns(UserWarning, match='Duplicate name'):
                archive.writestr(tool.NAMESPACE + 'manifest.json', (package / 'manifest.json').read_bytes())
    with zipfile.ZipFile(archive_path) as archive, pytest.raises(ValueError):
        tool.verify_apk(archive, repository)


def test_apk_audit_checks_real_verified_software_through_aapt2(tmp_path):
    source = os.environ.get('TOOLKIT_ZZZ_CATALOGUE_ASSETS')
    aapt2 = os.environ.get('TOOLKIT_ZZZ_AAPT2')
    android_jar = os.environ.get('TOOLKIT_ZZZ_ANDROID_JAR')
    if not all((source, aapt2, android_jar)):
        pytest.skip('Exact staged ZZZ software and installed AAPT2/SDK are required')
    target = tmp_path / 'assets'
    target.mkdir()
    tool = load('android-zzz-catalogue-assets')
    proof = tool.assemble(source, target / 'zzz-catalogue')
    assert proof['manifest_sha256'] == json.loads((ROOT / tool.PIN).read_bytes())['manifest_sha256']
    assert proof['runtime_files'] == 16 and proof['source_files'] == 20
    fixture = (ROOT / 'packaging/android/zzz-catalogue/authored-operation.json').read_bytes().replace(b'\r\n', b'\n')
    (target / 'zzz-catalogue-authored.json').write_bytes(fixture)

    manifest = tmp_path / 'AndroidManifest.xml'
    manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                        'package="io.github.firebird55.authored"><application /></manifest>')
    apk = tmp_path / 'authored.apk'
    subprocess.run([aapt2, 'link', '--manifest', str(manifest), '-I', android_jar, '-A', str(target), '-o', str(apk)],
                   check=True, capture_output=True, timeout=30)
    apk_audit = load('verify-android-apk')
    with zipfile.ZipFile(apk) as archive:
        assert apk_audit.verify_zzz_catalogue_component(archive, ROOT) == {
            **proof, 'authored_fixture_sha256': receipt(fixture)['sha256']}
