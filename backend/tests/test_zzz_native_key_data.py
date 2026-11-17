"""Original-data key rotation/relocation must not require an executable client."""
import base64
import hashlib
import random
import struct

import pytest
from Crypto.PublicKey import RSA

from backend import zzz_native_key_data as original


@pytest.fixture(scope='module')
def keys():
    return RSA.generate(1024), RSA.generate(1024)


def initializer(key, mask=0xb2, *, registers=(2, 0, 1), missing=False):
    values = {'Modulus': key.n, 'Exponent': key.e, 'D': key.d, 'P': key.p, 'Q': key.q,
              'DP': key.d % (key.p - 1), 'DQ': key.d % (key.q - 1),
              'InverseQ': pow(key.q, -1, key.p)}
    xml = '<RSAKeyValue>' + ''.join(
        f'<{name}>{base64.b64encode(value.to_bytes((value.bit_length()+7)//8,"big")).decode()}</{name}>'
        for name, value in values.items()) + '</RSAKeyValue>'
    plain = xml.encode() + bytes(-len(xml) % 8)
    encoded = bytearray([plain[0] ^ mask])
    for value in plain[1:]:
        encoded.append(value ^ encoded[-1])
    literal, receiver, data = registers
    header = b'\xba' + struct.pack('<I', len(encoded)) + b'\xe8\0\0\0\0'
    lea = bytes([0x48 | (4 if data >= 8 else 0) | (1 if receiver >= 8 else 0),
                 0x8d, 0x40 | (data % 8 << 3) | receiver % 8, 32])
    stores = []
    for offset in range(0, len(encoded), 8):
        if missing and offset == 8:
            continue
        instruction = bytes([0x48 | (literal // 8), 0xb8 | literal % 8]) + encoded[offset:offset+8]
        displacement = offset + 32
        mode = 1 if displacement < 128 else 2
        instruction += b'\x45\x31\xe4'  # Authored unrelated-register noise; data only.
        instruction += bytes([0x48 | (4 if literal >= 8 else 0) | (receiver // 8), 0x89,
                              mode << 6 | (literal % 8 << 3) | receiver % 8])
        instruction += displacement.to_bytes(1 if mode == 1 else 4, 'little')
        stores.append(instruction)
    random.Random(723).shuffle(stores)
    xor = bytes(([0x41] if data >= 8 else []) + [0x80, 0x30 | data % 8, mask])
    return header + lea + b''.join(stores) + xor + b'\x90' * 16


def image(data, *, rva=0x301000, offset=0x800, name=b'.upx0'):
    header = bytearray(offset)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 60, 64)
    header[64:68] = b'PE\0\0'
    struct.pack_into('<HH', header, 68, 0x8664, 1)
    struct.pack_into('<H', header, 84, 240)
    struct.pack_into('<H', header, 88, 0x20b)
    section = 88 + 240
    header[section:section + len(name)] = name
    struct.pack_into('<4I', header, section + 8, len(data), rva, len(data), offset)
    struct.pack_into('<I', header, section + 36, 0x60000020)
    return bytes(header) + data


def locate(payload):
    reads = []
    def read(start, length):
        reads.append((start, length))
        return payload[start:start + length]
    plan = original.source_plan(len(payload), read)
    assert all(start + length <= plan['offset'] for start, length in reads)
    return original.candidates(payload[plan['offset']:plan['offset'] + plan['bytes']], plan)


@pytest.mark.parametrize('registers', [(2, 0, 1), (11, 3, 10)])
def test_changed_keys_addresses_masks_and_literal_order_follow_original_input(keys, registers):
    first = locate(image(b'\x90' * 53 + initializer(keys[0], registers=registers)))
    changed = locate(image(b'\x90' * 913 + initializer(keys[1], 0x31, registers=registers),
                           rva=0x711000, offset=0x1800))
    assert len(first) == len(changed) == 1
    assert first[0].key.n == keys[0].n and changed[0].key.n == keys[1].n
    assert first[0].proof['initializer_offset'] != changed[0].proof['initializer_offset']
    assert first[0].proof['array_sha256'] != changed[0].proof['array_sha256']
    assert 'Modulus' not in repr(changed[0]) and str(keys[1].d) not in repr(changed[0])


def test_distinct_candidates_are_preserved_for_response_join_and_identical_keys_deduplicate(keys):
    payload = initializer(keys[0]) + initializer(keys[1], 0x92) + initializer(keys[0])
    found = locate(image(payload))
    assert {candidate.key.n for candidate in found} == {key.n for key in keys}


def test_larger_original_rsa_key_uses_its_authored_array_length_and_parameters():
    key = RSA.generate(2048)
    candidate, = locate(image(initializer(key, 0x6a), rva=0x916000))
    assert candidate.key.size_in_bits() == 2048 and candidate.key.n == key.n
    assert candidate.proof['array_bytes'] > 1024


@pytest.mark.parametrize('change', ['missing-store', 'wrong-mask', 'truncated', 'foreign-section', 'wrong-machine'])
def test_invalid_new_key_source_fails_without_borrowing_an_old_key(keys, change):
    data = initializer(keys[1], missing=change == 'missing-store')
    if change == 'wrong-mask':
        data = data[:-17] + bytes([data[-17] ^ 1]) + data[-16:]
    payload = image(data, name=b'.other' if change == 'foreign-section' else b'.upx0')
    if change == 'truncated':
        payload = payload[:-8]
    elif change == 'wrong-machine':
        payload = payload[:68] + b'\x64\xaa' + payload[70:]
    with pytest.raises(ValueError, match='original ZZZ gateway key data'):
        locate(payload)


def test_source_plan_reads_only_header_metadata_before_download_consent(keys):
    data = image(initializer(keys[0]))
    forbidden = 0x800
    def header_only(start, count):
        assert start + count <= forbidden
        return data[start:start + count]
    result = original.source_plan(len(data), header_only)
    assert result['offset'] == forbidden and result['bytes'] < original.MAX_SECTION


def test_provenance_has_hashes_and_bounds_without_private_xml(keys):
    candidate, = locate(image(initializer(keys[0])))
    assert set(candidate.proof) == {'profile', 'section', 'initializer_offset', 'initializer_bytes',
                                    'array_bytes', 'array_sha256'}
    assert len(candidate.proof['array_sha256']) == 64
    assert hashlib.sha256(keys[0].export_key()).hexdigest() not in repr(candidate.proof)


def test_streamed_source_preserves_initializers_crossing_windows_without_whole_section_read(keys, monkeypatch):
    monkeypatch.setattr(original, 'READ_WINDOW', 1024)
    monkeypatch.setattr(original, 'MAX_INITIALIZER', 4096)
    data = b'\x90' * 877 + initializer(keys[0]) + b'\x90' * 6003 + initializer(keys[1], 0x31)
    plan = {'name': '.upx0', 'offset': 913, 'bytes': len(data), 'profile': original.PROFILE}
    reads = []
    def read(start, count):
        reads.append((start, count))
        return data[start - plan['offset']:start - plan['offset'] + count]
    found = original.read_candidates(plan, read)
    assert {candidate.key.n for candidate in found} == {key.n for key in keys}
    assert max(count for _, count in reads) <= 5120 < len(data)
