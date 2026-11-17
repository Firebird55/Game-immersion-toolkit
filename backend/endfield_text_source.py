"""Quoted original TableCfg acquisition, without audio or legacy tool caches.

The complete typed catalog supplies current table ownership. Language selection
excludes unrequested I18n bodies; other tables are retained as a complete shared
catalog, including non-narrative table overhead. This is a source stage, not a
dialogue snapshot, and never activates a partially acquired catalog.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .endfield_client_source import identity_stamp
from .endfield_resource_source import DETAIL_LIMIT, _file
from . import endfield_tables as tables, endfield_vfs as vfs

TEXT_LOCALES = {'en': 'EN', 'zh-Hans': 'CN', 'zh-Hant': 'TC', 'ja': 'JP', 'ko': 'KR',
    'fr': 'FR', 'de': 'DE', 'it': 'IT', 'es-419': 'MX', 'pt-BR': 'BR', 'ru': 'RU',
    'th': 'TH', 'vi': 'VN', 'id': 'ID'}
MAX_CATALOG = 512 * 1024**2
MAX_FILE = 64 * 1024**2
RECEIPT_ALLOWANCE = 2 * 1024**2


def _helpers():
    from .game_data import _read, _write_bytes
    from .game_data_protocol import GameDataError
    from .private_data_paths import _no_links
    return _read, _write_bytes, GameDataError, _no_links


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _root(ctx):
    return Path(ctx.cache_directory) / 'endfield-text-tables'


def _payload(ctx, row):
    """A cache entry is warm only after whole MD5 and typed source checks."""
    _, _, _, no_links = _helpers()
    path = _root(ctx) / 'assets' / row.content_hashes[1]
    no_links(path)
    if not path.is_file() or path.stat().st_size != row.size:
        return None
    raw = path.read_bytes()
    try:
        _validate(row, raw)
    except (ValueError, UnicodeError):
        return None
    return raw


def _validate(row, raw):
    if len(raw) != row.size or hashlib.md5(raw).hexdigest() != row.content_hashes[1]:
        raise ValueError('Complete original table checksum differs')
    # This proves the authored embedded type/root, not a guessed JSON schema.
    return tables.read(raw, row.name.removeprefix('Data/TableCfg/').removesuffix('.bytes'))


def _selected(ctx, common, index):
    _, _, Error, _ = _helpers()
    request = ctx.request
    if (ctx.game != 'endfield' or request.content_mode not in {'text', 'text-audio'} or
            request.source_locale not in {'en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'} or
            any(code not in TEXT_LOCALES for code in request.target_locales)):
        raise Error('invalid_game_languages', 'Choose the official Endfield text languages and download mode.')
    wanted = {TEXT_LOCALES[code] for code in (request.source_locale, *request.target_locales)}
    params = vfs.IndexParameters(common.key, common.directories, common.protocol)
    try:
        files = vfs.parse_index(index, params, 18, suffix='.bytes')
        names = set()
        selected, found = [], set()
        for row in files:
            name = re.fullmatch(r'Data/TableCfg/([A-Za-z0-9_]+)\.bytes', row.name)
            if (not name or row.name in names or not 12 <= row.size <= MAX_FILE or
                    len(row.content_hashes) != 2 or not re.fullmatch('[0-9a-f]{32}', row.content_hashes[1]) or
                    not re.fullmatch(r'[0-9A-F]{32}\.chk', row.chunk)):
                raise ValueError('Original table ownership is invalid')
            names.add(row.name)
            if name[1].startswith('I18nTextTable_'):
                locale = name[1].removeprefix('I18nTextTable_')
                if locale not in wanted:
                    continue
                found.add(locale)
            selected.append(row)
        if not selected or found != wanted or sum(row.size for row in selected) > MAX_CATALOG:
            raise ValueError('Selected original text catalog is missing or too large')
    except (ValueError, TypeError, KeyError) as error:
        raise Error('unsupported_original_text', 'Endfield original text index failed its CRC, ownership or language checks. Existing data is retained.') from error
    return tuple(sorted(selected, key=lambda row: row.name)), len(files)


def _owner(identity, common, generation):
    _, _, Error, _ = _helpers()
    try:
        if generation['client_sha256'] != identity_stamp(identity) or generation['region'] != identity['region']:
            raise ValueError('Current client differs')
        directory = common.directories[18]
        base = generation['layers']['main']['url'] + '/VFS/' + directory + '/'
    except (ValueError, TypeError, KeyError) as error:
        raise Error('unverified_original_source', 'Endfield text has no current original client/resource owner.') from error
    return directory, base


def _plan(ctx, identity, common, generation, index):
    directory, base = _owner(identity, common, generation)
    selected, total = _selected(ctx, common, index)
    entries, pending, retained = [], 0, 0
    for row in selected:
        ctx.check()
        warm = _payload(ctx, row) is not None
        pending += 0 if warm else row.size
        retained += row.size if warm else 0
        entries.append({'file': _file(row), 'cached': warm})
    # Download calls rebuild this plan and perform a final generation check.
    # Quote both complete resource-list/index rechecks, not only asset bytes.
    rechecks = 2 * (DETAIL_LIMIT + sum(row['index_bytes'] for row in generation['layers'].values()) + len(index))
    return {'schema': 1, 'stage': 'original-text-tables', 'generation': generation,
        'request': ctx.request.json(), 'directory': directory, 'base': base,
        'index_sha256': hashlib.sha256(index).hexdigest(), 'index_bytes': len(index),
        'catalog_entries': total, 'selected_entries': len(entries), 'files': entries,
        'payload_bytes': pending, 'retained_verified_bytes': retained,
        'metadata_recheck_upper': rechecks, 'download_bytes': pending + rechecks,
        'required_disk_bytes': 2 * pending + 2 * (len(index) + RECEIPT_ALLOWANCE),
        'download_is_upper_bound': True}


def plan(ctx, identity, common, generation, transport):
    """Plan reads only the complete original index, never table/audio bodies."""
    ctx.check()
    directory, base = _owner(identity, common, generation)
    raw, _ = transport.fetch_bytes(base + directory + '.blc', limit=vfs.MAX_INDEX, kind='metadata')
    return _plan(ctx, identity, common, generation, raw), raw


def download(ctx, identity, common, approved, index, transport, *, recheck):
    """Publish a source receipt only after every selected table is complete."""
    _, write, Error, _ = _helpers()
    ctx.check()
    if ctx.phase != 'download':
        raise Error('unapproved_asset_transfer', 'Approve the Endfield original text-table download first.')
    current = _plan(ctx, identity, common, approved['generation'], index)
    if current != approved:
        raise Error('publisher_size_changed', 'Endfield original text ownership, selection or verified cache changed. Check its size again.')
    selected, _ = _selected(ctx, common, index)
    transfers = []
    for row, entry in zip(selected, approved['files'], strict=True):
        ctx.check()
        raw = _payload(ctx, row)
        if raw is None:
            if entry['cached']:
                raise Error('invalid_local_state', 'A previously verified Endfield table needs a new download plan.')
            raw, receipt = transport.fetch_bytes(approved['base'] + row.chunk, limit=row.size,
                expected_size=row.size, kind='asset', original_range=(row.offset, row.size, row.chunk_size))
            raw = vfs.chacha(raw, common.key, row.nonce) if row.nonce else raw
            try:
                _validate(row, raw)
            except (ValueError, UnicodeError) as error:
                raise Error('publisher_checksum_mismatch', 'Endfield complete original table failed its MD5 or embedded SparkBuffer checks. Existing data is retained.') from error
            ctx.check()
            write(_root(ctx) / 'assets' / row.content_hashes[1], raw)
            transfers.append({'name': row.name, 'receipt': receipt.json()})
    ctx.check()
    if recheck() != (identity, approved['generation']):
        raise Error('publisher_object_changed', 'Endfield changed before complete text-source publication. Existing data is retained.', 409)
    body = {'schema': 1, 'kind': 'endfield-original-text-tables', 'client': identity,
        'generation': approved['generation'], 'request': ctx.request.json(),
        'index_sha256': approved['index_sha256'], 'files': [entry['file'] for entry in approved['files']],
        'transfers': transfers}
    encoded = _json(body)
    if len(encoded) > RECEIPT_ALLOWANCE:
        raise Error('unsupported_original_text', 'Endfield original text receipt exceeds its quoted bound.')
    digest = hashlib.sha256(encoded).hexdigest()
    root = _root(ctx) / 'sources' / digest
    write(root / 'index.blc', index)
    ctx.check()
    write(root / 'receipt.json', encoded)
    return {'schema': 1, 'stage': 'original-text-tables-downloaded',
        'client_sha256': identity_stamp(identity), 'generation_sha256': hashlib.sha256(_json(approved['generation'])).hexdigest(),
        'request': ctx.request.json(), 'receipt_sha256': digest}


class Catalog:
    """Explicit offline original tables; no ambient legacy cache fallback."""
    def __init__(self, ctx, identity, common, reference):
        read, _, Error, no_links = _helpers()
        if (not isinstance(reference, dict) or type(reference.get('schema')) is not int or reference['schema'] != 1 or
                reference.get('stage') != 'original-text-tables-downloaded' or
                reference.get('client_sha256') != identity_stamp(identity) or
                reference.get('request') != ctx.request.json() or
                not re.fullmatch('[0-9a-f]{64}', reference.get('receipt_sha256', ''))):
            raise Error('invalid_local_state', 'Endfield text reference belongs to another source request.')
        root = _root(ctx) / 'sources' / reference['receipt_sha256']
        for name in ('receipt.json', 'index.blc'):
            no_links(root / name)
        body = read(root / 'receipt.json')
        try:
            if (hashlib.sha256(_json(body)).hexdigest() != reference['receipt_sha256'] or
                    body['client'] != identity or body['request'] != ctx.request.json() or
                    body['kind'] != 'endfield-original-text-tables' or body['schema'] != 1 or
                    hashlib.sha256(_json(body['generation'])).hexdigest() != reference['generation_sha256']):
                raise ValueError('Original receipt differs')
            _owner(identity, common, body['generation'])
            path = root / 'index.blc'
            if path.stat().st_size > vfs.MAX_INDEX:
                raise ValueError('Original index is too large')
            index = path.read_bytes()
            if hashlib.sha256(index).hexdigest() != body['index_sha256']:
                raise ValueError('Original index differs')
            selected, _ = _selected(ctx, common, index)
            if [_file(row) for row in selected] != body['files']:
                raise ValueError('Original file ownership differs')
        except (ValueError, KeyError, TypeError, OSError) as error:
            raise Error('invalid_local_state', 'Endfield original text source needs repair; existing data is retained.') from error
        self.ctx, self.files, self.generation = ctx, {row.name: row for row in selected}, body['generation']
        self.revision = 'endfield-resources-' + reference['generation_sha256']
        self.revision_title = identity['version']

    def file(self, relative, *, optional=False):
        _, _, Error, _ = _helpers()
        self.ctx.check()
        name = re.fullmatch(r'TableCfg/([A-Za-z0-9_]+)\.json', relative)
        if not name:
            raise Error('invalid_local_state', 'Use an original Endfield table name.')
        row = self.files.get('Data/TableCfg/' + name[1] + '.bytes')
        if row is None and optional:
            return {}
        raw = _payload(self.ctx, row) if row else None
        if raw is None:
            raise Error('invalid_local_state', 'Endfield original text table is missing or changed; restore the verified source.')
        return _validate(row, raw)
