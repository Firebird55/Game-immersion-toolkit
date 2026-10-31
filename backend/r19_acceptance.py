"""Candidate-bound consistency review, never native execution or promotion.

The verifier consumes private, independently reviewed receipts. Hashing a claim
does not establish that it happened; even a consistent complete matrix still
requires the acceptance reviewer and cannot enable a runtime profile.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

SHA = re.compile(r'[a-f0-9]{64}')
COMMIT = re.compile(r'[a-f0-9]{40}')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}')
COMPONENT_GATES = {'python-supplier', 'python-native', 'javascript-native', 'models',
    'vgmstream', 'ffmpeg', 'copyleft', 'game-helper-rights', 'compiler-free-helpers',
    'native-dll-isolation', 'frontend-equivalence', 'supervised-update'}
OPERATIONS = {
    'clean_host': ('ordinary_user_no_devtools', 'declared_prerequisites', 'wrong_architecture',
        'missing_crt', 'restricted_store', 'offline_first_start', 'insufficient_space'),
    'resources_children': ('unicode_unrelated_cwd', 'immutable_full_inventory', 'frozen_children',
        'native_dll_origins', 'missing_resource', 'owned_child_cleanup'),
    'native_ocr_capture': ('authored_chinese_ocr', 'authored_non_chinese_ocr', 'window_capture',
        'monitor_capture', 'dpi_125', 'dpi_150', 'dpi_200', 'multiple_monitors',
        'negative_display_coordinates', 'missing_stale_ocr', 'denied_unavailable_capture',
        'transcript_survives_audio_failure'),
    'distinct_toolchains': ('all_game_chain_locale_mapping', 'each_distinct_real_chain',
        'wrong_missing_corrupt_tool', 'absent_voice_pack', 'interrupted_extraction'),
    'actual_format': ('authored_real_subprocess_formats', 'owned_audio_decode',
        'text_voice_identity', 'actual_output_parsing', 'installed_pack_limits_declared'),
    'host_browser': ('chromium_existing_profile', 'firefox_existing_profile', 'retained_origins',
        'reader_modes_lookup_audio_export', 'http_ws_recovery', 'real_extension_scope_declared'),
    'static_mobile': ('route_hydration_equivalence', 'worker_wasm_model_urls',
        'allowlisted_assets', 'old_current_caches', 'offline_reopen_preserves_stores'),
    'data_origin': ('writer_stop_proof', 'copied_state_roundtrip', 'sqlite_wal_consistency',
        'same_user_protected_test', 'named_store_failure_preserved', 'indexeddb_and_opfs',
        'copy_interruption_no_space_locks_unknown_schema', 'original_state_preserved'),
    'update_rollback': ('verified_candidate_standby', 'bounded_quiesce_single_capture_owner',
        'legacy_guard_update_contention', 'checksum_provenance_failure', 'crash_checkpoint_recovery',
        'previous_compatible_runtime_restart', 'post_activation_writes_preserved'),
    'baseline_delivery': ('same_machine_source_comparison', 'frontend_runtime_ready_first_caption',
        'cold_and_five_warm_samples', 'process_tree_cpu_memory', 'idle_60_seconds',
        'sizes_peak_failure_disk', 'bounded_recovery', 'downloaded_checksums_provenance',
        'signature_attestation_separate'),
}
NATIVE_ROWS = {'clean_host', 'native_ocr_capture', 'host_browser', 'data_origin', 'baseline_delivery'}


class AcceptanceError(ValueError):
    """Fixed public contract text only; never echo private receipt contents."""


def _require(condition, message):
    if not condition:
        raise AcceptanceError(message)


def _keys(value, names):
    _require(isinstance(value, dict) and set(value) == set(names), 'Unexpected or missing receipt fields.')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'Duplicate JSON field.')
        result[key] = value
    return result


def decode(data):
    _require(len(data) <= 2 * 1024 * 1024, 'Receipt exceeds its size bound.')
    try:
        return json.loads(data.decode('utf-8-sig'), object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(AcceptanceError('Non-finite JSON value.')))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise AcceptanceError('Malformed acceptance JSON.') from error


def _name(name):
    _require(isinstance(name, str) and name and '\\' not in name and ':' not in name
        and not PurePosixPath(name).is_absolute()
        and all(part not in {'', '.', '..'} and not part.endswith((' ', '.'))
                and not any(ord(c) < 32 for c in part) for part in name.split('/')),
        'Evidence needs a canonical relative path.')
    return name


def _read(root, name, expected):
    _require(isinstance(expected, str) and SHA.fullmatch(expected), 'Evidence needs an exact SHA-256.')
    path = Path(root).absolute() / _name(name)
    for item in (path, *path.parents):
        _require(not item.is_symlink() and not (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400),
            'Evidence cannot use links or reparse points.')
    _require(path.is_file() and path.stat().st_size <= 2 * 1024 * 1024, 'Evidence file unavailable or oversized.')
    data = path.read_bytes()
    _require(hashlib.sha256(data).hexdigest() == expected, 'Evidence bytes differ from their pinned digest.')
    return decode(data)


def candidate(inventory_bytes):
    value = decode(inventory_bytes)
    _require(isinstance(value, dict) and value.get('schema') == 'proxy-r19-runtime-inventory-v1'
        and isinstance(value.get('profile'), str) and value['profile'] in {'runtime-experiment', 'runtime'}
        and isinstance(value.get('source_commit'), str) and COMMIT.fullmatch(value['source_commit'])
        and isinstance(value.get('build_id'), str) and LABEL.fullmatch(value['build_id']),
        'Need an exact extracted-runtime inventory identity.')
    files = value.get('files')
    _require(isinstance(files, list) and files and type(value.get('file_count')) is int
        and len(files) == value['file_count'], 'Incomplete candidate file inventory.')
    names = set()
    total = 0
    for entry in files:
        _keys(entry, {'path', 'sha256', 'bytes'})
        name = _name(entry['path']).casefold()
        _require(name not in names and isinstance(entry['sha256'], str) and SHA.fullmatch(entry['sha256'])
            and type(entry['bytes']) is int and entry['bytes'] >= 0, 'Invalid or aliased candidate file identity.')
        names.add(name); total += entry['bytes']
    _require(type(value.get('bytes')) is int and total == value['bytes'], 'Candidate inventory byte count differs.')
    return {'source_commit': value['source_commit'], 'build_id': value['build_id'],
        'inventory_sha256': hashlib.sha256(inventory_bytes).hexdigest()}, value


def template(inventory_bytes):
    identity, _value = candidate(inventory_bytes)
    return {'schema': 'proxy-r19-acceptance-input-v1', **identity,
        'rows': {name: {'status': 'unavailable', 'receipts': []} for name in OPERATIONS}}


def _native(environment):
    _keys(environment, {'os', 'release', 'display_version', 'build', 'architecture', 'elevated',
        'developer_tools', 'interactive', 'physical_display', 'environment_id', 'browser_profiles'})
    _require(environment['os'] == 'windows-client' and environment['release'] == '11'
        and environment['display_version'] == '25H2' and type(environment['build']) is int
        and environment['build'] == 26200 and environment['architecture'] == 'x64'
        and environment['elevated'] is False and environment['developer_tools'] == []
        and environment['interactive'] is True and environment['physical_display'] is True
        and isinstance(environment['environment_id'], str) and SHA.fullmatch(environment['environment_id']),
        'Native acceptance needs ordinary-user interactive Windows 11 25H2 x64 without developer tools.')
    return environment['environment_id']


def _authored(environment):
    _keys(environment, {'os', 'release', 'display_version', 'build', 'architecture', 'elevated',
        'developer_tools', 'interactive', 'physical_display', 'environment_id', 'browser_profiles'})
    _require(environment['os'] == 'windows-server' and environment['release'] == '2025'
        and isinstance(environment['display_version'], str) and environment['display_version'] in {'24H2', '2025', ''}
        and type(environment['build']) is int and environment['build'] == 26100
        and environment['architecture'] == 'x64' and environment['elevated'] is False
        and environment['developer_tools'] == [] and type(environment['interactive']) is bool
        and type(environment['physical_display']) is bool
        and isinstance(environment['environment_id'], str) and SHA.fullmatch(environment['environment_id'])
        and isinstance(environment['browser_profiles'], dict)
        and set(environment['browser_profiles']) <= {'chromium', 'firefox'}
        and all(isinstance(v, str) and v in {'authored-test', 'ordinary-selected'} for v in environment['browser_profiles'].values()),
        'Authored extracted-runtime receipts need ordinary-user Windows Server 2025 x64 without developer tools; client receipts need native-client.')


def _measurements(measurements, environment_id):
    _keys(measurements, {'source', 'candidate', 'signature', 'attestation'})
    for mode in ('source', 'candidate'):
        sample = measurements[mode]
        fields = {'environment_id', 'cold_start_ms', 'warm_start_ms', 'first_caption_ms', 'peak_private_bytes',
            'peak_rss_bytes', 'cpu_ms', 'idle_cpu_ms', 'idle_seconds', 'extracted_bytes', 'compressed_bytes',
            'peak_prepare_bytes', 'peak_failed_update_bytes', 'recovery_ms'}
        _keys(sample, fields)
        _require(sample['environment_id'] == environment_id and sample['idle_seconds'] == 60
            and isinstance(sample['warm_start_ms'], list) and len(sample['warm_start_ms']) == 5,
            'R02b needs the same machine, five warm starts and 60 seconds idle.')
        numbers = [sample[k] for k in fields - {'environment_id', 'warm_start_ms'}] + sample['warm_start_ms']
        _require(all(type(n) in {int, float} and math.isfinite(n) and n >= 0 for n in numbers)
            and sample['recovery_ms'] <= 30000, 'Invalid or incomplete R02b samples/recovery.')
    _require(isinstance(measurements['signature'], str) and measurements['signature'] in {'verified', 'not-signed', 'unavailable'}
        and isinstance(measurements['attestation'], str) and measurements['attestation'] in {'verified', 'not-attested', 'unavailable'},
        'Signature and attestation need separate declared observations.')


def review(inventory_bytes, manifest, evidence_root):
    identity, inventory = candidate(inventory_bytes)
    _keys(manifest, {'schema', *identity, 'rows'})
    _require(manifest['schema'] == 'proxy-r19-acceptance-input-v1'
        and all(manifest[k] == v for k, v in identity.items()), 'Review belongs to another candidate.')
    _require(isinstance(manifest['rows'], dict) and set(manifest['rows']) == set(OPERATIONS),
        'Every R18 acceptance row must be answered exactly once.')
    rows, native_ids = {}, set()
    for name, operations in OPERATIONS.items():
        row = manifest['rows'][name]
        _keys(row, {'status', 'receipts'})
        _require(isinstance(row['status'], str) and row['status'] in {'passed', 'failed', 'unavailable'} and isinstance(row['receipts'], list)
            and len(row['receipts']) <= 16, 'Invalid acceptance row status or receipt count.')
        if row['status'] != 'passed':
            _require(not row['receipts'], 'Keep partial/source evidence outside a complete-row pass.')
            rows[name] = {'status': row['status'], 'receipt_sha256': []}
            continue
        _require(row['receipts'], 'A passed row needs observed receipt bytes.')
        covered, hashes = set(), []
        for reference in row['receipts']:
            _keys(reference, {'path', 'sha256'})
            receipt = _read(evidence_root, reference['path'], reference['sha256'])
            _keys(receipt, {'schema', *identity, 'row', 'status', 'method', 'operations', 'environment',
                'live_accounts_accessed', 'real_data_modified', 'measurements'})
            _require(receipt['schema'] == 'proxy-r19-acceptance-receipt-v1'
                and all(receipt[k] == v for k, v in identity.items()) and receipt['row'] == name
                and receipt['status'] == 'passed', 'Receipt is failed, stale or belongs to another candidate/row.')
            _require(receipt['live_accounts_accessed'] is False and receipt['real_data_modified'] is False,
                'Acceptance review uses protected TEST/synthetic copies, not live account writes or migration.')
            checks = receipt['operations']
            _require(isinstance(checks, dict) and checks and set(checks) <= set(operations)
                and all(isinstance(v, str) for v in checks.values())
                and set(checks.values()) == {'passed'}, 'Receipt lacks a passed required operation.')
            if name in NATIVE_ROWS:
                _require(receipt['method'] == 'native-client', 'Source, Server and mock receipts cannot prove native client acceptance.')
                environment_id = _native(receipt['environment']); native_ids.add(environment_id)
                if name == 'host_browser':
                    _require(receipt['environment']['browser_profiles'] == {'chromium': 'ordinary-selected', 'firefox': 'ordinary-selected'},
                        'Browser continuity requires the selected ordinary profiles for both browser engines.')
                if name == 'baseline_delivery':
                    _measurements(receipt['measurements'], environment_id)
                else:
                    _require(receipt['measurements'] is None, 'Measurements belong in the baseline row.')
            else:
                _require(isinstance(receipt['method'], str) and receipt['method'] in {'authored-native', 'native-client'} and receipt['measurements'] is None,
                    'Mocked/source-only success is not an actual runtime/format receipt.')
                if receipt['method'] == 'native-client':
                    _native(receipt['environment'])
                else:
                    _authored(receipt['environment'])
            covered.update(checks); hashes.append(reference['sha256'])
        _require(covered == set(operations), 'A passed row does not cover its full acceptance contract.')
        rows[name] = {'status': 'passed', 'receipt_sha256': sorted(set(hashes))}
    _require(len(native_ids) <= 1, 'Native continuity/baseline rows refer to different environments.')
    gates = inventory.get('gates', {})
    eligible = (isinstance(gates, dict) and set(gates) == COMPONENT_GATES
        and all(isinstance(v, str) for v in gates.values()) and set(gates.values()) == {'approved'})
    complete = all(row['status'] == 'passed' for row in rows.values())
    return {'schema': 'proxy-r19-acceptance-consistency-v1', **identity, 'rows': rows,
        'component_disposition_complete': eligible, 'required_row_coverage_complete': complete,
        'ready_for_independent_acceptance_review': eligible and complete,
        'evidence_level': 'receipt-integrity-and-scope-consistency-only; not proof of execution or license grant',
        'production_execution_allowed': False, 'r19_complete': False, 'installer': 'not-built'}
