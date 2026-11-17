"""Explicit large original manifest/index stages for text presentation owners.

Registry MD5, complete typed indexes and immutable receipts prove acquisition,
not AES/header parameters or capture readiness. No original code is executed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .endfield_client_source import identity_stamp
from .endfield_resource_source import DETAIL_LIMIT, _file
from .endfield_presentation_owners import WORLD_UI, SNS_UI, TRAINING_UI, DIALOG_GRAPHS
from . import endfield_vfs as vfs, endfield_film_registry as registry

MANIFEST = 'Data/Bundles/Windows/manifest.hgmmap'
MAX_MANIFEST = 160 * 1024**2
MAX_REGISTRY = 384 * 1024**2
MAX_BUNDLE_INDEX = 96 * 1024**2
SMALL_INDEX = 65536
HEADER = 16
UI = frozenset((*WORLD_UI.values(), *SNS_UI.values(), *TRAINING_UI.values()))


def _helpers():
    from .game_data import _read, _write_bytes
    from .game_data_protocol import GameDataError
    from .private_data_paths import _no_links
    return _read, _write_bytes, GameDataError, _no_links


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _root(ctx):
    return Path(ctx.cache_directory) / 'endfield-text-navigation'


def _store_index(ctx, digest, raw):
    _, write, _, no_links = _helpers()
    path = _root(ctx) / 'indices' / (digest + '.blc')
    no_links(path)
    ctx.check()
    if path.is_file() and path.stat().st_size == len(raw) and _sha(path.read_bytes()) == digest:
        return
    write(path, raw)


def _params(common):
    return vfs.IndexParameters(common.key, common.directories, common.protocol)


def _base(identity, common, generation, block):
    _, _, Error, _ = _helpers()
    try:
        if generation['client_sha256'] != identity_stamp(identity) or generation['region'] != identity['region']:
            raise ValueError('Client owner differs')
        role = 'initial' if block in (2, 4) else 'main'
        return generation['layers'][role]['url'] + '/VFS/' + common.directories[block] + '/'
    except (ValueError, KeyError, TypeError) as error:
        raise Error('unverified_original_source', 'Endfield presentation navigation needs its exact original client/resource owner.') from error


def _manifest(ctx, common, row):
    _, _, _, no_links = _helpers()
    path = _root(ctx) / 'manifests' / row.content_hashes[1]
    no_links(path)
    if not path.is_file() or path.stat().st_size != row.size:
        return None
    raw = path.read_bytes()
    if hashlib.md5(raw).hexdigest() != row.content_hashes[1]:
        return None
    # A good checksum does not make an unsupported registry usable.
    _owners(raw)
    return raw


def _owners(raw):
    plain = registry.inflate(raw, MAX_REGISTRY)
    found = {}
    for _, path, bundle in registry.bindings(plain, path_prefixes=(*sorted(UI), DIALOG_GRAPHS)):
        if path not in UI and not (path.startswith(DIALOG_GRAPHS) and path.endswith('.json')):
            continue
        if path in found:
            raise ValueError('Repeated original presentation owner')
        found[path] = 'Data/Bundles/Windows/' + bundle
    if not UI <= found.keys() or not any(path.startswith(DIALOG_GRAPHS) for path in found):
        raise ValueError('Required original UI/dialogue owners are missing')
    return found


def _index_key(identity, generation, url):
    return _sha(_json({'client': identity_stamp(identity), 'generation': generation, 'url': url}))


def _cached_index(ctx, identity, generation, common, entry):
    read, _, _, no_links = _helpers()
    path = _root(ctx) / 'index-owners' / (_index_key(identity, generation, entry['url']) + '.json')
    no_links(path)
    try:
        body = read(path)
        if (not isinstance(body, dict) or body.get('owner') != entry['owner'] or
                not re.fullmatch('[0-9a-f]{64}', body.get('sha256', ''))):
            return None
        target = _root(ctx) / 'indices' / (body['sha256'] + '.blc')
        no_links(target)
        if not target.is_file() or target.stat().st_size != entry['bytes']:
            return None
        raw = target.read_bytes()
        if _sha(raw) != body['sha256'] or _sha(raw[:HEADER]) != entry['owner']['header_sha256']:
            return None
        vfs.parse_index(raw, _params(common), entry['block'], suffix='.ab', names=frozenset())
        return raw
    except (OSError, ValueError, KeyError, TypeError):
        return None


def plan(ctx, identity, common, generation, transport):
    """Only small owner discovery; never hide a large index in plan metadata."""
    _, _, Error, _ = _helpers()
    ctx.check()
    if ctx.game != 'endfield' or ctx.request.content_mode not in {'text', 'text-audio'} or ctx.request.region != identity.get('region'):
        raise Error('invalid_game_languages', 'Choose the exact Endfield region and content selection before navigation planning.')
    base = _base(identity, common, generation, 4)
    index, _ = transport.fetch_bytes(base + common.directories[4] + '.blc', limit=SMALL_INDEX, kind='metadata')
    try:
        manifest, = vfs.parse_index(index, _params(common), 4, suffix='.hgmmap', names=frozenset({MANIFEST}))
        if (not 16 <= manifest.size <= MAX_MANIFEST or len(manifest.content_hashes) != 2 or
                not re.fullmatch('[0-9a-f]{32}', manifest.content_hashes[1])):
            raise ValueError('Original manifest ownership is invalid')
        raw = _manifest(ctx, common, manifest)
        owners = _owners(raw) if raw is not None else None
    except (ValueError, TypeError, KeyError) as error:
        raise Error('unsupported_original_navigation', 'Endfield original presentation registry failed its CRC, ownership or bounded structure checks. Existing data is retained.') from error
    entries = []
    if owners is not None:
        roles = {name.split('/')[3] for name in owners.values()}
        for role in sorted(roles):
            block = {'initial': 2, 'main': 11}[role]
            url = _base(identity, common, generation, block) + common.directories[block] + '.blc'
            header, receipt = transport.fetch_bytes(url, limit=HEADER, expected_size=HEADER, kind='metadata',
                original_range=(0, HEADER, None))
            actual = receipt.original_range
            if (not actual or actual[:2] != (0, HEADER) or type(actual[2]) is not int or
                    not HEADER <= actual[2] <= MAX_BUNDLE_INDEX):
                raise Error('publisher_range_changed', 'Endfield original bundle index has no bounded current owner.')
            owner = {'bytes': actual[2], 'header_sha256': _sha(header), 'response_etag': receipt.response_etag}
            entry = {'block': block, 'url': url, 'bytes': actual[2], 'owner': owner}
            entry['cached'] = _cached_index(ctx, identity, generation, common, entry) is not None
            entries.append(entry)
    pending = manifest.size if owners is None else sum(row['bytes'] for row in entries if not row['cached'])
    rechecks = 2 * (DETAIL_LIMIT + sum(row['index_bytes'] for row in generation['layers'].values()) + len(index) + 2 * HEADER)
    # Inflation stays in memory; it must not be presented as disk allocation.
    disk = 2 * pending + 2 * 1024**2
    return {'schema': 1, 'stage': 'original-text-manifest' if owners is None else 'original-text-navigation-indices',
        'client_sha256': identity_stamp(identity), 'generation': generation, 'request': ctx.request.json(),
        'manifest': _file(manifest), 'manifest_url': base + manifest.chunk,
        'manifest_index_sha256': _sha(index), 'manifest_index_bytes': len(index),
        'manifest_cached': owners is not None, 'indices': entries,
        'required_ui_paths': sorted(UI), 'dialog_graph_prefix': DIALOG_GRAPHS,
        'owned_ui_paths': len(UI) if owners is not None else None,
        'owned_dialog_graph_paths': len(owners) - len(UI) if owners is not None else None,
        'selected_bundle_count': len(set(owners.values())) if owners is not None else None,
        'payload_bytes': pending, 'metadata_recheck_upper': rechecks,
        'registry_working_memory_upper_bytes': MAX_REGISTRY,
        'download_bytes': pending + rechecks, 'required_disk_bytes': disk,
        'download_is_upper_bound': True}, index


def _selection(common, owners, indices):
    files = {}
    for block, raw in indices.items():
        role = 'initial' if block == 2 else 'main'
        wanted = frozenset(name for name in owners.values() if name.startswith('Data/Bundles/Windows/' + role + '/'))
        for row in vfs.parse_index(raw, _params(common), block, suffix='.ab', names=wanted):
            if row.name in files or not re.fullmatch('[0-9a-f]{32}', row.content_hashes[1]):
                raise ValueError('Repeated or unbound original bundle')
            files[row.name] = row
    if set(files) != set(owners.values()):
        raise ValueError('Original graph/UI bundle owner is missing')
    return files


def download(ctx, identity, common, approved, manifest_index, transport, *, recheck):
    _, write, Error, _ = _helpers()
    ctx.check()
    if ctx.phase != 'download' or approved.get('request') != ctx.request.json():
        raise Error('unapproved_asset_transfer', 'Approve the exact Endfield navigation stage before downloading.')
    try:
        manifest, = vfs.parse_index(manifest_index, _params(common), 4, suffix='.hgmmap', names=frozenset({MANIFEST}))
        if (_file(manifest) != approved['manifest'] or _sha(manifest_index) != approved['manifest_index_sha256'] or
                approved['client_sha256'] != identity_stamp(identity)):
            raise ValueError('Original manifest differs')
        base = _base(identity, common, approved['generation'], 4)
        if approved['manifest_url'] != base + manifest.chunk:
            raise ValueError('Original manifest URL differs')
    except (ValueError, TypeError, KeyError) as error:
        raise Error('publisher_size_changed', 'Endfield original navigation ownership differs from its approved quote.') from error
    raw = _manifest(ctx, common, manifest)
    if approved['stage'] == 'original-text-manifest':
        if raw is not None or approved['payload_bytes'] != manifest.size:
            raise Error('publisher_size_changed', 'Endfield navigation cache changed. Check the smaller download size again.')
        raw, receipt = transport.fetch_bytes(approved['manifest_url'], limit=manifest.size, expected_size=manifest.size,
            kind='asset', original_range=(manifest.offset, manifest.size, manifest.chunk_size))
        raw = vfs.chacha(raw, common.key, manifest.nonce) if manifest.nonce else raw
        if hashlib.md5(raw).hexdigest() != manifest.content_hashes[1]:
            raise Error('publisher_checksum_mismatch', 'Endfield complete original registry failed its publisher MD5.')
        try:
            _owners(raw)
        except ValueError as error:
            raise Error('unsupported_original_navigation', 'Endfield original registry lacks its required graph/UI owners.') from error
        ctx.check()
        if recheck() != (identity, approved['generation']):
            raise Error('publisher_object_changed', 'Endfield changed before navigation source publication. Existing data is retained.', 409)
        write(_root(ctx) / 'manifests' / manifest.content_hashes[1], raw)
        _store_index(ctx, approved['manifest_index_sha256'], manifest_index)
        return {'schema': 1, 'stage': 'original-text-navigation-pending',
                'manifest_md5': manifest.content_hashes[1], 'manifest_index_sha256': approved['manifest_index_sha256'],
                'manifest_transfer_receipt': receipt.json()}
    if approved['stage'] != 'original-text-navigation-indices' or raw is None:
        raise Error('invalid_local_state', 'Endfield needs its complete verified original registry before the index stage.')
    owners = _owners(raw)
    indices, controls = {}, []
    expected_roles = {name.split('/')[3] for name in owners.values()}
    expected_blocks = {2 if role == 'initial' else 11 for role in expected_roles}
    if len(approved['indices']) != len(expected_blocks) or {entry['block'] for entry in approved['indices']} != expected_blocks:
        raise Error('publisher_size_changed', 'Endfield selected graph/UI index owners differ from the quote.')
    for entry in approved['indices']:
        ctx.check()
        url = _base(identity, common, approved['generation'], entry['block']) + common.directories[entry['block']] + '.blc'
        if entry['url'] != url or entry['bytes'] != entry['owner']['bytes'] or not HEADER <= entry['bytes'] <= MAX_BUNDLE_INDEX:
            raise Error('publisher_size_changed', 'Endfield original index range differs from the quote.')
        value = _cached_index(ctx, identity, approved['generation'], common, entry)
        if value is None:
            if entry['cached']:
                raise Error('invalid_local_state', 'Endfield cached original index needs a new size plan.')
            headers = {'If-Match': entry['owner']['response_etag']} if entry['owner']['response_etag'] else None
            value, _ = transport.fetch_bytes(url, limit=entry['bytes'], expected_size=entry['bytes'], kind='metadata',
                original_range=(0, entry['bytes'], entry['bytes']), headers=headers)
            if _sha(value[:HEADER]) != entry['owner']['header_sha256']:
                raise Error('publisher_object_changed', 'Endfield original index changed after its bounded preflight.', 409)
        try:
            vfs.parse_index(value, _params(common), entry['block'], suffix='.ab', names=frozenset())
        except ValueError as error:
            raise Error('unsupported_original_navigation', 'Endfield complete original bundle index failed its CRC/type checks.') from error
        indices[entry['block']] = value
        controls.append({'block': entry['block'], 'owner': entry['owner'], 'sha256': _sha(value), 'url': url})
    try:
        files = _selection(common, owners, indices)
    except ValueError as error:
        raise Error('unsupported_original_navigation', 'Endfield selected graph/UI owners are incomplete in the original indexes.') from error
    ctx.check()
    if recheck() != (identity, approved['generation']):
        raise Error('publisher_object_changed', 'Endfield changed before complete navigation publication. Existing data is retained.', 409)
    for control in controls:
        value = indices[control['block']]
        _store_index(ctx, control['sha256'], value)
        key = _index_key(identity, approved['generation'], control['url'])
        write(_root(ctx) / 'index-owners' / (key + '.json'), _json(control))
    body = {'schema': 1, 'kind': 'endfield-original-text-navigation', 'client': identity,
        'generation': approved['generation'], 'request': ctx.request.json(), 'manifest': _file(manifest),
        'manifest_index_sha256': approved['manifest_index_sha256'],
        'manifest_url_sha256': _sha(approved['manifest_url'].encode()),
        'indices': controls, 'owned_ui_paths': len(UI), 'owned_dialog_graph_paths': len(owners) - len(UI),
        'selected_bundle_count': len(files), 'selected_bundle_payload_bytes': sum(row.size for row in files.values()),
        'selection_sha256': _sha(_json({'owners': owners, 'files': [_file(files[key]) for key in sorted(files)]})),
        'aes_header_parameters_verified': False, 'bundle_payloads_downloaded': False}
    encoded = _json(body)
    digest = _sha(encoded)
    ctx.check()
    _store_index(ctx, approved['manifest_index_sha256'], manifest_index)
    write(_root(ctx) / 'sources' / (digest + '.json'), encoded)
    return {'schema': 1, 'stage': 'original-text-navigation-verified', 'receipt_sha256': digest,
        'client_sha256': identity_stamp(identity), 'generation_sha256': _sha(_json(approved['generation'])),
        'selected_bundle_count': len(files), 'selected_bundle_payload_bytes': body['selected_bundle_payload_bytes']}
