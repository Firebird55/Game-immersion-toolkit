"""Original publisher key-update records, retained as immutable wire inputs.

The standard public operation is inferred from the native updater's inputs
and corroborated by complete original encrypted package index hashes. The
packed native LoadKeys implementation was not executed or decoded. Candidates
remain distinct from independently package-verified bootstrap/default inputs.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urlsplit
import uuid

from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure

KEYLIST_LIMIT = 16 * 1024
PACKET_LIMIT = 1024 * 1024
BUNDLE_LIMIT = 2 * 1024 * 1024
MAX_RECORDS = 4096


def _check(value):
    if not value:
        raise ValueError('Invalid original Wuthering publisher key metadata.')


class Parameters(tuple):
    """Baseline candidates and separately UUID-owned native candidates."""
    def __new__(cls, baseline, native, sources, *, verified_defaults=()):
        # A value published as UUID-owned native input cannot simultaneously
        # become an unrelated/default candidate through the legacy feed.
        owned = set(native.values())
        independent = set(verified_defaults)
        result = super().__new__(cls, (value for value in baseline if value not in owned or value in independent))
        result.native = MappingProxyType(dict(native))
        result.sources = tuple(dict(source) for source in sources)
        result.bootstrap = getattr(baseline, 'bootstrap', None)
        return result

    def __repr__(self):
        return '<Wuthering archive parameter inputs>'


def _base64(value):
    _check(isinstance(value, str) and value.isascii())
    raw = base64.b64decode(value, validate=True)
    _check(base64.b64encode(raw).decode('ascii') == value)
    return raw


def descriptor(value):
    _check(isinstance(value, dict))
    digest, random, encoded, updated = (value.get(key) for key in ('Hash', 'Random', 'Key', 'UpdateTime'))
    _check(type(updated) is int and 0 <= updated <= 2**63 - 1)
    if digest == encoded == '':
        return None
    _check(isinstance(digest, str) and re.fullmatch('[0-9a-fA-F]{40}', digest))
    _check(isinstance(random, str) and re.fullmatch('[A-Za-z0-9]{1,128}', random))
    raw = _base64(encoded)
    _check(len(raw) == 128)
    modulus = int.from_bytes(raw, 'little')
    _check(modulus.bit_length() == 1024 and modulus & 1 and math.gcd(modulus, 65537) == 1)
    return digest.lower(), random, modulus


def records(config, packet):
    """Decode only strict complete UUID/comma/Base64-AES32 records.

    No candidate is authorized as a package parameter here. Its native footer
    UUID and complete decrypted main/directory hashes must still agree.
    """
    selected = descriptor(config)
    _check(isinstance(packet, bytes) and len(packet) <= PACKET_LIMIT)
    if selected is None:
        _check(not packet)
        return {}
    digest, _, modulus = selected
    _check(hashlib.sha1(packet).hexdigest() == digest)
    lines = packet.splitlines()
    _check(0 < len(lines) <= MAX_RECORDS)
    result = {}
    for line in lines:
        _check(len(line) == 172 and line.isascii())
        raw = _base64(line.decode('ascii'))
        _check(len(raw) == 128)
        integer = int.from_bytes(raw, 'big')
        _check(0 < integer < modulus)
        encoded = pow(integer, 65537, modulus).to_bytes(128, 'big')
        separator = encoded.find(b'\0', 2)
        _check(encoded[:2] == b'\0\1' and separator >= 10
               and encoded[2:separator] == b'\xff' * (separator - 2))
        value = encoded[separator + 1:]
        _check(len(value) == 81 and value[36:37] == b',')
        text = value[:36].decode('ascii')
        identity = uuid.UUID(text)
        _check(identity.int and str(identity) == text.lower())
        parameter = _base64(value[37:].decode('ascii'))
        _check(len(parameter) == 32 and (identity not in result or result[identity] == parameter))
        result[identity] = parameter
    return result


def _context(base, version, region, role):
    _check(region in ('global', 'cn') and role in ('resource', 'video'))
    _check(isinstance(version, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version))
    _check(isinstance(base, str))
    url = urlsplit(base)
    domain = 'net' if region == 'global' else 'com'
    _check(url.scheme == 'https' and re.fullmatch(r'[a-z0-9-]+\.aki-game\.' + domain, url.netloc)
           and re.fullmatch('/prod/client/[A-Za-z0-9]{16,80}/Windows/', url.path)
           and not url.query and not url.fragment)
    return {'region': region, 'base': base, 'version': version, 'role': role}


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _path(tools, context, wire_digest):
    _check(isinstance(wire_digest, str) and re.fullmatch('[0-9a-f]{64}', wire_digest))
    partition = hashlib.sha256(_encoded(context)).hexdigest()
    return (Path(tools) / 'wuwa-publisher' / 'native-key-inputs' / context['region']
            / context['version'] / partition / (wire_digest + '.json'))


def _bundle(raw, context, wire, decode):
    _check(isinstance(raw, bytes) and len(raw) <= BUNDLE_LIMIT)
    value = json.loads(raw)
    _check(isinstance(value, dict) and type(value.get('schema')) is int
           and value['schema'] == 1 and value.get('context') == context)
    stored = _base64(value.get('keylist'))
    _check(stored == wire and len(stored) <= KEYLIST_LIMIT)
    packet = _base64(value.get('packet'))
    return records(decode(stored), packet)


def _merge(target, additions):
    for identity, parameter in additions.items():
        _check(identity not in target or target[identity] == parameter)
        target[identity] = parameter


def current(tools, base, version, region, baseline, fetch, decode, pointers, *, verified_defaults=()):
    """Discover both native lists on the already selected publisher CDN.

    Persist original encoded wire only. The immutable descriptor carries its
    hashes, never recovered values or a mutable latest-key pointer.
    """
    native, sources = {}, []
    try:
        for role, name in (('resource', f'KeyList_{version}.json'), ('video', 'KeyList.json')):
            context = _context(base, version, region, role)
            url = base + name
            wire = fetch(url, limit=KEYLIST_LIMIT)
            _check(isinstance(wire, bytes) and len(wire) <= KEYLIST_LIMIT)
            config = decode(wire)
            selected = descriptor(config)
            wire_digest = hashlib.sha256(wire).hexdigest()
            path = _path(tools, context, wire_digest)
            retained = path.read_bytes() if path.is_file() and path.stat().st_size <= BUNDLE_LIMIT else None
            try:
                additions = _bundle(retained, context, wire, decode)
                raw = retained
            except (ValueError, TypeError, KeyError, UnicodeError):
                packet = (fetch(base + 'client_key/' + version + '/' + selected[1] + '/PakData', limit=PACKET_LIMIT)
                          if selected is not None else b'')
                additions = records(config, packet)
                raw = _encoded({'schema': 1, 'context': context,
                    'keylist': base64.b64encode(wire).decode('ascii'),
                    'packet': base64.b64encode(packet).decode('ascii')})
                _check(len(raw) <= BUNDLE_LIMIT)
                _atomic_file(path, raw)
            _merge(native, additions)
            sources.append({**context, 'keylist_sha256': wire_digest, 'sha256': hashlib.sha256(raw).hexdigest()})
            pointers[url] = wire
        return Parameters(baseline, native, sources, verified_defaults=verified_defaults)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        raise PreparationFailure('publisher_key_metadata_failed',
            'The original Wuthering key-update metadata could not be verified or retained. '
            'Check the publisher connection and toolkit cache, then retry. '
            'The previous prepared index and recordings are kept.') from error


def restore(tools, references, region, baseline, decode, *, verified_defaults=()):
    """Restore exactly the native inputs owned by one immutable descriptor."""
    native = {}
    try:
        _check(isinstance(references, list) and len(references) == 2)
        roles = set()
        for reference in references:
            _check(isinstance(reference, dict) and reference.get('region') == region)
            context = _context(*(reference.get(key) for key in ('base', 'version', 'region', 'role')))
            _check(context['role'] not in roles)
            roles.add(context['role'])
            path = _path(tools, context, reference.get('keylist_sha256'))
            _check(path.is_file() and path.stat().st_size <= BUNDLE_LIMIT)
            raw = path.read_bytes()
            _check(hashlib.sha256(raw).hexdigest() == reference.get('sha256'))
            value = json.loads(raw)
            _check(isinstance(value, dict))
            wire = _base64(value.get('keylist'))
            _check(hashlib.sha256(wire).hexdigest() == reference['keylist_sha256'])
            _merge(native, _bundle(raw, context, wire, decode))
        _check(roles == {'resource', 'video'})
        return Parameters(baseline, native, references, verified_defaults=verified_defaults)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        raise PreparationFailure('publisher_key_inputs_missing',
            'The retained original Wuthering key inputs are missing or invalid. '
            'Refresh this game from its selected publisher to restore them. '
            'Previously saved transcripts and recordings are kept.') from error
