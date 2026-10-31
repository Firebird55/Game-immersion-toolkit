"""Real authored PE review through finalization, not native source/load proof."""
import hashlib
import importlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.tests.test_native_images import authored_pe, candidate


@pytest.fixture
def collection(candidate, monkeypatch):
    root, path, inventory = candidate
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'packaging/runtime-bundle'))
    closure = importlib.import_module('closure')
    images = importlib.import_module('native_images')
    output = root.parent / 'quarantine'; output.mkdir()
    target = output / 'ProxyTranscriptRuntime'; root.rename(target)
    manifest = output / 'RUNTIME-INVENTORY.json'; path.rename(manifest)
    value = {key: inventory[key] for key in ('profile', 'source_commit', 'build_id')}
    value.update(components=[], resources=[])
    return SimpleNamespace(root=target, manifest=manifest, inventory=inventory, output=output,
        value=value, closure=closure, images=images)


def save(collection):
    collection.inventory['bytes'] = sum(item['bytes'] for item in collection.inventory['files'])
    collection.manifest.write_text(json.dumps(collection.inventory), encoding='utf-8')


def failure(collection):
    raw = (collection.output / 'NATIVE-IMAGES-FAILED.json').read_bytes()
    result = json.loads(raw)
    assert set(result) == {'schema', 'source_commit', 'build_id', 'profile', 'status', 'phase', 'failure_code',
        'native_closure', 'rights_review', 'source_delivery_approved', 'production_execution_allowed',
        'native_windows_11_acceptance', 'r19_complete', 'installer', 'raw_paths_published',
        'raw_exceptions_published', 'raw_imports_published', 'diagnostic'}
    assert result['schema'] == 'proxy-r19-native-images-failure-v1' and result['status'] == 'failed'
    assert result['phase'] == 'finalize' and result['rights_review'] == 'pending-exact-output'
    assert result['native_closure'] == 'unverified' and result['native_windows_11_acceptance'] == 'unavailable'
    assert all(result[key] is False for key in ('source_delivery_approved', 'production_execution_allowed',
        'r19_complete', 'raw_paths_published', 'raw_exceptions_published', 'raw_imports_published'))
    assert str(collection.output) not in raw.decode() and 'PRIVATE' not in raw.decode()
    assert not (collection.output / 'NATIVE-IMAGES.json').exists()
    return result


def test_real_parser_observation_is_bound_to_written_inventory_outside_application(collection, monkeypatch):
    case = collection; calls = []; actual = case.images.inspect_pe
    def inspect(raw):
        result = actual(raw); calls.append(result['architecture']); return result
    monkeypatch.setattr(case.images, 'inspect_pe', inspect)
    report = case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert len(calls) == 4 and 'anycpu' in calls
    assert json.loads((case.output / 'NATIVE-IMAGES.json').read_bytes()) == report
    assert report['inventory'] == {'bytes': case.manifest.stat().st_size,
        'sha256': hashlib.sha256(case.manifest.read_bytes()).hexdigest()}
    assert report['status'] == 'observed-not-approved' and report['production_execution_allowed'] is False
    assert {row['tree'] for row in report['files']} == {'main', 'asr'}
    assert not (case.root / 'NATIVE-IMAGES.json').exists()
    assert not (case.output / 'NATIVE-IMAGES-FAILED.json').exists()


def test_write_candidate_mandatorily_runs_real_image_review_after_inventory_and_asr_relocation(collection, monkeypatch):
    case = collection
    case.manifest.unlink()
    (case.root / 'asr').rename(case.output / 'ProxyTranscriptAsr')
    source = case.output.parent / 'source'; source.mkdir()
    (source / 'package.json').write_text('{"version":"0.0.1"}')
    evidence = case.output.parent / 'evidence'; evidence.mkdir()
    def codec_not_tested(_value, _source, _evidence, output):
        assert not (output / 'ProxyTranscriptRuntime/_internal/codecs').exists()
    def source_provenance_not_tested(_value, _evidence, _output, files, _manifest):
        assert any(Path(row['path']).suffix == '.exe' for row in files)
        return {'schema': 'authored-p1-source-stub-v1', 'status': 'source-provenance-not-tested',
            'production_execution_allowed': False, 'r19_complete': False}
    monkeypatch.setattr(case.closure, 'validate_codec_output', codec_not_tested)
    monkeypatch.setattr(case.closure, 'validate_native_collection', source_provenance_not_tested)
    actual = case.images.inspect_pe; calls = []
    def inspect(raw):
        assert case.manifest.is_file(), 'The existing final inventory must be written first'
        assert (case.root / 'asr/ProxyTranscriptAsr.exe').is_file(), 'Use the existing relocated ASR tree'
        result = actual(raw); calls.append(result['implementation']); return result
    monkeypatch.setattr(case.images, 'inspect_pe', inspect)
    case.closure.write_candidate(case.value, source, evidence, case.output)
    report = json.loads((case.output / 'NATIVE-IMAGES.json').read_bytes())
    assert len(calls) == 4 and report['file_count'] == 4
    assert report['inventory']['sha256'] == hashlib.sha256(case.manifest.read_bytes()).hexdigest()
    assert json.loads((case.output / 'NATIVE-COLLECTION.json').read_bytes())['status'] == 'source-provenance-not-tested'
    inventory = json.loads(case.manifest.read_bytes())
    assert all(set(row) == {'path', 'bytes', 'sha256'} for row in inventory['files'])
    assert not any('NATIVE-IMAGES' in row['path'] for row in inventory['files'])


@pytest.mark.parametrize('kind,code', [('x86', 'unsupported-architecture'), ('malformed', 'malformed-pe')])
def test_bad_image_refuses_with_fixed_metadata_and_no_success_sidecar(collection, kind, code):
    case = collection
    raw = authored_pe(machine=0x14c, plus=False, dll=False) if kind == 'x86' else b'PRIVATE native contents C:\\PRIVATE\\data'.ljust(128, b'X')
    target = case.root / 'ProxyTranscriptRuntime.exe'; target.write_bytes(raw)
    case.inventory['files'][0].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()); save(case)
    with pytest.raises(case.closure.ClosureError, match=code) as error:
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert error.value.__suppress_context__ is True and 'PRIVATE' not in str(error.value)
    assert failure(case)['failure_code'] == code


@pytest.mark.parametrize('target,tree,role,ordinal,count', [
    ('ProxyTranscriptRuntime.exe', 'main', 'runtime-primary', 1, 4),
    ('asr/ProxyTranscriptAsr.exe', 'asr', 'asr-primary', 3, 4),
    ('asr/_internal/engine.pyd', 'asr', 'other-native', 4, 4),
    ('_internal/helpers/nte/ToolkitReader.dll', 'main', 'helper', 3, 5),
])
def test_real_import_refusal_locates_selected_native_without_publishing_names_or_bytes(collection, target, tree, role, ordinal, count):
    case = collection; raw = authored_pe(dll=target.endswith(('.dll', '.pyd')), delayed=('PRIVATE name.dll',))
    path = case.root / target; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    row = {'path': target, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    old = next((item for item in case.inventory['files'] if item['path'] == target), None)
    if old is not None: old.update(row)
    else:
        case.inventory['files'].append(row); case.inventory['file_count'] += 1
        case.inventory['directories'] = sorted(set(case.inventory['directories']) |
            {parent.as_posix() for parent in Path(target).parents if parent != Path('.')})
    save(case)
    with pytest.raises(case.closure.ClosureError, match='invalid-import'):
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    report = failure(case)
    assert report['diagnostic'] == {'status': 'available',
        'selected_native': {'ordinal': ordinal, 'count': count, 'tree': tree, 'role': role},
        'imports': {'import_table': 'delay', 'import_phase': 'name', 'import_reason': 'name-format'}}
    encoded = json.dumps(report)
    assert target not in encoded and 'ToolkitReader' not in encoded and 'optional.dll' not in encoded
    assert len(encoded.encode('utf-8')) < 2048


@pytest.mark.parametrize('section,key,value', [
    ('selected', 'ordinal', True), ('selected', 'ordinal', 0), ('selected', 'ordinal', 5),
    ('selected', 'count', 20001), ('selected', 'count', 1), ('selected', 'count', False), ('selected', 'count', '4'),
    ('selected', 'tree', 'PRIVATE'), ('selected', 'tree', []), ('selected', 'role', 'PRIVATE'),
    ('selected', 'role', 'asr-primary'), ('selected', 'PRIVATE', 'PRIVATE'),
    ('context', 'import_table', 'PRIVATE'), ('context', 'import_phase', 'PRIVATE'),
    ('context', 'import_reason', 'PRIVATE'), ('context', 'import_reason', ['PRIVATE']),
    ('context', 'import_reason', 'missing-terminator'), ('context', 'PRIVATE', 'PRIVATE'),
    ('context', 'import_table', None), ('context', 'import_phase', []),
])
def test_failure_projector_refuses_mutated_unknown_or_mismatched_diagnostic_fields(collection, monkeypatch, section, key, value):
    case = collection
    def refuse(*_args):
        error = case.images.NativeImageError('invalid-import')
        error.selected = {'ordinal': 1, 'count': 4, 'tree': 'main', 'role': 'runtime-primary'}
        error.context = {'import_table': 'normal', 'import_phase': 'name', 'import_reason': 'name-format'}
        getattr(error, section)[key] = deepcopy(value)
        error.private_path = str(case.root)
        raise error
    monkeypatch.setattr(case.images, 'review_native_images', refuse)
    with pytest.raises(case.closure.ClosureError, match='invalid-import'):
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert failure(case)['diagnostic'] == {'status': 'unavailable'}


@pytest.mark.parametrize('change', ['missing-selected', 'missing-context', 'selected-list', 'context-list',
    'normal-delay-attributes', 'asr-runtime-primary', 'selected-missing-key', 'context-missing-key', 'wrong-reason-code'])
def test_partial_diagnostic_and_cross_field_conflicts_are_unavailable(collection, monkeypatch, change):
    case = collection
    def refuse(*_args):
        error = case.images.NativeImageError('invalid-import')
        error.selected = {'ordinal': 1, 'count': 4, 'tree': 'main', 'role': 'runtime-primary'}
        error.context = {'import_table': 'normal', 'import_phase': 'name', 'import_reason': 'name-format'}
        if change == 'missing-selected': error.selected = None
        elif change == 'missing-context': error.context = None
        elif change == 'selected-list': error.selected = ['PRIVATE']
        elif change == 'context-list': error.context = ['PRIVATE']
        elif change == 'normal-delay-attributes': error.context.update(import_phase='descriptor', import_reason='delay-attributes')
        elif change == 'asr-runtime-primary': error.selected['tree'] = 'asr'
        elif change == 'selected-missing-key': del error.selected['ordinal']
        elif change == 'wrong-reason-code': error.code = 'malformed-pe'
        else: del error.context['import_phase']
        raise error
    monkeypatch.setattr(case.images, 'review_native_images', refuse)
    with pytest.raises(case.closure.ClosureError, match='malformed-pe' if change == 'wrong-reason-code' else 'invalid-import'):
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert failure(case)['diagnostic'] == {'status': 'unavailable'}


def test_diagnostic_projection_failure_preserves_fixed_refusal_and_sanitized_metadata(collection, monkeypatch):
    case = collection
    def refuse(*_args): raise case.images.NativeImageError('invalid-import')
    def broken(*_args): raise OSError('PRIVATE diagnostic ' + str(case.root))
    monkeypatch.setattr(case.images, 'review_native_images', refuse)
    monkeypatch.setattr(case.closure, '_native_image_diagnostic', broken)
    with pytest.raises(case.closure.ClosureError, match='invalid-import') as error:
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert 'PRIVATE' not in str(error.value)
    assert failure(case)['diagnostic'] == {'status': 'unavailable'}


def test_build_identity_mismatch_refuses_without_copying_arbitrary_inventory_fields(collection):
    case = collection
    case.inventory['build_id'] = 'another-build'
    case.inventory['PRIVATE'] = str(case.root)
    save(case)
    with pytest.raises(case.closure.ClosureError, match='invalid-inventory'):
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert failure(case)['build_id'] == case.value['build_id']


@pytest.mark.parametrize('malicious_code', [None, 'PRIVATE', ['PRIVATE']])
def test_unknown_parser_exceptions_and_mutated_error_fields_never_escape_failure_projection(collection, monkeypatch, malicious_code):
    case = collection
    def refuse(*_args):
        error = case.images.NativeImageError('malformed-pe')
        error.code = malicious_code
        error.private_path = str(case.root)
        raise error
    monkeypatch.setattr(case.images, 'review_native_images', refuse)
    with pytest.raises(case.closure.ClosureError, match='observation-failed'):
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert failure(case)['failure_code'] == 'observation-failed'


def test_metadata_channel_failure_cannot_become_success_or_print_raw_error(collection, monkeypatch):
    case = collection; runtime = importlib.import_module('record_runtime'); actual = runtime.write_native_json
    def unavailable(root, name, value):
        if name == 'NATIVE-IMAGES.json': raise OSError('PRIVATE metadata channel ' + str(root))
        return actual(root, name, value)
    monkeypatch.setattr(runtime, 'write_native_json', unavailable)
    with pytest.raises(case.closure.ClosureError, match='observation-failed') as error:
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert 'PRIVATE' not in str(error.value)
    assert failure(case)['failure_code'] == 'observation-failed'


def test_unsafe_report_root_preserves_unrelated_tree_even_during_failure_recording(collection):
    case = collection; outside = case.output.with_name('unrelated-report-root')
    case.output.rename(outside)
    before = {path.relative_to(outside).as_posix(): path.read_bytes() for path in outside.rglob('*') if path.is_file()}
    try: case.output.symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip('This host cannot create the authored report-root link.')
    with pytest.raises(case.closure.ClosureError, match='observation-failed'):
        case.closure.validate_native_images(case.value, case.output, case.inventory)
    assert {path.relative_to(outside).as_posix(): path.read_bytes() for path in outside.rglob('*') if path.is_file()} == before


def test_workflow_admits_only_fixed_image_metadata_names_and_runs_both_contract_modules():
    source = (Path(__file__).resolve().parents[2] / '.github/workflows/r19-runtime-experiment.yml').read_text()
    assert "'native_images', 'native_image_collection'" in source
    refusal = source.split('- name: Retain only sanitized native image refusal', 1)[1].split('- name:', 1)[0]
    assert 'if: ${{ failure() }}' in refusal
    paths = [line.strip()[6:] for line in refusal.splitlines() if line.strip().startswith('path: ')]
    assert paths == ['output/runtime-bundle/quarantine/NATIVE-IMAGES-FAILED.json']
    earlier = source.split('- name: Retain completed observations before native image refusal', 1)[1].split('- name:', 1)[0]
    assert "if: ${{ failure() && hashFiles('output/runtime-bundle/quarantine/NATIVE-IMAGES-FAILED.json') != '' }}" in earlier
    assert 'name: r19-failed-run-observed-not-approved-native-metadata' in earlier
    paths = [line.strip() for line in earlier.split('path: |', 1)[1].split('if-no-files-found:', 1)[0].splitlines() if line.strip()]
    assert paths == ['output/runtime-bundle/quarantine/RUNTIME-INVENTORY.json',
        'output/runtime-bundle/quarantine/NATIVE-COLLECTION-INPUTS.json',
        'output/runtime-bundle/quarantine/NATIVE-COLLECTION.json']
    assert '*' not in earlier and '.zip' not in earlier and '.log' not in earlier
    metadata = source.split('name: r19-integrated-runtime-metadata', 1)[1].split('if-no-files-found:', 1)[0]
    assert 'output/runtime-bundle/quarantine/NATIVE-IMAGES.json' in metadata
    assert '*.' not in metadata and '**' not in metadata
