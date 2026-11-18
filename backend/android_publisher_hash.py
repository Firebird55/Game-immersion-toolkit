"""Explicit verified Android XXH3 data hashing; no xxhash namespace override."""
from dataclasses import dataclass, field
import json
import hashlib
import re

SOURCE_SHA256 = 'c9b288e4c1f5dae54417bc8a05e6f6daf505783d916b4783f4dd2f2e7d5db486'
HEADER_SHA256 = '3dc8d161e867a62d3417f7885b55fdaded8b7b497e2f165d05c94f4fe24f2ca4'
MAX_BYTES = 4096


def _check(value):
    if not value:
        raise ValueError('Unsupported publisher hash input or verified runtime.')


@dataclass(frozen=True, repr=False, init=False)
class AndroidPublisherHash:
    _native: object = field(repr=False)
    runtime: dict = field(repr=False)

    @classmethod
    def from_native(cls, native):
        try:
            from java import jclass
            _check(isinstance(native, jclass('io.github.firebird55.gameimmersiontoolkit.PublisherHash')))
            value = json.loads(str(native.proof()))
            _check(value.get('schema') == 'toolkit-publisher-hash-v1' and value.get('algorithm') == 'XXH3-64'
                and value.get('version') == '0.8.4' and value.get('source_sha256') == SOURCE_SHA256
                and value.get('header_sha256') == HEADER_SHA256 and value.get('abi') in ('arm64-v8a', 'x86_64')
                and type(value.get('seed')) is int and value['seed'] == 0 and value.get('custom_secret') is False
                and type(value.get('max_bytes')) is int and value['max_bytes'] == MAX_BYTES
                and type(value.get('pointer_bits')) is int and value['pointer_bits'] == 64
                and value.get('apk_entry_verified') is True and value.get('licenses_verified') is True
                and value.get('system_fallback') is False and value.get('original_client_execution') is False)
            for name in ('library_sha256', 'manifest_sha256'):
                _check(isinstance(value.get(name), str) and re.fullmatch('[0-9a-f]{64}', value[name]))
            result = object.__new__(cls)
            object.__setattr__(result, '_native', native)
            object.__setattr__(result, 'runtime', value)
            return result
        except Exception:
            raise ValueError('The verified Android publisher hash runtime is unavailable.') from None

    def xxh3_64(self, data):
        _check(type(data) is bytes and len(data) <= MAX_BYTES)
        try:
            # A string preserves the entire unsigned result, including >2**63.
            result = str(self._native.xxh3_64(data))
            _check(re.fullmatch('[0-9a-f]{16}', result))
            return int(result, 16)
        except Exception:
            raise ValueError('Unsupported publisher hash input or verified runtime.') from None


def authored_probe(host, fixture_json):
    """DEBUG acceptance hook; callers must separately establish target execution."""
    _check(isinstance(fixture_json, str) and len(fixture_json) <= 65536)
    fixture = json.loads(fixture_json)
    _check(fixture.get('schema') == 'toolkit-authored-publisher-hash-v1' and fixture.get('algorithm') == 'XXH3-64'
        and fixture.get('seed') == 0 and fixture.get('custom_secret') is False and fixture.get('original_game_bytes') is False
        and isinstance(fixture.get('cases'), list) and len(fixture['cases']) == 47)
    native = host.publisherHash(); hashing = AndroidPublisherHash.from_native(native)
    for row in fixture['cases']:
        _check(isinstance(row, dict) and isinstance(row.get('expected_hex'), str)
               and re.fullmatch('[0-9a-f]{16}', row['expected_hex']))
        if row.get('pattern') == 'sequence-73-19':
            _check(type(row.get('bytes')) is int and 0 <= row['bytes'] <= MAX_BYTES)
            data = bytes((i*73+19)&255 for i in range(row['bytes']))
        else:
            _check(row.get('pattern') == 'utf8' and isinstance(row.get('text'), str) and len(row['text']) <= MAX_BYTES)
            data = row['text'].encode('utf8')
        _check(hashing.xxh3_64(data) == int(row['expected_hex'], 16))
    rejected = 0
    for data in (None, bytes(MAX_BYTES+1)):
        try: native.xxh3_64(data)
        except Exception: rejected += 1
    _check(rejected == 2)
    return json.dumps({'schema':'toolkit-authored-publisher-hash-proof-v1', 'passed':True,
        'cases':len(fixture['cases']), 'native_boundary_rejections':rejected,
        'fixture_sha256':hashlib.sha256(fixture_json.encode('utf8')).hexdigest(),
        'runtime':hashing.runtime, 'original_game_bytes':False})
