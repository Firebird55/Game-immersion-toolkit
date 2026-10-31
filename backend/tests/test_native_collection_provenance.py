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
    allowed_native_payloads = {python_dll.read_bytes(), members['owned/one.dll'], members['owned/two.dll'],
        *(('authored '+item['path']).encode() for item in resources),
        b'authored generated main', b'authored generated asr',
        b'authored generated ProxyTranscriptRuntime', b'authored generated ProxyTranscriptAsr'}
    native_image_stub_calls = []
    def authored_byte_only_native_images_not_tested(actual_value, actual_output, inventory):
        # This fixture owns non-PE strings only. The independent parser and
        # finalizer integration tests own the mandatory real PE-review gate.
        assert actual_value is value and actual_output == output
        selected = [item for item in inventory['files'] if Path(item['path']).suffix.lower() in {'.dll', '.pyd', '.exe'}]
        assert selected
        for item in selected:
            raw = (actual_output/'ProxyTranscriptRuntime'/item['path']).read_bytes()
            assert raw in allowed_native_payloads and not raw.startswith(b'MZ')
            assert item['bytes'] == len(raw) and item['sha256'] == checksum(raw)
        state = {'schema': 'authored-byte-only-native-images-not-tested', 'status': 'not-tested',
            'production_execution_allowed': False, 'r19_complete': False,
            'native_windows_11_acceptance': 'unavailable'}
        native_image_stub_calls.append(state)
        return state
    monkeypatch.setattr('closure.validate_native_images', authored_byte_only_native_images_not_tested)
    return SimpleNamespace(module=module, base=base, evidence=evidence, prefix=prefix, installed=installed,
        system=system, build=build, output=output, source=source, value=value, manifest=manifest,
        python_dll=python_dll, one=installed/'owned/one.dll', two=installed/'owned/two.dll', system_dll=system_dll,
        native_image_stub_calls=native_image_stub_calls)


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
    assert toy.native_image_stub_calls == [{'schema': 'authored-byte-only-native-images-not-tested', 'status': 'not-tested',
        'production_execution_allowed': False, 'r19_complete': False, 'native_windows_11_acceptance': 'unavailable'}]
    assert not (toy.output/'NATIVE-IMAGES.json').exists()


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
    error.analysis_diagnostic = {'private-exception-attribute': str(toy.base)}
    toy.module.native_failure(toy.value, toy.output, 'private-phase-marker', error, 10**30)
    report = failed(toy)
    assert report['failure_code'] == 'observation-failed' and report['phase'] == 'finalize'
    assert report['observed_records'] == 20000
    assert 'raw_toc' not in report and 'private-marker' not in json.dumps(report)
    assert 'analysis_diagnostic' not in report, 'Exception attributes are never a diagnostic source.'


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
    analyses = []
    def analysis(*_args, **_kwargs):
        analyses.append('main')
        return SimpleNamespace(pure=[], scripts=[], binaries=[('foreign.dll', str(foreign), 'BINARY'),
            ('owned.dll', str(toy.one), 'BINARY'), ('another.dll', str(foreign), 'BINARY')], datas=[])
    def forbidden(*_args, **_kwargs): pytest.fail('EXE/COLLECT ran before refusing unknown Analysis input')
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        runpy.run_path(str(repository/'packaging/runtime-bundle/runtime.spec'), init_globals={
            'SPECPATH': str(repository/'packaging/runtime-bundle'), 'DISTPATH': str(toy.output),
            'Analysis': analysis, 'PYZ': forbidden, 'EXE': forbidden, 'COLLECT': forbidden})
    report = failed(toy)
    assert analyses == ['main'], 'ASR Analysis must not move before the existing main EXE/COLLECT.'
    assert report['phase'] == 'analysis'
    assert report['analysis_diagnostic']['status'] == 'complete-current-call'
    assert report['analysis_diagnostic']['unresolved_rows'] == 2
    assert report['analysis_diagnostic']['analyses'] == {'main': 'current-call', 'asr': 'not-run'}
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


def unknown(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/name
    path.write_bytes(b'private-native-content-sentinel; authored and not executable')
    return path


def test_same_analysis_census_aggregates_unknowns_without_open_hash_copy_or_record_admission(toy, monkeypatch):
    base_interpreter = toy.base/'private-base-interpreter'; base_interpreter.mkdir()
    (base_interpreter/'python312.dll').write_bytes(toy.python_dll.read_bytes())
    monkeypatch.setattr(sys, 'base_prefix', str(base_interpreter))
    windows = toy.base/'authoritative-windows-root'; windows.mkdir()
    queries = []
    def provider():
        queries.append(True)
        return windows
    observer = toy.module.NativeCollectionObservation(toy.value, toy.evidence, toy.output, toy.build,
        toy.manifest, windows_directory_provider=provider)
    files = [unknown(toy.prefix/'private-unlisted', 'MSVCP140.dll'),
        unknown(toy.prefix/'private-unlisted', 'vcruntime140_1.dll'),
        unknown(base_interpreter/'private-unlisted', 'ucrtbase.dll'),
        unknown(toy.evidence/'private-unlisted', 'API-MS-WIN-CRT-STDIO-L1-1-0.DLL'),
        unknown(toy.build/'private-unlisted', 'api-ms-win-core-synch-l1-2-0.dll'),
        unknown(windows/'private-not-system', 'private-windows-sentinel.dll'),
        unknown(toy.base/'private-other', 'private-unknown-sentinel.dll')]
    explicit = unknown(toy.evidence/'private-explicit', 'private-resource-sentinel.dll')
    blocked = {os.path.normcase(str(path)) for path in [*files, explicit]}
    accesses = []
    def guard(label, original):
        def call(path, *args, **kwargs):
            try: selected = os.path.normcase(os.fspath(path)) in blocked
            except TypeError: selected = False
            if selected:
                accesses.append(label)
                pytest.fail('Unresolved native contents must remain unopened and unhashed')
            return original(path, *args, **kwargs)
        return call
    # The known row following unknown rows must still be observed in the same
    # actual TOC; unknown rows must not acquire output/source records.
    rows = [('private-output-'+str(index)+'.dll', str(path), 'BINARY') for index, path in enumerate(files)]
    rows.insert(2, ('renamed-owned.dll', str(toy.one), 'BINARY'))
    rows.append(('private-ignore.txt', 'private-non-native-origin-sentinel', 'DATA'))
    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', guard('open', builtins.open))
        patch.setattr(io, 'open', guard('io.open', io.open))
        patch.setattr(toy.module, 'native_file_identity', guard('identity/hash', toy.module.native_file_identity))
        patch.setattr(toy.module, 'digest', guard('digest', toy.module.digest))
        patch.setattr(shutil, 'copyfile', lambda *_a, **_k: pytest.fail('Census cannot copy native sources'))
        with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
            observer.observe_analysis('main', rows, [('private-explicit.dll', str(explicit), 'DATA')])
    assert accesses == [] and queries == [True]
    assert set(observer.records) == set(observer.private) == {'_internal/renamed-owned.dll'}
    report = failed(toy); census = report['analysis_diagnostic']
    assert report['observed_records'] == 1
    assert census['status'] == 'complete-current-call' and census['scope'] == 'current-observe-analysis-call'
    assert census['rows_examined'] == 10 and census['native_rows_examined'] == 9 and census['unresolved_rows'] == 8
    assert census['windows_root_query'] == 'observed'
    assert census['buckets'] == [
        {'processing': 'analysis-native', 'family': 'api-core', 'root': 'build-root', 'count': 1},
        {'processing': 'analysis-native', 'family': 'api-crt', 'root': 'declared-evidence', 'count': 1},
        {'processing': 'analysis-native', 'family': 'not-allowlisted', 'root': 'other', 'count': 1},
        {'processing': 'analysis-native', 'family': 'not-allowlisted', 'root': 'windows-outside-system', 'count': 1},
        {'processing': 'analysis-native', 'family': 'ucrt', 'root': 'base-interpreter', 'count': 1},
        {'processing': 'analysis-native', 'family': 'vc-runtime', 'root': 'current-environment', 'count': 2},
        {'processing': 'explicit-native-resource', 'family': 'not-allowlisted', 'root': 'declared-evidence', 'count': 1}]
    serialized = json.dumps(report)
    for path in [*files, explicit]:
        assert path.name not in serialized and checksum(path.read_bytes()) not in serialized
    assert 'private-' not in serialized and not (toy.output/toy.module.NATIVE_SOURCE_INPUTS).exists()


@pytest.mark.parametrize(('name', 'family'), [
    ('API-MS-WIN-CORE-WINRT-ERROR-L1-1-0.DLL', 'api-core'),
    ('api-ms-win-crt-runtime-l1-1-0.dll', 'api-crt'), ('UCRTBASE.DLL', 'ucrt'),
    ('VCRUNTIME140_1.DLL', 'vc-runtime'), ('msvcp140_atomic_wait.dll', 'vc-runtime'),
    ('private-api-ms-win-core-synch-l1-2-0.dll', 'not-allowlisted'),
    ('api-ms-win-core-synch.dll', 'not-allowlisted'), ('ucrtbase.dll.pyd', 'not-allowlisted'),
    ('vcruntime140_forged.dll', 'not-allowlisted')])
def test_diagnostic_family_is_case_insensitive_finite_spelling_and_never_source_admission(toy, name, family):
    path = unknown(toy.prefix/'private-unlisted', name)
    observer = start(toy)
    assert toy.module.native_diagnostic_family(path) == family
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        observer.observe_analysis('main', [('unknown.dll', str(path), 'BINARY')])
    assert failed(toy)['analysis_diagnostic']['buckets'] == [
        {'processing': 'analysis-native', 'family': family, 'root': 'current-environment', 'count': 1}]
    assert observer.records == {}


def test_nested_diagnostic_roots_choose_most_specific_and_system_subdirectories_stay_observed(toy):
    build = toy.prefix/'private-nested-build'; build.mkdir()
    observer = toy.module.NativeCollectionObservation(toy.value, toy.evidence, toy.output, build, toy.manifest,
        windows_directory_provider=lambda: pytest.fail('Known roots do not need a Windows-root query'))
    foreign = unknown(build, 'private-unresolved.dll')
    system = unknown(toy.system/'downlevel', 'api-ms-win-core-synch-l1-2-0.dll')
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        observer.observe_analysis('main', [('system.dll', str(system), 'BINARY'), ('unknown.dll', str(foreign), 'BINARY')])
    assert observer.records['_internal/system.dll']['source'] == {'role': 'windows-system-observed',
        'system_member': 'downlevel/api-ms-win-core-synch-l1-2-0.dll', 'provider': 'GetSystemDirectoryW'}
    census = failed(toy)['analysis_diagnostic']
    assert census['windows_root_query'] == 'not-needed'
    assert census['buckets'] == [{'processing': 'analysis-native', 'family': 'not-allowlisted', 'root': 'build-root', 'count': 1}]


@pytest.mark.parametrize('provider_result', ['zero', 'oversized', 'exception', 'valid'])
def test_shared_windows_root_uses_fixed_win32_query_and_no_environment_fallback(toy, monkeypatch, provider_result):
    import ctypes
    windows = toy.base/'authoritative-windows-root'; windows.mkdir()
    calls = []
    class Function:
        def __call__(self, buffer, capacity):
            calls.append(capacity)
            assert capacity == 32768
            if provider_result == 'exception': raise OSError('private-query-sentinel '+str(toy.base))
            buffer.value = str(windows)
            return {'zero': 0, 'oversized': 32768, 'valid': len(buffer.value)}[provider_result]
    function = Function()
    def kernel(name, **kwargs):
        assert name == 'kernel32.dll' and kwargs == {'use_last_error': True}
        return SimpleNamespace(GetSystemWindowsDirectoryW=function)
    monkeypatch.setenv('WINDIR', str(toy.base/'private-bait'))
    monkeypatch.setenv('SystemRoot', str(toy.base/'private-bait'))
    with monkeypatch.context() as patch:
        patch.setattr(sys, 'platform', 'win32')
        patch.setattr(ctypes, 'WinDLL', kernel, raising=False)
        if provider_result == 'valid':
            assert toy.module.native_windows_directory() == windows
        else:
            with pytest.raises(toy.module.NativeCollectionError, match='source-unavailable') as error:
                toy.module.native_windows_directory()
            assert 'private-' not in str(error.value)
    assert calls == [32768] and len(function.argtypes) == 2


def test_unavailable_windows_query_is_bounded_and_cannot_choose_environment_bait(toy, monkeypatch):
    bait = toy.base/'private-bait'; bait.mkdir()
    monkeypatch.setenv('WINDIR', str(bait)); monkeypatch.setenv('SystemRoot', str(bait))
    queries = []
    def unavailable():
        queries.append(True)
        raise OSError('private-provider-sentinel '+str(bait))
    observer = toy.module.NativeCollectionObservation(toy.value, toy.evidence, toy.output, toy.build,
        toy.manifest, windows_directory_provider=unavailable)
    paths = [unknown(bait, 'ucrtbase.dll'), unknown(bait, 'private-second.dll')]
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        observer.observe_analysis('main', [('unknown'+str(i)+'.dll', str(p), 'BINARY') for i, p in enumerate(paths)])
    census = failed(toy)['analysis_diagnostic']
    assert queries == [True] and census['status'] == 'complete-current-call'
    assert census['windows_root_query'] == 'unavailable'
    assert {row['root'] for row in census['buckets']} == {'unavailable'}
    assert 'private-provider-sentinel' not in json.dumps(census) and observer.records == {}


@pytest.mark.parametrize(('change', 'code'), [('malformed', 'invalid-toc'), ('missing', 'unsafe-source'),
    ('changed', 'source-changed'), ('unbound-explicit', 'unbound-supplier-member')])
def test_census_does_not_defer_other_errors_or_claim_complete_after_them(toy, change, code):
    observer = start(toy)
    path = unknown(toy.prefix/'private-unlisted', 'private-unknown.dll')
    first = ('unknown.dll', str(path), 'BINARY')
    if change == 'malformed': bad = ('private-malformed',)
    elif change == 'missing': bad = ('bad.dll', str(toy.base/'private-absent.dll'), 'BINARY')
    elif change == 'changed':
        toy.one.write_bytes(b'private-changed-sentinel'); bad = ('bad.dll', str(toy.one), 'BINARY')
    else: bad = ('bad.dll', str(toy.one), 'DATA')
    def rows():
        if change != 'unbound-explicit': yield first
        yield bad
        pytest.fail('A non-unresolved error must stop before the next TOC row')
    with pytest.raises(toy.module.NativeCollectionError, match=code):
        observer.observe_analysis('main', [first] if change == 'unbound-explicit' else rows(),
            rows() if change == 'unbound-explicit' else ())
    report = failed(toy); census = report['analysis_diagnostic']
    assert report['failure_code'] == code and census['status'] == 'incomplete-current-call'
    assert census['unresolved_rows'] == 1 and observer.records == {}
    assert census['analyses']['asr'] == 'not-run'


@pytest.mark.parametrize('bound', ['total', 'native'])
def test_census_bounds_stop_before_excess_native_source_and_label_truncation(toy, monkeypatch, bound):
    monkeypatch.setattr(toy.module, 'NATIVE_ANALYSIS_ROW_LIMIT', 3)
    monkeypatch.setattr(toy.module, 'NATIVE_ANALYSIS_NATIVE_LIMIT', 2)
    observer = start(toy)
    path = unknown(toy.prefix/'private-unlisted', 'private-unknown.dll')
    row = ('unknown.dll', str(path), 'BINARY')
    seen = []
    source = observer._source
    def observe(path):
        seen.append(True)
        return source(path)
    monkeypatch.setattr(observer, '_source', observe)
    rows = [row, ('ignored.txt', 'private-unused', 'DATA'), ('ignored2.txt', 'private-unused', 'DATA'), row] if bound == 'total' else [row]*3
    with pytest.raises(toy.module.NativeCollectionError, match='invalid-toc'):
        observer.observe_analysis('main', rows)
    census = failed(toy)['analysis_diagnostic']
    assert census['status'] == ('truncated-row-limit' if bound == 'total' else 'truncated-native-limit')
    assert census['rows_examined'] == 3 and census['native_rows_examined'] == (1 if bound == 'total' else 2)
    assert len(seen) == census['unresolved_rows'] == census['native_rows_examined']
    assert census['row_limit'] == 3 and census['native_row_limit'] == 2 and observer.records == {}


def test_asr_census_distinguishes_only_the_current_call_from_an_earlier_main_analysis(toy):
    observer = start(toy)
    observer.observe_analysis('main', [('owned.dll', str(toy.one), 'BINARY')])
    path = unknown(toy.prefix/'private-unlisted', 'private-unknown.dll')
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        observer.observe_analysis('asr', [('unknown.pyd', str(path), 'EXTENSION')])
    census = failed(toy)['analysis_diagnostic']
    assert census['process'] == 'asr' and census['analyses'] == {'main': 'previous-call', 'asr': 'current-call'}
    assert census['rows_examined'] == census['unresolved_rows'] == 1


@pytest.mark.parametrize('change', ['schema', 'scope', 'process', 'status', 'analysis-state', 'analysis-extra',
    'second-current', 'rows-bool', 'native-overflow', 'unresolved-negative', 'row-limit', 'native-limit-bool',
    'family', 'root', 'processing', 'count-bool', 'count-mismatch', 'duplicate-bucket', 'extra-bucket-field',
    'extra-field', 'too-many-buckets', 'query', 'other-without-query', 'unavailable-without-query'])
def test_failure_projector_revalidates_every_census_field_and_never_serializes_malformed_data(toy, change):
    observer = start(toy)
    path = unknown(toy.prefix/'private-unlisted', 'private-source-sentinel.dll')
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        observer.observe_analysis('main', [('unknown.dll', str(path), 'BINARY')])
    diagnostic = failed(toy)['analysis_diagnostic']
    (toy.output/toy.module.NATIVE_SOURCE_FAILED).unlink()
    marker = 'private-projection-sentinel:' + str(toy.base)
    if change in {'schema', 'scope', 'process', 'status'}: diagnostic[change] = marker
    elif change == 'analysis-state': diagnostic['analyses']['asr'] = marker
    elif change == 'analysis-extra': diagnostic['analyses'][marker] = 'not-run'
    elif change == 'second-current': diagnostic['analyses']['asr'] = 'current-call'
    elif change == 'rows-bool': diagnostic['rows_examined'] = True
    elif change == 'native-overflow': diagnostic['native_rows_examined'] = 20001
    elif change == 'unresolved-negative': diagnostic['unresolved_rows'] = -1
    elif change == 'row-limit': diagnostic['row_limit'] = 50001
    elif change == 'native-limit-bool': diagnostic['native_row_limit'] = False
    elif change in {'family', 'root', 'processing'}: diagnostic['buckets'][0][change] = marker
    elif change == 'count-bool': diagnostic['buckets'][0]['count'] = True
    elif change == 'count-mismatch': diagnostic['buckets'][0]['count'] = 2
    elif change == 'duplicate-bucket': diagnostic['buckets'].append(deepcopy(diagnostic['buckets'][0]))
    elif change == 'extra-bucket-field': diagnostic['buckets'][0]['private-field'] = marker
    elif change == 'extra-field': diagnostic['private-field'] = marker
    elif change == 'too-many-buckets': diagnostic['buckets'] *= 81
    elif change == 'query': diagnostic['windows_root_query'] = marker
    elif change == 'other-without-query': diagnostic['buckets'][0]['root'] = 'other'
    elif change == 'unavailable-without-query': diagnostic['buckets'][0]['root'] = 'unavailable'
    error = toy.module.NativeCollectionError('other-host-unresolved')
    error.private_projection = marker
    toy.module.native_failure(toy.value, toy.output, 'analysis', error, analysis_diagnostic=diagnostic)
    report = failed(toy)
    assert report['analysis_diagnostic'] == {'schema': toy.module.NATIVE_DIAGNOSTIC_SCHEMA, 'status': 'unavailable'}
    assert marker not in json.dumps(report) and path.name not in json.dumps(report)


def test_failure_projector_does_not_attribute_analysis_census_to_another_phase(toy):
    observer = start(toy)
    path = unknown(toy.prefix/'private-unlisted', 'private-unknown.dll')
    with pytest.raises(toy.module.NativeCollectionError, match='other-host-unresolved'):
        observer.observe_analysis('main', [('unknown.dll', str(path), 'BINARY')])
    diagnostic = failed(toy)['analysis_diagnostic']
    (toy.output/toy.module.NATIVE_SOURCE_FAILED).unlink()
    toy.module.native_failure(toy.value, toy.output, 'generated', toy.module.NativeCollectionError('missing-source'),
        analysis_diagnostic=diagnostic)
    report = failed(toy)
    assert report['phase'] == 'generated'
    assert report['analysis_diagnostic'] == {'schema': toy.module.NATIVE_DIAGNOSTIC_SCHEMA, 'status': 'unavailable'}
