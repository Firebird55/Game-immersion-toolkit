"""Desktop-only immutable NTE materialization, separate from discovery recipes.

Portable exports retain only the resolved snapshot's opaque fingerprint. They do
not import this module or carry keys, schemas, profiles or desktop receipts.
"""
import hashlib
import json
from pathlib import Path
import re
import struct

from .game_tools import _atomic_file
from .local_game import dialogue_voice_status, dialogue_audio_scope, dialogue_capture_channels
from .preparation_errors import PreparationFailure

SNAPSHOT = 'nte-materialized-publisher-v1'
PROFILE = 'nte-materialized-metadata-v1'
RECEIPT = 'nte-materialized-approval-v1'
LIMIT = 4 * 1024**2


def _check(condition):
    if not condition:
        raise PreparationFailure('game_metadata_unavailable',
            'Compatible NTE information for this library is missing or could not be verified. '
            'Prepare or repair the game data, then retry; the previous completed library is retained.')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _decode(raw):
    def unique(rows):
        result = {}
        for key, value in rows:
            _check(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def _digest(value):
    _check(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value))
    return value


def _stamp(value):
    _check(isinstance(value, str) and re.fullmatch('nte-[0-9a-f]{64}', value))
    return value


def policy(*, allow_community_fallback=False):
    from . import nte_community_metadata as community
    body = {'schema': 'nte-hybrid-policy-v1',
            'sources': {family: list(spec) for family, spec in community.SOURCES.items()},
            'community_fallback': ('research-opt-in' if allow_community_fallback else
                                   'disabled-pending-official-first-validation'),
            'validation': 'nte-original-generation-required-closure-v1'}
    return {'sha256': _sha(_json(body)), 'description': body}


def check_policy(value):
    _check(isinstance(value, dict) and set(value) == {'sha256', 'description'})
    _check(isinstance(value['description'], dict)
           and _digest(value['sha256']) == _sha(_json(value['description']))
           and value['description'].get('schema') == 'nte-hybrid-policy-v1')
    return value


def dataset_sha256(payload):
    """Bind authored records while normalizing the index's three derived fields.

    The resolved publisher ID is replaced by its discovery recipe to avoid a
    circular snapshot hash. Callers separately require every actual audio ID to
    name the exact resolved snapshot. No record text or source binding is dropped.
    """
    header = {key: payload.get(key) for key in ('game', 'source_locale', 'source_region')}
    mode = payload.get('content_mode', 'text-audio')
    _check(mode in ('text', 'text-audio'))
    if mode == 'text':
        header['content_mode'] = mode
    digest = hashlib.sha256(_json(header))
    rows = payload.get('records')
    _check(isinstance(rows, list) and 0 < len(rows) <= 1_000_000)
    recipe = _stamp(payload['fingerprint'])
    for original in rows:
        _check(isinstance(original, dict))
        row = dict(original)
        audio = row.get('audio')
        if audio is not None:
            _check(isinstance(audio, dict))
            row['audio'] = {**audio, 'publisher': recipe}
        omitted = row.get('audio_omitted_by_request', False)
        binding = row.get('source_voice_binding')
        _check(not omitted or mode == 'text')
        _check(mode != 'text' or not audio)
        row['voice_status'] = dialogue_voice_status(audio, row.get('voice_status'),
            audio_omitted_by_request=omitted, source_voice_binding=binding)
        if omitted:
            row.update(audio_omitted_by_request=True, source_voice_binding=binding)
        else:
            # Newly added consumer defaults must not invalidate immutable
            # libraries approved before the optional omission fields existed.
            row.pop('audio_omitted_by_request', None)
            if binding is None:
                row.pop('source_voice_binding', None)
        row['audio_scope'] = dialogue_audio_scope(audio, row.get('audio_scope', 'line'))
        row['channels'] = sorted(dialogue_capture_channels(row.get('channels')))
        raw = _json(row)
        digest.update(struct.pack('<I', len(raw))); digest.update(raw)
    return digest.hexdigest()


def native_evidence(recipe, proof, cache):
    from . import nte_native_metadata as metadata, nte_native_provider as provider
    _check(isinstance(proof, tuple) and len(proof) == 2)
    schema, validation = proof
    candidate = metadata.load(schema, Path(cache)/'native-candidates')
    raw = (Path(cache)/'native-candidates/validations'/(_digest(validation)+'.json')).read_bytes()
    _check(0 < len(raw) <= LIMIT and _sha(raw) == validation)
    value = _decode(raw)
    inventory = provider.discovery(recipe)
    _check(value.get('required_schema_eligible') is True and value.get('schema') == schema
           and value.get('reader_sha256') == recipe['reader']
           and value.get('report', {}).get('client_sha256') == candidate.receipt['native_sha256']
           and value['report'].get('schema_sha256') == schema['sha256']
           and candidate.receipt['source_manifest_sha256'] == _sha(metadata._json(inventory))
           and candidate.receipt['dependencies']['reader'] == recipe['reader'])
    name = candidate.receipt['native_path']
    _check(name in inventory['files'] and candidate.receipt['native_file'] == inventory['files'][name])
    return {'reader_sha256': recipe['reader'], 'inventory_sha256': _sha(metadata._json(inventory)),
            'native_sha256': candidate.receipt['native_sha256'], 'native_path': name,
            'native_file': candidate.receipt['native_file'], 'schema': schema,
            'validation_sha256': validation}


def _publish(path, raw):
    _check(len(raw) <= LIMIT)
    if path.exists():
        _check(path.is_file() and path.read_bytes() == raw)
        return
    _atomic_file(path, raw)


def publish(tools, recipe_id, recipe, payload, native, materials):
    """Publish the snapshot marker last, after full caller-side source checks."""
    _check('nte-'+_sha(_json(recipe)) == _stamp(recipe_id) and payload['fingerprint'] == recipe_id)
    check_policy(recipe['metadata_policy'])
    cache = Path(tools)/'nte-publisher'
    _check(native == native_evidence(recipe, (native['schema'], native['validation_sha256']), cache))
    check_materials(recipe, native, materials, cache)
    profile = {'schema': PROFILE, 'recipe': recipe_id, 'policy_sha256': recipe['metadata_policy']['sha256'],
               'native': native, 'materials': materials, 'source_locale': payload['source_locale'],
               'source_region': payload['source_region'], 'dataset_sha256': dataset_sha256(payload)}
    raw = _json(profile); profile_hash = _sha(raw)
    receipt = {'schema': RECEIPT, 'recipe': recipe_id, 'profile_sha256': profile_hash,
               'inventory_sha256': native['inventory_sha256'], 'reader_sha256': native['reader_sha256'],
               'native_sha256': native['native_sha256'], 'dataset_sha256': profile['dataset_sha256']}
    approval = _json(receipt); receipt_hash = _sha(approval)
    header = {'schema': 2, 'kind': SNAPSHOT, 'recipe': recipe_id,
              'profile_sha256': profile_hash, 'receipt_sha256': receipt_hash}
    encoded = _json(header); snapshot_id = 'nte-'+_sha(encoded)
    root = Path(tools)/'nte-publisher'
    _publish(root/'metadata-profiles'/(profile_hash+'.json'), raw)
    _publish(root/'metadata-profiles/receipts'/(receipt_hash+'.json'), approval)
    _publish(root/snapshot_id/'release.json', encoded)
    return snapshot_id


def _read(path, digest):
    _check(path.is_file() and 0 < path.stat().st_size <= LIMIT)
    raw = path.read_bytes()
    _check(_sha(raw) == _digest(digest))
    return _decode(raw)


def check_materials(recipe, native, materials, cache):
    """Every selected description retains its same-original immutable proof."""
    from . import nte_community_metadata as community, nte_release as release
    from .nte_archive_metadata import LIMIT as SOURCE_LIMIT
    _check(isinstance(materials, dict) and set(materials) == {'archive', 'localization', 'updater'})
    original = {'region': recipe['region'], 'branch': recipe['branch'], 'version': recipe['version'],
                'sha256': native['inventory_sha256']}
    archive = materials['archive']
    _check(isinstance(archive, dict) and 0 < len(archive) <= 128)
    for digest, binding in archive.items():
        _check(isinstance(binding, dict) and set(binding) ==
               {'archive', 'signature', 'guid', 'index_sha256', 'metadata', 'key_sha256'})
        names = [name for name, item in recipe['files'].items()
                 if item == binding['archive'] and name.endswith('.pak')]
        _check(len(names) == 1 and recipe['files'].get(names[0][:-4]+'.sig') == binding['signature']
               and binding['archive']['digest'] == digest
               and isinstance(binding['guid'], str) and re.fullmatch('[0-9a-f]{32}', binding['guid']))
        for name in ('index_sha256', 'key_sha256'):
            _digest(binding[name])
        ref = community.reference(binding['metadata']['source'])
        _check(ref['family'] == 'archive')
        proof = community.check_receipt(binding['metadata'], original, Path(cache)/'format/community')
        _check(proof['verification'] == {'kind': 'archive-index', 'sha256': binding['index_sha256']})
        # Historical playback is entirely local: never repair a missing source
        # by consulting latest metadata during a supposedly available snapshot.
        path = Path(cache)/'format/community/sources/archive'/(ref['sha256']+'.data')
        _check(path.is_file() and 0 < path.stat().st_size <= SOURCE_LIMIT
               and _sha(path.read_bytes()) == ref['sha256'])
    localization = materials['localization']
    _check(isinstance(localization, dict) and 0 < len(localization) <= 32)
    for name, binding in localization.items():
        _check(isinstance(name, str) and re.fullmatch(r'HT/Content/Localization/Game/[A-Za-z-]+/Game.locres', name)
               and isinstance(binding, dict) and set(binding) == {'archive', 'member_sha256', 'metadata', 'key_required'}
               and binding['archive'] in recipe['files'] and binding['archive'].endswith('.pak'))
        _digest(binding['member_sha256'])
        _check(type(binding['key_required']) is bool)
        if not binding['key_required']:
            _check(binding['metadata'] is None)
            continue
        ref = community.reference(binding['metadata']['source'])
        _check(ref['family'] == 'localization')
        proof = community.check_receipt(binding['metadata'], original, Path(cache)/'format/community')
        _check(proof['verification'] == {'kind': 'localization', 'sha256': binding['member_sha256']})
        path = Path(cache)/'format/community/sources/localization'/(ref['sha256']+'.data')
        _check(path.is_file() and 0 < path.stat().st_size <= SOURCE_LIMIT
               and _sha(path.read_bytes()) == ref['sha256'])
    if 'updater_metadata' in recipe:
        _check(materials['updater'] == recipe['updater_metadata'])
        value = recipe['updater_metadata']
        community.check_receipt({'source': value['source'], 'proof_sha256': value['proof_sha256']},
                                value['original'], Path(cache)/'format/community')
        ref = community.reference(value['source'])
        path = Path(cache)/'format/community/sources'/ref['family']/(ref['sha256']+'.data')
        _check(path.is_file() and 0 < path.stat().st_size <= community.SOURCES[ref['family']][2]
               and _sha(path.read_bytes()) == ref['sha256'])
    else:
        _check(materials['updater'] == {'global': list(release.GLOBAL_FORMAT),
               **({'mainland': list(release.CN_FORMAT)} if recipe['region'] == 'nte-cn' else {})})


def load(tools, snapshot_id, header, recipe):
    _check(isinstance(header, dict) and set(header) ==
           {'schema', 'kind', 'recipe', 'profile_sha256', 'receipt_sha256'})
    _check(header['schema'] == 2 and header['kind'] == SNAPSHOT
           and 'nte-'+_sha(_json(header)) == _stamp(snapshot_id)
           and 'nte-'+_sha(_json(recipe)) == _stamp(header['recipe']))
    check_policy(recipe['metadata_policy'])
    root = Path(tools)/'nte-publisher/metadata-profiles'
    profile = _read(root/(_digest(header['profile_sha256'])+'.json'), header['profile_sha256'])
    receipt = _read(root/'receipts'/(_digest(header['receipt_sha256'])+'.json'), header['receipt_sha256'])
    _check(set(profile) == {'schema', 'recipe', 'policy_sha256', 'native', 'materials',
                           'source_locale', 'source_region', 'dataset_sha256'}
           and profile['schema'] == PROFILE and profile['recipe'] == header['recipe']
           and profile['policy_sha256'] == recipe['metadata_policy']['sha256'])
    native = profile['native']
    from . import nte_native_metadata as metadata, nte_native_provider as provider
    _check(isinstance(native, dict) and native.get('reader_sha256') == recipe['reader']
           and native.get('inventory_sha256') == _sha(metadata._json(provider.discovery(recipe)))
           and native.get('native_path') in recipe['publisher_files']
           and native.get('native_file') == recipe['publisher_files'][native['native_path']])
    for name in ('reader_sha256', 'inventory_sha256', 'native_sha256', 'validation_sha256'):
        _digest(native[name])
    _check(native == native_evidence(recipe, (native['schema'], native['validation_sha256']),
                                    Path(tools)/'nte-publisher'))
    check_materials(recipe, native, profile['materials'], Path(tools)/'nte-publisher')
    _check(receipt == {'schema': RECEIPT, 'recipe': header['recipe'],
        'profile_sha256': header['profile_sha256'], 'inventory_sha256': native['inventory_sha256'],
        'reader_sha256': native['reader_sha256'], 'native_sha256': native['native_sha256'],
        'dataset_sha256': profile['dataset_sha256']})
    return profile


def validate_payload(payload, profile, header, snapshot_id):
    _check(payload.get('game') == 'nte' and payload.get('install') is None
           and payload.get('source_mode') == 'publisher'
           and payload.get('fingerprint') == header['recipe']
           and payload.get('publisher_snapshot') == snapshot_id
           and payload.get('source_locale') == profile['source_locale']
           and payload.get('source_region') == profile['source_region']
           and dataset_sha256(payload) == profile['dataset_sha256'])
    _check(all(not row.get('audio') or row['audio'].get('publisher') == snapshot_id
               for row in payload['records']))


def portable_snapshot(payload):
    """The reviewed PC export keeps one opaque ID, never desktop material."""
    _stamp(payload['publisher_snapshot'])
    return {**payload, 'fingerprint': payload['publisher_snapshot']}
