"""Owned Python boundary and software reference, not Android/JNI execution."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from backend import android_publisher_hash as boundary, endfield_xxhash

ROOT = Path(__file__).resolve().parents[2]


def proof():
    return {'schema':'toolkit-publisher-hash-v1', 'algorithm':'XXH3-64', 'version':'0.8.4',
        'source_sha256':boundary.SOURCE_SHA256, 'header_sha256':boundary.HEADER_SHA256,
        'abi':'arm64-v8a', 'pointer_bits':64, 'max_bytes':4096, 'seed':0, 'custom_secret':False,
        'original_client_execution':False, 'apk_entry_verified':True, 'licenses_verified':True,
        'system_fallback':False, 'library_sha256':'a'*64, 'manifest_sha256':'b'*64}


class Native:
    def __init__(self, identity=None, result='ffffffffffffffff'):
        self.identity = proof() if identity is None else identity
        self.result = result; self.calls = []

    def proof(self): return json.dumps(self.identity)
    def xxh3_64(self, data): self.calls.append(data); return self.result


@pytest.fixture
def java(monkeypatch):
    def resolve(name):
        assert name == 'io.github.firebird55.gameimmersiontoolkit.PublisherHash'
        return Native
    monkeypatch.setitem(sys.modules, 'java', SimpleNamespace(jclass=resolve))


def test_explicit_android_path_preserves_unsigned_and_never_imports_the_windows_supplier(java, monkeypatch):
    monkeypatch.setattr(endfield_xxhash, 'implementation', lambda: pytest.fail('Windows loader invoked'))
    native = Native(); hashing = boundary.AndroidPublisherHash.from_native(native)
    assert endfield_xxhash.hash64(b'authored', hashing=hashing) == 2**64-1
    assert native.calls == [b'authored']
    with pytest.raises(ValueError): endfield_xxhash.hash64(b'a', hashing=object())
    with pytest.raises(ValueError): boundary.AndroidPublisherHash.from_native(object())
    with pytest.raises(TypeError): boundary.AndroidPublisherHash(Native(), proof())
    with pytest.raises(ValueError): boundary.AndroidPublisherHash().xxh3_64(b'authored')


@pytest.mark.parametrize('name,value', [('schema','changed'), ('version','0.8.3'), ('algorithm','XXH64'),
    ('source_sha256','0'*64), ('header_sha256','0'*64), ('abi','armeabi-v7a'), ('pointer_bits',32),
    ('max_bytes',8192), ('max_bytes',True), ('seed',False), ('seed',1), ('custom_secret',True),
    ('original_client_execution',True), ('apk_entry_verified',False), ('licenses_verified',False),
    ('system_fallback',True), ('library_sha256','unknown'), ('manifest_sha256',None)])
def test_changed_or_unverified_native_identity_fails_closed(java, name, value):
    identity = proof(); identity[name] = value
    with pytest.raises(ValueError): boundary.AndroidPublisherHash.from_native(Native(identity))


@pytest.mark.parametrize('data', [b'x'*4097, bytearray(b'x'), memoryview(b'x'), 'private text', None])
def test_invalid_inputs_reject_before_jni(java, data):
    native = Native(); hashing = boundary.AndroidPublisherHash.from_native(native)
    with pytest.raises(ValueError): hashing.xxh3_64(data)
    assert not native.calls


@pytest.mark.parametrize('result', ['-1', str(2**64-1), 'F'*16, 'a'*17, 'a'*15, None])
def test_wire_is_exact_unsigned_lowercase_hex_not_json_or_java_signed_long(java, result):
    with pytest.raises(ValueError): boundary.AndroidPublisherHash.from_native(Native(result=result)).xxh3_64(b'')


def test_authored_vectors_match_existing_pinned_software_reference():
    import xxhash
    assert xxhash.VERSION == '4.1.0' and xxhash.XXHASH_VERSION == '0.8.4'
    value = json.loads((ROOT/'packaging/android/publisher-hash-authored-vectors.json').read_text(encoding='utf8'))
    assert value['original_game_bytes'] is False and len(value['cases']) == 47
    oracle = endfield_xxhash.implementation() if sys.platform == 'win32' else xxhash.xxh3_64_intdigest
    high_bit = False
    for row in value['cases']:
        raw = bytes((i*73+19)&255 for i in range(row['bytes'])) if row['pattern']=='sequence-73-19' else row['text'].encode()
        assert len(raw) <= 4096 and format(oracle(raw), '016x') == row['expected_hex']
        high_bit |= oracle(raw) >= 2**63
    assert high_bit


def test_default_windows_gate_remains_intact(monkeypatch):
    endfield_xxhash.implementation.cache_clear()
    monkeypatch.setattr(endfield_xxhash.sys, 'platform', 'linux')
    with pytest.raises(ValueError, match='Windows'): endfield_xxhash.hash64(b'authored')
    endfield_xxhash.implementation.cache_clear()


def test_future_target_probe_uses_real_maintained_adapter_and_native_rejection_contract(java):
    import xxhash
    class AuthoredHostNative(Native):
        def xxh3_64(self, data):
            if data is None or len(data)>4096: raise ValueError('Authored native boundary rejection')
            return format(xxhash.xxh3_64_intdigest(data),'016x')
    raw=(ROOT/'packaging/android/publisher-hash-authored-vectors.json').read_text(encoding='utf8')
    result=json.loads(boundary.authored_probe(SimpleNamespace(publisherHash=lambda:AuthoredHostNative()),raw))
    assert result['passed'] and result['cases']==47 and result['native_boundary_rejections']==2
    # This host simulation is intentionally not an Android/JNI execution proof.
    assert 'native_android_execution' not in result
