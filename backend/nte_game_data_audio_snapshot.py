"""Immutable original audio sources; historical restore has no publisher lookup."""
import json
import os
import re

from . import nte_game_data_snapshot as text
from .game_data_protocol import GameDataError, GameDataRequest, SnapshotSource, SourceProof
from .private_data_paths import MAX_ROWS, MAX_TEXT, _no_links
from .nte_game_data_voice import OriginalVoiceSource, binding, codecs, DUBS

SCHEMA = 'nte-original-audio-snapshot-v1'
PROFILE = 'nte-original-audio-profile-v1'
MAX_ORIGINALS = 32*1024**2


def _failure():
    return GameDataError('nte_audio_source_invalid',
        'The downloaded NTE audio library could not be verified. Your previous library and history are retained.', 409)


def _payload(payload, request):
    if (not isinstance(payload, dict) or payload.get('format') != 2 or payload.get('game') != 'nte'
            or payload.get('source_locale') != request['source_locale'] or payload.get('content_mode') != 'text-audio'
            or payload.get('source_mode') != 'publisher' or payload.get('source_region') != request['region']
            or payload.get('install') is not None or payload.get('targets_requested') != request['target_locales']
            or payload.get('missing_translation_locales') != [] or not isinstance(payload.get('records'), list)
            or not 0 < len(payload['records']) <= MAX_ROWS): raise _failure()
    for row in payload['records']:
        if (not isinstance(row, dict) or row.get('audio_omitted_by_request')
                or row.get('source_locale') != request['source_locale'] or not isinstance(row.get('texts'), dict)
                or row['texts'].get(request['source_locale']) != row.get('source_text')): raise _failure()


def _originals(value, payload, request, recipe):
    if (not isinstance(value, dict) or set(value) != {'schema', 'request', 'recipe_sha256', 'files', 'bindings', 'codecs'}
            or value['schema'] != SCHEMA or value['request'] != request or value['recipe_sha256'] != recipe
            or not isinstance(value['files'], dict) or len(value['files']) > 100000
            or not isinstance(value['codecs'], dict)): raise _failure()
    prefix = 'HT/Content/WwiseAudio/Media/'+DUBS[request['source_locale']]+'/'
    for path, item in value['files'].items():
        if (not isinstance(path, str) or not path.startswith(prefix) or re.fullmatch(r'[0-9]+\.wem', path[len(prefix):]) is None
                or not isinstance(item, dict) or set(item) != {'sha256', 'bytes', 'member_sha256'}
                or any(not isinstance(item[key], str) or text.HEX.fullmatch(item[key]) is None for key in ('sha256', 'member_sha256'))
                or type(item['bytes']) is not int or not 12 <= item['bytes'] <= 512*1024**2): raise _failure()
    needed = {row['audio']['depot'] for row in payload['records'] if row.get('audio')}
    expected = sorted({binding(row) for row in payload['records'] if row.get('audio')})
    if set(value['files']) != needed or value['bindings'] != expected: raise _failure()


def publish(payload, inputs, original_receipt, object_paths, ctx, layout, write):
    ctx.check(); request = ctx.request.json()
    if request['content_mode'] != 'text-audio': raise _failure()
    text._inputs(inputs); _payload(payload, request)
    _originals(original_receipt, payload, request, inputs['recipe_sha256'])
    if codecs(layout)[1] != original_receipt['codecs']: raise _failure()
    original_raw = text._json(original_receipt)
    if len(original_raw) > MAX_ORIGINALS: raise _failure()
    profile = {'schema': PROFILE, 'request': request, 'inputs': inputs,
        'body_sha256': text._hash(text._json(text._body(payload))), 'originals_sha256': text._hash(original_raw)}
    profile_raw = text._json(profile)
    if len(profile_raw) > text.MAX_PROFILE: raise _failure()
    identity = text._hash(profile_raw); payload['fingerprint'] = 'nte-'+identity
    raw = text._json(payload)
    if not 0 < len(raw) <= MAX_TEXT: raise _failure()
    receipt = {'schema': SCHEMA, 'profile_sha256': identity, 'snapshot_sha256': text._hash(raw),
        'recipe_sha256': inputs['recipe_sha256'], 'request_sha256': text._hash(text._json(request)),
        'body_sha256': profile['body_sha256'], 'originals_sha256': profile['originals_sha256'],
        'origin': 'official', 'publisher_content_verified': True}
    receipt_raw = text._json(receipt)
    handle = {'schema': SCHEMA, 'profile': identity, 'receipt': text._hash(receipt_raw),
        'snapshot': receipt['snapshot_sha256'], 'recipe': inputs['recipe_sha256'], 'originals': profile['originals_sha256']}
    with ctx.transfer_lock:
        ctx.check(); root = ctx.directory/'originals'; _no_links(root); root.mkdir()
        for item in original_receipt['files'].values():
            destination = root/(item['sha256']+'.wem')
            source = object_paths[item['sha256']]; _no_links(source); _no_links(destination)
            if not destination.exists(): os.link(source, destination)
        for name, data in (('textmap.json', raw), ('nte-source-profile.json', profile_raw),
                ('nte-audio-originals.json', original_raw), ('nte-source-receipt.json', receipt_raw)):
            path = ctx.directory/name; _no_links(path); write(path, data)
        ctx.check()
    return restore(handle, ctx, layout)


def restore(handle, ctx, layout):
    ctx.check()
    try:
        if (not isinstance(handle, dict) or set(handle) != {'schema', 'profile', 'receipt', 'snapshot', 'recipe', 'originals'}
                or handle['schema'] != SCHEMA or any(not isinstance(handle[key], str) or text.HEX.fullmatch(handle[key]) is None
                    for key in set(handle)-{'schema'})): raise _failure()
        request = ctx.request.json()
        if request['content_mode'] != 'text-audio': raise _failure()
        values = {}
        for name, key, limit in (('nte-source-profile.json', 'profile', text.MAX_PROFILE),
                ('nte-source-receipt.json', 'receipt', 256*1024), ('textmap.json', 'snapshot', MAX_TEXT),
                ('nte-audio-originals.json', 'originals', MAX_ORIGINALS)):
            path = ctx.directory/name; _no_links(path)
            if not path.is_file() or not 0 < path.stat().st_size <= limit: raise _failure()
            raw = path.read_bytes()
            if text._hash(raw) != handle[key]: raise _failure()
            values[key] = json.loads(raw)
        profile, receipt, payload, originals = (values[key] for key in ('profile', 'receipt', 'snapshot', 'originals'))
        if (not isinstance(profile, dict) or set(profile) != {'schema', 'request', 'inputs', 'body_sha256', 'originals_sha256'}
                or profile['schema'] != PROFILE or GameDataRequest.parse(profile['request']).json() != request
                or profile['request'] != request or profile['originals_sha256'] != handle['originals']): raise _failure()
        text._inputs(profile['inputs']); _payload(payload, request)
        _originals(originals, payload, request, handle['recipe'])
        body = text._hash(text._json(text._body(payload)))
        expected = {'schema': SCHEMA, 'profile_sha256': handle['profile'], 'snapshot_sha256': handle['snapshot'],
            'recipe_sha256': handle['recipe'], 'request_sha256': text._hash(text._json(request)),
            'body_sha256': body, 'originals_sha256': handle['originals'], 'origin': 'official', 'publisher_content_verified': True}
        if (receipt != expected or profile['body_sha256'] != body
                or profile['inputs']['recipe_sha256'] != handle['recipe']
                or payload.get('fingerprint') != 'nte-'+handle['profile'] or codecs(layout)[1] != originals['codecs']): raise _failure()
        voice = OriginalVoiceSource(ctx, payload, originals['files'], originals['codecs'], layout)
        if not all(voice.has(row) for row in payload['records'] if row.get('audio')): raise _failure()
        ctx.check()
        return SnapshotSource(ctx.directory/'textmap.json', handle, SourceProof('official', handle['receipt'], True), voice)
    except GameDataError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        raise _failure() from error
