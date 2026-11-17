"""Explicit provider-local original AKPK witness; no ambient legacy adoption.

Only a signed original native member and a complete original selected package
can activate this material. References expose hashes, never parameter values.
This is not a dialogue snapshot or a publisher-content SourceProof.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .endfield_client_source import Metadata, Image, identity_stamp
from .endfield_client_contract import derive as common_candidate
from .endfield_native_import import NativeImage, managed_import
from .endfield_native_source import OriginalNativeSource
from .endfield_akpk_contract import derive as audio_candidate
from .endfield_akpk_controls import validate
from .endfield_vfs import IndexParameters, Parameters


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _helpers():
    from .game_data import _read, _write_bytes
    from .game_data_protocol import GameDataError
    from .private_data_paths import _no_links
    return _read, _write_bytes, GameDataError, _no_links


def _digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def voice_block(locale):
    _, _, Error, _ = _helpers()
    try:
        return {'zh': 101, 'en': 102, 'ja': 103, 'ko': 104}[locale.split('-')[0]]
    except (KeyError, AttributeError) as error:
        raise Error('invalid_game_languages', 'Choose an official Endfield original voice language.') from error


def activate(ctx, bootstrap, native_stage, generation, index, block, name, payload, *, recheck):
    """Rebuild both candidates; validate whole current data before publication."""
    _, write, Error, _ = _helpers()
    ctx.check()
    if ctx.phase != 'download':
        raise Error('unapproved_asset_transfer', 'Approve original Endfield audio preparation before activating its source parameters.')
    identity = bootstrap.identity
    if (ctx.game != 'endfield' or ctx.request.content_mode != 'text-audio' or
            not isinstance(native_stage, dict) or native_stage.get('stage') != 'original-audio-native-source-downloaded' or
            native_stage.get('client') != identity or native_stage.get('request') != ctx.request.json()):
        raise Error('invalid_local_state', 'Endfield original audio master belongs to another source request.')
    if block != voice_block(ctx.request.source_locale):
        raise Error('invalid_game_languages', 'Endfield original audio control belongs to another requested voice language.')
    if not isinstance(generation, dict) or not generation or len(_json(generation)) > 128 * 1024:
        raise Error('unverified_original_source', 'Endfield original resource generation is missing.')
    metadata, image = Metadata(bootstrap.artifact('Endfield_Data/il2cpp_data/Metadata/global-metadata.dat')), Image(bootstrap.artifact('GameAssembly.dll'))
    imported = managed_import(metadata, image)
    raw, module = OriginalNativeSource(ctx, identity, bootstrap.transport).verified(imported, native_stage.get('source_receipt_sha256'))
    common = common_candidate(metadata, image)
    parameters, control = validate(audio_candidate(NativeImage(raw), imported),
        IndexParameters(common.key, common.directories, common.protocol), index, block, name, payload)
    ctx.check()
    if recheck() != (identity, generation):
        raise Error('publisher_object_changed', 'Endfield changed before original audio master publication. Existing data is retained.', 409)
    # Provider-local, content-addressed and explicitly referenced. No write to
    # legacy tools or a clientless/frozen parameter profile is permitted here.
    body = {'schema': 1, 'kind': 'endfield-original-akpk-witness', 'client': identity,
            'generation': generation, 'native_source_receipt_sha256': native_stage['source_receipt_sha256'],
            'module_sha256': module['sha256'], 'control': control,
            'parameters': {'key': parameters.key.hex(), 'directories': {str(k): v for k, v in parameters.directories.items()},
                           'protocol': parameters.protocol, 'multiplier': parameters.multiplier,
                           'xor_constant': parameters.xor_constant}}
    encoded = _json(body)
    witness, resource = hashlib.sha256(encoded).hexdigest(), hashlib.sha256(_json(generation)).hexdigest()
    reference = {'schema': 1, 'client_sha256': identity_stamp(identity), 'generation_sha256': resource,
                 'module_sha256': module['sha256'], 'control_sha256': hashlib.sha256(_json(control)).hexdigest(),
                 'witness_sha256': witness}
    path = Path(ctx.cache_directory) / 'endfield-original-akpk' / resource / (witness + '.json')
    ctx.check()
    write(path, encoded)
    ctx.check()
    return reference


def restore(ctx, reference, identity, generation):
    """Load only the exact caller-supplied client/resource/module/control proof."""
    _, _, Error, no_links = _helpers()
    ctx.check()
    keys = {'schema', 'client_sha256', 'generation_sha256', 'module_sha256', 'control_sha256', 'witness_sha256'}
    if (not isinstance(reference, dict) or set(reference) != keys or type(reference['schema']) is not int or
            reference['schema'] != 1 or not all(_digest(reference[n]) for n in keys - {'schema'}) or
            reference['client_sha256'] != identity_stamp(identity) or
            reference['generation_sha256'] != hashlib.sha256(_json(generation)).hexdigest()):
        raise Error('invalid_local_state', 'Endfield original audio witness does not match this generation.')
    path = (Path(ctx.cache_directory) / 'endfield-original-akpk' / reference['generation_sha256'] /
            (reference['witness_sha256'] + '.json'))
    no_links(path)
    try:
        if path.stat().st_size > 256 * 1024:
            raise Error('invalid_local_state', 'Endfield original audio witness exceeds its bound.')
        raw = path.read_bytes()
    except OSError as error:
        raise Error('source_not_prepared', 'The explicitly referenced Endfield original audio witness is unavailable. Prepare its source again.') from error
    if hashlib.sha256(raw).hexdigest() != reference['witness_sha256']:
        raise Error('invalid_local_state', 'Endfield original audio witness checksum differs.')
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise Error('invalid_local_state', 'Endfield original audio witness is malformed.') from error
    if (not isinstance(body, dict) or type(body.get('schema')) is not int or body['schema'] != 1 or
            body.get('kind') != 'endfield-original-akpk-witness' or body.get('client') != identity or
            body.get('generation') != generation or body.get('module_sha256') != reference['module_sha256'] or
            hashlib.sha256(_json(body.get('control'))).hexdigest() != reference['control_sha256'] or
            not _digest(body.get('native_source_receipt_sha256'))):
        raise Error('invalid_local_state', 'Endfield original audio witness source ownership differs.')
    value = body.get('parameters')
    if (not isinstance(value, dict) or set(value) != {'key', 'directories', 'protocol', 'multiplier', 'xor_constant'} or
            not isinstance(value.get('key'), str) or
            re.fullmatch('[0-9a-f]{64}', value['key']) is None or not isinstance(value.get('directories'), dict) or
            type(value.get('protocol')) is not int or type(value.get('multiplier')) is not int or
            type(value.get('xor_constant')) is not int):
        raise Error('invalid_local_state', 'Endfield original audio witness parameters are invalid.')
    try:
        directories = value['directories']
        if set(directories) != {'1', '21', '101', '102', '103', '104'}:
            raise ValueError('Wrong original voice namespace')
        result = Parameters(bytes.fromhex(value['key']), {int(n): v for n, v in directories.items()},
                            value['multiplier'], value['xor_constant'], value['protocol'])
    except (ValueError, TypeError) as error:
        raise Error('invalid_local_state', 'Endfield original audio witness parameters are invalid.') from error
    ctx.check()
    return result
