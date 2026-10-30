"""Exact public notice delivery; no binary execution or redistribution approval."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import zipfile

import pytest

from backend.tests.test_runtime_experiment import recorder


def inputs(tmp_path, monkeypatch):
    module = recorder(monkeypatch)
    repository = Path(__file__).resolve().parents[2]
    source = tmp_path / 'source'
    home = source / 'packaging/runtime-bundle'
    home.mkdir(parents=True)
    shutil.copytree(repository / 'packaging/runtime-bundle/python-notices', home / 'python-notices')
    shutil.copyfile(repository / 'packaging/runtime-bundle/python-supplier.json', home / 'python-supplier.json')
    pin = json.loads((home / 'python-supplier.json').read_bytes())
    evidence = tmp_path / 'evidence'; evidence.mkdir()
    return module, source, home / 'python-notices', pin, evidence


def test_all_retained_supplier_texts_and_provenance_reach_hashed_third_party_inputs(tmp_path, monkeypatch):
    module, source, notices, pin, evidence = inputs(tmp_path, monkeypatch)
    records = module.collect_python_notices(evidence, source, pin)
    assert len(records) == 21 and records == module.expected_python_notice_records(source, pin)
    assert sum((notices / row['path'].rsplit('/', 1)[-1]).stat().st_size for row in records[1:]) == 126019
    for row in records:
        data = (evidence / row['path']).read_bytes()
        assert row['sha256'] == hashlib.sha256(data).hexdigest() and row['bytes'] == len(data)
    from closure import validate_python_notice_delivery
    validate_python_notice_delivery({'licenses': records}, source, evidence)
    provenance = json.loads((notices / 'PROVENANCE.json').read_bytes())
    assert provenance['native_closure'] == 'unverified'
    assert provenance['redistribution_review'] == 'pending-exact-output'
    with pytest.raises(FileExistsError): module.collect_python_notices(evidence, source, pin)


@pytest.mark.parametrize('failure', ['changed-text', 'missing-text', 'extra-file', 'different-supplier', 'claimed-approval'])
def test_retained_text_or_supplier_discrepancy_blocks_before_delivery(tmp_path, monkeypatch, failure):
    module, source, notices, pin, evidence = inputs(tmp_path, monkeypatch)
    path = notices / 'LICENSE.openssl-3.txt'
    if failure == 'changed-text': path.write_bytes(b'altered license text')
    elif failure == 'missing-text': path.unlink()
    elif failure == 'extra-file': (notices / 'unexpected.dll').write_bytes(b'not a notice')
    elif failure == 'different-supplier': pin['source_commit'] = 'd' * 40
    else:
        provenance = notices / 'PROVENANCE.json'
        value = json.loads(provenance.read_bytes()); value['native_closure'] = 'reviewed'
        provenance.write_text(json.dumps(value))
    with pytest.raises(module.ClosureError): module.collect_python_notices(evidence, source, pin)
    assert not (evidence / 'licenses/cpython/supplier').exists()


def test_closure_rejects_removed_stale_or_changed_delivered_notice_bytes(tmp_path, monkeypatch):
    module, source, _notices, pin, evidence = inputs(tmp_path, monkeypatch)
    records = module.collect_python_notices(evidence, source, pin)
    from closure import validate_python_notice_delivery
    with pytest.raises(module.ClosureError, match='missing or source-invalid'):
        validate_python_notice_delivery({'licenses': records[:-1]}, source, evidence)
    stale = [{**row, 'sha256': '0' * 64} for row in records]
    with pytest.raises(module.ClosureError, match='missing or source-invalid'):
        validate_python_notice_delivery({'licenses': stale}, source, evidence)
    (evidence / records[0]['path']).write_bytes(b'changed provenance bytes')
    with pytest.raises(module.ClosureError, match='checksum'):
        validate_python_notice_delivery({'licenses': records}, source, evidence)


def test_finalized_experiment_delivers_original_texts_and_pins_their_output_hashes(tmp_path, monkeypatch):
    module, source, _notices, pin, evidence = inputs(tmp_path, monkeypatch)
    records = module.collect_python_notices(evidence, source, pin)
    (source / 'package.json').write_text(json.dumps({'version': '0.0.1'}))
    output = tmp_path / 'candidate'
    (output / 'ProxyTranscriptAsr/_internal').mkdir(parents=True)
    component = {'name': 'cpython', 'version': pin['version'], 'source': pin['url'],
        'architecture': 'win-amd64', 'license_expression': 'retained notices; review pending',
        'artifact': {'sha256': pin['sha256']}, 'licenses': records}
    value = {'profile': 'runtime-experiment', 'source_commit': 'a' * 40,
        'build_id': 'authored-test', 'components': [component]}
    from closure import write_candidate
    write_candidate(value, source, evidence, output)
    inventory = json.loads((output / 'RUNTIME-INVENTORY.json').read_bytes())
    files = {row['path']: row for row in inventory['files']}
    for record in records:
        name = 'THIRD_PARTY/cpython/' + record['path']
        assert files[name]['sha256'] == record['sha256'] and files[name]['bytes'] == record['bytes']
        assert (output / 'ProxyTranscriptRuntime' / name).read_bytes() == (evidence / record['path']).read_bytes()
    assert inventory['components'][0]['rights_review'] == 'pending-exact-output'
    assert inventory['native_windows_11_acceptance'] == 'unavailable' and inventory['r19_complete'] is False


@pytest.mark.parametrize('profile', ['runtime-experiment', 'runtime'])
def test_runtime_preflight_cannot_omit_required_supplier_delivery(tmp_path, monkeypatch, profile):
    module, source, _notices, _pin, evidence = inputs(tmp_path, monkeypatch)
    from closure import validate_inputs
    artifact = evidence / 'observed.bin'; artifact.write_bytes(b'authored build input')
    row = {'path': artifact.name, 'sha256': module.digest(artifact)}
    names = ['cpython', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'packaging', 'pefile', 'pywin32-ctypes', 'setuptools']
    components = [{'name': name, 'version': '3.12.16' if name == 'cpython' else '1.0',
        'source': 'https://example.test/authored-input', 'architecture': 'win-amd64',
        'review_status': 'approved' if profile == 'runtime' else 'observed-experiment',
        'native_closure': 'reviewed' if profile == 'runtime' else 'unverified',
        'license_expression': 'authored test only', 'artifact': row,
        'licenses': [row], 'installed_files': [row]} for name in names]
    value = {'schema': 'proxy-runtime-build-inputs-v1', 'profile': profile,
        'source_commit': 'a' * 40, 'build_id': 'authored-test', 'components': components}
    with pytest.raises(module.ClosureError, match='supplier notice delivery'):
        validate_inputs(value, source, evidence, check_host=False)


def test_supplier_delivery_refuses_linked_evidence_ancestry_before_writing(tmp_path, monkeypatch):
    module, source, _notices, pin, evidence = inputs(tmp_path, monkeypatch)
    outside = tmp_path / 'unrelated'; outside.mkdir()
    keep = outside / 'keep.txt'; keep.write_bytes(b'preserved')
    try: (evidence / 'licenses').symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip('This host cannot create directory symlinks.')
    from backend.preparation_errors import PreparationFailure
    with pytest.raises(PreparationFailure): module.collect_python_notices(evidence, source, pin)
    assert list(outside.iterdir()) == [keep] and keep.read_bytes() == b'preserved'


def onnx_input(tmp_path, monkeypatch):
    module = recorder(monkeypatch)
    evidence = tmp_path / 'evidence'; evidence.mkdir()
    prefix = tmp_path / 'environment'; prefix.mkdir()
    member = 'onnxruntime/ThirdPartyNotices.txt'
    data = b'Authored incorporated notices\r\nPreserve original bytes.\r\n'
    original = prefix / member; original.parent.mkdir(); original.write_bytes(data)
    wheel = evidence / 'owned-onnx.whl'
    with zipfile.ZipFile(wheel, 'w') as package:
        package.writestr('onnxruntime-1.24.4.dist-info/METADATA', b'Name: onnxruntime\nVersion: 1.24.4\n')
        package.writestr(member, data)
    component = {'name': 'onnxruntime', 'version': '1.24.4', 'architecture': 'win-amd64',
        'source': 'https://example.test/authored-wheel', 'license_expression': 'authored fixture; review pending',
        'artifact': {'path': wheel.name, 'sha256': module.digest(wheel)},
        'installed_files': [{'path': member, 'sha256': hashlib.sha256(data).hexdigest()}], 'licenses': []}
    monkeypatch.setattr(sys, 'prefix', str(prefix))
    monkeypatch.setattr(module.metadata, 'distribution', lambda _: SimpleNamespace(version='1.24.4', locate_file=lambda name: prefix / name))
    return module, evidence, component, original, wheel, data


def test_onnx_notice_binds_wheel_installed_and_final_third_party_bytes(tmp_path, monkeypatch):
    module, evidence, component, _original, _wheel, data = onnx_input(tmp_path, monkeypatch)
    notice = module.collect_onnx_third_party_notice(evidence, component)
    assert notice['bytes'] == len(data) and (evidence / notice['path']).read_bytes() == data
    component['licenses'].append(notice)
    source = tmp_path / 'source'; source.mkdir()
    (source / 'package.json').write_text(json.dumps({'version': '0.0.1'}))
    output = tmp_path / 'candidate'; (output / 'ProxyTranscriptAsr/_internal').mkdir(parents=True)
    from closure import write_candidate
    write_candidate({'profile': 'runtime-experiment', 'source_commit': 'a' * 40,
        'build_id': 'authored-onnx', 'components': [component]}, source, evidence, output)
    target = output / 'ProxyTranscriptRuntime/THIRD_PARTY/onnxruntime' / notice['path']
    assert target.read_bytes() == data
    inventory = json.loads((output / 'RUNTIME-INVENTORY.json').read_bytes())
    assert inventory['components'][0]['notice_sha256'] == [hashlib.sha256(data).hexdigest()]
    assert inventory['components'][0]['rights_review'] == 'pending-exact-output'


@pytest.mark.parametrize('failure', ['wheel-bytes', 'installed-bytes', 'installed-record', 'missing-notice'])
def test_onnx_third_party_notice_rejects_unbound_or_missing_bytes(tmp_path, monkeypatch, failure):
    module, evidence, component, original, wheel, _data = onnx_input(tmp_path, monkeypatch)
    if failure == 'wheel-bytes': wheel.write_bytes(b'changed wheel')
    elif failure == 'installed-bytes': original.write_bytes(b'changed installed text')
    elif failure == 'installed-record': component['installed_files'] = []
    else:
        with zipfile.ZipFile(wheel, 'w') as package:
            package.writestr('onnxruntime-1.24.4.dist-info/METADATA', b'Name: onnxruntime\nVersion: 1.24.4\n')
        component['artifact']['sha256'] = module.digest(wheel)
    with pytest.raises(module.ClosureError): module.collect_onnx_third_party_notice(evidence, component)
    assert not (evidence / 'licenses/onnxruntime/ThirdPartyNotices.txt').exists()
