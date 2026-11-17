"""Release-owned common-key/map candidates, activated only after original checks."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from . import endfield_metadata
from .endfield_client_contract import Candidate, derive
from .endfield_client_source import Image, Metadata, Ranges, check, identity_stamp, metadata_sections
from .endfield_private_cache import atomic_bytes as _atomic_file


def source_runtime():
    """Fail before cold source acquisition when the reviewed host closure is absent."""
    from .genshin_native_x64 import decoder
    from .endfield_xxhash import implementation
    from .preparation_errors import PreparationFailure
    try:
        decoder()
        implementation()
    except (OSError, ValueError, ImportError) as error:
        raise PreparationFailure('missing_toolkit_runtime',
            'Endfield official-client parameter preparation needs the verified Capstone and XXH3 runtime. '
            'This toolkit currently provides that source reader for Windows amd64 with Python 3.12. '
            'Use a compatible toolkit installation; independent preparation on other hosts requires its '
            'reviewed native runtime. Existing prepared data is retained. This is a toolkit runtime '
            'limitation, not a changed game format.', previous_snapshot_retained=True) from error


def _path(tools, identity):
    return Path(tools) / 'endfield-client-metadata' / identity_stamp(identity) / 'validated-parameters.json'


def _decode(payload):
    check(isinstance(payload, dict) and type(payload.get('schema')) is int and payload['schema'] == 1)
    key = payload.get('common_key')
    check(isinstance(key, str) and re.fullmatch('[0-9a-f]{64}', key))
    labels = payload.get('directories')
    check(isinstance(labels, dict) and 1 <= len(labels) <= 256)
    check(all(isinstance(k, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', k) and 0 <= int(k) <= 255 and
              isinstance(v, str) and re.fullmatch('[0-9A-F]{8}', v) for k, v in labels.items()))
    check(len({int(k) for k in labels}) == len(labels) and len(set(labels.values())) == len(labels))
    check(type(payload.get('protocol')) is int and payload['protocol'] == 3)
    return Candidate(bytes.fromhex(key), {int(k): v for k, v in labels.items()}, 3)


def _active(tools, identity):
    try:
        path = _path(tools, identity)
        check(path.stat().st_size <= 128 * 1024)
        envelope = json.loads(path.read_bytes())
        payload = envelope['payload']
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        check(hashlib.sha256(raw).hexdigest() == envelope['sha256'] and payload['client'] == identity)
        witnesses = payload['validated_indices']
        check(isinstance(witnesses, dict) and 1 <= len(witnesses) <= 256 and
              all(isinstance(k, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', k) and 0 <= int(k) <= 255 and
                  isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v) for k, v in witnesses.items()))
        return _decode(payload), payload
    except (OSError, ValueError, KeyError, TypeError):
        return None


@lru_cache(maxsize=6)
def _candidate(tools, encoded_identity):
    identity = json.loads(encoded_identity)
    active = _active(tools, identity)
    if active:
        return active[0]
    # Check the fixed software/host closure before fetching large inert tables.
    source_runtime()
    metadata = Ranges(tools, identity, 'Endfield_Data/il2cpp_data/Metadata/global-metadata.dat')
    native = Ranges(tools, identity, 'GameAssembly.dll')
    return derive(Metadata(metadata), Image(native))


def candidate(tools, identity):
    return _candidate(tools, json.dumps(identity, sort_keys=True, separators=(',', ':')))


def preflight_client(tools, identity):
    """At most 4,352 header bytes precede the cold metadata-size decision.

    The later selected-content plan needs decrypted current VFS indexes. This
    deliberately reports that amount as unknown rather than using the size of
    the whole launcher package or silently fetching a large metadata body.
    """
    if _active(tools, identity):
        return {'schema': 1, 'client': identity_stamp(identity), 'metadata_bytes': 0,
                'metadata_overhead_upper_bytes': 0, 'parameters_already_validated': True,
                'content_bytes': None, 'requires_current_index_plan': True}
    source_runtime()
    metadata = Ranges(tools, identity, 'Endfield_Data/il2cpp_data/Metadata/global-metadata.dat')
    native = Ranges(tools, identity, 'GameAssembly.dll')
    tables = metadata_sections(metadata)
    image = Image(native, read_tables=False)
    ranges = [{'artifact': 'metadata', 'offset': offset, 'bytes': size}
              for name, (offset, size) in tables.items()
              if name in {'strings', 'methods', 'types', 'images', 'literals', 'literal_data'}]
    ranges += [{'artifact': 'native', 'offset': image.sections[name][2], 'bytes': image.sections[name][3]}
               for name in ('.rdata', '.data')]
    return {'schema': 1, 'client': identity_stamp(identity), 'header_bytes': 4352,
            'metadata_bytes': sum(row['bytes'] for row in ranges),
            'metadata_overhead_upper_bytes': 256 * 1024 + 64 * 1024 + 4096,
            'ranges': ranges, 'parameters_already_validated': False,
            'content_bytes': None, 'requires_current_index_plan': True,
            'authentication': 'declared launcher artifacts; HTTPS range receipts; no complete-native-file hash claim'}


def crypto_parameters(tools, identity):
    """Only common key/map are native-derived; other crypto masters stay explicit."""
    original = candidate(tools, identity)
    frozen = endfield_metadata.parameters(tools)
    from .endfield_vfs import Parameters
    required = set(endfield_metadata.BLOCKS.values())
    check(required <= original.directories.keys(), 'An original required voice block is unavailable.')
    return Parameters(original.key, {k: original.directories[k] for k in required},
                      frozen.multiplier, frozen.xor_constant, protocol=original.protocol)


def index_parameters(tools, identity):
    """Plain tables/Lua/index discovery must not acquire an unused audio seed."""
    original = candidate(tools, identity)
    from .endfield_vfs import IndexParameters
    return IndexParameters(original.key, dict(original.directories), original.protocol)


def activate(tools, identity, original, parameters, block, data, *, recheck, suffix='.pck', names=None):
    """Pass original CRC/schema checks, then publish the parameter witness.

    Recheck the publisher's original client declaration immediately before the
    immutable-client cache is published. A failed update cannot replace any
    other client's active parameters or previously retained recordings.
    """
    check(type(block) is int and block in original.directories and isinstance(data, bytes))
    check(parameters.key == original.key and parameters.protocol == original.protocol and
          all(original.directories.get(k) == value for k, value in parameters.directories.items()),
          'Index parameters do not belong to the original client candidate.')
    from .endfield_vfs import parse_index
    rows = parse_index(data, parameters, block, suffix=suffix, names=names)
    previous = _active(tools, identity)
    digest = hashlib.sha256(data).hexdigest()
    if previous and previous[0] == original and previous[1]['validated_indices'].get(str(block)) == digest:
        return rows
    check(recheck() == identity, 'Publisher client changed before parameter activation; retry preparation.')
    witnesses = dict(previous[1]['validated_indices']) if previous else {}
    witnesses[str(block)] = digest
    payload = {'schema': 1, 'client': identity, 'common_key': original.key.hex(),
               'directories': {str(k): v for k, v in original.directories.items()},
               'protocol': original.protocol, 'validated_indices': witnesses,
               'source_authentication': 'official HTTPS ranges + original index CRC/schema; not full native-file hash'}
    _decode(payload)
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    _atomic_file(_path(tools, identity), json.dumps({'payload': payload,
                 'sha256': hashlib.sha256(raw).hexdigest()}, sort_keys=True).encode())
    return rows
