"""Current original resource generations and a separately quoted bank control.

Every I/O operation uses the caller's explicit preparation transport. The bank
control is an original audio acquisition, never planning metadata or text mode.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import re
from urllib.parse import urlencode

from .endfield_client_source import identity_stamp
from .endfield_game_data import CHANNELS
from . import endfield_vfs as vfs

DETAIL_LIMIT = 2 * 1024**2
INDEX_LIMIT = 8 * 1024**2


def _error():
    from .game_data_protocol import GameDataError
    return GameDataError


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _file(row):
    value = asdict(row)
    value['nonce'] = row.nonce.hex() if row.nonce is not None else None
    value['content_hashes'] = list(row.content_hashes)
    return value


def discover(ctx, identity, transport):
    Error = _error()
    ctx.check()
    region, version = identity['region'], identity['version']
    launcher, app, _, _, host = CHANNELS[region]
    minor = version.rsplit('.', 1)[0]
    suffix = identity['url'].rsplit('/', 2)[1].removeprefix(version + '_')
    query = urlencode(dict(appcode=app, game_version=minor, version=version, platform='Windows', rand_str=suffix))
    raw, _ = transport.fetch_bytes('https://' + launcher + '/api/game/get_latest_resources?' + query,
                                    limit=DETAIL_LIMIT, kind='metadata')
    try:
        result = json.loads(raw)
        rows = result['resources']
        if not isinstance(rows, list) or len(rows) > 256:
            raise ValueError('Original resource list is invalid')
        layers = {}
        for row in rows:
            role = row['name']
            if role not in {'initial', 'main'}:
                continue
            base = row['path']
            if (role in layers or not isinstance(base, str) or re.fullmatch(
                    re.escape('https://' + host + '/' + app + '/' + minor + '/resource/Windows/' + role + '/') +
                    r'[0-9]+-[0-9]+_[A-Za-z0-9]+/files', base) is None or
                    base.rsplit('/', 2)[1].split('_', 1)[0] != row['version']):
                raise ValueError('Original resource generation is invalid')
            index, _ = transport.fetch_bytes(base + '/index_' + role + '.json', limit=INDEX_LIMIT, kind='metadata')
            if len(index) < 32:
                raise ValueError('Original complete resource index is truncated')
            layers[role] = {'url': base, 'version': row['version'], 'sha256': hashlib.sha256(index).hexdigest(),
                            'index_bytes': len(index)}
        if set(layers) != {'initial', 'main'}:
            raise ValueError('Original resource generation is incomplete')
    except (ValueError, TypeError, KeyError) as error:
        raise Error('publisher_response_invalid', 'Endfield returned an incomplete original resource generation.') from error
    return {'client_sha256': identity_stamp(identity), 'region': region, 'layers': layers}


def control_plan(ctx, identity, common, generation, transport):
    from .endfield_akpk_witness import voice_block
    from .endfield_akpk_controls import MAX_CONTROL
    Error = _error()
    ctx.check()
    if ctx.game != 'endfield' or ctx.request.content_mode != 'text-audio':
        raise Error('audio_not_requested', 'Endfield original audio controls require the audio selection.')
    block = voice_block(ctx.request.source_locale)
    if block not in common.directories or generation.get('client_sha256') != identity_stamp(identity):
        raise Error('unverified_original_source', 'Endfield original audio index has no current client owner.')
    params = vfs.IndexParameters(common.key, common.directories, common.protocol)
    directory = params.directories[block]
    base = generation['layers']['main']['url'] + '/VFS/' + directory + '/'
    raw, _ = transport.fetch_bytes(base + directory + '.blc', limit=vfs.MAX_INDEX, kind='metadata')
    try:
        files = vfs.parse_index(raw, params, block)
    except ValueError as error:
        raise Error('unsupported_game_format', 'Endfield original audio index failed its CRC or structure check.') from error
    # Pick a complete small authored bank package in the selected official dub.
    # Names do not bind dialogue; these are crypto/format controls only.
    options = [row for row in files if row.name.rsplit('/', 1)[-1].endswith('_banks.pck') and
               12 <= row.size <= MAX_CONTROL and len(row.content_hashes) == 2 and
               re.fullmatch('[0-9a-f]{32}', row.content_hashes[1]) and
               re.fullmatch(r'[0-9A-F]{32}\.chk', row.chunk)]
    if not options:
        raise Error('source_not_prepared', 'Endfield has no bounded complete original bank control for this voice language.')
    selected = sorted(options, key=lambda row: (row.size, row.name, row.chunk, row.offset))[0]
    plan = {'schema': 1, 'stage': 'original-audio-package-control', 'generation': generation,
            'block': block, 'directory': directory, 'index_sha256': hashlib.sha256(raw).hexdigest(),
            'index_bytes': len(raw), 'file': _file(selected), 'url': base + selected.chunk,
            'payload_bytes': selected.size,
            'metadata_recheck_upper': 2 * (DETAIL_LIMIT + sum(row['index_bytes'] for row in generation['layers'].values()) + len(raw)),
            'required_disk_bytes': 2 * selected.size + 256 * 1024}
    plan['download_bytes'] = selected.size + plan['metadata_recheck_upper']
    plan['download_is_upper_bound'] = True
    return plan, raw


def download_control(ctx, identity, common, plan, index, transport):
    from .endfield_akpk_witness import voice_block
    from .endfield_akpk_controls import MAX_CONTROL
    Error = _error()
    ctx.check()
    if ctx.phase != 'download' or ctx.request.content_mode != 'text-audio':
        raise Error('unapproved_asset_transfer', 'Approve the Endfield original audio control download first.')
    block = voice_block(ctx.request.source_locale)
    try:
        params = vfs.IndexParameters(common.key, common.directories, common.protocol)
        files = vfs.parse_index(index, params, block)
        matches = [row for row in files if _file(row) == plan['file']]
        if (plan['block'] != block or plan['generation']['client_sha256'] != identity_stamp(identity) or
                hashlib.sha256(index).hexdigest() != plan['index_sha256'] or len(matches) != 1):
            raise ValueError('Control ownership changed')
        selected = matches[0]
        directory = common.directories[block]
        expected = plan['generation']['layers']['main']['url'] + '/VFS/' + directory + '/' + selected.chunk
        if expected != plan['url'] or not 12 <= selected.size <= MAX_CONTROL or selected.size != plan['payload_bytes']:
            raise ValueError('Control payload changed')
    except (ValueError, KeyError, TypeError) as error:
        raise Error('publisher_size_changed', 'Endfield original package control differs from its quote.') from error
    raw, _ = transport.fetch_bytes(expected, limit=selected.size, expected_size=selected.size, kind='audio',
        original_range=(selected.offset, selected.size, selected.chunk_size))
    payload = vfs.chacha(raw, common.key, selected.nonce) if selected.nonce else raw
    if hashlib.md5(payload).hexdigest() != selected.content_hashes[1]:
        raise Error('publisher_checksum_mismatch', 'Endfield complete original audio control failed its publisher MD5.')
    ctx.check()
    return selected, payload
