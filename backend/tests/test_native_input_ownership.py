"""Exact-byte attribution and privacy boundaries, without native execution."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend.r19_acceptance import candidate
from backend.tests.test_runtime_experiment import recorder


def component(name, checksum):
    return {'name': name, 'version': '1.0', 'artifact': {'sha256': 'a' * 64},
        'installed_files': [{'path': 'Lib/site-packages/owned/Library.dll', 'sha256': checksum}]}


def row(path, checksum):
    return {'path': path, 'sha256': checksum, 'bytes': 10}


def report(monkeypatch, components, resources, files):
    recorder(monkeypatch)
    from native_ownership import native_input_ownership
    return native_input_ownership(components, resources, files)


def test_output_path_and_filename_do_not_override_exact_input_bytes(monkeypatch):
    checksum = 'b' * 64
    files = [row('_internal/renamed.dll', checksum), row('asr/_internal/renamed.dll', checksum),
        row('_internal/Library.dll', 'c' * 64), row('ProxyTranscriptRuntime.exe', 'd' * 64)]
    result = report(monkeypatch, [component('owned', checksum)], [], files)
    assert result['counts'] == {'exact': 2, 'ambiguous': 0, 'unmatched': 1, 'generated': 1}
    for entry in result['files']:
        if entry['status'] == 'exact':
            assert entry['inputs'] == [{'kind': 'component', 'component': 'owned', 'version': '1.0',
                'artifact_sha256': 'a' * 64, 'input_path': 'Lib/site-packages/owned/Library.dll', 'input_sha256': checksum}]
        else: assert entry['inputs'] == []
    assert result['native_closure'] == 'unverified' and result['production_execution_allowed'] is False


def test_identical_component_or_resource_inputs_stay_ambiguous_and_deterministic(monkeypatch):
    checksum = 'b' * 64
    resources = [{'path': 'codecs/xiph-flac/FLAC.dll', 'sha256': checksum, 'version': '1.5.0',
        'source': 'https://github.com/xiph/flac/releases/tag/1.5.0'}]
    components = [component('second', checksum), component('first', checksum)]
    files = [row('_internal/codecs/xiph-flac/FLAC.dll', checksum)]
    result = report(monkeypatch, components, resources, files)
    assert result == report(monkeypatch, list(reversed(components)), resources, files)
    entry = result['files'][0]
    assert entry['status'] == 'ambiguous' and len(entry['inputs']) == 3
    assert entry['inputs'][-1]['kind'] == 'resource'
    assert entry['inputs'][-1]['input_path'] == 'codecs/xiph-flac/FLAC.dll'
    assert entry['inputs'][-1]['source'] == resources[0]['source']


@pytest.mark.parametrize('version', ['1.0+cpu.build-7', '25.12.19+local.1', 'supplier release 2026-10-30'])
def test_exact_local_versions_and_resource_release_labels_remain_intact(monkeypatch, version):
    checksum = 'b' * 64
    entry = component('owned', checksum); entry['version'] = version
    resources = [{'path': 'helpers/nte/owned.dll', 'version': version, 'sha256': checksum,
        'source': 'https://github.com/owned/project/tree/abc123'}]
    result = report(monkeypatch, [entry], resources, [row('_internal/owned.dll', checksum)])
    assert [match['version'] for match in result['files'][0]['inputs']] == [version, version]


def test_private_paths_repr_and_unused_input_fields_are_never_copied(tmp_path, monkeypatch):
    checksum = 'b' * 64
    private = str(tmp_path / 'private-profile' / 'credential-store')
    entry = component('owned', checksum)
    entry.update(source=private, diagnostics=SimpleNamespace(private_path=private))
    entry['artifact']['path'] = private
    entry['installed_files'][0]['private_diagnostic'] = repr(SimpleNamespace(path=private))
    resource = {'path': 'helpers/nte/owned.dll', 'version': '1.0', 'sha256': checksum,
        'source': 'https://github.com/owned/project/tree/abc123', 'license_expression': private,
        'diagnostic_source': private}
    text = json.dumps(report(monkeypatch, [entry], [resource], [row('_internal/owned.dll', checksum)]))
    assert private not in text and str(tmp_path) not in text and 'private_diagnostic' not in text
    entry['installed_files'][0]['path'] = private
    with pytest.raises(ValueError) as error:
        report(monkeypatch, [entry], [], [row('_internal/owned.dll', checksum)])
    assert private not in str(error.value) and private not in repr(error.value)
    entry['installed_files'][0]['path'] = 'Lib/site-packages/owned/Library.dll'
    resource['source'] = private
    with pytest.raises(ValueError) as error:
        report(monkeypatch, [entry], [resource], [row('_internal/owned.dll', checksum)])
    assert private not in str(error.value) and private not in repr(error.value)


def test_additive_report_preserves_exact_files_entry_schema_and_existing_candidate_reader(monkeypatch):
    files = [row('_internal/owned.dll', 'b' * 64), row('readme.txt', 'c' * 64)]
    original = deepcopy(files)
    ownership = report(monkeypatch, [component('owned', 'b' * 64)], [], files)
    inventory = {'schema': 'proxy-r19-runtime-inventory-v1', 'profile': 'runtime-experiment',
        'source_commit': 'a' * 40, 'build_id': 'authored-attribution', 'files': files,
        'file_count': len(files), 'bytes': 20, 'native_input_ownership': ownership}
    data = json.dumps(inventory).encode()
    identity, parsed = candidate(data)
    assert files == original and all(set(entry) == {'path', 'sha256', 'bytes'} for entry in files)
    assert identity['inventory_sha256'] == hashlib.sha256(data).hexdigest()
    assert parsed['native_input_ownership']['files'][0]['status'] == 'exact'


@pytest.mark.parametrize('control', ['\t', '\r', '\n', '\x00', '\x1f', '\x7f'])
def test_public_source_rejects_original_controls_before_url_normalization(monkeypatch, control):
    resource = {'path': 'helpers/nte/owned.dll', 'version': '1.0', 'sha256': 'b' * 64,
        'source': 'https://github.com/owned/' + control + 'private-fixture'}
    with pytest.raises(ValueError) as error:
        report(monkeypatch, [], [resource], [row('_internal/owned.dll', 'b' * 64)])
    assert 'private-fixture' not in str(error.value) and resource['source'] not in repr(error.value)


def test_malformed_public_source_parser_error_never_exposes_private_netloc(monkeypatch):
    # urllib rejects this netloc during NFKC validation and includes its raw
    # spelling in its own error. Public attribution must replace that message.
    resource = {'path': 'helpers/nte/owned.dll', 'version': '1.0', 'sha256': 'b' * 64,
        'source': 'https://private-fixture\u2100github.com/source'}
    with pytest.raises(ValueError) as error:
        report(monkeypatch, [], [resource], [row('_internal/owned.dll', 'b' * 64)])
    assert 'private-fixture' not in str(error.value) and 'private-fixture' not in repr(error.value)
    assert error.value.__cause__ is None and error.value.__suppress_context__ is True
