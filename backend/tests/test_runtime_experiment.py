"""Extracted-runtime failures not exercised by source or frontend-only tests.

Tiny authored archives prove payload binding before a Windows build; they do not
claim native execution, supplier rights or actual game/model acceptance.
"""
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
import marshal
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


@pytest.mark.parametrize('host', ['darwin', 'linux', 'win32'])
def test_runtime_lock_selects_current_windows_entries_without_host_marker_defaults(monkeypatch, host):
    recorder(monkeypatch)
    from closure import windows_runtime_requirements, normalized
    from packaging.requirements import Requirement
    import packaging.markers
    monkeypatch.setattr(sys, 'platform', host)
    monkeypatch.setattr(packaging.markers, 'default_environment',
        lambda: pytest.fail('A Windows lock review must not borrow the review host environment'))
    lock = Path(__file__).resolve().parents[2] / 'requirements.lock.txt'
    unconditional = {}
    for line in lock.read_text().splitlines():
        if line.strip() and not line.startswith('#') and ';' not in line:
            item = Requirement(line)
            unconditional[normalized(item.name)] = next(iter(item.specifier)).version
    selected = windows_runtime_requirements(lock)
    assert {name: version for name, version in selected.items() if name in unconditional} == unconditional
    assert set(selected) - set(unconditional) == {'windows-capture', 'oneocr', 'pyaudiowpatch'}
    assert selected['windows-capture'] == '2.0.1' and selected['oneocr'] == '1.0.12'
    assert selected['pyaudiowpatch'] == '0.2.12.9'


@pytest.mark.parametrize('line', [
    "owned==1.0; sys_platform == 'freebsd'",
    "owned==1.0; sys_platform == 'Windows'",
    "owned==1.0; platform_system == 'Windows'",
    "owned==1.0; platform_release == 'unobserved'",
    "owned==1.0; python_version == '3.12'",
    "owned==1.0; sys_platform == 'win32' and os_name == 'nt'",
    "owned==1.0; sys_platform == 'win32' or sys_platform == 'darwin'",
    'owned>=1.0', 'owned===1.0', 'owned==1.*', 'owned[extra]==1.0',
    'owned @ https://example.test/owned.whl', 'owned==1.0,!=1.1', 'not a requirement',
])
def test_runtime_lock_refuses_unreviewed_target_policy_or_nonexact_pins(tmp_path, monkeypatch, line):
    module = recorder(monkeypatch)
    from closure import windows_runtime_requirements
    lock = tmp_path / 'requirements.lock.txt'; lock.write_text(line + '\n')
    with pytest.raises(module.ClosureError, match='Unsupported|exact version'):
        windows_runtime_requirements(lock)


@pytest.mark.parametrize('second', ["owned_fixture==1.0", "owned_fixture==2.0; sys_platform != 'linux'"])
def test_runtime_lock_refuses_duplicate_selected_names_even_when_versions_match(tmp_path, monkeypatch, second):
    module = recorder(monkeypatch)
    from closure import windows_runtime_requirements
    lock = tmp_path / 'requirements.lock.txt'
    lock.write_text('owned-fixture==1.0\n' + second + '\n')
    with pytest.raises(module.ClosureError, match='Duplicate selected'):
        windows_runtime_requirements(lock)


@pytest.mark.parametrize('fault,reason', [
    (None, None), ('missing-windows', 'windows-capture'), ('wrong-windows-version', 'windows-capture'),
    ('missing-unconditional', 'owned-required'), ('wrong-unconditional-version', 'owned-required'),
    ('windows-artifact', 'checksum'), ('windows-installed-files', 'installed build files'),
    ('windows-notice', 'license/notice'), ('python-architecture', 'CPython 3.12 Windows x64'),
])
def test_offhost_runtime_input_gate_keeps_selected_windows_evidence_and_later_gates(tmp_path, monkeypatch, fault, reason):
    module = recorder(monkeypatch)
    import closure
    source = tmp_path / 'source'; source.mkdir()
    evidence = tmp_path / 'evidence'; evidence.mkdir()
    (source / 'requirements.lock.txt').write_text(
        "owned-required==1.0\nwindows-capture==2.0.1; sys_platform == 'win32'\n"
        "python-xlib==0.33; sys_platform == 'linux'\npyobjc-core==13.0; sys_platform == 'darwin'\n")
    components = []
    for name in ('cpython', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'packaging',
                 'pefile', 'pywin32-ctypes', 'setuptools', 'flatbuffers', 'owned-required', 'windows-capture'):
        path = evidence / (name + '.authored'); path.write_bytes(b'authored non-native input')
        entry = {'path': path.name, 'sha256': module.digest(path)}
        components.append({'name': name, 'version': {'cpython': '3.12.16', 'windows-capture': '2.0.1'}.get(name, '1.0'),
            'architecture': 'win-amd64', 'source': 'https://example.test/authored-fixture',
            'license_expression': 'authored test only; no rights evidence',
            'review_status': 'observed-experiment', 'native_closure': 'unverified',
            'artifact': entry, 'licenses': [entry], 'installed_files': [entry]})
    windows = components[-1]
    if fault == 'missing-windows': components.remove(windows)
    elif fault == 'wrong-windows-version': windows['version'] = '2.0.0'
    elif fault == 'missing-unconditional': components.pop(-2)
    elif fault == 'wrong-unconditional-version': components[-2]['version'] = '2.0'
    elif fault == 'windows-artifact': (evidence / windows['artifact']['path']).write_bytes(b'changed')
    elif fault == 'windows-installed-files': windows['installed_files'] = []
    elif fault == 'windows-notice': windows['licenses'] = []
    elif fault == 'python-architecture': components[0]['architecture'] = 'any'
    value = {'schema': 'proxy-runtime-build-inputs-v1', 'profile': 'runtime-experiment',
        'source_commit': 'a' * 40, 'build_id': 'authored-marker-only', 'components': components}
    # This fixture isolates marker selection. Supplier notice delivery has its
    # own exact-byte tests; no frontend/native/helper acceptance is manufactured.
    monkeypatch.setattr(closure, 'validate_python_notice_delivery', lambda *_: None)
    monkeypatch.setattr(closure, 'validate_flatbuffers_notice_delivery', lambda *_: None)
    class LaterFrontendGate(Exception):
        pass
    def still_requires_frontend(*_):
        raise LaterFrontendGate()
    monkeypatch.setattr('backend.desktop_frontend.FrontendBuild', still_requires_frontend)
    expected = module.ClosureError if fault else LaterFrontendGate
    with pytest.raises(expected, match=reason):
        closure.validate_inputs(value, source, evidence, check_host=False)


@pytest.mark.parametrize('profile,kind', [('diagnostic', 'native'), ('frontend-experiment', 'api'),
                                       ('runtime-experiment', 'asr')])
def test_probe_refuses_wrong_profile_or_native_image_before_import(tmp_path, monkeypatch, profile, kind):
    layout = frozen_layout(tmp_path, profile=profile)
    monkeypatch.setattr(bundle_entry, 'discover_layout', lambda: layout)
    monkeypatch.setattr(runtime_probe, 'main', lambda *_: pytest.fail('Disabled probe executed'))
    with pytest.raises(runtime_bundle.RuntimeBundleError, match='profile|isolated'):
        bundle_entry.main(['--runtime-probe', kind])


def test_experiment_manifest_allows_fixed_account_dialog_but_cannot_expand_to_update_children(tmp_path, monkeypatch):
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
    assert 'account-key' in layout.children
    for child in ('toolkit-update', 'unregistered-command'):
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
    with pytest.raises(module.ClosureError, match=r'owned: owned\.py \(content mismatch\)') as failure:
        module.verify_wheel(wheel)
    assert str(prefix) not in str(failure.value)
    (prefix / 'owned.py').unlink()
    with pytest.raises(module.ClosureError, match=r'owned: owned\.py \(missing file\)'):
        module.verify_wheel(wheel)


def test_actual_utf8_wheel_notice_metadata_can_be_recorded_as_json(tmp_path, monkeypatch):
    module = recorder(monkeypatch)
    wheel = tmp_path / 'unicode-notice.whl'
    with zipfile.ZipFile(wheel, 'w') as package:
        package.writestr('owned-1.0.dist-info/METADATA', 'Name: owned\nVersion: 1.0\nLicense: Copyright \u00e9\n'.encode())
    with zipfile.ZipFile(wheel) as package:
        value = module.wheel_metadata(package)
    assert json.loads(json.dumps({'license': value['License']})) == {'license': 'Copyright \u00e9'}


@pytest.mark.parametrize('optimization', [0, 1, 2])
def test_pip_recompiled_wheel_cache_requires_matching_verified_source(tmp_path, monkeypatch, optimization):
    module = recorder(monkeypatch)
    prefix = tmp_path / 'environment'; prefix.mkdir()
    source = prefix / 'owned.py'
    source.write_bytes(b'"authored module"\nassert True\nOWNED = True\n')
    cache = Path(importlib.util.cache_from_source(str(source), optimization=optimization or ''))
    cache.parent.mkdir()
    cache_name = cache.relative_to(prefix).as_posix()
    wheel = tmp_path / 'owned.whl'
    with zipfile.ZipFile(wheel, 'w') as package:
        package.writestr('owned-1.0.dist-info/METADATA', b'Name: owned\nVersion: 1.0\n')
        package.writestr('owned.py', source.read_bytes())
        package.writestr(cache_name, b'supplier cache from another build location')
    metadata_path = prefix / 'owned-1.0.dist-info/METADATA'
    metadata_path.parent.mkdir(); metadata_path.write_bytes(b'Name: owned\nVersion: 1.0\n')
    monkeypatch.setattr(sys, 'prefix', str(prefix))
    monkeypatch.setattr(module.metadata, 'distribution', lambda _: SimpleNamespace(locate_file=lambda name: prefix / name))
    header = importlib.util.MAGIC_NUMBER + bytes(12)
    cache.write_bytes(header + marshal.dumps(compile(source.read_bytes(), str(source), 'exec', optimize=optimization)))
    module.verify_wheel(wheel)
    cache.write_bytes(header + marshal.dumps(compile('OWNED = False', str(source), 'exec', optimize=optimization)))
    with pytest.raises(module.ClosureError, match='content mismatch'):
        module.verify_wheel(wheel)
    source.unlink()
    with zipfile.ZipFile(wheel) as package:
        assert not module.verified_recompiled_cache(package, cache_name, cache, SimpleNamespace(locate_file=lambda name: prefix / name))


def test_collected_tree_rejects_empty_private_directories(tmp_path, monkeypatch):
    # File-only scans miss empty private roots and cannot detect directory-only
    # application writes. Empty directory creation is still an application write.
    module = recorder(monkeypatch)
    from closure import inventory_output
    (tmp_path / 'data').mkdir()
    with pytest.raises(module.ClosureError, match='Private trees'):
        inventory_output(tmp_path)


def test_runtime_collection_binds_owned_bridge_to_current_sources_not_only_receipt_strings(tmp_path, monkeypatch):
    # Reader dispatch tests bind nested/outer files, but did not bind the
    # packaging collector to the actual source files of this runtime commit.
    from backend.tests.test_prebuilt_readers import helper_fixture, save, digest
    from backend import prebuilt_readers
    monkeypatch.setattr(prebuilt_readers, 'host_platform', lambda: 'win-x64')
    module = recorder(monkeypatch)
    layout, home, manifest = helper_fixture(tmp_path, 'nte')
    source = tmp_path / 'source'
    for name in manifest['source_inputs']:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'owned source fixture')
    manifest['source_inputs'] = {name: digest((source / name).read_bytes()) for name in manifest['source_inputs']}
    receipt = json.loads((home / 'build-receipt.json').read_bytes())
    receipt['source_inputs'] = manifest['source_inputs']
    data = json.dumps(receipt).encode(); (home / 'build-receipt.json').write_bytes(data)
    manifest['files']['build-receipt.json'] = {'bytes': len(data), 'sha256': digest(data)}
    layout = save(layout, home, manifest)
    resources = [{'path': name, 'sha256': value} for name, value in layout.resources.items()]
    helper = module.verified_nte(layout.resource_root, resources, layout.source_commit, source)
    assert helper.kind == 'nte'
    (source / 'scripts/game-readers/NteReader.cs').write_bytes(b'changed current source')
    with pytest.raises(module.ClosureError, match='sources differ'):
        module.verified_nte(layout.resource_root, resources, layout.source_commit, source)


@pytest.mark.parametrize('linked', ['evidence', 'helpers'])
@pytest.mark.parametrize('kind', ['nte', 'codec'])
def test_collection_rejects_linked_destination_before_copying_outside_evidence(tmp_path, monkeypatch, linked, kind):
    # Input-tree link checks do not protect the copy destination: validation
    # after copytree used to leave helper bytes in an unrelated directory.
    from backend.preparation_errors import PreparationFailure
    module = recorder(monkeypatch)
    helper = tmp_path / 'owned-helper'; helper.mkdir()
    (helper / 'owned.txt').write_bytes(b'authored helper fixture')
    outside = tmp_path / 'unrelated'; outside.mkdir()
    preserved = outside / 'preserved.txt'; preserved.write_bytes(b'preserve unrelated bytes')
    evidence = tmp_path / 'evidence'
    link = evidence
    if linked == 'helpers':
        evidence.mkdir()
        link = evidence / ('helpers' if kind == 'nte' else 'codecs')
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('This host cannot create directory symlinks.')
    with pytest.raises(PreparationFailure):
        collect = module.collect_nte if kind == 'nte' else module.collect_codec
        collect(helper, evidence, 'a' * 40, tmp_path / 'source')
    assert list(outside.iterdir()) == [preserved]
    assert preserved.read_bytes() == b'preserve unrelated bytes'
