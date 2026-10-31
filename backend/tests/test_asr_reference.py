"""Source/notice/graph boundaries of the distinct ASR experiment, no native pass."""
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module():
    return load('asr_reference_test', 'scripts/reference-asr.py')


def archive(path, files, *, link=None, root='upstream'):
    with tarfile.open(path, 'w:gz') as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(root + '/' + name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if link:
            info = tarfile.TarInfo('upstream/' + link)
            info.type = tarfile.SYMTYPE
            info.linkname = 'owned.c'
            tar.addfile(info)


def item(module, path, *, prefixes=None):
    return {'name': 'sherpa-onnx', 'kind': 'source', 'filename': path.name,
        'url': 'https://github.com/owned/fixture/archive/fixed.tar.gz',
        **module.attributes(path.read_bytes()), 'archive_root': 'upstream',
        'selected_prefixes': prefixes or [], 'fetchcontent_name': None,
        'notices': {'LICENSE': module.attributes(b'Owned source fixture notice\n')}}


def prepared(module, tmp_path, monkeypatch, *, with_cmake=False):
    source, inputs, output = tmp_path / 'repo', tmp_path / 'inputs', tmp_path / 'private-run'
    source.mkdir(); inputs.mkdir()
    upstream = (b'  /* Define "empty" TTS symbols */\n'
        b'  m.attr("OfflineTtsMatchaModelConfig") = py::none();\n')
    path = inputs / 'fixture.tar.gz'
    archive(path, {'LICENSE': b'Owned source fixture notice\n', 'owned.c': b'// owned\n',
        'sherpa-onnx/python/csrc/sherpa-onnx.cc': upstream})
    production = module.pin()
    patch = {'file': 'patch.diff', 'sha256': module.sha(b'owned patch identity'),
        'target': 'sherpa-onnx/python/csrc/sherpa-onnx.cc', 'before_sha256': module.sha(upstream),
        'after_sha256': module.sha(upstream.replace(b'  /* Define "empty" TTS symbols */\n',
            b'  /* Define "empty" TTS symbols */\n  m.attr("GenerationConfig") = py::none();\n')
            .replace(b'  m.attr("OfflineTtsMatchaModelConfig") = py::none();\n',
            b'  m.attr("OfflineTtsMatchaModelConfig") = py::none();\n  m.attr("OfflineTtsSupertonicModelConfig") = py::none();\n'))}
    (source / 'patch.diff').write_bytes(b'owned patch identity')
    (source / 'recipe.py').write_bytes(b'# owned recipe\n')
    (source / 'patch-license.txt').write_bytes(b'Owned source fixture notice\n')
    (source / 'patch-notice.txt').write_bytes(b'Owned attribution and modification notice\n')
    patch.update(license_file='patch-license.txt', attribution_file='patch-notice.txt')
    production['patch_notices'] = {name: module.attributes((source / name).read_bytes())
        for name in ('patch-license.txt', 'patch-notice.txt')}
    supplier = source / production['python_supplier_manifest']
    supplier.parent.mkdir(parents=True)
    supplier.write_text(json.dumps({'sha256': '1' * 64, 'supplier_acceptance': 'owned-fixture-pending'}))
    production.update(inputs=[item(module, path)], patch=patch)
    source_files = ('pin.json', 'patch.diff', 'recipe.py', 'patch-license.txt', 'patch-notice.txt')
    if with_cmake:
        tool_script = source / 'scripts/pinned-build-cmake.py'
        tool_script.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / 'scripts/pinned-build-cmake.py', tool_script)
        tool_policy = source / module.CMAKE_TOOL_POLICY
        tool_policy.parent.mkdir(parents=True, exist_ok=True)
        tool_pin = json.loads((ROOT / module.CMAKE_TOOL_POLICY).read_bytes())
        root = tool_pin['archive']['root']
        payload = {root + '/bin/cmake.exe': b'Owned non-executable CMake fixture',
            root + '/doc/cmake/LICENSE.rst': b'Owned tool notice fixture\n'}
        tool_archive = inputs / tool_pin['archive']['filename']
        with zipfile.ZipFile(tool_archive, 'w') as archive_zip:
            for name, data in payload.items(): archive_zip.writestr(name, data)
        tool_pin['archive'].update(**module.attributes(tool_archive.read_bytes()),
            entries=len(payload), regular_files=len(payload), expanded_bytes=sum(map(len, payload.values())))
        tool_pin['executable'] = {'path': root + '/bin/cmake.exe', **module.attributes(payload[root + '/bin/cmake.exe'])}
        tool_pin['notices'] = [{'path': root + '/doc/cmake/LICENSE.rst',
            **module.attributes(payload[root + '/doc/cmake/LICENSE.rst'])}]
        tool_policy.write_text(json.dumps(tool_pin))
        tool_spec = importlib.util.spec_from_file_location('owned_cmake_fixture', tool_script)
        tool_module = importlib.util.module_from_spec(tool_spec); tool_spec.loader.exec_module(tool_module)
        tool_module.prepare(tool_archive, tmp_path / 'pinned-cmake')
        source_files += (module.CMAKE_TOOL_POLICY, 'scripts/pinned-build-cmake.py')
    manifest = source / 'pin.json'; manifest.write_text(json.dumps(production))
    monkeypatch.setattr(module, 'ROOT', source)
    monkeypatch.setattr(module, 'MANIFEST', 'pin.json')
    monkeypatch.setattr(module, 'SOURCE_FILES', source_files)
    module.prepare(inputs, output)
    return source, inputs, output


def test_asr_recipe_binds_shared_cmake_policy_helper_and_verified_fixture_tree(module, tmp_path, monkeypatch):
    source, _inputs, output = prepared(module, tmp_path, monkeypatch, with_cmake=True)
    tool_policy = json.loads((source / module.CMAKE_TOOL_POLICY).read_bytes())
    container = tmp_path / 'pinned-cmake'; payload = container / tool_policy['archive']['root']
    verified = module.verify_pinned_cmake(container, payload)
    assert verified['operation'] == 'verified' and verified['version'] == '4.4.5'
    assert verified['runtime_collection_allowed'] is False
    assert verified['production_execution_allowed'] is False
    receipt = module.verify_sources(output)
    for name in (module.CMAKE_TOOL_POLICY, 'scripts/pinned-build-cmake.py'):
        assert receipt['source_inputs'][name] == module.attributes((source / name).read_bytes())
        assert (output / 'recipes' / name).read_bytes() == (source / name).read_bytes()
    assert not list((output / 'recipes').rglob('*.zip'))
    assert not list((output / 'recipes').rglob('*.exe'))
    assert str(tmp_path) not in json.dumps(verified)


@pytest.mark.parametrize('changed', ['selected-payload', 'native-bytes', 'retained-zip', 'recipe-policy', 'recipe-helper'])
def test_asr_rejects_unbound_or_changed_shared_cmake_inputs(module, tmp_path, monkeypatch, changed):
    source, _inputs, output = prepared(module, tmp_path, monkeypatch, with_cmake=True)
    tool_policy = json.loads((source / module.CMAKE_TOOL_POLICY).read_bytes())
    container = tmp_path / 'pinned-cmake'; payload = container / tool_policy['archive']['root']
    if changed == 'selected-payload': payload = tmp_path / 'ambient-cmake'
    if changed == 'native-bytes': (container / tool_policy['executable']['path']).write_bytes(b'changed')
    if changed == 'retained-zip': (container / 'inputs' / tool_policy['archive']['filename']).write_bytes(b'changed')
    if changed.startswith('recipe-'):
        name = module.CMAKE_TOOL_POLICY if changed == 'recipe-policy' else 'scripts/pinned-build-cmake.py'
        (source / name).write_bytes(b'changed')
        with pytest.raises(ValueError): module.verify_sources(output)
    else:
        with pytest.raises(ValueError): module.verify_pinned_cmake(container, payload)


def test_exact_preparation_patch_notice_and_pending_gates(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    report = module.verify_sources(output)
    assert report['status'] == 'prepared-not-built'
    assert report['rights_approval'] is False
    assert report['gates']['production_execution_allowed'] is False
    assert report['gates']['runtime_collection_allowed'] is False
    assert report['gates']['native_windows_11_acceptance'] == 'unavailable'
    assert report['gates']['r19_complete'] is False
    assert (output / 'notices/sherpa-onnx/LICENSE').read_bytes() == b'Owned source fixture notice\n'
    assert (output / 'recipes/patch-license.txt').read_bytes() == b'Owned source fixture notice\n'
    assert (output / 'recipes/patch-notice.txt').read_bytes() == b'Owned attribution and modification notice\n'
    patched = (output / 'sources/sherpa-onnx/sherpa-onnx/python/csrc/sherpa-onnx.cc').read_bytes()
    assert b'm.attr("GenerationConfig") = py::none();' in patched
    assert b'm.attr("OfflineTtsSupertonicModelConfig") = py::none();' in patched
    assert str(tmp_path) not in json.dumps(report)


@pytest.mark.parametrize('changed', ['source', 'notice', 'archive', 'recipe', 'copied-recipe', 'gates', 'patch-license', 'patch-attribution'])
def test_changed_input_or_delivered_notice_rejected(module, tmp_path, monkeypatch, changed):
    source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    target = {'source': output / 'sources/sherpa-onnx/owned.c',
        'notice': output / 'notices/sherpa-onnx/LICENSE', 'archive': output / 'fixture.tar.gz',
        'recipe': source / 'recipe.py', 'copied-recipe': output / 'recipes/recipe.py',
        'patch-license': source / 'patch-license.txt', 'patch-attribution': source / 'patch-notice.txt'}.get(changed)
    if target:
        target.write_bytes(b'changed')
    else:
        report = module.read_json(output / 'PREPARED.json')
        report['gates']['r19_complete'] = True
        module.write_json(output / 'PREPARED.json', report)
    with pytest.raises(ValueError):
        module.verify_sources(output)


def test_public_patch_license_must_remain_the_complete_upstream_text_before_any_write(module, tmp_path, monkeypatch):
    source, inputs, _output = prepared(module, tmp_path, monkeypatch)
    (source / 'patch-license.txt').write_bytes(b'truncated license')
    new_output = tmp_path / 'must-not-be-created'
    with pytest.raises(ValueError): module.prepare(inputs, new_output)
    assert not new_output.exists()


@pytest.mark.parametrize('invalid', ['traversal', 'link', 'case', 'notice', 'hash', 'file-parent'])
def test_exact_archive_scope_rejects_unsafe_or_unbound_input(module, tmp_path, invalid):
    path = tmp_path / 'input.tar.gz'
    files = {'LICENSE': b'Owned source fixture notice\n', 'owned.c': b'// owned\n'}
    if invalid == 'traversal': files['../outside'] = b'outside'
    if invalid == 'case': files.update({'Dir/a': b'a', 'dir/b': b'b'})
    if invalid == 'file-parent': files.update({'dir': b'a', 'dir/b': b'b'})
    archive(path, files, link='selected-link' if invalid == 'link' else None)
    record = item(module, path)
    if invalid == 'notice': record['notices']['LICENSE']['sha256'] = '0' * 64
    if invalid == 'hash': record['sha256'] = '0' * 64
    with pytest.raises(ValueError): module.archive_files(path, record)
    assert not (tmp_path / 'outside').exists()


def test_unselected_main_platform_link_cannot_enter_selected_source(module, tmp_path):
    path = tmp_path / 'input.tar.gz'
    archive(path, {'LICENSE': b'Owned source fixture notice\n', 'source/owned.c': b'// owned\n'}, link='android/link')
    files = module.archive_files(path, item(module, path, prefixes=['LICENSE', 'source']))
    assert set(files) == {'LICENSE', 'source/owned.c'}


def trace(module, path, extra=None, *, omit=None):
    events = []
    for record in module.pin()['inputs']:
        name = record['fetchcontent_name']
        if name and name != omit:
            events += [{'cmd': 'FetchContent_Declare', 'args': [name]},
                {'cmd': 'FetchContent_Populate', 'args': [name]}]
    if extra: events.append(extra)
    path.write_text('\n'.join(json.dumps(e) for e in events))


@pytest.mark.parametrize('change', ['unknown-fetch', 'network', 'downloader', 'missing'])
def test_source_graph_does_not_accept_unreviewed_or_incomplete_fetch(module, tmp_path, change):
    path = tmp_path / 'trace.jsonl'
    extra = {'unknown-fetch': {'cmd': 'FetchContent_Declare', 'args': ['espeak-ng']},
        'network': {'cmd': 'file', 'args': ['DOWNLOAD', 'https://example.test/file']},
        'downloader': {'cmd': 'execute_process', 'args': ['COMMAND', 'curl', 'https://example.test/file']}}.get(change)
    trace(module, path, extra, omit='kissfft' if change == 'missing' else None)
    with pytest.raises(ValueError): module.verify_trace(path, tmp_path)


def test_exact_source_graph_keeps_no_network_sandbox_or_rights_claim(module, tmp_path):
    path = tmp_path / 'trace.jsonl'; trace(module, path)
    report = module.verify_trace(path, tmp_path)
    assert 'simple-sentencepiece' in report['populated']
    assert report['network_sandbox'] is False
    assert 'espeak-ng' not in report['declared']


def test_actual_cache_cannot_enable_tts_or_select_an_ambient_source(module, tmp_path):
    lines = [f'{k}:STRING={v}' for k, v in module.pin()['cmake'].items()]
    lines += ['FETCHCONTENT_SOURCE_DIR_' + i['fetchcontent_name'].upper() + ':PATH=' +
        str(tmp_path / 'sources' / i['name']) for i in module.pin()['inputs'] if i['fetchcontent_name']]
    cache = tmp_path / 'CMakeCache.txt'; cache.write_text('\n'.join(lines))
    module.verify_cache(cache, tmp_path)
    cache.write_text('\n'.join(lines).replace('SHERPA_ONNX_ENABLE_TTS:STRING=OFF', 'SHERPA_ONNX_ENABLE_TTS:STRING=ON'))
    with pytest.raises(ValueError): module.verify_cache(cache, tmp_path)
    cache.write_text('\n'.join(lines).replace(str(tmp_path / 'sources/kissfft'), str(tmp_path / 'ambient/kissfft')))
    with pytest.raises(ValueError): module.verify_cache(cache, tmp_path)


@pytest.mark.parametrize('bad', ['espeak-export', 'piper-import', 'ambient-crt', 'private-path'])
def test_native_scope_requires_actual_python_binding_and_bounded_imports(module, bad):
    evidence = {'imports': ['KERNEL32.dll', 'onnxruntime.dll', 'python312.dll'],
        'delay_imports': [], 'exports': ['PyInit__sherpa_onnx']}
    module.validate_native(evidence)
    if bad == 'espeak-export': evidence['exports'].append('espeak_Initialize')
    if bad == 'piper-import': evidence['imports'].append('piper.dll')
    if bad == 'ambient-crt': evidence['imports'].append('VCRUNTIME140.dll')
    if bad == 'private-path': evidence['exports'].append('C:/r19-authored-private/export')
    with pytest.raises(ValueError): module.validate_native(evidence)


def test_toolchain_summary_hides_private_roots_and_detects_changed_bytes(module, tmp_path):
    roots = {}
    for name in ['vc', 'vc-auxiliary', 'msbuild', 'sdk-include', 'sdk-lib', 'sdk-bin', 'cmake', 'python']:
        path = tmp_path / 'private-owner' / name; path.mkdir(parents=True)
        (path / 'owned-fixture.txt').write_bytes(b'owned-tool-fixture')
        roots[name] = str(path)
    first = module.seal_toolchain(roots)
    public = module.toolchain_summary(first)
    assert 'private-owner' not in repr(public)
    assert str(tmp_path) not in repr(public)
    (Path(roots['vc']) / 'owned-fixture.txt').write_bytes(b'changed-tool-fixture')
    assert first != module.seal_toolchain(roots)


@pytest.mark.parametrize('invalid', ['array', 'empty-array', 'missing', 'file', 'extra-root'])
def test_tool_roots_reject_ambiguous_or_unavailable_selection_before_inventory(module, tmp_path, monkeypatch, invalid):
    roots = {}
    for name in ['vc', 'vc-auxiliary', 'msbuild', 'sdk-include', 'sdk-lib', 'sdk-bin', 'cmake', 'python']:
        path = tmp_path / name; path.mkdir()
        roots[name] = str(path)
    if invalid == 'array': roots['cmake'] = [roots['cmake'], roots['vc']]
    if invalid == 'empty-array': roots['cmake'] = []
    if invalid == 'missing': roots['cmake'] = str(tmp_path / 'missing')
    if invalid == 'file':
        file = tmp_path / 'owned-tool.exe'; file.write_bytes(b'owned non-executable fixture')
        roots['cmake'] = str(file)
    if invalid == 'extra-root': roots['ambient'] = roots['vc']
    def no_inventory(_path):
        pytest.fail('No source/tool bytes may be inventoried before root selection is unambiguous.')
    monkeypatch.setattr(module, 'inventory', no_inventory)
    with pytest.raises(ValueError): module.seal_toolchain(roots)


@pytest.mark.parametrize('observed,valid', [('4.4.5', True), ('4.4.4', False)])
def test_cmake_numeric_observation_preserves_exact_constraint_without_private_text(module, tmp_path, monkeypatch, observed, valid):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    executable = tmp_path / 'private-directory/cmake.exe'; executable.parent.mkdir()
    executable.write_bytes(b'owned non-executable CMake fixture with private model text')
    def version_query(command, **kwargs):
        assert command == [str(executable), '--version']
        assert kwargs['stderr'] == module.subprocess.STDOUT and kwargs['timeout'] == 30
        return 'cmake version ' + observed + '\nprivate directory/model/exception text\n'
    monkeypatch.setattr(module.subprocess, 'check_output', version_query)
    if valid:
        observation = module.observe_cmake_version(executable, '4.4.5')
    else:
        with pytest.raises(ValueError): module.observe_cmake_version(executable, '4.4.5')
        report = module.failed_build_receipt(output, 'cmake-version-review', ValueError('private exception'))
        assert report['status'] == 'failed' and report['native_reference_probes_passed'] is False
        observation = report['cmake_observation']
        assert not (output / 'ASR-RECEIPT.json').exists()
    assert observation == {'expected_version': '4.4.5', 'observed_version': observed,
        'executable': module.attributes(executable.read_bytes())}
    assert str(tmp_path) not in json.dumps(observation) and 'private' not in json.dumps(observation)
    assert module.pin()['toolchain']['cmake_version'] == '4.4.5'


def test_cmake_observation_never_serializes_raw_version_output_or_unbounded_private_state(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    executable = tmp_path / 'cmake.exe'; executable.write_bytes(b'owned executable fixture')
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *_args, **_kwargs:
        'cmake version 4.4.5/private-model-and-path\n')
    with pytest.raises(ValueError): module.observe_cmake_version(executable, '4.4.5')
    assert module.safe_cmake_observation()['observed_version'] is None
    monkeypatch.setattr(module, '_BUILD_CMAKE_OBSERVATION', {'expected_version': '4.4.5',
        'observed_version': str(tmp_path / 'private-model'),
        'executable': {**module.attributes(executable.read_bytes()), 'path': str(executable)},
        'raw_output': 'private model and log text'})
    report = module.failed_build_receipt(output, 'cmake-version-review', ValueError('private message'))
    assert report['cmake_observation']['observed_version'] is None
    delivered = (output / 'ASR-FAILURE.json').read_text()
    assert str(tmp_path) not in delivered and 'private' not in delivered and 'raw_output' not in delivered


def test_actual_python_tree_must_match_supplier_archive_not_only_version(module, tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    archive_path = tmp_path / 'python.tar.gz'
    archive(archive_path, {'python.exe': b'owned non-executable interpreter fixture',
        'include/Python.h': b'owned header'}, root='python')
    (source / 'supplier.json').write_text(json.dumps({'archive': archive_path.name,
        'sha256': module.sha(archive_path.read_bytes())}))
    monkeypatch.setattr(module, 'ROOT', source)
    monkeypatch.setattr(module, 'pin', lambda: {'python_supplier_manifest': 'supplier.json'})
    output = tmp_path / 'supplier-extracted'
    module.prepare_python(archive_path, output)
    module.verify_python(tmp_path, output / 'python')
    (output / 'python/sitecustomize.py').write_bytes(b'# ambient extra file')
    with pytest.raises(ValueError): module.verify_python(tmp_path, output / 'python')


@pytest.mark.parametrize('timeout', [False, True])
def test_private_command_is_owned_before_spawn_and_drained_even_on_timeout(module, tmp_path, monkeypatch, timeout):
    events = []
    class Owner:
        def command(self, value):
            events.append('wrap-before-spawn')
            return ['owned-bootstrap', *value]
        def terminate(self, **_kwargs): events.append('drain-owned-job')
        def close(self): events.append('close-owned-job')
    class Process:
        def __init__(self): self.code = None
        def wait(self, **_kwargs):
            if timeout and self.code is None:
                raise module.subprocess.TimeoutExpired('owned-command', 1)
            self.code = 0 if not timeout else 1
            events.append('reap-bootstrap')
            return self.code
        def poll(self): return self.code
        def kill(self):
            events.append('kill-owned-bootstrap')
            self.code = 1
    def popen(command, **kwargs):
        assert command == ['owned-bootstrap', 'owned-command']
        assert kwargs['stdout'] is not None
        events.append('spawn-bootstrap')
        return Process()
    monkeypatch.setattr(module, 'process_owner', Owner)
    monkeypatch.setattr(module.subprocess, 'Popen', popen)
    monkeypatch.setattr(module.subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    if timeout:
        with pytest.raises(module.subprocess.TimeoutExpired):
            module.run_private(['owned-command'], tmp_path / 'private.log', {}, tmp_path, 1)
        assert events.index('kill-owned-bootstrap') < events.index('reap-bootstrap')
    else:
        module.run_private(['owned-command'], tmp_path / 'private.log', {}, tmp_path, 1)
    assert events.index('wrap-before-spawn') < events.index('spawn-bootstrap')
    assert events.index('reap-bootstrap') < events.index('drain-owned-job') < events.index('close-owned-job')


def test_parent_msbuild_import_is_rejected_and_preserved(module, tmp_path):
    parent = tmp_path / 'parent'; parent.mkdir()
    output = parent / 'owned'; output.mkdir()
    ambient = parent / 'Directory.Build.targets'; ambient.write_bytes(b'owned ambient-import fixture')
    with pytest.raises(ValueError): module.reject_parent_imports(output)
    assert ambient.read_bytes() == b'owned ambient-import fixture'


def test_private_command_cleanup_failure_cannot_be_reported_as_success(module, tmp_path, monkeypatch):
    events = []
    class Owner:
        def command(self, value): return value
        def terminate(self, **_kwargs):
            events.append('unconfirmed-drain')
            raise OSError('owned cleanup failure fixture')
        def close(self): events.append('close-handle-only')
    class Process:
        def wait(self, **_kwargs): return 0
        def poll(self): return 0
    monkeypatch.setattr(module, 'process_owner', Owner)
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(module.subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    with pytest.raises(OSError, match='owned cleanup failure fixture'):
        module.run_private(['owned-command'], tmp_path / 'private.log', {}, tmp_path, 1)
    assert events == ['unconfirmed-drain', 'close-handle-only']


def test_failed_receipt_contains_only_fixed_phase_known_codes_and_categories(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    logs = output / 'private-logs'; logs.mkdir()
    raw = (str(tmp_path / 'private-profile/model-secret.onnx') + '\n'
        'fatal error C1083: raw private missing-header text\n'
        'error LNK1104: raw private library text\n'
        'error MSB8020: raw private toolchain text\n'
        'error C9999: unrecognized code must not leave the host\n'
        'CMake Error at private-profile/private-build.cmake:42\n'
        'Configuring incomplete, errors occurred!\n'
        '[ONNXRuntimeError]: private model text\n')
    (logs / 'configure.log').write_text(raw)
    monkeypatch.setattr(module, '_BUILD_SOURCE_COMMIT', 'private-profile/not-a-commit')
    report = module.failed_build_receipt(output, 'cmake-configure', OSError(raw))
    delivered = (output / 'ASR-FAILURE.json').read_text()
    assert report['schema'] == 'proxy-r19-asr-source-failure-v1' and report['status'] == 'failed'
    assert report['phase'] == 'cmake-configure'
    assert report['failure_category'] == 'io-or-cleanup-unconfirmed'
    assert report['diagnostics']['known_codes'] == ['C1083', 'LNK1104', 'MSB8020']
    assert 'cmake-error' in report['diagnostics']['categories']
    assert 'onnx-native-error' in report['diagnostics']['categories']
    assert 'unclassified-tool-error' in report['diagnostics']['categories']
    assert report['source_commit'] is None
    assert report['native_reference_probes_passed'] is False
    assert report['success_receipt_for_this_attempt'] is False
    assert report['gates']['production_execution_allowed'] is False
    assert report['gates']['runtime_collection_allowed'] is False
    assert report['gates']['r19_complete'] is False and report['rights_approval'] is False
    for private in [str(tmp_path), 'private-profile', 'model-secret', 'private missing-header', 'C9999']:
        assert private not in delivered
    assert not (output / 'ASR-RECEIPT.json').exists()


@pytest.mark.parametrize('kind,expected', [('command', 'private-command-failed'),
    ('timeout', 'owned-process-timeout'), ('cleanup', 'io-or-cleanup-unconfirmed')])
def test_build_failure_wrapper_never_issues_a_success_receipt(module, tmp_path, monkeypatch, capsys, kind, expected):
    _source, inputs, output = prepared(module, tmp_path, monkeypatch)
    logs = output / 'private-logs'; logs.mkdir()
    (logs / 'build.log').write_text('fatal error C2065: private-symbol-and-model-text\n')
    def failure(*_args):
        module.build_phase('native-build')
        if kind == 'timeout':
            raise module.subprocess.TimeoutExpired([str(tmp_path / 'private-tool.exe')], 1)
        if kind == 'cleanup':
            raise OSError(str(tmp_path / 'private-handle-diagnostic'))
        raise ValueError(str(tmp_path / 'private-native-failure'))
    monkeypatch.setattr(module, '_build', failure)
    with pytest.raises((ValueError, OSError, module.subprocess.TimeoutExpired)):
        module.build(output, tmp_path / 'roots.json', tmp_path / 'vs', inputs)
    report = module.read_json(output / 'ASR-FAILURE.json')
    assert report['status'] == 'failed' and report['failure_category'] == expected
    assert report['diagnostics']['known_codes'] == ['C2065']
    assert report['success_receipt_for_this_attempt'] is False
    assert not (output / 'ASR-RECEIPT.json').exists()
    public = capsys.readouterr().err + json.dumps(report)
    assert str(tmp_path) not in public and 'private-symbol-and-model-text' not in public


def test_failure_report_refuses_unprepared_or_unbounded_caller_and_preserves_previous_record(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        module.failed_build_receipt(output, str(tmp_path / 'private-phase'), ValueError('private'))
    assert not (output / 'ASR-FAILURE.json').exists()
    empty = tmp_path / 'unprepared'; empty.mkdir()
    with pytest.raises(OSError):
        module.failed_build_receipt(empty, 'native-build', ValueError('private'))
    assert list(empty.iterdir()) == []
    module.failed_build_receipt(output, 'native-build', ValueError('first private message'))
    original = (output / 'ASR-FAILURE.json').read_bytes()
    with pytest.raises(FileExistsError):
        module.failed_build_receipt(output, 'native-build', ValueError('second private message'))
    assert (output / 'ASR-FAILURE.json').read_bytes() == original


def test_failed_receipt_cannot_be_published_as_native_asr_success(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    failed = module.failed_build_receipt(output, 'native-build', ValueError('owned failure'))
    with pytest.raises(ValueError): module.publish_success_receipt(output, failed)
    assert not (output / 'ASR-RECEIPT.json').exists()
    assert not (output / 'PRIVATE-ASR-RECEIPT.pending.json').exists()


def test_fixture_is_owned_dynamic_format_graph_with_no_pretrained_payload(tmp_path):
    fixture = load('asr_owned_fixture_test', 'scripts/probe-reference-asr.py')
    report = fixture.fixtures(tmp_path / 'fixtures')
    graph = (tmp_path / 'fixtures/model.onnx').read_bytes()
    assert len(graph) < 4096
    assert b'OwnedFormatFixture' in graph and b'Range' in graph and b'OneHot' in graph
    assert b'features_length' in graph and b'language' in graph and b'text_norm' in graph
    assert b'no trained weights' in graph
    assert graph != (tmp_path / 'fixtures/wrong-shape.onnx').read_bytes()
    assert report['silence.f32']['bytes'] == 8000 * 4
    assert not any((tmp_path / 'fixtures/silence.f32').read_bytes())
    assert (tmp_path / 'fixtures/tokens.txt').read_text().endswith('AUTHORED 5\n')


def test_private_variant_wheel_preserves_notices_and_actual_record_hashes(module, tmp_path):
    import base64
    import csv
    import zipfile
    output = tmp_path / 'private-output'
    package = output / 'sources/sherpa-onnx/sherpa-onnx/python/sherpa_onnx'
    package.mkdir(parents=True)
    (package / '__init__.py').write_bytes(b'# owned Python package fixture\n')
    native = output / 'sources/onnxruntime/lib'; native.mkdir(parents=True)
    (native / 'onnxruntime.dll').write_bytes(b'owned non-executable native-file fixture')
    pyd = tmp_path / '_sherpa_onnx.cp312-win_amd64.pyd'; pyd.write_bytes(b'owned non-executable binding fixture')
    notice = output / 'notices/sherpa-onnx/LICENSE'; notice.parent.mkdir(parents=True)
    notice.write_bytes(b'owned retained notice\r\n')
    wheel = module.make_wheel(output, pyd)
    with zipfile.ZipFile(wheel) as archive:
        dist = 'proxy_r19_sherpa_asr_reference-1.13.8+proxy.r19.asr1.dist-info'
        assert archive.read(dist + '/notices/sherpa-onnx/LICENSE') == b'owned retained notice\r\n'
        assert archive.read(dist + '/notices/PROJECT-LICENSE.txt') == (ROOT / 'LICENSE').read_bytes()
        assert archive.read(dist + '/notices/TTS-OFF-MODIFICATION.patch') == (ROOT / module.pin()['patch']['file']).read_bytes()
        for name, expected_notice in module.pin()['patch_notices'].items():
            delivered = archive.read(dist + '/notices/' + Path(name).name)
            assert delivered == (ROOT / name).read_bytes()
            assert module.attributes(delivered) == expected_notice
        notice = archive.read(dist + '/notices/SHERPA-PATCH-NOTICE.txt')
        assert b'sherpa_onnx/__init__.py' in notice
        assert b'__version__ = "1.13.8+proxy.r19.asr1"' in notice
        metadata = archive.read(dist + '/METADATA')
        assert b'Name: proxy-r19-sherpa-asr-reference' in metadata
        assert b'sherpa-onnx-core' not in metadata
        for name, digest, size in csv.reader(io.StringIO(archive.read(dist + '/RECORD').decode())):
            if name.endswith('/RECORD'): continue
            data = archive.read(name)
            expected = 'sha256=' + base64.urlsafe_b64encode(bytes.fromhex(module.sha(data))).decode().rstrip('=')
            assert digest == expected and int(size) == len(data)


def test_manual_workflow_has_metadata_only_delivery_and_no_default_runtime_replacement(module):
    workflow = (ROOT / '.github/workflows/r19-asr-source-experiment.yml').read_text()
    assert 'workflow_dispatch:' in workflow and '\n  push:' not in workflow
    uploads = set(re.findall(r'\$\{\{\s*env\.R19_ASR_OUTPUT\s*\}\}/([^\s\'\"]+)', workflow))
    assert {'PREPARED.json', 'ASR-RECEIPT.json'} <= uploads
    assert uploads <= {'PREPARED.json', 'ASR-RECEIPT.json', 'ASR-FAILURE.json'}
    assert module.pin()['identity'] == 'sherpa-onnx-1.13.8-asr-reference.1'
    assert module.pin()['cmake']['SHERPA_ONNX_ENABLE_TTS'] == 'OFF'
    assert 'SHERPA_ONNX_SPLIT_PYTHON_PACKAGE' not in module.pin()['cmake']
    locked = (ROOT / 'requirements.lock.txt').read_text()
    assert 'sherpa_onnx==1.13.8' in locked and 'sherpa-onnx-core==1.13.8' in locked
