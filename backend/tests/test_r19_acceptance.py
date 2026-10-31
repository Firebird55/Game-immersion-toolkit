"""Receipt-integrity/scope failures, not simulated native acceptance passes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from backend.r19_acceptance import AcceptanceError, COMPONENT_GATES, OPERATIONS, candidate, decode, review, template


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def fixture(tmp_path, *, approved=True):
    inventory = encoded({'schema': 'proxy-r19-runtime-inventory-v1', 'profile': 'runtime-experiment',
        'source_commit': 'a'*40, 'build_id': 'owned-candidate', 'file_count': 1, 'bytes': 12,
        'files': [{'path': 'owned.exe', 'sha256': 'b'*64, 'bytes': 12}],
        'gates': {key: 'approved' if approved else 'pending' for key in COMPONENT_GATES}})
    identity, _ = candidate(inventory)
    manifest = template(inventory)
    receipts = {}
    environment = {'os': 'windows-client', 'release': '11', 'display_version': '25H2', 'build': 26200,
        'architecture': 'x64', 'elevated': False, 'developer_tools': [], 'interactive': True,
        'physical_display': True, 'environment_id': 'c'*64,
        'browser_profiles': {'chromium': 'ordinary-selected', 'firefox': 'ordinary-selected'}}
    sample = {'environment_id': 'c'*64, 'cold_start_ms': 1200, 'warm_start_ms': [100, 105, 99, 103, 101],
        'first_caption_ms': 1400, 'peak_private_bytes': 4096, 'peak_rss_bytes': 8192, 'cpu_ms': 10,
        'idle_cpu_ms': 1, 'idle_seconds': 60, 'extracted_bytes': 12, 'compressed_bytes': 10,
        'peak_prepare_bytes': 100, 'peak_failed_update_bytes': 110, 'recovery_ms': 500}
    for row, operations in OPERATIONS.items():
        value = {'schema': 'proxy-r19-acceptance-receipt-v1', **identity, 'row': row, 'status': 'passed',
            'method': 'native-client', 'operations': {key: 'passed' for key in operations},
            'environment': deepcopy(environment), 'live_accounts_accessed': False, 'real_data_modified': False,
            'measurements': {'source': deepcopy(sample), 'candidate': deepcopy(sample),
                'signature': 'not-signed', 'attestation': 'not-attested'} if row == 'baseline_delivery' else None}
        receipts[row] = value
        save(tmp_path, manifest, row, value)
    return inventory, manifest, receipts


def save(root, manifest, row, receipt):
    data = encoded(receipt); name = row+'.json'; (root/name).write_bytes(data)
    manifest['rows'][row] = {'status': 'passed', 'receipts': [{'path': name, 'sha256': hashlib.sha256(data).hexdigest()}]}


def test_consistent_complete_claims_still_cannot_enable_runtime_or_grant_acceptance(tmp_path):
    inventory, manifest, _ = fixture(tmp_path)
    result = review(inventory, manifest, tmp_path)
    assert result['ready_for_independent_acceptance_review'] is True
    assert result['production_execution_allowed'] is False and result['r19_complete'] is False
    assert result['installer'] == 'not-built' and 'not proof of execution' in result['evidence_level']
    assert 'environment' not in encoded(result).decode() and '26200' not in encoded(result).decode()


def test_pending_component_rights_and_any_unavailable_row_block_review_readiness(tmp_path):
    inventory, manifest, _ = fixture(tmp_path, approved=False)
    result = review(inventory, manifest, tmp_path)
    assert result['required_row_coverage_complete'] is True
    assert result['ready_for_independent_acceptance_review'] is False
    manifest['rows']['data_origin'] = {'status': 'unavailable', 'receipts': []}
    assert review(inventory, manifest, tmp_path)['required_row_coverage_complete'] is False
    assert set(template(inventory)['rows']) == set(OPERATIONS)
    assert all(r['status'] == 'unavailable' for r in template(inventory)['rows'].values())


@pytest.mark.parametrize('field,value', [('source_commit', 'd'*40), ('build_id', 'different'), ('inventory_sha256', 'd'*64)])
def test_mixed_or_stale_candidate_receipts_fail_even_when_rehashed(tmp_path, field, value):
    inventory, manifest, receipts = fixture(tmp_path)
    receipts['native_ocr_capture'][field] = value; save(tmp_path, manifest, 'native_ocr_capture', receipts['native_ocr_capture'])
    with pytest.raises(AcceptanceError, match='another candidate'): review(inventory, manifest, tmp_path)


@pytest.mark.parametrize('field,value', [('os', 'windows-server'), ('architecture', 'arm64'), ('display_version', '24H2'),
    ('build', 26100), ('elevated', True), ('developer_tools', ['python']), ('physical_display', False), ('interactive', False)])
def test_server_arm64_developer_and_noninteractive_claims_cannot_prove_native_acceptance(tmp_path, field, value):
    inventory, manifest, receipts = fixture(tmp_path)
    receipts['native_ocr_capture']['environment'][field] = value
    save(tmp_path, manifest, 'native_ocr_capture', receipts['native_ocr_capture'])
    with pytest.raises(AcceptanceError, match='Windows 11'): review(inventory, manifest, tmp_path)


@pytest.mark.parametrize('method', ['mocked', 'source-only', 'authored-native'])
def test_mock_or_source_receipt_does_not_replace_client_execution(tmp_path, method):
    inventory, manifest, receipts = fixture(tmp_path)
    receipts['data_origin']['method'] = method; save(tmp_path, manifest, 'data_origin', receipts['data_origin'])
    with pytest.raises(AcceptanceError, match='Source, Server and mock'): review(inventory, manifest, tmp_path)


@pytest.mark.parametrize('change', [{}, {'os': 'linux'}, {'architecture': 'arm64'},
    {'developer_tools': ['python']}, {'elevated': True}, {'build': 26200}])
def test_authored_receipt_validates_scoped_windows_host_without_granting_client_acceptance(tmp_path, change):
    inventory, manifest, receipts = fixture(tmp_path)
    receipt = receipts['actual_format']; receipt['method'] = 'authored-native'
    receipt['environment'].update(os='windows-server', release='2025', display_version='24H2',
        build=26100, interactive=False, physical_display=False, browser_profiles={})
    receipt['environment'].update(change); save(tmp_path, manifest, 'actual_format', receipt)
    if change:
        with pytest.raises(AcceptanceError, match='Windows Server 2025'): review(inventory, manifest, tmp_path)
    else:
        assert review(inventory, manifest, tmp_path)['required_row_coverage_complete'] is True
        receipts['clean_host']['method'] = 'authored-native'
        receipts['clean_host']['environment'] = deepcopy(receipt['environment'])
        save(tmp_path, manifest, 'clean_host', receipts['clean_host'])
        with pytest.raises(AcceptanceError, match='Source, Server and mock'): review(inventory, manifest, tmp_path)


def test_wrong_bytes_partial_operations_and_missing_rows_never_count_as_full_coverage(tmp_path):
    inventory, manifest, receipts = fixture(tmp_path)
    (tmp_path/'clean_host.json').write_bytes(b'changed')
    with pytest.raises(AcceptanceError, match='pinned digest'): review(inventory, manifest, tmp_path)
    save(tmp_path, manifest, 'clean_host', receipts['clean_host'])
    receipts['clean_host']['operations'].pop('missing_crt'); save(tmp_path, manifest, 'clean_host', receipts['clean_host'])
    with pytest.raises(AcceptanceError, match='full acceptance contract'): review(inventory, manifest, tmp_path)
    manifest['rows'].pop('clean_host')
    with pytest.raises(AcceptanceError, match='every|Every'): review(inventory, manifest, tmp_path)


def test_fresh_profiles_different_native_hosts_and_incomplete_measurements_are_not_continuity(tmp_path):
    inventory, manifest, receipts = fixture(tmp_path)
    receipts['host_browser']['environment']['browser_profiles']['firefox'] = 'fresh'
    save(tmp_path, manifest, 'host_browser', receipts['host_browser'])
    with pytest.raises(AcceptanceError, match='selected ordinary profiles'): review(inventory, manifest, tmp_path)
    receipts['host_browser']['environment']['browser_profiles']['firefox'] = 'ordinary-selected'
    receipts['host_browser']['environment']['environment_id'] = 'd'*64
    save(tmp_path, manifest, 'host_browser', receipts['host_browser'])
    with pytest.raises(AcceptanceError, match='different environments'): review(inventory, manifest, tmp_path)
    receipts['host_browser']['environment']['environment_id'] = 'c'*64; save(tmp_path, manifest, 'host_browser', receipts['host_browser'])
    receipts['baseline_delivery']['measurements']['source']['warm_start_ms'].pop()
    save(tmp_path, manifest, 'baseline_delivery', receipts['baseline_delivery'])
    with pytest.raises(AcceptanceError, match='five warm'): review(inventory, manifest, tmp_path)


def test_path_escape_and_duplicate_json_are_refused_without_echoing_private_data(tmp_path):
    inventory, manifest, _ = fixture(tmp_path)
    manifest['rows']['clean_host']['receipts'][0]['path'] = '../private.json'
    with pytest.raises(AcceptanceError, match='canonical relative path'): review(inventory, manifest, tmp_path)
    with pytest.raises(AcceptanceError, match='Duplicate'): decode(b'{"secret":"one","secret":"two"}')
    with pytest.raises(AcceptanceError, match='Non-finite'): decode(b'{"sample":NaN}')


def test_review_cli_preserves_existing_output_and_initializes_only_unavailable_rows(tmp_path):
    inventory, _, _ = fixture(tmp_path)
    source = tmp_path/'inventory.json'; source.write_bytes(inventory)
    target = tmp_path/'matrix.json'; target.write_bytes(b'preserve unrelated output')
    script = Path(__file__).resolve().parents[2]/'scripts/check-r19-acceptance.py'
    command = [sys.executable, '-B', str(script), '--inventory', str(source), '--template', '--output', str(target)]
    result = subprocess.run(command, capture_output=True, timeout=10)
    assert result.returncode == 2 and target.read_bytes() == b'preserve unrelated output'
    assert str(tmp_path).encode() not in result.stderr
    target.unlink()
    assert subprocess.run(command, capture_output=True, timeout=10).returncode == 0
    matrix = json.loads(target.read_bytes())
    assert all(r == {'status': 'unavailable', 'receipts': []} for r in matrix['rows'].values())
    report = tmp_path/'review.json'
    result = subprocess.run([sys.executable, '-B', str(script), '--inventory', str(source), '--manifest', str(target),
        '--evidence-root', str(tmp_path), '--output', str(report)], capture_output=True, timeout=10)
    assert result.returncode == 1
    assert json.loads(report.read_bytes())['ready_for_independent_acceptance_review'] is False
