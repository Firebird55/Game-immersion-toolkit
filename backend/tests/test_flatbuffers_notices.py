"""Exact notice/payload delivery using authored package bytes, not rights approval."""
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
    source = tmp_path / 'source'
    home = source / 'packaging/runtime-bundle/flatbuffers-notices'
    repository = Path(__file__).resolve().parents[2]
    shutil.copytree(repository / 'packaging/runtime-bundle/flatbuffers-notices', home)
    provenance = json.loads((home / 'PROVENANCE.json').read_bytes())
    prefix = tmp_path / 'environment'
    package_root = prefix / 'Lib/site-packages'
    evidence = tmp_path / 'evidence'; evidence.mkdir()
    wheel = evidence / provenance['wheel']['name']
    records = []
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('flatbuffers-25.12.19.dist-info/METADATA', b'Name: flatbuffers\nVersion: 25.12.19\n')
        for index, entry in enumerate(provenance['python_payload']):
            data = f'# Independently authored package fixture {index}\n'.encode()
            path = package_root / entry['path']; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            archive.writestr(entry['path'], data)
            entry.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            records.append({'path': path.relative_to(prefix).as_posix(), 'sha256': entry['sha256']})
    provenance['wheel'].update(sha256=module.digest(wheel), bytes=wheel.stat().st_size)
    (home / 'PROVENANCE.json').write_text(json.dumps(provenance))
    component = {'name': 'flatbuffers', 'version': '25.12.19', 'architecture': 'any',
        'artifact': {'path': wheel.name, 'sha256': module.digest(wheel)}, 'installed_files': records,
        'licenses': [], 'source': 'https://example.test/authored-wheel', 'license_expression': 'authored test; review pending',
        'review_status': 'observed-experiment', 'native_closure': 'unverified'}
    monkeypatch.setattr(sys, 'prefix', str(prefix))
    monkeypatch.setattr(module.metadata, 'distribution', lambda _: SimpleNamespace(
        version=component['version'], locate_file=lambda name: package_root / name))
    return module, source, home, evidence, component, wheel, package_root


def test_source_notice_binds_all_observed_payloads_and_reaches_central_notices(tmp_path, monkeypatch):
    module, source, home, evidence, component, _wheel, _package_root = inputs(tmp_path, monkeypatch)
    records = module.collect_flatbuffers_notices(evidence, source, component)
    component['licenses'].extend(records)
    assert records == module.expected_flatbuffers_notice_records(evidence, source, component)
    assert len(records) == 2 and (evidence / records[0]['path']).read_bytes() == (home / 'LICENSE').read_bytes()
    from closure import validate_flatbuffers_notice_delivery, write_candidate
    validate_flatbuffers_notice_delivery(component, source, evidence)
    (source / 'package.json').write_text(json.dumps({'version': '0.0.1'}))
    output = tmp_path / 'candidate'; (output / 'ProxyTranscriptAsr/_internal').mkdir(parents=True)
    # This test owns notice delivery; actual isolated codec scope has separate disk tests.
    monkeypatch.setattr(sys.modules['closure'], 'validate_codec_output', lambda *_: None)
    write_candidate({'profile': 'runtime-experiment', 'source_commit': 'a' * 40,
        'build_id': 'authored-source-notices', 'components': [component]}, source, evidence, output)
    for row in records:
        delivered = output / 'ProxyTranscriptRuntime/THIRD_PARTY/flatbuffers' / row['path']
        assert delivered.read_bytes() == (evidence / row['path']).read_bytes()
    inventory = json.loads((output / 'RUNTIME-INVENTORY.json').read_bytes())
    assert inventory['components'][0]['notice_sha256'] == [row['sha256'] for row in records]
    assert inventory['components'][0]['rights_review'] == 'pending-exact-output'
    assert inventory['r19_complete'] is False and inventory['native_windows_11_acceptance'] == 'unavailable'
    assert component['review_status'] == 'observed-experiment' and component['native_closure'] == 'unverified'
    with pytest.raises(FileExistsError): module.collect_flatbuffers_notices(evidence, source, component)


@pytest.mark.parametrize('failure', ['changed-notice', 'different-wheel', 'changed-installed',
    'missing-installed-record', 'wrong-source-member', 'partial-source-payload', 'claimed-approval'])
def test_unbound_notice_source_or_installed_payload_is_rejected_before_delivery(tmp_path, monkeypatch, failure):
    module, source, home, evidence, component, _wheel, package_root = inputs(tmp_path, monkeypatch)
    provenance_file = home / 'PROVENANCE.json'; provenance = json.loads(provenance_file.read_bytes())
    if failure == 'changed-notice': (home / 'LICENSE').write_bytes(b'changed upstream notice')
    elif failure == 'different-wheel': component['artifact']['sha256'] = '0' * 64
    elif failure == 'changed-installed': (package_root / provenance['python_payload'][0]['path']).write_bytes(b'changed payload')
    elif failure == 'missing-installed-record': component['installed_files'].pop()
    elif failure == 'wrong-source-member': provenance['python_payload'][0]['source_member'] = 'unrelated/source.py'
    elif failure == 'partial-source-payload': provenance['python_payload'].pop()
    else: provenance['redistribution_review'] = 'approved'
    provenance_file.write_text(json.dumps(provenance))
    with pytest.raises(module.ClosureError): module.collect_flatbuffers_notices(evidence, source, component)
    assert not (evidence / 'licenses/flatbuffers/source').exists()


def test_preflight_rejects_omitted_or_changed_delivered_source_notices(tmp_path, monkeypatch):
    module, source, _home, evidence, component, _wheel, _package_root = inputs(tmp_path, monkeypatch)
    records = module.collect_flatbuffers_notices(evidence, source, component)
    from closure import validate_flatbuffers_notice_delivery
    component['licenses'] = records[:-1]
    with pytest.raises(module.ClosureError, match='missing or source-invalid'):
        validate_flatbuffers_notice_delivery(component, source, evidence)
    component['licenses'] = records
    (evidence / records[0]['path']).write_bytes(b'changed delivered notice')
    with pytest.raises(module.ClosureError, match='checksum'):
        validate_flatbuffers_notice_delivery(component, source, evidence)
