"""Release-owned Lua key candidates and complete original source witnesses."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from .endfield_client_source import Image, Metadata, Ranges, check, identity_stamp
from .game_tools import _atomic_file


def _path(tools, identity):
    return Path(tools) / 'endfield-client-metadata' / identity_stamp(identity) / 'validated-lua.json'


def _active(tools, identity):
    try:
        path = _path(tools, identity)
        check(path.stat().st_size <= 128 * 1024)
        envelope = json.loads(path.read_bytes())
        payload = envelope['payload']
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        check(hashlib.sha256(raw).hexdigest() == envelope['sha256'] and payload['client'] == identity and
              type(payload['schema']) is int and payload['schema'] == 1)
        key = bytes.fromhex(payload['key'])
        check(len(key) == 16 and key.decode('utf-8', 'strict').encode('utf-8') == key)
        witnesses = payload['sources']
        check(isinstance(witnesses, dict) and 1 <= len(witnesses) <= 256)
        for digest, source in witnesses.items():
            check(re.fullmatch('[0-9a-f]{32}', digest) and isinstance(source, dict) and
                  re.fullmatch('[0-9a-f]{64}', source['index_sha256']) and
                  re.fullmatch('[0-9a-f]{64}', source['decrypted_sha256']))
        return key, payload
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


@lru_cache(maxsize=6)
def _candidate(tools, encoded_identity):
    identity = json.loads(encoded_identity)
    active = _active(tools, identity)
    if active:
        return active[0]
    from .endfield_parameters import source_runtime
    from .endfield_lua_contract import derive
    source_runtime()  # Reject an unavailable/unverified runtime before large tables.
    return derive(Metadata(Ranges(tools, identity, 'Endfield_Data/il2cpp_data/Metadata/global-metadata.dat')),
                  Image(Ranges(tools, identity, 'GameAssembly.dll')))


def candidate(tools, identity):
    return _candidate(tools, json.dumps(identity, sort_keys=True, separators=(',', ':')))


def activate(tools, identity, key, index_digest, sources, *, recheck):
    """Publish only complete MD5-bound source controls, retaining prior clients."""
    check(isinstance(key, bytes) and len(key) == 16 and
          isinstance(index_digest, str) and re.fullmatch('[0-9a-f]{64}', index_digest))
    check(isinstance(sources, dict) and 1 <= len(sources) <= 256)
    witnesses = {}
    for digest, (original, decoded) in sources.items():
        check(isinstance(digest, str) and re.fullmatch('[0-9a-f]{32}', digest) and
              isinstance(original, bytes) and hashlib.md5(original).hexdigest() == digest and
              isinstance(decoded, str) and re.search(r'\b(?:local|function)\b', decoded),
              'Original Lua source control is incomplete.')
        # Decode again at the trust boundary: an arbitrary caller's supplied
        # plaintext or a different key cannot become an activation witness.
        from .endfield_presentation_source import decode_lua
        check(decode_lua(original, key) == decoded, 'Original Lua candidate does not decode its source.')
        witnesses[digest] = {'index_sha256': index_digest,
                             'decrypted_sha256': hashlib.sha256(decoded.encode('utf-8')).hexdigest()}
    previous = _active(tools, identity)
    if previous and previous[0] == key and all(previous[1]['sources'].get(k) == v for k, v in witnesses.items()):
        return
    check(recheck() == identity, 'Publisher client changed before Lua activation; retry preparation.')
    retained = dict(previous[1]['sources']) if previous and previous[0] == key else {}
    retained.update(witnesses)
    check(len(retained) <= 256)
    payload = {'schema': 1, 'client': identity, 'key': key.hex(), 'sources': retained,
               'source_authentication': 'official HTTPS ranges + original VFS CRC/schema + complete Lua MD5/source; not full native-file hash'}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    _atomic_file(_path(tools, identity), json.dumps({'payload': payload,
                 'sha256': hashlib.sha256(raw).hexdigest()}, sort_keys=True).encode())


def scripts(tools, stamp, files):
    """The UI producers share this path; no voice inventory or media is fetched."""
    from . import endfield_release as release, endfield_metadata
    from .endfield_presentation_source import decode_lua
    descriptor = release.descriptor(tools, stamp)
    identity = descriptor.get('client')
    if identity:
        key = candidate(tools, identity)
        from .endfield_parameters import _active as common_active
        common = common_active(tools, identity)
        check(common and '17' in common[1]['validated_indices'], 'Original Lua index is not validated.')
        index_digest = common[1]['validated_indices']['17']
    else:
        # An old immutable descriptor retains its original extraction provenance;
        # it is never relabelled as a newly derived official-client recipe.
        root = endfield_metadata.cache_root(tools)
        secret = endfield_metadata._one(r'XxteaKey\s*=\s*(?:System\.Text\.)?Encoding.UTF8.GetBytes\("([^"\\]*)"\)',
                                       (root / 'Keys.cs').read_text(encoding='utf-8-sig'))
        key = secret.encode('utf-8')[:16].ljust(16, b'\0')
    result, controls = {}, {}
    for name, (base, file) in files.items():
        original = release._whole(tools, base, file, 256 * 1024)
        result[name] = decode_lua(original, key)
        controls[file.content_hashes[1]] = original, result[name]
    if identity:
        activate(tools, identity, key, index_digest, controls,
                 recheck=lambda: release.latest_client(descriptor.get('region', 'global'))[1])
    return result
