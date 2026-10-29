"""Extracted-runtime failures not exercised by source or frontend-only tests.

Tiny authored archives prove payload binding before a Windows build; they do not
claim native execution, supplier rights or actual game/model acceptance.
"""
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
from types import SimpleNamespace
import zipfile

import pytest

from backend import bundle_entry, runtime_bundle, runtime_probe
from backend.tests.test_runtime_bundle import frozen_layout


def recorder(monkeypatch):
    path = Path(runtime_bundle.__file__).resolve().parents[1] / 'packaging/runtime-bundle/record_runtime.py'
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location('runtime_experiment_recorder_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('profile,kind', [('diagnostic', 'native'), ('frontend-experiment', 'api'),
                                       ('runtime-experiment', 'asr')])
def test_probe_refuses_wrong_profile_or_native_image_before_import(tmp_path, monkeypatch, profile, kind):
    layout = frozen_layout(tmp_path, profile=profile)
    monkeypatch.setattr(bundle_entry, 'discover_layout', lambda: layout)
    monkeypatch.setattr(runtime_probe, 'main', lambda *_: pytest.fail('Disabled probe executed'))
    with pytest.raises(runtime_bundle.RuntimeBundleError, match='profile|isolated'):
        bundle_entry.main(['--runtime-probe', kind])


def test_experiment_manifest_cannot_expand_to_credential_or_update_children(tmp_path, monkeypatch):
    layout = frozen_layout(tmp_path, children=runtime_bundle.EXPERIMENT_CHILDREN, profile='runtime-experiment')
    manifest = dict(schema=runtime_bundle.MANIFEST_SCHEMA, profile=layout.profile, version=layout.version,
        source_commit=layout.source_commit, build_id=layout.build_id,
        children=list(layout.children), resources={})
    path = layout.resource_root / 'runtime-manifest.json'
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(layout.resource_root), raising=False)
    monkeypatch.setattr(sys, 'executable', str(layout.executable))
    path.write_text(json.dumps(manifest))
    env = layout.child_environment(environ={})
    assert runtime_bundle.discover_layout(env).children == runtime_bundle.EXPERIMENT_CHILDREN
    for child in ('toolkit-update', 'account-key'):
        manifest['children'] = [*layout.children, child]
        path.write_text(json.dumps(manifest))
        with pytest.raises(runtime_bundle.RuntimeBundleError, match='child inventory'):
            runtime_bundle.discover_layout(env)


def test_synthetic_probe_refuses_unmarked_or_foreign_private_roots(tmp_path):
    layout = frozen_layout(tmp_path, profile='runtime-experiment')
    with pytest.raises(runtime_bundle.RuntimeBundleError, match='synthetic roots'):
        runtime_probe.synthetic_roots(layout)
    layout.state_root.mkdir(parents=True)
    marker = layout.state_root / 'synthetic-probe.json'
    marker.write_text(json.dumps({'build_id': 'another-build', 'synthetic': True}))
    with pytest.raises(runtime_bundle.RuntimeBundleError, match='synthetic roots'):
        runtime_probe.synthetic_roots(layout)
    marker.write_text(json.dumps({'build_id': layout.build_id, 'synthetic': True}))
    runtime_probe.synthetic_roots(layout)
    with pytest.raises(runtime_bundle.RuntimeBundleError, match='synthetic roots'):
        runtime_probe.synthetic_roots(replace(layout, data_root=tmp_path / 'other-private-data'))


def test_probe_blocks_remote_transport_without_reading_accounts():
    runtime_probe.block_remote_access('socket.connect', (None, ('127.0.0.1', 8766)))
    for address in [('example.test', 443), ('192.0.2.1', 80), ('::1', 443), '/private/socket']:
        with pytest.raises(runtime_bundle.RuntimeBundleError, match='remote'):
            runtime_probe.block_remote_access('socket.connect', (None, address))


def test_supplier_archive_is_bound_to_installed_bytes_and_exact_hash(tmp_path, monkeypatch):
    module = recorder(monkeypatch)
    archive = tmp_path / 'owned-python.tar.gz'
    prefix = tmp_path / 'python'; prefix.mkdir()
    payload = b'authored native fixture, not executable'
    (prefix / 'python312.dll').write_bytes(payload)
    with tarfile.open(archive, 'w:gz') as package:
        member = tarfile.TarInfo('python/python312.dll'); member.size = len(payload)
        package.addfile(member, io.BytesIO(payload))
    pin = {'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    assert module.verify_python(archive, prefix, pin) == [{'path': 'python312.dll', 'sha256': hashlib.sha256(payload).hexdigest()}]
    (prefix / 'python312.dll').write_bytes(b'tampered')
    with pytest.raises(module.ClosureError, match='differs from the supplier archive'):
        module.verify_python(archive, prefix, pin)
    with pytest.raises(module.ClosureError, match='exact observed pin'):
        module.verify_python(archive, prefix, {'sha256': '0' * 64})


@pytest.mark.parametrize('name,link', [('python/../escape', False), ('python/aliased.dll', True)])
def test_supplier_archive_rejects_traversal_and_links(tmp_path, monkeypatch, name, link):
    module = recorder(monkeypatch)
    archive = tmp_path / 'unsafe.tar.gz'
    with tarfile.open(archive, 'w:gz') as package:
        member = tarfile.TarInfo(name)
        if link:
            member.type = tarfile.SYMTYPE; member.linkname = 'python312.dll'
        package.addfile(member)
    with pytest.raises((module.ClosureError, runtime_bundle.RuntimeBundleError)):
        module.verify_python(archive, tmp_path, {'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()})


def test_wheel_payload_tampering_is_not_accepted_by_version_metadata(tmp_path, monkeypatch):
    module = recorder(monkeypatch)
    prefix = tmp_path / 'environment'; prefix.mkdir()
    files = {'owned-1.0.dist-info/METADATA': b'Name: owned\nVersion: 1.0\n',
             'owned-1.0.dist-info/RECORD': b'original archive inventory', 'owned.py': b'OWNED = True\n'}
    wheel = tmp_path / 'owned.whl'
    with zipfile.ZipFile(wheel, 'w') as package:
        for name, content in files.items():
            package.writestr(name, content)
            target = prefix / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    monkeypatch.setattr(sys, 'prefix', str(prefix))
    monkeypatch.setattr(module.metadata, 'distribution', lambda _: SimpleNamespace(locate_file=lambda name: prefix / name))
    (prefix / 'owned-1.0.dist-info/RECORD').write_bytes(b'pip rewritten installed inventory')
    module.verify_wheel(wheel)
    (prefix / 'owned.py').write_bytes(b'ALTERED = True\n')
    with pytest.raises(module.ClosureError, match='differs from archive'):
        module.verify_wheel(wheel)
