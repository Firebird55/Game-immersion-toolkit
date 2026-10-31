"""Retain real license bytes and refuse changed or unsafe build inputs."""
from importlib.util import module_from_spec, spec_from_file_location
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tarfile
from types import SimpleNamespace
import zipfile

import pytest

spec = spec_from_file_location('native_notices', Path(__file__).resolve().parents[2] / 'scripts/build-native-notices.py')
native = module_from_spec(spec)
spec.loader.exec_module(native)


def fixture(cache, *, kind='tar', fault=None):
    cache.mkdir()
    archive = cache / ('supplier.tar.gz' if kind == 'tar' else 'supplier.zip')
    files = {'supplier/LICENSE': b'Authored full license fixture.',
             'supplier/deps/COPYING': b'Authored transitive license fixture.',
             'supplier/src/library.c': b'/* Authored source fixture. */'}
    if fault == 'missing':
        del files['supplier/LICENSE']
    if fault == 'escape':
        files['supplier/../../LICENSE'] = b'escape'
    if fault == 'duplicate':
        files['supplier/license'] = b'Conflicting spelling'
    if kind == 'tar':
        with tarfile.open(archive, 'w:gz') as source:
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                if fault == 'symlink' and name.endswith('/LICENSE'):
                    member.type = tarfile.SYMTYPE
                    member.linkname = '../../external'
                    member.size = 0
                source.addfile(member, io.BytesIO(data))
    else:
        with zipfile.ZipFile(archive, 'w') as source:
            for name, data in files.items():
                member = zipfile.ZipInfo(name)
                if fault == 'symlink' and name.endswith('/LICENSE'):
                    member.create_system = 3
                    member.external_attr = (stat.S_IFLNK | 0o777) << 16
                source.writestr(member, data)
    return {'schema': 'toolkit-native-notice-inputs-v1', 'version': 'fixture',
            'limitations': ['Authored test inputs; no release approval.'],
            'components': [{'name': 'supplier', 'archive': archive.name, 'format': kind,
                'root': 'supplier', 'required_notices': ['LICENSE'],
                'url': 'https://invalid.example/never-requested', 'sha256': native.digest(archive)}]}


@pytest.mark.parametrize('kind', ['tar', 'zip'])
def test_full_sources_and_transitive_notices_survive_collection(tmp_path, kind):
    cache, output = tmp_path / 'cache', tmp_path / 'output'
    pins = fixture(cache, kind=kind)
    receipt = native.build(output, cache, pins, runtime_verifier=lambda _: [])
    root = output / native.PREFIX / 'supplier'
    archive = pins['components'][0]['archive']
    assert (root / archive).read_bytes() == (cache / archive).read_bytes()
    index = json.loads((root / 'notices/index.json').read_text())
    by_origin = {record['source_path']: root / 'notices' / name for name, record in index.items()}
    assert by_origin['LICENSE'].read_bytes() == b'Authored full license fixture.'
    assert by_origin['deps/COPYING'].read_bytes() == b'Authored transitive license fixture.'
    assert 'src/library.c' not in by_origin
    assert receipt['rights_review'] == 'pending-exact-output'
    for file in receipt['files']:
        data = (output / file['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == file['sha256']
        assert len(data) == file['bytes']
    # Verify compatibility with the production collector and private-file gate.
    runtime_spec = spec_from_file_location('notice_runtime', native.ROOT / 'scripts/build-desktop-runtime.py')
    runtime = module_from_spec(runtime_spec)
    runtime_spec.loader.exec_module(runtime)
    collected = tmp_path / 'collected'
    runtime.extra_resources(output, collected)
    assert len(runtime.tree(collected)) == len(receipt['files'])


@pytest.mark.parametrize('kind', ['tar', 'zip'])
@pytest.mark.parametrize('fault', ['changed', 'missing', 'escape', 'duplicate', 'symlink'])
def test_invalid_supplier_input_never_creates_a_resource_bundle(tmp_path, kind, fault):
    cache, output = tmp_path / 'cache', tmp_path / 'output'
    pins = fixture(cache, kind=kind, fault=fault)
    if fault == 'changed':
        (cache / pins['components'][0]['archive']).write_bytes(b'changed')
    with pytest.raises(ValueError):
        native.build(output, cache, pins, runtime_verifier=lambda _: [])
    assert not output.exists()


@pytest.mark.parametrize('fault', ['version', 'geos', 'model'])
def test_runtime_or_model_mismatch_cannot_receive_unrelated_notices(tmp_path, monkeypatch, fault):
    model = tmp_path / 'model.onnx'
    model.write_bytes(b'authored model fixture')
    pins = {'distributions': {'rapidocr-onnxruntime': '1.4.4'}, 'geos_version': '3.13.1',
            'ocr_models': {'files': [{'name': 'model', 'installed_path': 'model.onnx',
                'sha256': native.digest(model), 'bytes': model.stat().st_size}]}}
    monkeypatch.setattr(native.metadata, 'version', lambda _: 'unexpected' if fault == 'version' else '1.4.4')
    monkeypatch.setattr(native.metadata, 'distribution', lambda _: SimpleNamespace(locate_file=lambda _: model))
    monkeypatch.setitem(sys.modules, 'shapely', SimpleNamespace(geos_version_string='changed' if fault == 'geos' else '3.13.1'))
    if fault == 'model':
        model.write_bytes(b'changed model')
    with pytest.raises(ValueError):
        native.verify_runtime(pins)


def test_existing_partial_download_is_preserved(tmp_path, monkeypatch):
    partial = tmp_path / 'source.tar.gz.part'
    partial.write_bytes(b'preexisting input')
    response = io.BytesIO(b'authored download')
    response.url = 'https://invalid.example/source'
    monkeypatch.setattr(native.urllib.request, 'urlopen', lambda *a, **k: response)
    with pytest.raises(FileExistsError):
        native.acquire({'name': 'supplier', 'archive': 'source.tar.gz',
            'url': response.url, 'sha256': '0' * 64}, tmp_path)
    assert partial.read_bytes() == b'preexisting input'


def test_changed_download_removes_only_its_own_partial_file(tmp_path, monkeypatch):
    response = io.BytesIO(b'authored download')
    response.url = 'https://invalid.example/source'
    monkeypatch.setattr(native.urllib.request, 'urlopen', lambda *a, **k: response)
    with pytest.raises(ValueError, match='checksum'):
        native.acquire({'name': 'supplier', 'archive': 'source.tar.gz',
            'url': response.url, 'sha256': '0' * 64}, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_pins_retain_separate_asr_license_and_default_tts_source():
    pins = json.loads(native.PINS.read_text())
    native.validate_pins(pins)
    sources = {entry['name']: entry for entry in pins['components']}
    assert sources['onnxruntime-asr-notices']['version'] == '1.28.2'
    assert 'COPYING' in sources['espeak-ng-for-piper']['required_notices']
    assert sources['geos']['version'] == pins['geos_version']
    assert len(pins['ocr_models']['files']) == 3
    assert 'training_revision' in pins['ocr_models']
