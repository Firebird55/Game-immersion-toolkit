"""Self-contained NTE text source receipts; restore has no native/network path."""
import hashlib
import json
import re

from .game_data_protocol import GameDataError, GameDataRequest, SnapshotSource, SourceProof
from .private_data_paths import MAX_ROWS, MAX_TEXT, _no_links

SCHEMA = 'nte-original-text-snapshot-v1'
PROFILE = 'nte-original-text-profile-v1'
MAX_PROFILE = 1024**2
HEX = re.compile('[0-9a-f]{64}')
INPUTS = {'recipe_sha256', 'metadata_receipt_sha256', 'authoring_receipt_sha256',
          'native_validation_sha256', 'reader', 'initial_descriptions'}


def _failure():
    return GameDataError('nte_text_source_invalid',
        'The prepared NTE text library could not be verified. Your previous library and history are retained.', 409)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _inputs(value):
    if not isinstance(value, dict) or set(value) != INPUTS: raise _failure()
    if any(not isinstance(value[key], str) or HEX.fullmatch(value[key]) is None for key in INPUTS-{'reader', 'initial_descriptions'}):
        raise _failure()
    reader = value['reader']
    if (not isinstance(reader, dict) or set(reader) != {'kind', 'source_sha256', 'dependencies_sha256'}
            or not isinstance(reader['kind'], str) or re.fullmatch('[a-z0-9_-]{1,80}', reader['kind']) is None
            or any(not isinstance(reader[key], str) or HEX.fullmatch(reader[key]) is None
                   for key in ('source_sha256', 'dependencies_sha256'))): raise _failure()
    initial = value['initial_descriptions']
    if (not isinstance(initial, dict) or set(initial) != {'archive', 'localization', 'seed'}
            or any(not isinstance(item, str) or HEX.fullmatch(item) is None for item in initial.values())):
        raise _failure()


def _body(payload):
    return {key: value for key, value in payload.items() if key != 'fingerprint'}


def _payload(payload, request):
    if (not isinstance(payload, dict) or payload.get('format') != 2 or payload.get('game') != 'nte'
            or payload.get('source_locale') != request['source_locale'] or payload.get('content_mode') != 'text'
            or payload.get('source_mode') != 'publisher' or payload.get('source_region') != request['region']
            or payload.get('install') is not None or payload.get('targets_requested') != request['target_locales']
            or payload.get('missing_translation_locales') != []
            or not isinstance(payload.get('records'), list) or not 0 < len(payload['records']) <= MAX_ROWS):
        raise _failure()
    for row in payload['records']:
        if (not isinstance(row, dict) or row.get('audio') is not None or row.get('audio_omitted_by_request') is not True
                or row.get('source_locale') != request['source_locale'] or not isinstance(row.get('texts'), dict)
                or row['texts'].get(request['source_locale']) != row.get('source_text')):
            raise _failure()


def publish(payload, inputs, ctx, write):
    """Called only after original-source/format verification by the producer."""
    ctx.check(); _inputs(inputs)
    request = ctx.request.json()
    if request['content_mode'] != 'text': raise _failure()
    _payload(payload, request)
    profile = {'schema': PROFILE, 'request': request, 'inputs': inputs, 'body_sha256': _hash(_json(_body(payload)))}
    profile_raw = _json(profile)
    if len(profile_raw) > MAX_PROFILE: raise _failure()
    identity = _hash(profile_raw)
    payload['fingerprint'] = 'nte-'+identity
    raw = _json(payload)
    if not 0 < len(raw) <= MAX_TEXT: raise _failure()
    receipt = {'schema': SCHEMA, 'profile_sha256': identity, 'snapshot_sha256': _hash(raw),
        'recipe_sha256': inputs['recipe_sha256'], 'request_sha256': _hash(_json(request)),
        'body_sha256': profile['body_sha256'], 'origin': 'official', 'publisher_content_verified': True}
    receipt_raw = _json(receipt)
    handle = {'schema': SCHEMA, 'profile': identity, 'receipt': _hash(receipt_raw),
        'snapshot': receipt['snapshot_sha256'], 'recipe': inputs['recipe_sha256']}
    with ctx.transfer_lock:
        ctx.check(); _no_links(ctx.directory)
        for name, data in (('textmap.json', raw), ('nte-source-profile.json', profile_raw), ('nte-source-receipt.json', receipt_raw)):
            path = ctx.directory/name; _no_links(path); write(path, data)
        ctx.check()
    return restore(handle, ctx)


def restore(handle, ctx):
    """Historical local playback needs only its exact snapshot/profile/receipt."""
    ctx.check()
    try:
        if (not isinstance(handle, dict) or set(handle) != {'schema', 'profile', 'receipt', 'snapshot', 'recipe'}
                or handle['schema'] != SCHEMA or any(not isinstance(handle[key], str) or HEX.fullmatch(handle[key]) is None
                    for key in ('profile', 'receipt', 'snapshot', 'recipe'))): raise _failure()
        request = ctx.request.json()
        if request['content_mode'] != 'text': raise _failure()
        values = {}
        for name, key, limit in (('nte-source-profile.json', 'profile', MAX_PROFILE),
                ('nte-source-receipt.json', 'receipt', 256*1024), ('textmap.json', 'snapshot', MAX_TEXT)):
            path = ctx.directory/name; _no_links(path)
            if not path.is_file() or not 0 < path.stat().st_size <= limit: raise _failure()
            raw = path.read_bytes()
            if _hash(raw) != handle[key]: raise _failure()
            values[key] = json.loads(raw)
        profile, receipt, payload = values['profile'], values['receipt'], values['snapshot']
        if (not isinstance(profile, dict) or set(profile) != {'schema', 'request', 'inputs', 'body_sha256'}
                or profile['schema'] != PROFILE or GameDataRequest.parse(profile['request']).json() != request
                or profile['request'] != request): raise _failure()
        _inputs(profile['inputs']); _payload(payload, request)
        body = _hash(_json(_body(payload)))
        expected = {'schema': SCHEMA, 'profile_sha256': handle['profile'], 'snapshot_sha256': handle['snapshot'],
            'recipe_sha256': handle['recipe'], 'request_sha256': _hash(_json(request)),
            'body_sha256': body, 'origin': 'official', 'publisher_content_verified': True}
        if (receipt != expected or profile['body_sha256'] != body
                or profile['inputs']['recipe_sha256'] != handle['recipe']
                or payload.get('fingerprint') != 'nte-'+handle['profile']): raise _failure()
        ctx.check()
        return SnapshotSource(ctx.directory/'textmap.json', handle, SourceProof('official', handle['receipt'], True))
    except GameDataError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        raise _failure() from error
