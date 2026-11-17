"""Quoted local canonical-table work, separate from capture admission.

Plans inspect original index metadata only. The complete current index is an
explicitly quoted download-stage read, even when its first bytes are unchanged.
Original table bodies must already belong to the retained text source.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from . import endfield_authored_validation as validation
from . import endfield_text_source as text
from .endfield_client_source import identity_stamp

MAX_FACTS = 128 * 1024**2
MAX_RECEIPT = 1024**2
HEADER = 16


def _helpers():
    from .game_data import _write_bytes
    from .game_data_protocol import GameDataError
    from .private_data_paths import _no_links
    return _write_bytes, GameDataError, _no_links


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _root(ctx):
    return Path(ctx.cache_directory) / 'endfield-authored-tables'


def _bounded(ctx, path, limit):
    _, Error, no_links = _helpers()
    ctx.check()
    no_links(path)
    try:
        if not path.is_file() or not 2 <= path.stat().st_size <= limit:
            raise ValueError('Missing or oversized evidence')
        return path.read_bytes()
    except (OSError, ValueError) as error:
        raise Error('invalid_local_state', 'Endfield original authored evidence needs repair; existing data is retained.') from error


def _catalog(ctx, identity, common, generation, reference):
    _, Error, _ = _helpers()
    catalog = text.Catalog(ctx, identity, common, reference)
    if catalog.generation != generation:
        raise Error('publisher_object_changed', 'Endfield original tables belong to another resource generation.', 409)
    return catalog


def _controls(ctx, catalog, controls):
    _, _, no_links = _helpers()
    required = {'TableCfg/I18nTextTable_' + text.TEXT_LOCALES[code] + '.json'
                for code in (ctx.request.source_locale, *ctx.request.target_locales)}
    if not required <= controls.keys():
        raise ValueError('Configured original translations are missing')
    for control in controls.values():
        ctx.check()
        file = control['file_control']
        if file is None:
            if control['absent_optional_entry'] is not True:
                raise ValueError('Original table control missing')
            continue
        row = catalog.files.get(file['name'])
        if row is None or row.size != file['bytes'] or row.content_hashes[1] != file['md5']:
            raise ValueError('Original table ownership differs')
        path = text._root(ctx) / 'assets' / file['md5']
        no_links(path)
        if not path.is_file() or path.stat().st_size != row.size:
            raise ValueError('Original consumed table changed')
        digest = hashlib.md5()
        with path.open('rb') as stream:
            while chunk := stream.read(65536):
                ctx.check()
                digest.update(chunk)
        if digest.hexdigest() != file['md5']:
            raise ValueError('Original consumed table changed')


def _index(ctx, identity, common, generation, catalog, transport, owner):
    _, Error, _ = _helpers()
    _, base = text._owner(identity, common, generation)
    url = base + common.directories[18] + '.blc'
    headers = {'If-Match': owner['response_etag']} if owner['response_etag'] else None
    raw, receipt = transport.fetch_bytes(url, limit=owner['bytes'], expected_size=owner['bytes'], kind='metadata',
        original_range=(0, owner['bytes'], owner['bytes']), headers=headers)
    if _sha(raw[:HEADER]) != owner['header_sha256']:
        raise Error('publisher_text_changed', 'Endfield original text index changed; check its text-source plan again.', 409)
    rows, _ = text._selected(ctx, common, raw)
    # Checking every authored file field also rejects a valid changed body
    # behind the same short header. Header/old SHA alone are never freshness.
    if {row.name: row for row in rows} != catalog.files:
        raise Error('publisher_text_changed', 'Endfield original text ownership changed; check its text-source plan again.', 409)
    return _sha(raw), receipt.json()


def plan(ctx, identity, common, generation, reference, transport):
    """No original table-body read/decode or large index read in planning."""
    _, Error, _ = _helpers()
    catalog = _catalog(ctx, identity, common, generation, reference)
    _, base = text._owner(identity, common, generation)
    url = base + common.directories[18] + '.blc'
    raw, receipt = transport.fetch_bytes(url, limit=HEADER, expected_size=HEADER, kind='metadata',
                                        original_range=(0, HEADER, None))
    owner = receipt.original_range
    if (not owner or owner[:2] != (0, HEADER) or type(owner[2]) is not int or
            not HEADER <= owner[2] <= text.vfs.MAX_INDEX):
        raise Error('publisher_range_changed', 'Endfield original text index has no bounded current owner.')
    return {'schema': 1, 'stage': 'original-authored-table-validation', 'generation': generation,
        'request': ctx.request.json(), 'text_source': reference,
        'index_owner': {'bytes': owner[2], 'header_sha256': _sha(raw), 'response_etag': receipt.response_etag},
        'wire_index_recheck_bytes': 2 * owner[2], 'local_output_upper_bytes': MAX_FACTS + MAX_RECEIPT,
        'required_disk_bytes': 2 * (MAX_FACTS + MAX_RECEIPT),
        'selected_original_table_count': len(catalog.files),
        'aes_header_parameters_verified': False, 'canonical_snapshot_prepared': False}


def restore(ctx, identity, common, generation, reference, text_reference):
    """Exact-source local evidence, never a fresh online publisher assertion."""
    _, Error, _ = _helpers()
    catalog = _catalog(ctx, identity, common, generation, text_reference)
    if (not isinstance(reference, dict) or type(reference.get('schema')) is not int or reference['schema'] != 1 or
            reference.get('stage') != 'original-authored-tables-validated' or
            reference.get('client_sha256') != identity_stamp(identity) or
            reference.get('generation_sha256') != _sha(_json(generation)) or
            reference.get('request') != ctx.request.json() or
            not isinstance(reference.get('receipt_sha256'), str) or
            not re.fullmatch('[0-9a-f]{64}', reference.get('receipt_sha256', ''))):
        raise Error('invalid_local_state', 'Endfield authored evidence belongs to another original request.')
    raw = _bounded(ctx, _root(ctx) / 'receipts' / (reference['receipt_sha256'] + '.json'), MAX_RECEIPT)
    try:
        body = json.loads(raw)
        if (_sha(raw) != reference['receipt_sha256'] or body['schema'] != 1 or body['client'] != identity or
                body['generation'] != generation or body['request'] != ctx.request.json() or
                body['text_source'] != text_reference or body['format'] != validation.FORMAT or
                body['canonical_snapshot_prepared'] is not False or body['aes_header_parameters_verified'] is not False or
                not re.fullmatch('[0-9a-f]{64}', body['facts_sha256']) or
                type(body['facts_bytes']) is not int or not 2 <= body['facts_bytes'] <= MAX_FACTS):
            raise ValueError('Original authored receipt differs')
        target = _root(ctx) / 'facts' / (body['facts_sha256'] + '.json')
        facts = _bounded(ctx, target, MAX_FACTS)
        if len(facts) != body['facts_bytes'] or _sha(facts) != body['facts_sha256']:
            raise ValueError('Authored output differs')
        # No SparkBuffer/body decode during plan/restore. Complete bytes still
        # have to match the original source used for these facts.
        _controls(ctx, catalog, body['table_controls'])
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise Error('invalid_local_state', 'Endfield original authored evidence needs repair; existing data is retained.') from error
    return body


def download(ctx, identity, common, approved, transport, *, recheck):
    from .preparation_errors import PreparationFailure
    write, Error, _ = _helpers()
    if ctx.phase != 'download' or approved.get('request') != ctx.request.json():
        raise Error('unapproved_asset_transfer', 'Approve the exact Endfield authored-table work first.')
    catalog = _catalog(ctx, identity, common, approved['generation'], approved['text_source'])
    first_index, first_receipt = _index(ctx, identity, common, approved['generation'], catalog, transport, approved['index_owner'])
    ctx.check()
    try:
        facts = validation.build(catalog, ctx.request.source_locale, ctx.request.target_locales,
                                 content_mode=ctx.request.content_mode)
        report = validation.validate_candidate(facts, facts['records'])
        encoded = _json(facts)
        if len(encoded) > MAX_FACTS:
            raise ValueError('Authored facts exceed the quoted local-output allowance')
        if any(value['file_control'] is None and not value['absent_optional_entry']
               for value in facts['original_table_controls'].values()):
            raise ValueError('Original authored table control is missing')
    except (ValueError, KeyError, TypeError, OSError, PreparationFailure) as error:
        raise Error('unsupported_original_text', 'Endfield original authored tables could not be fully validated; existing data is retained.') from error
    second_index, second_receipt = _index(ctx, identity, common, approved['generation'], catalog, transport, approved['index_owner'])
    if second_index != first_index or recheck() != (identity, approved['generation']):
        raise Error('publisher_object_changed', 'Endfield changed during authored-table validation; existing data is retained.', 409)
    try:
        _controls(ctx, catalog, facts['original_table_controls'])
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise Error('invalid_local_state', 'Endfield retained original tables changed; check their source size again.') from error
    body = {'schema': 1, 'format': validation.FORMAT, 'client': identity, 'generation': approved['generation'],
        'request': ctx.request.json(), 'text_source': approved['text_source'], 'facts_sha256': _sha(encoded),
        'facts_bytes': len(encoded), 'table_controls': facts['original_table_controls'], 'validation_report': report,
        'current_index_sha256': first_index, 'index_receipts': [first_receipt, second_receipt],
        'aes_header_parameters_verified': False, 'canonical_snapshot_prepared': False}
    receipt = _json(body)
    if len(receipt) > MAX_RECEIPT:
        raise Error('unsupported_original_text', 'Endfield authored receipt exceeds its quoted local-output allowance.')
    ctx.check()
    write(_root(ctx) / 'facts' / (_sha(encoded) + '.json'), encoded)
    ctx.check()
    write(_root(ctx) / 'receipts' / (_sha(receipt) + '.json'), receipt)
    return {'schema': 1, 'stage': 'original-authored-tables-validated', 'client_sha256': identity_stamp(identity),
        'generation_sha256': _sha(_json(approved['generation'])), 'request': ctx.request.json(),
        'receipt_sha256': _sha(receipt)}
