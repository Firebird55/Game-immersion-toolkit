"""Source/notice/graph boundaries of the distinct ASR experiment, no native pass."""
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
from types import SimpleNamespace
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


def prepared(module, tmp_path, monkeypatch, *, with_cmake=False, vc_props=None):
    source, inputs, output = tmp_path / 'repo', tmp_path / 'inputs', tmp_path / 'private-run'
    source.mkdir(); inputs.mkdir()
    upstream = (b'  /* Define "empty" TTS symbols */\n'
        b'  m.attr("OfflineTtsMatchaModelConfig") = py::none();\n')
    path = inputs / 'fixture.tar.gz'
    archive(path, {'LICENSE': b'Owned source fixture notice\n', 'owned.c': b'// owned\n',
        'sherpa-onnx/python/csrc/sherpa-onnx.cc': upstream})
    production = module.pin()
    if vc_props is not None:
        production['toolchain']['vc_targets']['default_props'] = module.attributes(vc_props)
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


@pytest.mark.parametrize('name', ['espeak_Initialize', 'espeak_ng_Synthesize',
    '__imp_espeak_Initialize', '?phonemize_eSpeak@piper@@YAX', '?phonemize_codepoints@piper@@YAX',
    'espeak-ng.lib', 'libespeak-ng.dll', '_deps/espeak_ng-build/Release/espeak-ng.lib',
    'piper_phonemize.lib', 'cmake/piper-phonemize.cmake', 'PiperPhonemizeLexicon',
    '?PiperPhonemesToIdsVits@sherpa_onnx@@', 'phonemizer'])
def test_native_tts_predicate_retains_real_api_library_path_and_mangled_name_rejection(module, name):
    assert module.native_tts_name(name)


@pytest.mark.parametrize('name', ['OfflineSpeakerDiarization', 'PybindOfflineSpeakerDiarization',
    '?PybindOfflineSpeakerDiarization@sherpa_onnx@@YAX', '??_7OfflineSpeakerDiarization@sherpa_onnx@@',
    'offline-speaker-diarization.cc', 'SpeakerEmbeddingExtractor'])
def test_native_tts_predicate_preserves_authored_asr_speaker_identifiers(module, name):
    assert not module.native_tts_name(name)


def test_linkmap_shaped_tts_evidence_remains_rejected_without_offline_speaker_false_positive(module):
    retained = (' 0001:00001234 ?PybindOfflineSpeakerDiarization@sherpa_onnx@@ 0000000180001234 f _sherpa_onnx.obj\n'
        ' 0002:00000020 ??_7OfflineSpeakerDiarization@sherpa_onnx@@ 0000000180010020 core.lib\n')
    assert not module.native_tts_name(retained)
    for native in ('espeak_Initialize', '__imp_espeak_ng_Synthesize', '?phonemize_eSpeak@piper@@YAX'):
        assert module.native_tts_name(retained + ' 0001:00004567 ' + native + ' 0000000180004567 f espeak-ng.lib\n')


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


def selected_vs_fixture(module, tmp_path, monkeypatch):
    instance = tmp_path / 'authored VS18'
    roots = {}
    for name, relative in {'vc': 'VC/Tools/MSVC/' + module.pin()['toolchain']['vc_tools_version'],
            'vc-auxiliary': 'VC/Auxiliary', 'msbuild': 'MSBuild'}.items():
        path = instance / relative; path.mkdir(parents=True)
        roots[name] = str(path)
    for name in ('sdk-include', 'sdk-lib', 'sdk-bin', 'cmake', 'python'):
        path = tmp_path / name; path.mkdir(); roots[name] = str(path)
    machine = tmp_path / 'authored Program Files x86'
    tool = machine / 'Microsoft Visual Studio/Installer/vswhere.exe'
    tool.parent.mkdir(parents=True); tool.write_bytes(b'owned non-executable query fixture')
    monkeypatch.setenv('ProgramFiles(x86)', str(machine))
    version = '18.11.12315.225'
    observed = [{'installationPath': str(instance), 'installationVersion': version,
        'displayName': 'private ignored instance metadata'}]
    def query(command, **kwargs):
        assert command == [str(tool), '-latest', '-products', '*', '-requires',
            'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-format', 'json', '-utf8']
        assert kwargs['stderr'] == module.subprocess.STDOUT and kwargs['timeout'] == 30
        return json.dumps(observed).encode()
    monkeypatch.setattr(module.subprocess, 'check_output', query)
    return instance, version, tool, roots, observed


def test_vs_instance_argument_uses_requeried_real_selection_and_sealed_root_binding(module, tmp_path, monkeypatch):
    instance, version, tool, roots, _ = selected_vs_fixture(module, tmp_path, monkeypatch)
    result = module.verify_vs_selection(instance, version, tool, roots)
    assert result == {'installation_version': version, 'vswhere': module.attributes(tool.read_bytes())}
    assert module.verify_vs_selection(instance, version, tool, roots, result) == result
    assert module.cmake_instance_spec(instance, version) == instance.resolve().as_posix() + ',version=' + version
    assert str(tmp_path) not in json.dumps(result) and 'private' not in json.dumps(result)


@pytest.mark.parametrize('version', [None, 18, ['18.11.12315.225'], '17.11.12315.225',
    '18.11.12315', '18.11.12315.225.1', '18.11.12315.225\n', '18.11.private.225',
    '18.11.12315.225,version=18.0.0.0'])
def test_vs_instance_argument_refuses_noncanonical_or_wrong_major_version_before_query(module, tmp_path, monkeypatch, version):
    instance, _, tool, roots, _ = selected_vs_fixture(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *_a, **_k: pytest.fail('Malformed selection must not execute a query.'))
    with pytest.raises(ValueError): module.verify_vs_selection(instance, version, tool, roots)


@pytest.mark.parametrize('role', ['vc', 'vc-auxiliary', 'msbuild', 'instance-root', 'query-origin'])
def test_vs_instance_cannot_choose_foreign_root_or_query_executable(module, tmp_path, monkeypatch, role):
    instance, version, tool, roots, _ = selected_vs_fixture(module, tmp_path, monkeypatch)
    other = tmp_path / 'foreign instance'; other.mkdir()
    if role in roots: roots[role] = str(other)
    if role == 'instance-root': instance = other
    if role == 'query-origin':
        tool = other / 'vswhere.exe'; tool.write_bytes(b'owned foreign query fixture')
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *_a, **_k: pytest.fail('Foreign origin must not execute a query.'))
    with pytest.raises(ValueError): module.verify_vs_selection(instance, version, tool, roots)


@pytest.mark.parametrize('change', ['version', 'root', 'multiple', 'query-bytes-during-query', 'query-bytes-before-final-query'])
def test_vs_selection_refuses_different_actual_identity_or_changed_query_bytes(module, tmp_path, monkeypatch, change):
    instance, version, tool, roots, observed = selected_vs_fixture(module, tmp_path, monkeypatch)
    initial = module.verify_vs_selection(instance, version, tool, roots)
    if change == 'version': observed[0]['installationVersion'] = '18.11.12316.225'
    if change == 'root':
        other = tmp_path / 'foreign actual instance'; other.mkdir(); observed[0]['installationPath'] = str(other)
    if change == 'multiple': observed.append(dict(observed[0]))
    if change == 'query-bytes-before-final-query': tool.write_bytes(b'changed owned query fixture')
    if change == 'query-bytes-during-query':
        def query(*_a, **_k):
            tool.write_bytes(b'changed owned query fixture'); return json.dumps(observed).encode()
        monkeypatch.setattr(module.subprocess, 'check_output', query)
    with pytest.raises(ValueError): module.verify_vs_selection(instance, version, tool, roots, initial)


@pytest.mark.parametrize('change', ['root', 'version'])
def test_configured_instance_must_retain_exact_selected_path_and_version(module, tmp_path, change):
    instance = tmp_path / 'authored VS18'; instance.mkdir()
    spec = module.cmake_instance_spec(instance, '18.11.12315.225')
    lines = [f'{k}:STRING={v}' for k, v in module.pin()['cmake'].items()]
    lines += ['FETCHCONTENT_SOURCE_DIR_' + i['fetchcontent_name'].upper() + ':PATH=' +
        str(tmp_path / 'sources' / i['name']) for i in module.pin()['inputs'] if i['fetchcontent_name']]
    lines.append('CMAKE_GENERATOR_INSTANCE:INTERNAL=' + spec)
    cache = tmp_path / 'CMakeCache.txt'; cache.write_text('\n'.join(lines))
    module.verify_cache(cache, tmp_path, spec)
    wrong = spec.replace('authored VS18', 'foreign VS18') if change == 'root' else spec.replace('12315', '12316')
    cache.write_text('\n'.join(lines).replace(spec, wrong))
    with pytest.raises(ValueError): module.verify_cache(cache, tmp_path, spec)


@pytest.mark.parametrize('observed,expected', [('18.11.12315.225', '18.11.12315.225'),
    ('C:/r19-authored-private/instance-version', None), ('18.11.12315.225\n', None)])
def test_failed_vs_metadata_keeps_only_strict_numeric_label(module, tmp_path, monkeypatch, observed, expected):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, '_BUILD_VS_VERSION', observed)
    report = module.failed_build_receipt(output, 'vs-installation-origin', ValueError('private root/version data'))
    assert report['visual_studio_instance_version'] == expected
    assert report['status'] == 'failed' and report['native_reference_probes_passed'] is False
    delivered = (output / 'ASR-FAILURE.json').read_text()
    assert str(tmp_path) not in delivered and 'r19-authored-private' not in delivered
    assert 'private root/version' not in delivered and not (output / 'ASR-RECEIPT.json').exists()


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


@pytest.mark.parametrize('labels', [[], ['v170'], ['v170', 'v180']])
def test_vc_target_diagnostics_keep_selected_pin_guard_and_collect_parent_categories_before_refusal(module, tmp_path, monkeypatch, labels):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    msbuild = tmp_path / 'msbuild'; msbuild.mkdir()
    for label in labels:
        props = msbuild / 'Microsoft/VC' / label / 'Microsoft.Cpp.Default.props'
        props.parent.mkdir(parents=True); props.write_bytes(('Owned props fixture ' + label).encode())
    (output.parent / 'Directory.Build.targets').write_bytes(b'owned parent import fixture')
    with pytest.raises(ValueError): module.review_vc_targets(output, msbuild)
    assert module._BUILD_PHASE == 'vc-target-selection'
    report = module.failed_build_receipt(output, module._BUILD_PHASE, ValueError('private failure text'))
    observation = report['build_environment_observation']
    assert observation['vc_targets']['candidate_count'] == len(labels)
    assert [v['label'] for v in observation['vc_targets']['candidates']] == labels
    assert observation['vc_targets']['selected_family'] == 'v180'
    assert observation['vc_targets']['selected_props_pin_matched'] is False
    assert observation['parent_import_categories'] == ['Directory.Build.targets']
    for candidate in observation['vc_targets']['candidates']:
        props = msbuild / 'Microsoft/VC' / candidate['label'] / 'Microsoft.Cpp.Default.props'
        assert candidate['props'] == module.attributes(props.read_bytes())
    assert str(tmp_path) not in json.dumps(observation)
    assert report['status'] == 'failed' and not (output / 'ASR-RECEIPT.json').exists()


def test_single_vc_target_does_not_bypass_parent_import_gate(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch, vc_props=b'owned props fixture')
    msbuild = tmp_path / 'msbuild'
    props = msbuild / 'Microsoft/VC/v180/Microsoft.Cpp.Default.props'
    props.parent.mkdir(parents=True); props.write_bytes(b'owned props fixture')
    (output.parent / 'MSBuild.rsp').write_bytes(b'owned response fixture')
    assert module.review_vc_targets(output, msbuild) == [props]
    module.build_phase('parent-import-review')
    with pytest.raises(ValueError): module.reject_parent_imports(output)
    report = module.failed_build_receipt(output, module._BUILD_PHASE, ValueError('owned refusal'))
    assert report['phase'] == 'parent-import-review'
    assert report['build_environment_observation']['parent_import_categories'] == ['MSBuild.rsp']


def test_explicit_pinned_vc_family_is_selected_among_other_sealed_families_without_latest_fallback(module, tmp_path, monkeypatch):
    data = b'owned selected props fixture'
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch, vc_props=data)
    msbuild = tmp_path / 'msbuild'
    for label in ('v160', 'v170', 'v180', 'v999'):
        props = msbuild / 'Microsoft/VC' / label / 'Microsoft.Cpp.Default.props'
        props.parent.mkdir(parents=True)
        props.write_bytes(data if label == 'v180' else b'owned unselected props fixture')
    selected = msbuild / 'Microsoft/VC/v180/Microsoft.Cpp.Default.props'
    assert module.review_vc_targets(output, msbuild) == [selected]
    observation = module.safe_build_environment_observation()['vc_targets']
    assert observation['candidate_count'] == 4
    assert [v['label'] for v in observation['candidates']] == ['v160', 'v170', 'v180', 'v999']
    assert observation['selected_family'] == 'v180' and observation['selected_candidate_count'] == 1
    assert observation['selected_props_pin_matched'] is True
    assert str(tmp_path) not in json.dumps(observation)


@pytest.mark.parametrize('changed', ['missing', 'props-bytes', 'props-size', 'family-case-alias', 'props-case-alias'])
def test_selected_vc_family_refuses_missing_changed_or_aliased_props(module, tmp_path, monkeypatch, changed):
    data = b'owned selected props fixture'
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch, vc_props=data)
    msbuild = tmp_path / 'msbuild'
    props = msbuild / 'Microsoft/VC/v180/Microsoft.Cpp.Default.props'
    if changed == 'family-case-alias': props = props.parent.with_name('V180') / props.name
    if changed == 'props-case-alias': props = props.with_name('microsoft.cpp.default.props')
    props.parent.mkdir(parents=True)
    props.write_bytes(data)
    if changed == 'missing': props.unlink()
    if changed == 'props-bytes': props.write_bytes(data.replace(b'owned', b'other'))
    if changed == 'props-size': props.write_bytes(data + b' changed')
    with pytest.raises(ValueError): module.review_vc_targets(output, msbuild)
    assert module.safe_build_environment_observation()['vc_targets']['selected_props_pin_matched'] is False


def test_duplicate_selected_vc_discovery_records_are_refused_even_with_matching_fixture_bytes(module, tmp_path, monkeypatch):
    data = b'owned selected props fixture'
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch, vc_props=data)
    msbuild = tmp_path / 'msbuild'
    props = msbuild / 'Microsoft/VC/v180/Microsoft.Cpp.Default.props'
    props.parent.mkdir(parents=True); props.write_bytes(data)
    glob = Path.glob
    def duplicate_selected(base, pattern):
        found = list(glob(base, pattern))
        return found + found if base == msbuild / 'Microsoft/VC' else found
    monkeypatch.setattr(Path, 'glob', duplicate_selected)
    with pytest.raises(ValueError): module.review_vc_targets(output, msbuild)
    observation = module.safe_build_environment_observation()['vc_targets']
    assert observation['selected_candidate_count'] == 2
    assert observation['selected_props_pin_matched'] is False


def test_build_environment_projection_cannot_publish_unknown_labels_paths_or_raw_props(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, '_BUILD_ENVIRONMENT_OBSERVATION', {'vc_targets': {
        'candidate_count': 1, 'selected_family': str(tmp_path / 'private-target'),
        'selected_candidate_count': 'private count', 'selected_props_pin_matched': 'private result',
        'candidates': [{'label': 'v-private-tenant',
            'props': {**module.attributes(b'owned props'), 'contents': 'private model text'},
            'path': str(tmp_path / 'private-props')}]},
        'parent_import_categories': ['Directory.Build.props', str(tmp_path / 'private-import'),
            {'unexpected': 'private object'}], 'raw_exception': 'private exception text'})
    report = module.failed_build_receipt(output, 'vc-target-selection', ValueError('private error'))
    observation = report['build_environment_observation']
    assert observation['vc_targets']['candidates'] == [{'label': None, 'props': module.attributes(b'owned props')}]
    assert observation['vc_targets']['selected_family'] is None
    assert observation['vc_targets']['selected_candidate_count'] is None
    assert observation['vc_targets']['selected_props_pin_matched'] is False
    assert observation['parent_import_categories'] == ['Directory.Build.props']
    delivered = (output / 'ASR-FAILURE.json').read_text()
    assert str(tmp_path) not in delivered and 'private' not in delivered and 'contents' not in delivered


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


@pytest.mark.parametrize('label,body', [
    ('cmake-generator-unavailable', 'Could not create named generator private-generator'),
    ('cmake-vs-instance-not-found', 'Generator Visual Studio 18 2026 could not find specified instance of Visual Studio:\n  {private}'),
    ('cmake-vs-installation-not-found', 'Generator Visual Studio 18 2026 could not find any instance of Visual Studio.'),
    ('cmake-vs-installer-instance-unknown', "The directory exists, but the instance is not known to the Visual Studio Installer, and no 'version=' field was given."),
    ('cmake-vs-instance-version-invalid', 'given instance specification {private} but the version field is not 4 integer components starting in 18.'),
    ('cmake-vs-instance-fields-invalid', "given instance specification {private} that contains invalid field 'private-model'."),
    ('cmake-msbuild-vctargets-query-failed', 'Failed to run MSBuild command:\n  {private}\nto get the value of VCTargetsPath:'),
    ('cmake-toolset-version-invalid', 'given toolset and version specification v145,version=14.51.36231 contains an invalid version specification.'),
    ('cmake-toolset-not-installed', 'given toolset and version specification v145,version=14.51.36231 does not seem to be installed at\n  {private}'),
    ('cmake-toolset-selection-ambiguous', 'given toolset and version specification {private} has multiple matches installed at {private}\nThe toolset and version specification must resolve\nto a single installed toolset'),
    ('cmake-toolset-fields-invalid', "given toolset specification {private} that contains duplicate field key 'private-model'."),
    ('cmake-flagtable-not-found', 'JSON flag table for private-table not found for toolset private-toolset'),
    ('cmake-flagtable-load-failed', 'JSON flag table could not be loaded:\n  {private}'),
    ('cmake-platform-fields-invalid', "given platform specification {private} that contains a field after the first ',' with no '='."),
    ('cmake-generator-specification-unsupported', 'Generator private-generator does not support platform specification, but platform private-platform was specified.'),
    ('cmake-platform-version-invalid', 'given platform specification containing a version=private-version field with unsupported value.'),
    ('cmake-windows-sdk-not-found', 'given platform specification with version=10.0.26100.0 field, but no Windows SDK with that version was found.'),
    ('cmake-build-program-not-found', 'CMake was unable to find a build program corresponding to "private-generator". CMAKE_MAKE_PROGRAM is not set.'),
    ('cmake-compiler-not-found', 'The CMAKE_CXX_COMPILER:\n  {private}\nis not a full path to an existing compiler tool.'),
    ('cmake-compiler-not-recorded', 'No CMAKE_C_COMPILER could be found.'),
    ('cmake-compiler-not-set', 'CMAKE_RC_COMPILER not set, after EnableLanguage'),
    ('cmake-environment-compiler-not-found', 'Could not find the compiler specified in the environment variable CXX:\n{private}.'),
    ('cmake-compiler-identification-build-failed', 'Compiling the CXX compiler identification source file "private-id.cxx" failed.'),
    ('cmake-msvc-version-not-detected', 'MSVC compiler version not detected properly: private-version'),
    ('cmake-msvc-clui-not-found', 'Could not find clui.dll !'),
    ('cmake-compiler-test-failed', 'The C compiler "{private}"\nis not able to compile a simple test program.'),
    ('cmake-cli-argument-invalid', 'Unknown argument {private}'),
    ('cmake-cli-argument-invalid', 'Parse error in command line argument: {private}\n Should be: VAR:type=value'),
    ('cmake-source-directory-invalid', 'The source directory "{private}" does not appear to contain CMakeLists.txt.'),
    ('cmake-cache-source-mismatch', 'The source "{private}" does not match the source "{private}" used to generate cache. Re-run cmake with a different source directory.'),
    ('cmake-cache-generator-mismatch', 'Error: generator : private-value\nDoes not match the generator used previously: private-value'),
    ('cmake-cache-instance-mismatch', 'Error: generator instance: {private}\nDoes not match the instance used previously: {private}'),
    ('cmake-cache-platform-mismatch', 'Error: generator platform: private-value\nDoes not match the platform used previously: private-value'),
    ('cmake-cache-toolset-mismatch', 'Error: generator toolset: private-value\nDoes not match the toolset used previously: private-value'),
    ('cmake-project-arguments-invalid', 'project with VERSION, DESCRIPTION or HOMEPAGE_URL must\nuse LANGUAGES before language names.'),
    ('cmake-project-include-unavailable', 'could not load requested file:\n  {private}'),
    ('cmake-minimum-version-required', 'CMake 4.5 or higher is required. You are running version 4.4.5'),
    ('cmake-compatibility-removed', 'Compatibility with CMake < 3.5 has been removed\nfrom CMake.'),
    ('cmake-policy-minimum-invalid', 'Invalid CMAKE_POLICY_VERSION_MINIMUM value "private-version". A numeric major.minor[.patch[.tweak]] must be given.'),
    ('cmake-policy-unknown', 'Policy "CMP1234" is not known to this version of CMake.'),
    ('cmake-policy-old-unsupported', 'Policy CMP0001 may not be set to OLD behavior because this version of CMake no longer supports it.'),
    ('cmake-policy-arguments-invalid', 'cmake_policy SET given unrecognized policy status "private-status"'),
    ('cmake-command-unknown', 'Unknown CMake command "private-command".'),
])
def test_cmake445_error_templates_yield_fixed_ids_without_private_values(module, tmp_path, label, body):
    content = 'CMake Error at ' + str(tmp_path / 'private-project.cmake') + ':26 (project):\n  '
    content += body.replace('{private}', str(tmp_path / 'private-owner/model-secret')) + '\n'
    categories, sites = module.cmake_failure_details(content)
    assert label in categories
    assert sites == [{'command': 'project', 'line': 26}]
    delivered = json.dumps({'categories': categories, 'cmake_error_sites': sites})
    for private in (str(tmp_path), 'private-', 'model-secret'):
        assert private not in delivered


def test_cmake_error_sites_are_bounded_known_commands_and_warnings_do_not_become_causes(module, tmp_path):
    warning = ('CMake Warning at ' + str(tmp_path / 'private.cmake') + ':12 (message):\n'
        '  could not find specified instance of Visual Studio: private-model\n')
    assert module.cmake_failure_details(warning) == ([], [])
    content = (warning + 'CMake Error at private.cmake:0 (project):\n  private-model\n'
        'CMake Error at private.cmake:10000000 (project):\n  private-model\n'
        'CMake Error at private.cmake:25 (private-command):\n  private-model\n')
    content += ''.join('CMake Error at ' + str(tmp_path / 'private.cmake') + ':' + str(line)
        + ' (project):\n  private-model\n' for line in range(1, 40))
    categories, sites = module.cmake_failure_details(content)
    assert categories == [] and len(sites) == 32
    assert sites == [{'command': 'project', 'line': line} for line in range(1, 33)]
    assert str(tmp_path) not in json.dumps(sites) and 'private' not in json.dumps(sites)


def test_cmake_failure_receipt_delivers_known_sites_and_tail_only_without_native_success(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    logs = output / 'private-logs'; logs.mkdir()
    prefix = b'CMake Error: Unknown CMake command "private-early-command".\n'
    tail = ('CMake Error at ' + str(tmp_path / 'private-project.cmake') + ':26 (project):\n'
        '  Generator Visual Studio 18 2026\n'
        '  could not find specified instance of Visual Studio:\n  private-instance\n'
        'CMake Warning at private-warning.cmake:7 (message):\n'
        '  Unknown argument private-warning\n'
        'Configuring incomplete, errors occurred!\n')
    (logs / 'configure.log').write_bytes(prefix + b'x' * (2 * 1024 * 1024) + b'\n' + tail.encode())
    report = module.failed_build_receipt(output, 'cmake-configure', ValueError('private exception'))
    diagnostics = report['diagnostics']
    assert 'cmake-vs-instance-not-found' in diagnostics['categories']
    assert 'cmake-command-unknown' not in diagnostics['categories']
    assert 'cmake-cli-argument-invalid' not in diagnostics['categories']
    assert diagnostics['cmake_error_sites'] == [{'command': 'project', 'line': 26}]
    assert report['status'] == 'failed' and report['native_reference_probes_passed'] is False
    assert report['rights_approval'] is False and report['gates']['production_execution_allowed'] is False
    assert not (output / 'ASR-RECEIPT.json').exists()
    delivered = (output / 'ASR-FAILURE.json').read_text()
    for private in (str(tmp_path), 'private-early-command', 'private-project',
                    'private-instance', 'private-warning', 'private exception'):
        assert private not in delivered


def test_compiler_context_observes_known_fields_without_reading_outside_compiler_paths(module, tmp_path, monkeypatch):
    _source, _inputs, output = prepared(module, tmp_path, monkeypatch)
    vc, sdk = tmp_path/'sealed-vc', tmp_path/'sealed-sdk-bin'
    vc.mkdir(); sdk.mkdir(); (vc/'cl.exe').write_bytes(b'owned compiler fixture'); (sdk/'rc.exe').write_bytes(b'owned resource tool fixture')
    roots={'vc':str(vc),'sdk-bin':str(sdk)}
    build=output/'build'; config=build/'CMakeFiles/4.4.5'; config.mkdir(parents=True)
    (build/'CMakeCache.txt').write_text('CMAKE_C_COMPILER:FILEPATH='+str(vc/'cl.exe')+'\n'
        'CMAKE_C_COMPILER_ID:STRING=MSVC\nCMAKE_C_COMPILER_VERSION:STRING=19.51.36260.0\n'
        'CMAKE_CXX_COMPILER:FILEPATH=CMAKE_CXX_COMPILER-NOTFOUND\n'
        'CMAKE_CXX_COMPILER_ID:STRING=private-compiler-id\nCMAKE_CXX_COMPILER_VERSION:STRING=private-version\n'
        'CMAKE_RC_COMPILER:FILEPATH='+str(sdk/'rc.exe')+'\n')
    (config/'CMakeCCompiler.cmake').write_text('set(CMAKE_C_COMPILER "'+(vc/'cl.exe').as_posix()+'")\n'
        'set(CMAKE_C_COMPILER_ID "MSVC")\nset(CMAKE_C_COMPILER_VERSION "19.51.36260.0")\n')
    outside=tmp_path/'private-account/compiler.exe'; outside.parent.mkdir(); outside.write_bytes(b'private compiler text')
    (config/'CMakeRCCompiler.cmake').write_text('set(CMAKE_RC_COMPILER "'+outside.as_posix()+'")\n')
    real_stat,real_open=Path.stat,Path.open
    def stat_guard(path,*a,**k):
        if path==outside: pytest.fail('Outside compiler paths must not be statted.')
        return real_stat(path,*a,**k)
    def open_guard(path,*a,**k):
        if path==outside: pytest.fail('Outside compiler paths must not be read.')
        return real_open(path,*a,**k)
    monkeypatch.setattr(Path,'stat',stat_guard); monkeypatch.setattr(Path,'open',open_guard)
    monkeypatch.setattr(module,'_BUILD_TOOL_ROOTS',roots)
    report=module.failed_build_receipt(output,'cmake-configure',ValueError('private failure text'))
    context=report['compiler_detection_context']; c,cxx,rc=context['languages']
    assert context['evidence_scope']=='compiler-file-observation-not-native-approval'
    assert c['cache']==c['configuration']=={'state':'observed','compiler_state':'sealed-vc-toolset','compiler_id':'MSVC','compiler_version':'19.51.36260.0'}
    assert cxx['cache']['compiler_state']=='not-found' and cxx['cache']['compiler_id'] is None
    assert cxx['cache']['compiler_version'] is None and cxx['configuration']['state']=='missing'
    assert rc['cache']['compiler_state']=='sealed-sdk-bin' and rc['configuration']['compiler_state']=='outside-declared-roots'
    delivered=(output/'ASR-FAILURE.json').read_text()
    for private in (str(tmp_path),'private-account','private-compiler-id','private-version','private compiler text','private failure text'):
        assert private not in delivered
    assert report['status']=='failed' and report['rights_approval'] is False and not (output/'ASR-RECEIPT.json').exists()


@pytest.mark.parametrize('value,state', [(None,'missing-entry'),('','empty'),('NOTFOUND','not-found'),
    ('CMAKE_C_COMPILER-NOTFOUND','not-found'),('private-NOTFOUND','not-absolute'),
    ('private-relative','not-absolute'),('private\nvalue','invalid-value'),([], 'invalid-value')])
def test_compiler_context_distinguishes_only_evidenced_missing_notfound_and_invalid_values(module, value, state):
    assert module.compiler_path_state(value,'C',None)==state


def test_compiler_context_parent_traversal_duplicate_values_and_file_caps_fail_closed(module, tmp_path, monkeypatch):
    _source,_inputs,output=prepared(module,tmp_path,monkeypatch)
    vc=tmp_path/'sealed-vc'; vc.mkdir()
    assert module.compiler_path_state(str(vc/'..'/'private-account'/'compiler.exe'),'C',{'vc':str(vc)})=='outside-declared-roots'
    build=output/'build'; config=build/'CMakeFiles/4.4.5'; config.mkdir(parents=True)
    (build/'CMakeCache.txt').write_text('CMAKE_C_COMPILER:FILEPATH=private-a\nCMAKE_C_COMPILER:FILEPATH=private-b\n')
    context=module.compiler_detection_context(output,{'vc':str(vc)})
    assert context['languages'][0]['cache']['state']=='duplicate-entry'
    monkeypatch.setattr(module,'COMPILER_CONTEXT_FILE_BYTES',32)
    (config/'CMakeCCompiler.cmake').write_bytes(b'private compiler text'*10)
    context=module.compiler_detection_context(output,{'vc':str(vc)})
    assert context['languages'][0]['cache']['state']==context['languages'][0]['configuration']['state']=='size-limit'
    assert 'private' not in json.dumps(context)


def test_compiler_context_link_and_nonregular_inputs_are_not_read(module, tmp_path, monkeypatch):
    _source,_inputs,output=prepared(module,tmp_path,monkeypatch)
    build=output/'build'; config=build/'CMakeFiles/4.4.5'; config.mkdir(parents=True)
    cache=build/'CMakeCache.txt'; cache.write_text('private linked input')
    (config/'CMakeCCompiler.cmake').mkdir()
    real_lstat=Path.lstat
    monkeypatch.setattr(Path,'lstat',lambda p,*a,**k:
        SimpleNamespace(st_mode=module.stat.S_IFLNK) if p==cache else real_lstat(p,*a,**k))
    context=module.compiler_detection_context(output,None)
    assert context['languages'][0]['cache']['state']=='inspection-error'
    assert context['languages'][0]['configuration']['state']=='not-regular'
    assert 'private' not in json.dumps(context)


def test_nested_logs_are_fixed_context_only_with_perfile_and_total_caps(module, tmp_path, monkeypatch):
    directory=tmp_path/'build/CMakeFiles';directory.mkdir(parents=True)
    first=directory/'CMakeConfigureLog.yaml'; second=directory/'CMakeError.log'
    first.write_bytes(b'error C1083: private early\n'+b'x'*80+b'\nerror C2065: private late\n')
    second.write_bytes(b'private prefix '*10+b'\nerror MSB8020\n')
    forbidden=directory/'CMakeOutput.log';forbidden.write_bytes(b'error LNK2019: private unknown log')
    monkeypatch.setattr(module,'LOG_TAIL_BYTES',64);monkeypatch.setattr(module,'NESTED_LOG_TOTAL_BYTES',80)
    real_reader=module.diagnostic_file;calls=[]
    def reader(path,limit,**options):
        assert path in (first,second)
        result=real_reader(path,limit,**options);calls.append((limit,len(result[1])));return result
    monkeypatch.setattr(module,'diagnostic_file',reader)
    context=module.nested_configure_log_context(tmp_path)
    assert context['evidence_scope']=='observed-context-not-fatal-cause'
    assert context['logs'][0]['known_codes']==['C2065'] and context['logs'][1]['known_codes']==['MSB8020']
    assert calls==[(64,64),(16,16)] and sum(n for _,n in calls)==80
    assert 'private' not in json.dumps(context) and str(tmp_path) not in json.dumps(context)
    monkeypatch.setattr(module,'NESTED_LOG_TOTAL_BYTES',1);calls.clear()
    context=module.nested_configure_log_context(tmp_path)
    assert calls==[(1,1)] and context['logs'][1]['state']=='total-byte-limit'


def test_nested_log_nonregular_and_unknown_codes_remain_private_context(module,tmp_path):
    directory=tmp_path/'build/CMakeFiles';directory.mkdir(parents=True)
    (directory/'CMakeConfigureLog.yaml').mkdir()
    (directory/'CMakeError.log').write_text('error C9999: private secret model text\n')
    context=module.nested_configure_log_context(tmp_path)
    assert context['logs'][0]['state']=='not-regular'
    assert context['logs'][1]['known_codes']==[] and context['logs'][1]['context_labels']==['compiler-or-linker-error','unclassified-tool-error']
    assert 'C9999' not in json.dumps(context) and 'private' not in json.dumps(context)


@pytest.mark.parametrize('kind',['symlink','windows-reparse'])
def test_nested_log_linked_parent_is_rejected_before_descendant_metadata_or_open(module,tmp_path,monkeypatch,kind):
    directory=tmp_path/'build/CMakeFiles';directory.mkdir(parents=True)
    for filename in ('CMakeConfigureLog.yaml','CMakeError.log'):
        (directory/filename).write_text('error C1083: private linked content\n')
    real_lstat,real_stat,real_open=Path.lstat,Path.stat,Path.open
    def reject_descendant(path):
        if path != directory and path.is_relative_to(directory):
            pytest.fail('Linked log parents must be rejected before descendant stat/lstat/open.')
    def lstat_guard(path,*a,**k):
        reject_descendant(path)
        if path==directory:
            return SimpleNamespace(st_mode=module.stat.S_IFLNK if kind=='symlink' else module.stat.S_IFDIR,
                st_file_attributes=0x400 if kind=='windows-reparse' else 0)
        return real_lstat(path,*a,**k)
    def stat_guard(path,*a,**k):
        reject_descendant(path);return real_stat(path,*a,**k)
    def open_guard(path,*a,**k):
        reject_descendant(path);return real_open(path,*a,**k)
    monkeypatch.setattr(Path,'lstat',lstat_guard);monkeypatch.setattr(Path,'stat',stat_guard)
    monkeypatch.setattr(Path,'open',open_guard)
    context=module.nested_configure_log_context(tmp_path)
    assert all(row['state']=='inspection-error' and row['known_codes']==[] for row in context['logs'])
    assert 'private' not in json.dumps(context)


@pytest.mark.parametrize('kind',['symlink','windows-reparse'])
def test_compiler_linked_parent_is_rejected_before_descendant_metadata_or_open(module,tmp_path,monkeypatch,kind):
    vc=tmp_path/'sealed-vc';directory=vc/'bin';directory.mkdir(parents=True)
    compiler=directory/'cl.exe';compiler.write_bytes(b'private compiler fixture')
    real_lstat,real_stat,real_open=Path.lstat,Path.stat,Path.open
    def reject_descendant(path):
        if path != directory and path.is_relative_to(directory):
            pytest.fail('Linked compiler parents must be rejected before descendant stat/lstat/open.')
    def lstat_guard(path,*a,**k):
        reject_descendant(path)
        if path==directory:
            return SimpleNamespace(st_mode=module.stat.S_IFLNK if kind=='symlink' else module.stat.S_IFDIR,
                st_file_attributes=0x400 if kind=='windows-reparse' else 0)
        return real_lstat(path,*a,**k)
    def stat_guard(path,*a,**k):
        reject_descendant(path);return real_stat(path,*a,**k)
    def open_guard(path,*a,**k):
        reject_descendant(path);return real_open(path,*a,**k)
    monkeypatch.setattr(Path,'lstat',lstat_guard);monkeypatch.setattr(Path,'stat',stat_guard)
    monkeypatch.setattr(Path,'open',open_guard)
    assert module.compiler_path_state(str(compiler),'C',{'vc':str(vc)})=='inspection-error'


def test_msb4019_context_labels_known_imports_without_inspecting_unknown_or_outside_targets(module,tmp_path,monkeypatch):
    msbuild=tmp_path/'sealed-msbuild';selected=msbuild/'Microsoft/VC/v180';selected.mkdir(parents=True)
    present=selected/'Microsoft.Cpp.Default.props';present.write_bytes(b'owned props fixture')
    missing=selected/'Microsoft.Cpp.props';nonregular=selected/'Microsoft.Cpp.targets';nonregular.mkdir()
    outside=tmp_path/'private-outside/Microsoft.Cpp.props';outside.parent.mkdir();outside.write_bytes(b'private import fixture')
    unknown=selected/'private-unknown.props';unknown.write_bytes(b'private unknown fixture')
    real_stat,real_lstat,real_open=Path.stat,Path.lstat,Path.open
    def guard(original):
        def call(path,*args,**kwargs):
            if path==unknown or path.is_relative_to(outside.parent):pytest.fail('Outside and unknown imports must not be inspected.')
            return original(path,*args,**kwargs)
        return call
    monkeypatch.setattr(Path,'stat',guard(real_stat));monkeypatch.setattr(Path,'lstat',guard(real_lstat))
    monkeypatch.setattr(Path,'open',guard(real_open))
    content='\n'.join('error MSB4019: The imported project "'+str(p)+'" was not found.'
        for p in (present,missing,nonregular,outside,unknown))
    content+='\nerror MSB4019: private new diagnostic template\nerror MSB4999: private unknown tool code\n'
    context=module.msb4019_import_context(content,{'msbuild':str(msbuild)},
        {'VCTargetsPath':str(selected)},16)
    assert context['truncated'] is False and len(context['records'])==6
    targets=[{key:row[key] for key in ('import_label','root_role','existence')} for row in context['records']]
    assert targets[:3]==[
        {'import_label':'microsoft-cpp-default-props','root_role':'selected-vc-targets','existence':'regular-file-present'},
        {'import_label':'microsoft-cpp-props','root_role':'selected-vc-targets','existence':'missing'},
        {'import_label':'microsoft-cpp-targets','root_role':'selected-vc-targets','existence':'nonregular'}]
    assert targets[3]=={'import_label':'microsoft-cpp-props','root_role':'outside-declared-roots','existence':'not-inspected'}
    assert targets[4:]==[{'import_label':'unknown-import','root_role':'not-inspected','existence':'not-inspected'}]*2
    # An expected property value cannot authorize reads outside declared roots.
    assert module.import_target_context(str(outside),{'msbuild':str(msbuild)},
        {'VCTargetsPath':str(outside.parent)})['root_role']=='outside-declared-roots'
    assert module.import_target_context(str(selected/'private-parent/../Microsoft.Cpp.props'),
        {'msbuild':str(msbuild)},{})['root_role']=='not-inspected'
    delivered=json.dumps(context)
    for value in (str(tmp_path),'private','MSB4999','owned props fixture'):
        assert value not in delivered


@pytest.mark.parametrize('caller,label,line,column',[
    (r'C:\private-root\CompilerIdC.vcxproj(21,7)','compiler-id-c-project',21,7),
    (r'C:\private-root\CompilerIdCXX.vcxproj(32)','compiler-id-cxx-project',32,None),
    (r'C:\private-root\Microsoft.Cpp.Default.props(42,3)','microsoft-cpp-default-props',42,3),
    (r'C:\private-root\private-caller.vcxproj(21,7)','unknown-caller',None,None),
    ('CompilerIdC.vcxproj(0,7)','unknown-caller',None,None),
    ('CompilerIdC.vcxproj(99999999,7)','unknown-caller',None,None),
    ('CompilerIdC.vcxproj(21,0)','unknown-caller',None,None)])
def test_msb4019_callers_are_only_primary_labels_and_bounded_positive_positions(module,caller,label,line,column):
    content='  '+caller+': error MSB4019: The imported project "private-target/Microsoft.Cpp.props" was not found.'
    result=module.msb4019_import_context(content,{},None,16)
    assert result['records'][0]['caller']=={'file_label':label,'line':line,'column':column}
    delivered=json.dumps(result)
    assert 'private-' not in delivered and caller not in delivered


def test_msb4019_context_limits_records_across_both_fixed_logs(module,tmp_path,monkeypatch):
    directory=tmp_path/'build/CMakeFiles';directory.mkdir(parents=True)
    message='error MSB4019: The imported project "private-root/Microsoft.Cpp.props" was not found.\n'
    for filename in ('CMakeConfigureLog.yaml','CMakeError.log'):(directory/filename).write_text(message*2)
    monkeypatch.setattr(module,'IMPORT_CONTEXT_LIMIT',3)
    result=module.nested_configure_log_context(tmp_path)
    contexts=[row['msb4019_imports'] for row in result['logs']]
    assert [len(row['records']) for row in contexts]==[2,1]
    assert [row['truncated'] for row in contexts]==[False,True]
    assert 'private-root' not in json.dumps(result)


def compiler_id_project(output,language,body):
    path=output/'build/CMakeFiles/4.4.5'/('CompilerId'+language)/('CompilerId'+language+'.vcxproj')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(body)
    return path


def test_compiler_id_globals_deliver_only_literal_match_states_from_actual_private_properties(module,tmp_path,monkeypatch):
    _source,_inputs,output=prepared(module,tmp_path,monkeypatch)
    properties={'VCTargetsPath':(tmp_path/'private-v180').as_posix()+'/',
        'UserRootDir':(tmp_path/'private-user').as_posix()+'/',
        'MSBuildUserExtensionsPath':(tmp_path/'private-extensions').as_posix()+'/',
        'ImportDirectoryBuildProps':'false','ImportDirectoryBuildTargets':'false'}
    prefix='<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003"><PropertyGroup Label="Globals">'
    suffix='</PropertyGroup></Project>'
    body=''.join('<'+key+'>'+value+'</'+key+'>' for key,value in properties.items())
    compiler_id_project(output,'CXX',(prefix+body+suffix).encode())
    changed=body.replace('<UserRootDir>','<UserRootDir>private-duplicate</UserRootDir><UserRootDir>',1)
    changed=changed.replace(properties['MSBuildUserExtensionsPath'],'private-different-value')
    changed=changed.replace('<ImportDirectoryBuildProps>false</ImportDirectoryBuildProps>',
        '<ImportDirectoryBuildProps Condition="private-condition">false</ImportDirectoryBuildProps>')
    changed=changed.replace('<ImportDirectoryBuildTargets>false</ImportDirectoryBuildTargets>','')
    changed+='<private-new-property>private-new-value</private-new-property>'
    compiler_id_project(output,'C',(prefix+changed+suffix).encode())
    monkeypatch.setattr(module,'_BUILD_PROPERTIES',properties)
    receipt=module.failed_build_receipt(output,'cmake-configure',ValueError('private exception'))
    context=receipt['compiler_id_globals_context']
    assert context['evidence_scope']=='observed-context-not-fatal-cause'
    c,cxx=context['projects']
    assert c['state']==cxx['state']=='observed'
    assert {p['property']:p['state'] for p in c['properties']}=={
        'VCTargetsPath':'exact-match','UserRootDir':'duplicate-property',
        'MSBuildUserExtensionsPath':'different','ImportDirectoryBuildProps':'structured-or-conditional-property',
        'ImportDirectoryBuildTargets':'missing'}
    assert all(p['state']=='exact-match' for p in cxx['properties'])
    delivered=(output/'ASR-FAILURE.json').read_text()
    assert str(tmp_path) not in delivered
    for value in ('private-v180','private-user','private-extensions','private-duplicate',
            'private-different-value','private-condition','private-new-property','private-new-value','private exception'):
        assert value not in delivered
    assert receipt['rights_approval'] is False and not (output/'ASR-RECEIPT.json').exists()
    unavailable=module.compiler_id_globals_context(output,None)
    assert all(p['state']=='expected-unavailable' for p in unavailable['projects'][1]['properties'])


@pytest.mark.parametrize('body',[
    b'<!DOCTYPE Project [<!ENTITY private "private value">]><Project>&private;</Project>',
    b'<!DOCTYPE Project SYSTEM "file:///private-authored-fixture"><Project/>',
    b'<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">&#97;</Project>',
    b'<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">&amp;</Project>',
    b'<Project>\xff</Project>',b'<Project>',b'<Project xmlns="private-unknown-namespace"/>'])
def test_compiler_id_globals_reject_entities_external_declarations_and_unsupported_xml(module,tmp_path,body):
    compiler_id_project(tmp_path,'C',body)
    result=module.compiler_id_globals_context(tmp_path,{})
    assert result['projects'][0]['state']=='unsupported-xml'
    assert all(p['state']=='unavailable' for p in result['projects'][0]['properties'])
    assert 'private' not in json.dumps(result) and str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize('groups,state',[
    ('','missing-globals'),
    ('<PropertyGroup Label="Globals"/><PropertyGroup Label="Globals"/>','ambiguous-globals'),
    ('<PropertyGroup Label="Globals" Condition="private-value"/>','ambiguous-globals')])
def test_compiler_id_globals_refuse_ambiguous_or_conditional_property_groups(module,tmp_path,groups,state):
    compiler_id_project(tmp_path,'C',('<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'+groups+'</Project>').encode())
    result=module.compiler_id_globals_context(tmp_path,{})
    assert result['projects'][0]['state']==state
    assert 'private-value' not in json.dumps(result)


def test_compiler_id_xml_byte_and_element_caps_reject_without_parsing_other_projects(module,tmp_path,monkeypatch):
    path=compiler_id_project(tmp_path,'C',b'<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">'+b'<X/>'*4096+b'</Project>')
    forbidden=path.parent/'private-other.vcxproj';forbidden.write_bytes(b'private external fixture')
    real_open=Path.open
    def open_guard(path,*args,**kwargs):
        if path==forbidden:pytest.fail('No arbitrary XML project discovery.')
        return real_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',open_guard)
    assert module.compiler_id_globals_context(tmp_path,{})['projects'][0]['state']=='unsupported-xml'
    monkeypatch.setattr(module,'COMPILER_CONTEXT_FILE_BYTES',32)
    assert module.compiler_id_globals_context(tmp_path,{})['projects'][0]['state']=='size-limit'


@pytest.mark.parametrize('operation',['import-context','numeric-import-context','compiler-id-xml'])
@pytest.mark.parametrize('kind',['symlink','windows-reparse'])
def test_import_and_xml_context_reject_linked_ancestors_before_descendant_metadata(module,tmp_path,monkeypatch,operation,kind):
    directory=tmp_path/'declared-root/linked-parent';directory.mkdir(parents=True)
    target=directory/'Microsoft.Cpp.props';target.write_bytes(b'private import fixture')
    if operation=='numeric-import-context':
        target=directory/('Microsoft.VCToolsVersion.'+module.pin()['toolchain']['vc_tools_version']+'.props')
        target.write_bytes(b'private numeric import fixture')
    if operation=='compiler-id-xml':
        target=compiler_id_project(tmp_path,'C',b'<Project/>');directory=target.parent
    real_stat,real_lstat,real_open=Path.stat,Path.lstat,Path.open
    def reject_descendant(path):
        if path!=directory and path.is_relative_to(directory):pytest.fail('Linked ancestors must precede all descendant metadata/read.')
    def lstat_guard(path,*args,**kwargs):
        reject_descendant(path)
        if path==directory:return SimpleNamespace(st_mode=module.stat.S_IFLNK if kind=='symlink' else module.stat.S_IFDIR,
            st_file_attributes=0x400 if kind=='windows-reparse' else 0)
        return real_lstat(path,*args,**kwargs)
    def stat_guard(path,*args,**kwargs):
        reject_descendant(path);return real_stat(path,*args,**kwargs)
    def open_guard(path,*args,**kwargs):
        reject_descendant(path);return real_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',lstat_guard);monkeypatch.setattr(Path,'stat',stat_guard)
    monkeypatch.setattr(Path,'open',open_guard)
    if operation in {'import-context','numeric-import-context'}:
        result=module.import_target_context(str(target),{'msbuild':str(directory.parent)},{})
        assert result['existence']=='inspection-error'
    else:
        result=module.compiler_id_globals_context(tmp_path,{})
        assert result['projects'][0]['state']=='inspection-error'
    assert str(tmp_path) not in json.dumps(result) and 'private' not in json.dumps(result)


@pytest.mark.parametrize('separator',['/','.'])
def test_generated_numeric_toolset_import_exposes_only_exact_verified_instance_suffix_branch(module,tmp_path,monkeypatch,separator):
    version=module.pin()['toolchain']['vc_tools_version'];observed='18.11.12315.225'
    vs=tmp_path/'private-vs';msbuild=vs/'MSBuild';selected=msbuild/'Microsoft/VC/v180'
    auxiliary=vs/'VC/Auxiliary';selected.mkdir(parents=True);auxiliary.mkdir(parents=True)
    roots={'msbuild':str(msbuild),'vc-auxiliary':str(auxiliary)}
    properties={'VCTargetsPath':str(selected)}
    for filename in ('Microsoft.Cpp.Default.props','Microsoft.Cpp.props','Microsoft.Cpp.targets'):
        (selected/filename).write_bytes(b'owned CPP property fixture')
    leaf='Microsoft.VCToolsVersion.'+version+'.props'
    good=auxiliary/('Build/'+version if separator=='/' else 'Build.'+version)/leaf
    good.parent.mkdir(parents=True);good.write_bytes(b'owned toolset property fixture')
    instance={'argument':vs.as_posix()+',version='+observed,'root':str(vs),'observed_version':observed}
    # Exactly the conditional construction in pinned CMakeDetermineCompilerId:
    # use the full instance string as a path before adding Build[/.]<version>.
    malformed=instance['argument']+'/VC/Auxiliary/Build'+separator+version+'/'+leaf
    prefix='<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003"><PropertyGroup Label="Globals">'
    prefix+='<VCTargetsPath>'+str(selected)+'</VCTargetsPath></PropertyGroup>'
    cpp='<Import Project="$(VCTargetsPath)\\Microsoft.Cpp.Default.props"/>'
    compiler_id_project(tmp_path,'C',(prefix+cpp+'<Import Project="'+malformed+'"/></Project>').encode())
    compiler_id_project(tmp_path,'CXX',(prefix+cpp+'<Import Project="'+good.as_posix()+'"/></Project>').encode())
    real_stat,real_lstat,real_open=Path.stat,Path.lstat,Path.open
    def guard(original):
        def call(path,*args,**kwargs):
            if ',version=' in str(path):pytest.fail('The malformed outside-root import cannot receive metadata or content access.')
            return original(path,*args,**kwargs)
        return call
    monkeypatch.setattr(Path,'stat',guard(real_stat));monkeypatch.setattr(Path,'lstat',guard(real_lstat))
    monkeypatch.setattr(Path,'open',guard(real_open))
    result=module.compiler_id_globals_context(tmp_path,properties,roots,instance)
    c,cxx=result['projects']
    assert c['imports'][0]['import_label']=='microsoft-cpp-default-props'
    assert c['imports'][0]['existence']=='regular-file-present' and c['imports'][0]['root_role']=='selected-vc-targets'
    bad=c['imports'][1];assert bad['import_label']=='mapped-toolset-version-template'
    assert bad['reviewed_version']==version and bad['contains_verified_instance_version_field'] is True
    assert bad['root_role']=='outside-declared-roots' and bad['existence']=='not-inspected'
    actual=cxx['imports'][1]
    assert actual['import_label']=='microsoft-vctools-version-props' and actual['reviewed_version']==version
    assert actual['contains_verified_instance_version_field'] is False
    assert actual['root_role']=='declared-vc-auxiliary' and actual['existence']=='regular-file-present'
    delivered=json.dumps(result)
    for private in (str(tmp_path),'private-vs',instance['argument'],observed,'owned toolset property fixture'):
        assert private not in delivered


def test_msb4019_literal_extraction_and_exact_reviewed_toolset_version_are_separate_states(module,tmp_path,monkeypatch):
    version=module.pin()['toolchain']['vc_tools_version']
    root=tmp_path/'private-vs';root.mkdir()
    instance={'argument':root.as_posix()+',version=18.11.12315.225','root':str(root),'observed_version':'18.11.12315.225'}
    monkeypatch.setattr(module,'_BUILD_INSTANCE',instance)
    target=instance['argument']+'/VC/Auxiliary/Build/'+version+'/Microsoft.VCToolsVersion.'+version+'.props'
    content='error MSB4019: The imported project "'+target+'" was not found.\n'
    content+='error MSB4019: The imported project "private/Microsoft.VCToolsVersion.14.51.999999.props" was not found.\n'
    content+='error MSB4019: private new template with unrecognized quotes\n'
    result=module.msb4019_import_context(content,{},None,16)
    known,unknown,unrecognized=result['records']
    assert known['literal_match_state']==unknown['literal_match_state']=='matched-import-template'
    assert known['import_label']=='mapped-toolset-version-template' and known['reviewed_version']==version
    assert known['contains_verified_instance_version_field'] is True
    assert unknown['import_label']=='unknown-import' and unknown['reviewed_version'] is None
    assert unknown['contains_verified_instance_version_field'] is None
    assert unrecognized['literal_match_state']=='unrecognized-template' and unrecognized['import_label']=='unknown-import'
    delivered=json.dumps(result)
    for private in ('private',str(tmp_path),'999999','18.11.12315.225',target):assert private not in delivered


@pytest.mark.parametrize('change',['argument','observed-version','root','missing-observation'])
def test_numeric_toolset_import_never_claims_verified_suffix_from_mismatched_private_instance(module,tmp_path,change):
    version=module.pin()['toolchain']['vc_tools_version'];root=tmp_path/'private-vs';root.mkdir()
    instance={'argument':root.as_posix()+',version=18.11.12315.225','root':str(root),'observed_version':'18.11.12315.225'}
    target=instance['argument']+'/VC/Auxiliary/Build/'+version+'/Microsoft.VCToolsVersion.'+version+'.props'
    if change=='argument':instance['argument']=root.as_posix()+',version=18.11.12315.226'
    elif change=='observed-version':instance['observed_version']='18.11.12315.226'
    elif change=='root':instance['root']=str(tmp_path/'private-other-vs')
    else:instance['observed_version']=None
    result=module.import_target_context(target,{},None,instance=instance)
    assert result['import_label']=='microsoft-vctools-version-props'
    assert result['contains_verified_instance_version_field'] is None and result['existence']=='not-inspected'
    assert 'private' not in json.dumps(result)


def test_generated_imports_are_bounded_and_unknown_macros_never_evaluated_or_inspected(module,tmp_path,monkeypatch):
    version=module.pin()['toolchain']['vc_tools_version'];msbuild=tmp_path/'private-msbuild';msbuild.mkdir()
    unknown=msbuild/'Microsoft.VCToolsVersion.14.51.999999.props';unknown.write_bytes(b'private unknown fixture')
    xml='<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003"><PropertyGroup Label="Globals"/>'
    xml+='<Import Project="$(privateMacro)/Microsoft.Cpp.props" Condition="private-condition"/>'
    xml+='<Import Project="'+unknown.as_posix()+'"/>'
    xml+='<Import Project="private/unknown-'+version+'.props"/></Project>'
    compiler_id_project(tmp_path,'C',xml.encode());compiler_id_project(tmp_path,'CXX',xml.encode())
    real_lstat=Path.lstat
    def lstat_guard(path,*args,**kwargs):
        if path==unknown:pytest.fail('Unreviewed numeric-version inputs remain unknown and uninspected.')
        return real_lstat(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',lstat_guard);monkeypatch.setattr(module,'COMPILER_ID_IMPORT_LIMIT',4)
    result=module.compiler_id_globals_context(tmp_path,{'VCTargetsPath':str(msbuild)},{'msbuild':str(msbuild)})
    c,cxx=result['projects'];assert len(c['imports'])==3 and len(cxx['imports'])==1
    assert c['imports_truncated'] is False and cxx['imports_truncated'] is True
    assert c['imports'][0]['existence']=='unexpanded-template' and c['imports'][0]['conditional'] is True
    assert c['imports'][1]['import_label']=='unknown-import' and c['imports'][1]['reviewed_version'] is None
    assert 'private' not in json.dumps(result) and '999999' not in json.dumps(result)


@pytest.mark.parametrize('state',['missing','different','duplicate'])
def test_generated_cpp_prefix_is_not_substituted_without_actual_literal_vctargets_match(module,tmp_path,monkeypatch,state):
    desired=tmp_path/'private-configured-targets';desired.mkdir()
    target=desired/'Microsoft.Cpp.props';target.write_bytes(b'private target fixture')
    property_xml='' if state=='missing' else '<VCTargetsPath>private-different-root</VCTargetsPath>'
    if state=='duplicate':property_xml=('<VCTargetsPath>'+str(desired)+'</VCTargetsPath>')*2
    xml='<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003"><PropertyGroup Label="Globals">'
    xml+=property_xml+'</PropertyGroup><Import Project="$(VCTargetsPath)\\Microsoft.Cpp.props"/></Project>'
    compiler_id_project(tmp_path,'C',xml.encode())
    real_lstat=Path.lstat
    def guard(path,*args,**kwargs):
        if path==desired or desired in path.parents:pytest.fail('Unmatched actual Globals cannot select a target for inspection.')
        return real_lstat(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',guard)
    result=module.compiler_id_globals_context(tmp_path,{'VCTargetsPath':str(desired)},{'msbuild':str(desired)})
    record=result['projects'][0]['imports'][0]
    assert record['import_label']=='microsoft-cpp-props' and record['existence']=='unexpanded-template'
    assert record['root_role']=='not-inspected' and 'private' not in json.dumps(result)


def alias_mapping_inputs(module,tmp_path,layout='/'):
    version=module.pin()['toolchain']['vc_tools_version'];alias='14.51.18.0'
    root=tmp_path/'private-vs';aux=root/'VC/Auxiliary'
    directory=aux/('Build/'+alias if layout=='/' else 'Build.'+alias);directory.mkdir(parents=True)
    metadata=directory/('Microsoft.VCToolsVersion.'+alias+'.txt')
    props=directory/('Microsoft.VCToolsVersion.'+alias+'.props')
    metadata.write_bytes((version+'\r\n').encode());props.write_bytes(b'owned auxiliary props fixture\n')
    index={p.relative_to(aux).as_posix():module.attributes(p.read_bytes()) for p in (metadata,props)}
    instance={'root':str(root),'argument':root.as_posix()+',version=18.11.12315.225',
        'observed_version':'18.11.12315.225'}
    value=instance['argument']+'/VC/Auxiliary/Build/'+alias+'/Microsoft.VCToolsVersion.'+alias+'.props'
    return version,alias,aux,metadata,props,index,instance,value


@pytest.mark.parametrize('layout',['/','.'])
def test_actual_alias_template_is_bound_to_initial_auxiliary_members_and_exact_policy_without_alias_disclosure(module,tmp_path,monkeypatch,layout):
    version,alias,aux,metadata,props,index,instance,value=alias_mapping_inputs(module,tmp_path,layout)
    prefix='<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003"><PropertyGroup Label="Globals"/>'
    compiler_id_project(tmp_path,'C',(prefix+'<Import Project="'+value+'"/></Project>').encode())
    real_lstat=Path.lstat
    def guard(path,*args,**kwargs):
        if ',version=' in str(path):pytest.fail('Only corrected members under the declared Auxiliary root may be inspected.')
        return real_lstat(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',guard)
    result=module.compiler_id_globals_context(tmp_path,{}, {'vc-auxiliary':str(aux)},instance,{'vc-auxiliary':index})
    record=result['projects'][0]['imports'][0]
    assert record['import_label']=='mapped-toolset-version-template' and record['reviewed_version']==version
    assert record['contains_verified_instance_version_field'] is True and record['root_role']=='outside-declared-roots'
    assert record['existence']=='not-inspected'
    assert record['toolset_mapping']=={'relationship':'verified-toolset-alias','matched_candidate_count':1,
        'matches_policy':True,'member_exists_state':'regular-files-present'}
    delivered=json.dumps(result)
    for private in (alias,str(tmp_path),str(metadata),str(props),instance['argument'],
            module.sha(metadata.read_bytes()),module.sha(props.read_bytes())):
        assert private not in delivered


@pytest.mark.parametrize('change,relationship,matches',[
    ('metadata-changed','sealed-member-changed',None),('props-changed','sealed-member-changed',None),
    ('different-policy','different-policy-version',False),('missing-member','unavailable-sealed-member',None),
    ('missing-props-seal','incomplete-or-unbounded-sealed-pair',None),
    ('unknown-layout','no-sealed-alias-candidate',None),('wrong-declared-root','declared-root-mismatch',None),
    ('missing-initial-seal','initial-seal-unavailable',None)])
def test_alias_mapping_cannot_replace_initial_source_binding_or_exact_metadata_policy(module,tmp_path,change,relationship,matches):
    version,alias,aux,metadata,props,index,instance,value=alias_mapping_inputs(module,tmp_path)
    roots={'vc-auxiliary':str(aux)};initial={'vc-auxiliary':index}
    if change=='metadata-changed':metadata.write_bytes(b'private changed metadata\n')
    elif change=='props-changed':props.write_bytes(b'private changed props\n')
    elif change=='different-policy':
        metadata.write_bytes(b'14.51.999999\r\n');index[metadata.relative_to(aux).as_posix()]=module.attributes(metadata.read_bytes())
    elif change=='missing-member':metadata.unlink()
    elif change=='missing-props-seal':del index[props.relative_to(aux).as_posix()]
    elif change=='unknown-layout':initial={'vc-auxiliary':{'private/../unknown.txt':module.attributes(b'private')}}
    elif change=='wrong-declared-root':roots={'vc-auxiliary':str(tmp_path/'private-other-auxiliary')}
    else:initial=None
    result=module.import_target_context(value,roots,{},instance=instance,initial_seal=initial)
    mapping=result['toolset_mapping']
    assert result['import_label']=='mapped-toolset-version-template' and result['contains_verified_instance_version_field'] is True
    assert mapping['relationship']==relationship and mapping['matches_policy'] is matches
    assert mapping['matched_candidate_count']==0
    if change=='props-changed':assert mapping['member_exists_state']=='regular-member-observed'
    if change=='metadata-changed':assert mapping['member_exists_state']=='size-limit'
    for private in (alias,str(tmp_path),'private','999999'):
        assert private not in json.dumps(result)


def test_alias_mapping_candidate_and_byte_limits_are_checked_before_native_member_access(module,tmp_path,monkeypatch):
    version,alias,aux,metadata,props,index,instance,value=alias_mapping_inputs(module,tmp_path)
    alternate=aux/('Build.'+alias);alternate.mkdir()
    for original in (metadata,props):
        target=alternate/original.name;target.write_bytes(original.read_bytes())
        index[target.relative_to(aux).as_posix()]=module.attributes(target.read_bytes())
    roots={'vc-auxiliary':str(aux)};initial={'vc-auxiliary':index}
    expected=sum(record['bytes']+1 for record in index.values())
    monkeypatch.setattr(module,'AUX_MAPPING_TOTAL_BYTES',expected)
    result=module.import_target_context(value,roots,{},instance=instance,initial_seal=initial)
    assert result['toolset_mapping']['relationship']=='ambiguous-toolset-alias'
    assert result['toolset_mapping']['matched_candidate_count']==2
    real_reader=module.diagnostic_file
    def forbidden(*_args,**_kwargs):pytest.fail('Over-limit mapping must not read a member.')
    monkeypatch.setattr(module,'diagnostic_file',forbidden)
    monkeypatch.setattr(module,'AUX_MAPPING_TOTAL_BYTES',expected-1)
    assert module.import_target_context(value,roots,{},instance=instance,initial_seal=initial)['toolset_mapping']['relationship']=='byte-limit'
    monkeypatch.setattr(module,'AUX_MAPPING_TOTAL_BYTES',expected)
    monkeypatch.setattr(module,'AUX_MAPPING_CANDIDATE_LIMIT',1)
    assert module.import_target_context(value,roots,{},instance=instance,initial_seal=initial)['toolset_mapping']['relationship']=='candidate-limit'
    monkeypatch.setattr(module,'AUX_MAPPING_CANDIDATE_LIMIT',32)
    monkeypatch.setattr(module,'AUX_SEAL_ENTRY_LIMIT',1)
    assert module.import_target_context(value,roots,{},instance=instance,initial_seal=initial)['toolset_mapping']['relationship']=='initial-seal-limit'
    monkeypatch.setattr(module,'AUX_SEAL_ENTRY_LIMIT',50000)
    monkeypatch.setattr(module,'AUX_MAPPING_FILE_BYTES',1)
    assert module.import_target_context(value,roots,{},instance=instance,initial_seal=initial)['toolset_mapping']['relationship']=='incomplete-or-unbounded-sealed-pair'
    monkeypatch.setattr(module,'diagnostic_file',real_reader)


@pytest.mark.parametrize('kind',['symlink','windows-reparse'])
def test_alias_mapping_rejects_linked_corrected_member_ancestor_before_leaf_metadata_or_read(module,tmp_path,monkeypatch,kind):
    version,alias,aux,metadata,props,index,instance,value=alias_mapping_inputs(module,tmp_path)
    directory=metadata.parent;real_lstat,real_stat,real_open=Path.lstat,Path.stat,Path.open
    def reject(path):
        if path!=directory and directory in path.parents:pytest.fail('Linked Auxiliary ancestor must precede corrected member metadata/read.')
    def lstat_guard(path,*args,**kwargs):
        reject(path)
        if path==directory:return SimpleNamespace(st_mode=module.stat.S_IFLNK if kind=='symlink' else module.stat.S_IFDIR,
            st_file_attributes=0x400 if kind=='windows-reparse' else 0)
        return real_lstat(path,*args,**kwargs)
    def stat_guard(path,*args,**kwargs):reject(path);return real_stat(path,*args,**kwargs)
    def open_guard(path,*args,**kwargs):reject(path);return real_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',lstat_guard);monkeypatch.setattr(Path,'stat',stat_guard);monkeypatch.setattr(Path,'open',open_guard)
    result=module.import_target_context(value,{'vc-auxiliary':str(aux)},{},instance=instance,initial_seal={'vc-auxiliary':index})
    assert result['toolset_mapping']['relationship']=='unavailable-sealed-member'
    assert result['toolset_mapping']['member_exists_state']=='inspection-error'
    assert alias not in json.dumps(result) and str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize('directory_alias,file_alias',[
    ('99.99','99.99'),('14','14'),('14.51.1.2.3','14.51.1.2.3'),('14.51.18.0','14.51.19.0')])
def test_new_unknown_numeric_layouts_cannot_become_mapped_policy_evidence(module,tmp_path,monkeypatch,directory_alias,file_alias):
    root=tmp_path/'private-vs';root.mkdir()
    instance={'argument':root.as_posix()+',version=18.11.12315.225','root':str(root),'observed_version':'18.11.12315.225'}
    value=instance['argument']+'/VC/Auxiliary/Build/'+directory_alias+'/Microsoft.VCToolsVersion.'+file_alias+'.props'
    def forbidden(*_args,**_kwargs):pytest.fail('Unknown numeric layouts cannot request corrected-member inspection.')
    monkeypatch.setattr(module,'diagnostic_file',forbidden)
    result=module.import_target_context(value,{},None,instance=instance,initial_seal={})
    assert result['import_label']=='unknown-import' and result['toolset_mapping'] is None
    for private in (str(tmp_path),directory_alias,file_alias):assert private not in json.dumps(result)


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
