"""Quote and retain exact original graph/UI containers, without AES admission.

The large inventory stays in a bounded private receipt, outside the service's
small handle. Each authored member survives byte-cache deduplication. Acquisition
does not establish decoded presentation ownership or a capture-ready library.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .endfield_client_source import identity_stamp
from .endfield_resource_source import DETAIL_LIMIT, _file
from . import endfield_navigation_source as navigation, endfield_vfs as vfs

MAX_FILE = 64 * 1024**2
MAX_INVENTORY = 8 * 1024**2
MAX_SOURCE = 8 * 1024**3


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
    return Path(ctx.cache_directory) / 'endfield-presentation-bundles'


def _payload(ctx, row):
    _, _, no_links = _helpers()
    path = _root(ctx) / 'assets' / row.content_hashes[1]
    no_links(path)
    if not path.is_file() or path.stat().st_size != row.size:
        return None
    raw = path.read_bytes()
    return raw if hashlib.md5(raw).hexdigest() == row.content_hashes[1] else None


def _read(ctx, folder, digest):
    _, Error, no_links = _helpers()
    if not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
        raise Error('invalid_local_state', 'Endfield source inventory has no valid immutable identity.')
    path = _root(ctx) / folder / (digest + '.json')
    no_links(path)
    try:
        if not path.is_file() or not 2 <= path.stat().st_size <= MAX_INVENTORY:
            raise ValueError('Source inventory is missing or oversized')
        raw = path.read_bytes()
        if _sha(raw) != digest:
            raise ValueError('Source inventory checksum differs')
        return json.loads(raw)
    except (OSError, ValueError) as error:
        raise Error('invalid_local_state', 'Endfield source inventory needs repair; existing prepared data is retained.') from error


def _groups(ctx, files):
    _, Error, _ = _helpers()
    groups = {}
    if sum(row.size for row in files.values()) > MAX_SOURCE:
        raise Error('source_not_prepared', 'Endfield selected original source containers exceed this preparation-stage capacity.')
    for name in sorted(files):
        ctx.check()
        row = files[name]
        if (not 16 <= row.size <= MAX_FILE or len(row.content_hashes) != 2 or
                re.fullmatch('[0-9a-f]{32}', row.content_hashes[1]) is None):
            raise Error('source_not_prepared', 'Endfield original presentation container needs a supported bounded acquisition stage.')
        key = (row.size, row.content_hashes[1])
        if key in groups:
            groups[key]['members'].append(name)
        else:
            groups[key] = {'file': _file(row), 'members': [name], 'cached': _payload(ctx, row) is not None}
    return list(groups.values())


def plan(ctx, identity, common, generation, reference, transport):
    """No container payload reads over the network; only navigation metadata."""
    write, Error, _ = _helpers()
    ctx.check()
    source, _owners, files = navigation.restore(ctx, identity, common, generation, reference)
    current, index4 = navigation.plan(ctx, identity, common, generation, transport)
    if current['stage'] != 'original-text-navigation-indices' or current['manifest'] != source['manifest']:
        raise Error('publisher_navigation_changed', 'Endfield original presentation registry changed. Recheck navigation before estimating its containers.', 409)
    groups = _groups(ctx, files)
    body = {'schema': 1, 'kind': 'endfield-presentation-container-plan', 'client': identity,
        'generation': generation, 'request': ctx.request.json(), 'navigation': reference,
        'selection_sha256': source['selection_sha256'], 'groups': groups}
    encoded = _json(body)
    if len(encoded) > MAX_INVENTORY:
        raise Error('source_not_prepared', 'Endfield source inventory exceeds this bounded preparation stage.')
    digest = _sha(encoded)
    ctx.check()
    write(_root(ctx) / 'plans' / (digest + '.json'), encoded)
    pending = sum(group['file']['size'] for group in groups if not group['cached'])
    retained = sum(group['file']['size'] for group in groups if group['cached'])
    # The current navigation plan includes two source-detail/index rechecks;
    # add the final container-stage generation recheck. Provider client/owner
    # lookup overhead is quoted separately by its ordinary adapter.
    rechecks = current['metadata_recheck_upper'] + DETAIL_LIMIT + sum(row['index_bytes'] for row in generation['layers'].values())
    result = {'schema': 1, 'stage': 'original-presentation-containers', 'request': ctx.request.json(),
        'client_sha256': identity_stamp(identity), 'generation': generation, 'navigation': reference,
        'navigation_recheck': current, 'inventory_sha256': digest,
        'selected_member_count': len(files), 'unique_payload_count': len(groups),
        'payload_bytes': pending, 'retained_verified_bytes': retained,
        'navigation_recheck_payload_bytes': current['payload_bytes'], 'metadata_recheck_upper': rechecks,
        'download_bytes': pending + current['payload_bytes'] + rechecks,
        'required_disk_bytes': 2 * pending + current['required_disk_bytes'] + 2 * len(encoded),
        'download_is_upper_bound': True, 'decoded_library_bytes': None,
        'mixed_container_overhead': 'Original selected source containers may include other bundled data; no dedicated audio packs are requested.'}
    return result, index4


def download(ctx, identity, common, approved, transport, *, recheck):
    write, Error, _ = _helpers()
    ctx.check()
    if ctx.phase != 'download' or approved.get('request') != ctx.request.json():
        raise Error('unapproved_asset_transfer', 'Approve the exact Endfield presentation-source download first.')
    inventory = _read(ctx, 'plans', approved.get('inventory_sha256'))
    if (inventory.get('client') != identity or inventory.get('generation') != approved['generation'] or
            inventory.get('request') != ctx.request.json() or inventory.get('navigation') != approved['navigation']):
        raise Error('invalid_local_state', 'Endfield source quote belongs to another client, generation or selection.')
    current, index4 = plan(ctx, identity, common, approved['generation'], approved['navigation'], transport)
    if current != approved:
        raise Error('publisher_size_changed', 'Endfield original source inventory, navigation or verified cache changed. Check its size again.')
    fresh = navigation.download(ctx, identity, common, approved['navigation_recheck'], index4, transport, recheck=recheck)
    fresh_source, _owners, files = navigation.restore(ctx, identity, common, approved['generation'], fresh)
    # A valid changed body behind the same weak/unavailable validator must get
    # a new source quote, before downloading any previously selected container.
    if fresh_source['selection_sha256'] != inventory['selection_sha256']:
        return {'stage': 'original-text-navigation-verified', 'navigation': fresh, 'selection_changed': True}
    if _groups(ctx, files) != inventory['groups']:
        raise Error('publisher_size_changed', 'Endfield source members or verified payload cache changed after navigation validation.')
    transfers = []
    for group in inventory['groups']:
        ctx.check()
        row = files[group['members'][0]]
        if _file(row) != group['file']:
            raise Error('publisher_size_changed', 'Endfield original source member differs from its quote.')
        raw = _payload(ctx, row)
        if raw is not None:
            continue
        if group['cached']:
            raise Error('invalid_local_state', 'A verified Endfield source container needs a new download plan.')
        block = 2 if row.name.startswith('Data/Bundles/Windows/initial/') else 11
        base = navigation._base(identity, common, approved['generation'], block)
        raw, receipt = transport.fetch_bytes(base + row.chunk, limit=row.size, expected_size=row.size,
            kind='asset', original_range=(row.offset, row.size, row.chunk_size))
        raw = vfs.chacha(raw, common.key, row.nonce) if row.nonce else raw
        if hashlib.md5(raw).hexdigest() != row.content_hashes[1]:
            raise Error('publisher_checksum_mismatch', 'Endfield complete original presentation container failed its publisher MD5.')
        ctx.check()
        write(_root(ctx) / 'assets' / row.content_hashes[1], raw)
        transfers.append({'md5': row.content_hashes[1], 'members': group['members'], 'receipt': receipt.json()})
    ctx.check()
    if recheck() != (identity, approved['generation']):
        raise Error('publisher_object_changed', 'Endfield changed before presentation-source publication. Existing prepared data is retained.', 409)
    body = {'schema': 1, 'kind': 'endfield-original-presentation-containers', 'client': identity,
        'generation': approved['generation'], 'request': ctx.request.json(), 'navigation': fresh,
        'selection_sha256': inventory['selection_sha256'], 'members': [_file(files[name]) for name in sorted(files)],
        'transfers': transfers, 'aes_header_parameters_verified': False, 'canonical_snapshot_prepared': False}
    encoded = _json(body)
    if len(encoded) > MAX_INVENTORY:
        raise Error('source_not_prepared', 'Endfield complete source receipt exceeds this bounded stage.')
    digest = _sha(encoded)
    ctx.check()
    write(_root(ctx) / 'sources' / (digest + '.json'), encoded)
    return {'schema': 1, 'stage': 'original-presentation-containers-downloaded',
        'receipt_sha256': digest, 'client_sha256': identity_stamp(identity),
        'generation_sha256': _sha(_json(approved['generation'])), 'navigation': fresh,
        'selected_member_count': len(files), 'unique_payload_count': len(inventory['groups'])}


def restore(ctx, identity, common, generation, reference):
    """Exact original container source only; no decoder or Ready admission."""
    _, Error, _ = _helpers()
    ctx.check()
    if (not isinstance(reference, dict) or reference.get('schema') != 1 or
            reference.get('stage') != 'original-presentation-containers-downloaded' or
            reference.get('client_sha256') != identity_stamp(identity) or
            reference.get('generation_sha256') != _sha(_json(generation))):
        raise Error('invalid_local_state', 'Endfield original containers belong to another source identity.')
    body = _read(ctx, 'sources', reference.get('receipt_sha256'))
    if (body.get('client') != identity or body.get('generation') != generation or body.get('request') != ctx.request.json() or
            body.get('kind') != 'endfield-original-presentation-containers' or body.get('navigation') != reference['navigation']):
        raise Error('invalid_local_state', 'Endfield original container receipt differs from its exact source.')
    source, owners, files = navigation.restore(ctx, identity, common, generation, reference['navigation'])
    if (body['selection_sha256'] != source['selection_sha256'] or
            body['members'] != [_file(files[name]) for name in sorted(files)]):
        raise Error('invalid_local_state', 'Endfield original container member ownership differs.')
    for group in _groups(ctx, files):
        if not group['cached']:
            raise Error('invalid_local_state', 'Endfield complete original presentation container is missing or changed.')
    ctx.check()
    return body, owners, files
