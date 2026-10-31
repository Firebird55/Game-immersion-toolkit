"""Actual LICENCE delivery; metadata and an upstream SBOM are not a license grant."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

from backend.tests.test_runtime_bundle import diagnostic_recorder_module


def test_british_licence_is_bound_and_delivered_without_copying_raw_sbom(tmp_path, monkeypatch):
    module = diagnostic_recorder_module(monkeypatch)
    evidence = tmp_path / 'evidence'; evidence.mkdir()
    prefix = tmp_path / 'environment'; prefix.mkdir()
    source = tmp_path / 'source'; source.mkdir()
    (source / 'package.json').write_text(json.dumps({'version': '0.0.1'}))
    (prefix / 'python.exe').write_bytes(b'authored interpreter fixture; never executed')
    (prefix / 'LICENSE.txt').write_bytes(b'authored interpreter notice')
    (evidence / 'python.tar.gz').write_bytes(b'authored supplier archive fixture')
    member = 'windows_capture-2.0.1.dist-info/licenses/LICENCE'
    sbom = 'windows_capture-2.0.1.dist-info/sboms/build.cyclonedx.json'
    notice = b'Authored MIT notice with copyright.\r\nPreserve original bytes.\r\n'
    package = prefix / 'Lib/site-packages'
    for name, data in [(member, notice), (sbom, b'PRIVATE_BUILD_PATH_SENTINEL')]:
        target = package / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    wheelhouse = evidence / 'wheelhouse'; wheelhouse.mkdir()
    wheel = wheelhouse / 'windows_capture-2.0.1-cp39-abi3-win_amd64.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('windows_capture-2.0.1.dist-info/METADATA',
            b'Name: windows-capture\nVersion: 2.0.1\nLicense-Expression: MIT\nLicense-File: LICENCE\n')
        archive.writestr(member, notice)
        archive.writestr(sbom, b'PRIVATE_BUILD_PATH_SENTINEL')
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys, 'prefix', str(prefix))
    monkeypatch.setattr(sys, 'base_prefix', str(prefix))
    monkeypatch.setattr(sys, 'executable', str(prefix / 'python.exe'))
    monkeypatch.setattr(module.platform, 'architecture', lambda: ('64bit', 'WindowsPE'))
    monkeypatch.setattr(module.platform, 'python_version', lambda: '3.12.16')
    monkeypatch.setattr(module.metadata, 'distribution', lambda _: SimpleNamespace(
        version='2.0.1', files=[Path(member), Path(sbom)], locate_file=lambda name: package / name))
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *_a, **_k: 'a' * 40)
    value = module.record(evidence, 'python.tar.gz', 'https://example.test/owned-input',
        'authored-licence', source, metadata_notices=True)
    component = next(row for row in value['components'] if row['name'] == 'windows-capture')
    assert len(component['licenses']) == 1 and component['licenses'][0]['path'].endswith('/LICENCE')
    assert component['review_status'] == 'observed-diagnostic' and component['native_closure'] == 'unverified'
    from closure import write_candidate
    output = tmp_path / 'candidate'
    write_candidate(value, source, evidence, output)
    delivered = output / 'ProxyTranscriptRuntime/THIRD_PARTY/windows-capture' / component['licenses'][0]['path']
    assert delivered.read_bytes() == notice
    assert not list((output / 'ProxyTranscriptRuntime').rglob('*.cyclonedx.json'))
    proof = json.loads((output / 'CANDIDATE-PROVENANCE.json').read_bytes())
    assert proof['redistribution_review'] == 'pending-exact-output'
    assert proof['native_acceptance'] == 'unavailable' and proof['r19_complete'] is False
