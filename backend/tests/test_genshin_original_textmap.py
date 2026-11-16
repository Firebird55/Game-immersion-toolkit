"""Owned native-template and original TextMap fixtures; no game bytes or keys."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct

import pytest

from backend import genshin_original_textmap as original


def parameters(generation=0):
    first = original.NativeTextMapParameters(0x12345678, 0x4a5b6c7d, 0x100000001b3,
        0x123456789abcdef0, 7, 0x123456789fedcba1, 0x9988776655443322,
        0x1122334455667788, 17, 0x1020304050607081, 0x8293a4b5c6d7e8f9,
        0x9182736455463728, '0' * 64)
    if generation:
        return replace(first, count_add=19, count_xor=0x87654321, mul0=0x10000000193,
            add0=0x9182736455463728, rot0=13, mul1=0x123456789fedcbf1,
            add1=0x8899aabbccddeeff, xor1=0x1020304050607081, rot1=31,
            mul2=0x1122334455667799, key_xor=0x9988776655443322, text_xor=0x8293a4b5c6d7e8f9)
    return first


def native_mix(spec, finish, *, interleaved=False):
    # Authored x64 instructions, never executed: rsi is the accumulator and
    # rdx holds constants. A compiler can independently load a buffer position.
    constant = lambda value: b'\x48\xba' + struct.pack('<Q', value)
    multiply, add, xor = b'\x48\x0f\xaf\xf2', b'\x48\x03\xf2', b'\x48\x31\xd6'
    independent = b'\x48\x63\xd1\x8b\x7c\x10\x20' if interleaved else b''
    return (constant(spec.mul0) + multiply + constant(spec.add0) + add
        + b'\x48\xc1\xc6' + bytes([spec.rot0]) + constant(spec.mul1) + multiply
        + constant(spec.add1) + add + constant(spec.xor1) + xor
        + b'\x48\xc1\xc6' + bytes([spec.rot1]) + independent
        + constant(spec.mul2) + multiply + constant(finish) + xor)


def count_shape(spec):
    return (b'\xbb' + struct.pack('<I', spec.count_add) + b'\x03\x5c\x10\x20'
            + b'\x89\x4f\x18\x81\xf3' + struct.pack('<I', spec.count_xor))


def native_method(spec, *, interleaved=False):
    return (b'\x55\x48\x89\xe5' + count_shape(spec)
        + native_mix(spec, spec.key_xor) + native_mix(spec, spec.text_xor)
        + count_shape(spec) + native_mix(spec, spec.key_xor)
        + native_mix(spec, spec.text_xor, interleaved=interleaved) + b'\x5d\xc3')


def shard(spec, strings=(), aliases=()):
    """Encode toy payloads independently of the production reader."""
    mask = (1 << 64) - 1
    rotate = lambda value, bits: ((value << bits) | (value >> (64 - bits))) & mask

    def mix(value, finish):
        value = (value * spec.mul0 + spec.add0) & mask
        value = (rotate(value, spec.rot0) * spec.mul1 + spec.add1) & mask
        return ((rotate(value ^ spec.xor1, spec.rot1) * spec.mul2) & mask) ^ finish

    def count(value):
        return struct.pack('<I', ((value ^ spec.count_xor) - spec.count_add) & 0xffffffff)

    def key(value, index):
        mixed = mix(index, spec.key_xor)
        return struct.pack('<I', ((value - (mixed >> 32)) & 0xffffffff) ^ (mixed & 0xffffffff))

    output = bytearray(count(len(strings)))
    for index, (identity, text) in enumerate(strings):
        raw = text.encode('utf-8')
        mixed = mix((index + identity) & 0xffffffff, spec.text_xor)
        output += key(identity, index)
        output += struct.pack('<H', ((len(raw) ^ ((mixed >> 32) & 0xffff)) - (mixed & 0xffff)) & 0xffff)
        output += bytes(value ^ mixed.to_bytes(8, 'little')[number & 7] for number, value in enumerate(raw))
    output += count(len(aliases))
    for offset, (identity, target) in enumerate(aliases):
        index = len(strings) + offset
        mixed = mix((index + identity) & 0xffffffff, spec.text_xor)
        output += key(identity, index)
        output += struct.pack('<I', ((target ^ (mixed >> 32)) - (mixed & 0xffffffff)) & 0xffffffff)
    return bytes(output)


@pytest.mark.parametrize('generation', [0, 1])
@pytest.mark.parametrize('interleaved', [False, True])
def test_original_parameters_are_derived_without_version_address_or_constant_lists(generation, interleaved):
    spec = parameters(generation)
    method = native_method(spec, interleaved=interleaved)
    found = original.derive_native_parameters(method)
    assert found == replace(spec, method_sha256=hashlib.sha256(method).hexdigest())
    values = {0: '', 12345: 'An authored synthetic subtitle.', 987654: '合成字幕。\n{M#测试}{F#測試}'}
    payload = shard(spec, list(values.items()), [(3333, 12345)])
    assert original.decode_textmaps([payload], found) == {**values, 3333: values[12345]}


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'conflicting-count', 'conflicting-mix', 'clobbered-accumulator', 'clobbered-key', 'unknown-opcode', 'wrong-width', 'truncated', 'oversized'])
def test_unproved_native_layouts_and_ambiguous_parameters_are_rejected(damage, monkeypatch):
    spec = parameters()
    method = native_method(spec, interleaved=True)
    if damage == 'missing':
        method = method.replace(native_mix(spec, spec.key_xor), b'', 1)
    elif damage == 'duplicate':
        method += native_method(spec)
    elif damage == 'conflicting-count':
        method = method.replace(count_shape(spec), count_shape(replace(spec, count_xor=72)), 1)
    elif damage == 'conflicting-mix':
        method = method.replace(native_mix(spec, spec.key_xor), native_mix(replace(spec, add0=17), spec.key_xor), 1)
    elif damage == 'clobbered-accumulator':
        method = method.replace(b'\x48\x63\xd1', b'\x48\x63\xf1')
    elif damage == 'clobbered-key':
        method = method.replace(b'\x48\x0f\xaf\xf2', b'\x48\x63\xd1\x48\x0f\xaf\xf2', 1)
    elif damage == 'unknown-opcode':
        method = method.replace(b'\x48\x63\xd1', b'\x90\x90\x90')
    elif damage == 'wrong-width':
        method = method.replace(b'\x48\x0f\xaf\xf2', b'\x0f\xaf\xf2')
    elif damage == 'truncated':
        method = method[:-40]
    else:
        monkeypatch.setattr(original, 'MAX_METHOD', len(method) - 1)
    with pytest.raises(ValueError):
        original.derive_native_parameters(method)


@pytest.mark.parametrize('field,value', [('count_add', True), ('count_xor', -1), ('count_add', 1 << 32),
    ('mul0', 0), ('mul1', 12), ('mul2', 1 << 64), ('rot0', 0), ('rot1', 64),
    ('method_sha256', '../untrusted'), ('method_sha256', 'A' * 64)])
def test_parameter_descriptions_are_typed_and_bounded(field, value):
    with pytest.raises(ValueError):
        replace(parameters(), **{field: value})


def test_aliases_resolve_across_shards_and_forward_chains_without_input_mutation():
    spec = parameters()
    earlier = shard(spec, [], [(8, 9), (9, 10)])
    later = shard(spec, [(10, 'An independently authored synthetic sentence.')])
    rows = original.decode_textmaps([earlier, later], spec)
    assert rows == {10: 'An independently authored synthetic sentence.',
                    8: 'An independently authored synthetic sentence.', 9: 'An independently authored synthetic sentence.'}
    assert earlier == shard(spec, [], [(8, 9), (9, 10)])


@pytest.mark.parametrize('payloads', ['duplicate-direct', 'duplicate-alias', 'direct-alias-conflict', 'cycle', 'missing-target', 'cross-shard-duplicate'])
def test_conflicting_or_unresolved_original_identities_cannot_form_a_cache(payloads):
    spec = parameters()
    data = {
        'duplicate-direct': [shard(spec, [(1, 'One'), (1, 'Another')])],
        'duplicate-alias': [shard(spec, [(1, 'One')], [(2, 1), (2, 1)])],
        'direct-alias-conflict': [shard(spec, [(1, 'One')], [(1, 1)])],
        'cycle': [shard(spec, [], [(1, 2), (2, 1)])],
        'missing-target': [shard(spec, [], [(1, 2)])],
        'cross-shard-duplicate': [shard(spec, [(1, 'One')]), shard(spec, [], [(1, 1)])],
    }[payloads]
    with pytest.raises(ValueError):
        original.decode_textmaps(data, spec)


@pytest.mark.parametrize('limit', ['MAX_SHARD', 'MAX_INPUT', 'MAX_SHARDS', 'MAX_ROWS'])
def test_payload_shard_and_total_limits_fail_before_large_allocation(limit, monkeypatch):
    spec = parameters()
    payload = shard(spec, [(1, 'One'), (2, 'Two')])
    monkeypatch.setattr(original, limit, len(payload) - 1 if limit in ('MAX_SHARD', 'MAX_INPUT') else 0 if limit == 'MAX_SHARDS' else 1)
    with pytest.raises(ValueError):
        original.decode_textmaps([payload], spec)


def test_frozen_reader_retains_old_cache_until_changed_parameters_and_new_ids_are_complete(tmp_path, monkeypatch):
    cache = tmp_path / 'publisher-textmap.json'
    first = original.derive_native_parameters(native_method(parameters()))
    assert original.refresh_textmap_cache(cache, [shard(first, [(123, 'The earlier synthetic caption.')])], first,
                                          source_sha256='1' * 64) == 1
    old = cache.read_bytes()
    second = original.derive_native_parameters(native_method(parameters(1), interleaved=True))
    new = shard(second, [(123, 'The changed synthetic caption.'), (991122, '新字幕。')], [(776655, 991122)])
    for end in range(len(new)):
        with pytest.raises(ValueError):
            original.refresh_textmap_cache(cache, [new[:end]], second, source_sha256='2' * 64)
        assert cache.read_bytes() == old
    for damaged in [new + b'\0', shard(second), shard(second, [], [(56, 78)])]:
        with pytest.raises(ValueError):
            original.refresh_textmap_cache(cache, [damaged], second, source_sha256='2' * 64)
        assert cache.read_bytes() == old
    real_replace = Path.replace
    def interrupted(path, target):
        if Path(target) == cache:
            raise OSError('Synthetic interruption before cache publication')
        return real_replace(path, target)
    monkeypatch.setattr(Path, 'replace', interrupted)
    with pytest.raises(OSError, match='Synthetic interruption'):
        original.refresh_textmap_cache(cache, [new], second, source_sha256='2' * 64)
    assert cache.read_bytes() == old and list(tmp_path.iterdir()) == [cache]
    monkeypatch.setattr(Path, 'replace', real_replace)
    assert original.refresh_textmap_cache(cache, [new], second, source_sha256='2' * 64) == 3
    restarted = json.loads(cache.read_text(encoding='utf-8'))
    assert restarted['source_sha256'] == '2' * 64
    assert restarted['method_sha256'] == second.method_sha256
    assert restarted['parameters_sha256'] != json.loads(old)['parameters_sha256']
    assert restarted['texts'] == {'123': 'The changed synthetic caption.', '991122': '新字幕。', '776655': '新字幕。'}
    with pytest.raises(ValueError):
        original.refresh_textmap_cache(cache, [new], first, source_sha256='3' * 64)
    assert json.loads(cache.read_bytes()) == restarted


def test_invalid_utf8_overlong_fields_and_bad_cache_identity_never_replace_a_generation(tmp_path):
    spec = parameters()
    cache = tmp_path / 'saved.json'
    original.refresh_textmap_cache(cache, [shard(spec, [(1, 'A')])], spec, source_sha256='a' * 64)
    prior = cache.read_bytes()
    invalid_utf8 = bytearray(shard(spec, [(1, 'A')]))
    invalid_utf8[10] ^= ord('A') ^ 0xff
    long_field = bytearray(shard(spec, [(1, 'A')]))
    long_field[8] ^= 0x80
    for bad in (bytes(invalid_utf8), bytes(long_field)):
        with pytest.raises(ValueError):
            original.refresh_textmap_cache(cache, [bad], spec, source_sha256='b' * 64)
        assert cache.read_bytes() == prior
    with pytest.raises(ValueError):
        original.refresh_textmap_cache(cache, [shard(spec, [(1, 'B')])], spec, source_sha256='../not-a-source')
    assert cache.read_bytes() == prior
