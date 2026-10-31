"""Authored file/TOC contracts only; no PE execution or real supplier approval."""
from copy import deepcopy
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import subprocess
import tarfile
from types import SimpleNamespace
import zipfile

import pytest

from backend.tests.test_runtime_experiment import recorder


def checksum(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def toy(tmp_path, monkeypatch):
    module = recorder(monkeypatch)
    monkeypatch.setitem(sys.modules, 'record_runtime', module)
    base = tmp_path.resolve()
    evidence = base / 'evidence'; evidence.mkdir()
    prefix = base / 'private-interpreter'; prefix.mkdir()
    system = base / 'authoritative-system-directory'; system.mkdir()
    build = base / 'build'; build.mkdir()
    output = base / 'quarantine'
    source = base / 'source'; source.mkdir()
    (source / 'package.json').write_text(json.dumps({'version': '0.0.1'}))
    python_dll = prefix / 'python312.dll'; python_dll.write_bytes(b'authored interpreter; not executable')
    archive = evidence / 'authored-python.tar.gz'
    with tarfile.open(archive, 'w:gz') as package:
        entry = tarfile.TarInfo('python/python312.dll'); entry.size = python_dll.stat().st_size
        package.addfile(entry, io.BytesIO(python_dll.read_bytes()))
    members = {'owned/one.dll': b'authored identical wheel DLL; not executable',
               'owned/two.dll': b'authored identical wheel DLL; not executable',
               'owned-1.0.dist-info/METADATA': b'Name: owned\nVersion: 1.0\n',
               'owned-1.0.dist-info/RECORD': b'authored original record'}
    wheel = evidence / 'authored-owned.whl'
    installed = prefix / 'Lib/site-packages'
    with zipfile.ZipFile(wheel, 'w') as package:
        for name, raw in members.items():
            package.writestr(name, raw)
            target = installed / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    monkeypatch.setattr(sys, 'prefix', str(prefix))
    monkeypatch.setattr(sys, 'base_prefix', str(prefix))
    monkeypatch.setattr(module.metadata, 'distribution', lambda _name: SimpleNamespace(locate_file=lambda name: installed / name))
    monkeypatch.setattr(module, 'native_system_directory', lambda: system)
    # Same bytes as a supplier DLL must not override the actual canonical source.
    system_dll = system / 'authored-system.dll'; system_dll.write_bytes(members['owned/one.dll'])
    monkeypatch.setenv('SystemRoot', str(base / 'private-environment-bait'))
    def component(name, version, artifact, files):
        return {'name': name, 'version': version, 'artifact': {'path': artifact.name, 'sha256': checksum(artifact.read_bytes())},
            'installed_files': files, 'architecture': 'win-amd64', 'source': 'https://pypi.org/project/' + name + '/',
            'license_expression': 'authored fixture only', 'licenses': []}
    values = [component('cpython', '3.12.16', archive, [{'path': 'python312.dll', 'sha256': checksum(python_dll.read_bytes())}]),
              component('owned', '1.0', wheel, [{'path': 'Lib/site-packages/' + name, 'sha256': checksum(raw)} for name, raw in members.items()])]
    resources = []
    for name in ('helpers/nte/owned-helper.dll', 'codecs/xiph-flac/FLAC.dll', 'codecs/xiph-flac/flac.exe'):
        path = evidence / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(('authored ' + name).encode())
        resources.append({'path': name, 'sha256': checksum(path.read_bytes()), 'version': '1.0',
            'source': 'https://github.com/owned/project/tree/abc123'})
    value = {'profile': 'runtime-experiment', 'source_commit': 'a'*40, 'build_id': 'authored-native-collection',
        'components': values, 'resources': resources}
    manifest = base / 'inputs.json'; manifest.write_text(json.dumps(value))
    return SimpleNamespace(module=module, base=base, evidence=evidence, prefix=prefix, installed=installed,
        system=system, build=build, output=output, source=source, value=value, manifest=manifest,
        python_dll=python_dll, one=installed/'owned/one.dll', two=installed/'owned/two.dll', system_dll=system_dll)


def start(toy):
    return toy.module.NativeCollectionObservation(toy.value, toy.evidence, toy.output, toy.build, toy.manifest)


def observe_and_copy(toy, *, finish=True):
    observer = start(toy)
    main = [('renamed.dll', str(toy.one), 'BINARY'), ('python312.dll', str(toy.python_dll), 'BINARY'),
            ('system.dll', str(toy.system_dll), 'BINARY')]
    explicit = [(r['path'], str(toy.evidence/r['path']), 'DATA') for r in toy.value['resources']]
    asr = [('owned/two.dll', str(toy.two), 'EXTENSION')]
    observer.observe_analysis('main', main, explicit)
    observer.observe_analysis('asr', asr)
    for process, rows in (('main', main+explicit), ('asr', asr)):
        folder = toy.output / ('ProxyTranscriptAsr' if process == 'asr' else 'ProxyTranscriptRuntime')
        for destination, origin, _kind in rows:
            target = folder/'_internal'/destination; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
        name = 'ProxyTranscriptAsr.exe' if process == 'asr' else 'ProxyTranscriptRuntime.exe'
        generated = toy.build/name; generated.write_bytes(('authored generated ' + process).encode())
        observer.observe_generated(process, generated)
        shutil.copyfile(generated, folder/name)
    if finish:
        observer.finish()
    return observer


def failed(toy):
    report = json.loads((toy.output/toy.module.NATIVE_SOURCE_FAILED).read_text())
    assert report['status'] == 'failed' and report['failure_code'] in toy.module.NATIVE_FAILURES
    assert report['raw_paths_published'] is False and report['raw_toc_published'] is False
    for gate in ('source_delivery_approved', 'production_execution_allowed', 'r19_complete'):
        assert report[gate] is False
    serialized = json.dumps(report)
    assert str(toy.base) not in serialized and 'private-' not in serialized
    assert not (toy.output/toy.module.NATIVE_SOURCE_FINAL).exists()
    return report


def test_actual_sources_ambiguity_generated_and_final_inventory_are_bound_without_changing_old_fields(toy, monkeypatch):
    observe_and_copy(toy)
    from closure import write_candidate
    from native_ownership import native_input_ownership
    monkeypatch.setattr('closure.validate_codec_output', lambda *_: None)  # Existing separate codec/source fixtures own that gate.
    write_candidate(toy.value, toy.source, toy.evidence, toy.output, input_manifest=toy.manifest)
    inventory_raw = (toy.output/'RUNTIME-INVENTORY.json').read_bytes()
    inventory = json.loads(inventory_raw)
    report = json.loads((toy.output/toy.module.NATIVE_SOURCE_FINAL).read_bytes())
    assert report['status'] == 'observed-not-approved'
    assert report['inventory_sha256'] == checksum(inventory_raw)
    assert report['input_snapshot']['sha256'] == checksum((toy.output/toy.module.NATIVE_SOURCE_INPUTS).read_bytes())
    assert report['build_inputs'] == {'bytes': toy.manifest.stat().st_size, 'sha256': checksum(toy.manifest.read_bytes())}
    assert report['source_commit'] == toy.value['source_commit'] and report['build_id'] == toy.value['build_id']
    assert all(set(r) == {'path','bytes','sha256'} for r in inventory['files'])
    assert inventory['native_input_ownership'] == native_input_ownership(toy.value['components'], toy.value['resources'], inventory['files'])
    rows = {r['path']: r for r in report['records']}
    assert len(rows['_internal/renamed.dll']['source']['resolved_inputs']) == 1
    assert len(rows['_internal/renamed.dll']['source']['byte_identical_inputs']) == 2
    assert rows['_internal/system.dll']['source'] == {'role': 'windows-system-observed',
        'provider': 'GetSystemDirectoryW', 'system_member': 'authored-system.dll'}
    assert rows['_internal/helpers/nte/owned-helper.dll']['processing'] == 'explicit-native-resource'
    assert rows['_internal/codecs/xiph-flac/FLAC.dll']['source']['resolved_inputs'][0]['kind'] == 'resource'
    assert rows['ProxyTranscriptRuntime.exe']['source']['role'] == 'generated-processing-observed'
    assert rows['asr/ProxyTranscriptAsr.exe']['source']['internals_provenance'] == 'unverified'
    assert report['rights_review'] == 'pending-exact-output' and report['native_closure'] == 'unverified'
    assert report['native_windows_11_acceptance'] == 'unavailable'
    for gate in ('source_delivery_approved', 'production_execution_allowed', 'r19_complete'):
        assert report[gate] is False
    assert str(toy.base) not in json.dumps(report)
    assert not any('NATIVE-COLLECTION' in r['path'] for r in inventory['files'])


@pytest.mark.parametrize('change', ['foreign', 'symlink', 'changed-source', 'aliased-destination', 'escaping-destination'])
def test_source_refusal_is_fixed_private_and_never_writes_a_passing_record(toy, change):
    observer = start(toy)
    origin = toy.one; destination = 'owned.dll'
    if change == 'foreign':
        origin = toy.base/'private-foreign.dll'; origin.write_bytes(toy.one.read_bytes())
    if change == 'symlink':
        origin = toy.base/'private-link.dll'
        try: origin.symlink_to(toy.one)
        except OSError: pytest.skip('File symlinks are unavailable on this host.')
    if change == 'changed-source': toy.one.write_bytes(b'changed after archive verification')
    if change == 'escaping-destination': destination = '../private-escape.dll'
    if change == 'aliased-destination': observer.observe_analysis('main', [('Owned.dll', str(origin), 'BINARY')])
    with pytest.raises(toy.module.NativeCollectionError) as error:
        observer.observe_analysis('main', [(destination, str(origin), 'BINARY')])
    assert str(toy.base) not in str(error.value) and 'private-' not in str(error.value)
    failed(toy)


@pytest.mark.parametrize('change', ['output', 'missing-record', 'source-fields', 'source-bytes', 'input-manifest', 'duplicate-json', 'unlisted-native'])
def test_finalization_refuses_tamper_missing_sources_and_unexplained_transformations(toy, change):
    observe_and_copy(toy)
    from closure import inventory_output, validate_native_collection
    (toy.output/'ProxyTranscriptAsr').rename(toy.output/'ProxyTranscriptRuntime/asr')
    snapshot = toy.output/toy.module.NATIVE_SOURCE_INPUTS
    value = json.loads(snapshot.read_bytes())
    if change == 'output': (toy.output/'ProxyTranscriptRuntime/_internal/renamed.dll').write_bytes(b'unexplained processed bytes')
    if change == 'missing-record': value['records'].pop(0)
    if change == 'source-fields': value['records'][0]['source']['private-extra-field'] = 'secret-marker'
    if change == 'source-bytes': toy.one.write_bytes(b'changed after snapshot')
    if change == 'input-manifest': toy.manifest.write_text(json.dumps({**toy.value, 'private-extra-field': 'secret-marker'}))
    if change == 'unlisted-native': (toy.output/'ProxyTranscriptRuntime/_internal/unlisted.dll').write_bytes(b'unlisted native bytes')
    if change == 'duplicate-json': snapshot.write_text('{"schema":"private-marker",' + snapshot.read_text()[1:])
    else: snapshot.write_text(json.dumps(value))
    files = inventory_output(toy.output/'ProxyTranscriptRuntime'); original = deepcopy(files)
    with pytest.raises(toy.module.NativeCollectionError) as error:
        validate_native_collection(toy.value, toy.evidence, toy.output, files, toy.manifest)
    assert files == original
    assert str(toy.base) not in str(error.value) and 'secret-marker' not in str(error.value)
    failed(toy)


def test_supplier_index_cannot_invent_a_member_from_a_manifest_hash(toy):
    other = toy.prefix/'Lib/site-packages/owned/forged.dll'; other.write_bytes(b'authored forged input')
    toy.value['components'][1]['installed_files'].append({'path': 'Lib/site-packages/owned/forged.dll', 'sha256': checksum(other.read_bytes())})
    toy.manifest.write_text(json.dumps(toy.value))
    observer = start(toy)
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        observer.observe_analysis('main', [('forged.dll', str(other), 'BINARY')])
    failed(toy)


@pytest.mark.parametrize('change', ['source', 'manifest'])
def test_source_or_manifest_change_during_collection_cannot_write_an_input_snapshot(toy, change):
    observer = observe_and_copy(toy, finish=False)
    if change == 'source': toy.one.write_bytes(b'changed during collector execution')
    else: toy.manifest.write_text(json.dumps({**toy.value, 'private-extra-field': 'secret-marker'}))
    with pytest.raises(toy.module.NativeCollectionError, match='source-changed'):
        observer.finish()
    assert not (toy.output/toy.module.NATIVE_SOURCE_INPUTS).exists()
    assert failed(toy)['phase'] == 'input-snapshot'


def test_fixed_failure_projection_strips_arbitrary_exception_and_error_attributes(toy):
    error = toy.module.NativeCollectionError('invalid-toc')
    error.code = 'private-marker:' + str(toy.base)
    error.raw_toc = {'path': str(toy.one)}
    toy.module.native_failure(toy.value, toy.output, 'private-phase-marker', error, 10**30)
    report = failed(toy)
    assert report['failure_code'] == 'observation-failed' and report['phase'] == 'finalize'
    assert report['observed_records'] == 20000
    assert 'raw_toc' not in report and 'private-marker' not in json.dumps(report)


def test_unsafe_failure_destination_cannot_write_through_a_link_to_an_unrelated_tree(toy):
    outside = toy.base/'unrelated'; outside.mkdir()
    preserved = outside/'preserved.txt'; preserved.write_bytes(b'preserve unrelated bytes')
    try: toy.output.symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip('Directory symlinks are unavailable on this host.')
    with pytest.raises(toy.module.NativeCollectionError, match='unsafe-source'):
        start(toy)
    assert list(outside.iterdir()) == [preserved] and preserved.read_bytes() == b'preserve unrelated bytes'


@pytest.mark.parametrize('component', ['cpython', 'wheel'])
def test_linked_native_ancestor_is_rejected_before_leaf_stat_open_or_hash(toy, monkeypatch, component):
    outside = toy.base/'outside-prefix'; outside.mkdir()
    if component == 'cpython':
        payload = b'authored linked native; not executable'
        (outside/'linked.pyd').write_bytes(payload)
        link = toy.prefix/'DLLs'
        targets = [link/'linked.pyd', outside/'linked.pyd']
        archive = toy.evidence/toy.value['components'][0]['artifact']['path']
        with tarfile.open(archive, 'w:gz') as package:
            for name, raw in [('python/python312.dll', toy.python_dll.read_bytes()), ('python/DLLs/linked.pyd', payload)]:
                entry = tarfile.TarInfo(name); entry.size = len(raw); package.addfile(entry, io.BytesIO(raw))
        toy.value['components'][0]['artifact']['sha256'] = checksum(archive.read_bytes())
        toy.value['components'][0]['installed_files'].append({'path': 'DLLs/linked.pyd', 'sha256': checksum(payload)})
    else:
        link = toy.installed/'owned'
        for path in tuple(link.iterdir()): path.rename(outside/path.name)
        link.rmdir()
        targets = [link/'one.dll', link/'two.dll', outside/'one.dll', outside/'two.dll']
        payload = (outside/'one.dll').read_bytes()
    toy.manifest.write_text(json.dumps(toy.value))
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        # Windows directory junctions do not need symbolic-link privilege.
        cmd = shutil.which('cmd.exe') if os.name == 'nt' else None
        if not cmd: pytest.skip('This host cannot create directory links.')
        result = subprocess.run([cmd, '/d', '/c', 'mklink', '/J', str(link), str(outside)],
            capture_output=True, timeout=10)
        if result.returncode: pytest.skip('This host cannot create directory links or junctions.')
    target_names = {os.path.normcase(str(path)) for path in targets}
    accesses = []
    def selected(path):
        try: return os.path.normcase(os.fspath(path)) in target_names
        except TypeError: return False
    def guard(name, original):
        def call(path, *args, **kwargs):
            if selected(path):
                accesses.append(name)
                raise AssertionError('A native leaf beneath a link was accessed before ancestor refusal')
            return original(path, *args, **kwargs)
        return call
    with monkeypatch.context() as patch:
        # Catch resolve/stat traversal as well as both archive-verifier read paths.
        patch.setattr(os, 'stat', guard('stat', os.stat))
        patch.setattr(os, 'lstat', guard('lstat', os.lstat))
        patch.setattr(builtins, 'open', guard('open', builtins.open))
        patch.setattr(io, 'open', guard('io.open', io.open))
        patch.setattr(toy.module, 'digest', guard('digest', toy.module.digest))
        with pytest.raises(toy.module.NativeCollectionError, match='unsafe-source'):
            start(toy)
    assert accesses == [], 'Rejection must come from the ancestor guard, not a forbidden leaf access'
    assert (outside/('linked.pyd' if component == 'cpython' else 'one.dll')).read_bytes() == payload
    assert failed(toy)['failure_code'] == 'unsafe-source'
    assert not (toy.output/toy.module.NATIVE_SOURCE_INPUTS).exists()


def test_system_directory_comes_from_bounded_win32_api_not_environment(toy, monkeypatch):
    class Function:
        def __call__(self, buffer, capacity):
            assert capacity == 32768
            buffer.value = str(toy.system)
            return len(buffer.value)
    calls = []
    function = Function()
    def kernel(name, **kwargs):
        calls.append((name, kwargs)); return SimpleNamespace(GetSystemDirectoryW=function)
    import ctypes
    with monkeypatch.context() as context:
        context.setattr(sys, 'platform', 'win32')
        context.setattr(ctypes, 'WinDLL', kernel, raising=False)
        # Use the function originally replaced by the fixture, with the actual API implementation.
        original = recorder(context).native_system_directory
        assert original() == toy.system
    assert calls == [('kernel32.dll', {'use_last_error': True})]


def test_real_spec_rejects_unknown_analysis_source_before_exe_or_collect(toy, monkeypatch):
    repository = Path(__file__).resolve().parents[2]
    foreign = toy.base/'private-foreign.dll'; foreign.write_bytes(toy.one.read_bytes())
    monkeypatch.setenv('PROXY_RUNTIME_BUILD_INPUTS', str(toy.manifest))
    monkeypatch.setenv('PROXY_RUNTIME_EVIDENCE_ROOT', str(toy.evidence))
    hooks = SimpleNamespace(collect_data_files=lambda *_a, **_k: [], collect_dynamic_libs=lambda *_a, **_k: [],
        collect_submodules=lambda *_a, **_k: [], copy_metadata=lambda *_a, **_k: [])
    monkeypatch.setitem(sys.modules, 'PyInstaller.utils.hooks', hooks)
    monkeypatch.setitem(sys.modules, 'PyInstaller.config', SimpleNamespace(CONF={'workpath': str(toy.build)}))
    def analysis(*_args, **_kwargs):
        return SimpleNamespace(pure=[], scripts=[], binaries=[('owned.dll', str(foreign), 'BINARY')], datas=[])
    def forbidden(*_args, **_kwargs): pytest.fail('EXE/COLLECT ran before refusing unknown Analysis input')
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        runpy.run_path(str(repository/'packaging/runtime-bundle/runtime.spec'), init_globals={
            'SPECPATH': str(repository/'packaging/runtime-bundle'), 'DISTPATH': str(toy.output),
            'Analysis': analysis, 'PYZ': forbidden, 'EXE': forbidden, 'COLLECT': forbidden})
    assert failed(toy)['phase'] == 'analysis'
    assert not (toy.output/toy.module.NATIVE_SOURCE_INPUTS).exists()


@pytest.mark.parametrize('collector_failure', [False, True])
def test_real_spec_uses_both_actual_analysis_objects_and_keeps_collector_errors_private(toy, monkeypatch, collector_failure):
    repository = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('PROXY_RUNTIME_BUILD_INPUTS', str(toy.manifest))
    monkeypatch.setenv('PROXY_RUNTIME_EVIDENCE_ROOT', str(toy.evidence))
    hooks = SimpleNamespace(collect_data_files=lambda *_a, **_k: [], collect_dynamic_libs=lambda *_a, **_k: [],
        collect_submodules=lambda *_a, **_k: [], copy_metadata=lambda *_a, **_k: [])
    monkeypatch.setitem(sys.modules, 'PyInstaller.utils.hooks', hooks)
    monkeypatch.setitem(sys.modules, 'PyInstaller.config', SimpleNamespace(CONF={'workpath': str(toy.build)}))
    analyses = []
    def analysis(*_args, datas, **_kwargs):
        rows = ([('python312.dll', str(toy.python_dll), 'BINARY'), ('owned.dll', str(toy.one), 'BINARY')]
            if not analyses else [('owned/two.dll', str(toy.two), 'EXTENSION')])
        value = SimpleNamespace(pure=[], scripts=[], binaries=rows,
            datas=[((Path(destination)/Path(origin).name).as_posix(), origin, 'DATA') for origin, destination in datas])
        analyses.append(value)
        return value
    def executable(*_args, name, **_kwargs):
        path = toy.build/(name+'.exe'); path.write_bytes(('authored generated '+name).encode())
        return SimpleNamespace(name=str(path))
    def collect(exe, binaries, datas, *, name):
        assert binaries is analyses[-1].binaries, 'The observer must consume the existing actual TOC.'
        if collector_failure: raise OSError('private-collector-marker '+str(toy.base))
        folder = toy.output/name; folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(exe.name, folder/Path(exe.name).name)
        for destination, origin, _kind in [*binaries, *datas]:
            path = folder/'_internal'/destination; path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, path)
        return SimpleNamespace(name=str(folder))
    def run():
        return runpy.run_path(str(repository/'packaging/runtime-bundle/runtime.spec'), init_globals={
            'SPECPATH': str(repository/'packaging/runtime-bundle'), 'DISTPATH': str(toy.output),
            'Analysis': analysis, 'PYZ': lambda *_a: None, 'EXE': executable, 'COLLECT': collect})
    if collector_failure:
        with pytest.raises(toy.module.NativeCollectionError) as error: run()
        assert 'private-collector-marker' not in str(error.value)
        assert error.value.__cause__ is None and error.value.__suppress_context__ is True
        assert failed(toy)['phase'] == 'collection'
        assert not (toy.output/toy.module.NATIVE_SOURCE_INPUTS).exists()
    else:
        run()
        assert len(analyses) == 2
        snapshot = json.loads((toy.output/toy.module.NATIVE_SOURCE_INPUTS).read_bytes())
        by_path = {r['path']: r for r in snapshot['records']}
        assert by_path['_internal/owned.dll']['process'] == 'main'
        assert by_path['asr/_internal/owned/two.dll']['process'] == 'asr'
        assert by_path['_internal/helpers/nte/owned-helper.dll']['processing'] == 'explicit-native-resource'
        from closure import write_candidate
        monkeypatch.setattr('closure.validate_codec_output', lambda *_: None)
        write_candidate(toy.value, toy.source, toy.evidence, toy.output, input_manifest=toy.manifest)
        assert json.loads((toy.output/toy.module.NATIVE_SOURCE_FINAL).read_bytes())['status'] == 'observed-not-approved'
