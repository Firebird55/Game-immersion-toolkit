"""Authored PE/compiler fixtures; no original publisher code or key material."""
import struct

import pytest

from backend.nte_original_updater import derive
from backend.nte_updater_native import decode


class Code:
    def __init__(self, address):
        self.address, self.data = address, bytearray()

    def put(self, value):
        self.data.extend(bytes.fromhex(value))

    def rip(self, opcode, target):
        self.put(opcode)
        self.data.extend(struct.pack('<i', target - self.address - len(self.data) - 4))

    def call(self, target):
        self.rip('e8', target)


def authored_sdk(*, base=0x180000000, member=0x80):
    data = bytearray(0x8400)
    data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', data, 0x84, 0x8664, 4)
    struct.pack_into('<H', data, 0x94, 240)
    optional = 0x98
    struct.pack_into('<H', data, optional, 0x20b)
    struct.pack_into('<Q', data, optional + 24, base)
    struct.pack_into('<II', data, optional + 56, 0xa000, 0x400)
    sections = [(b'.text', 0x1000, 0x4000, 0x400, 0x60000020),
                (b'.rdata', 0x6000, 0x2000, 0x4400, 0x40000040),
                (b'.data', 0x8000, 0x1000, 0x6400, 0xc0000040),
                (b'.pdata', 0x9000, 0x1000, 0x7400, 0x40000040)]
    for index, (name, rva, size, offset, flags) in enumerate(sections):
        at = optional + 240 + index * 40
        data[at:at + len(name)] = name
        struct.pack_into('<IIII', data, at + 8, size, rva, size, offset)
        struct.pack_into('<I', data, at + 36, flags)

    def write(rva, value):
        _, start, _, offset, _ = next(s for s in sections if s[1] <= rva < s[1] + s[2])
        at = offset + rva - start
        data[at:at + len(value)] = value

    write(0x6000, b'PatcherXML0\0')
    write(0x6020, b'appId\0')
    write(0x6040, b'fixture!')
    write(0x6060, b'fixture-iv')
    write(0x6100, struct.pack('<5I', 419, 16, 16, 16, 0x1002))
    write(0x6ff0, b'\x01\0\0\0')
    addresses = {key: base + value for key, value in {'consumer': 0x1000, 'cipher': 0x1300,
        'setter': 0x1400, 'writer': 0x1500, 'getter': 0x1600, 'json': 0x1800,
        'context': 0x1b00, 'provider': 0x1b20, 'dummy': 0x1b40}.items()}
    functions = []

    def code(name, owned=True):
        result = Code(addresses[name])
        functions.append((name, result, owned))
        return result

    c = code('consumer')
    c.rip('48 8d 15', base + 0x6000)
    c.put('48 c7 45 98 0f000000 48 c7 45 90 0a000000')
    c.rip('f2 0f 10 05', base + 0x6060)
    c.put('f2 0f 11 45 80')
    c.rip('0f b7 05', base + 0x6068)
    c.put('66 89 45 88 c6 45 8a 00 4c 8d 4d 80')
    c.rip('4c 8d 05', base + 0x8000)
    c.put('48 8d 55 c0 48 8d 4d e0')
    c.call(addresses['cipher']); c.put('c3')

    c = code('cipher')
    c.put('bb 10000000 41 b0 30 41 b0 30 48 83 f8 10')
    c.call(addresses['provider']); c.put('48 8b d0')
    c.call(addresses['dummy']); c.put('c3')

    c = code('setter', False)
    c.rip('48 8d 05', base + 0x8000)
    c.put('48 3b c1 74 19 48 83 79 18 10 48 8b d1 72 03 48 8b 11 4c 8b 41 10 48 8b c8')
    c.rip('e9', addresses['dummy']); c.put('c3')

    c = code('writer')
    c.call(addresses['getter']); c.put('90 48 8b c8')
    c.call(addresses['setter']); c.put('c3')

    c = code('getter')
    c.call(addresses['context'])
    c.put('4c 8d 80'); c.data.extend(struct.pack('<i', member))
    c.put('49 8b 48 10')
    c.rip('48 8d 05', base + 0x6040)
    c.put('48 c7 44 24 30 08000000 48 89 44 24 28 48 89 4c 24 20 48 8b cb')
    c.call(addresses['dummy']); c.put('c3')

    c = code('json')
    c.rip('48 8d 15', base + 0x6020)
    c.put('48 8d 4d a0'); c.call(addresses['dummy'])
    c.put('4c 8d 4d c0 4c 8d 45 e0 48 8d 55 a0 48 8d 4c 24 70')
    c.call(addresses['dummy']); c.put('90')
    c.call(addresses['context'])
    c.put('48 8d 88'); c.data.extend(struct.pack('<i', member))
    c.put('48 8d 55 e0'); c.call(addresses['dummy']); c.put('c3')

    c = code('context', False); c.rip('48 8b 05', base + 0x8040); c.put('c3')
    c = code('provider', False); c.rip('48 8d 05', base + 0x6100); c.put('c3')
    c = code('dummy', False); c.put('c3')
    table = bytearray()
    for name, body, owned in functions:
        rva = addresses[name] - base
        write(rva, body.data)
        if owned:
            table.extend(struct.pack('<III', rva, rva + len(body.data), 0x6ff0))
    write(0x9000, table)
    struct.pack_into('<II', data, optional + 112 + 3 * 8, 0x9000, len(table))
    return bytes(data)


@pytest.mark.parametrize('base,member', [(0x180000000, 0x80), (0x190000000, 0x180)])
def test_original_consumer_join_derives_relocated_parameters_without_release_addresses(base, member):
    result = derive(authored_sdk(base=base, member=member), {'appId': 'authored-demo'})
    assert result.key == (b'authored-demofixture!')[:16]
    assert result.iv == b'fixture-iv000000'
    assert 'fixture' not in repr(result) and 'authored-demo' not in repr(result)


def test_native_instruction_decoder_does_not_invent_a_call_inside_a_mov_immediate():
    row = decode(bytes.fromhex('48 b8 e800000000000000'), 0x1000)
    assert row.size == 10 and row.call is None


@pytest.mark.parametrize('data', [bytes.fromhex('e8 0102'), bytes.fromhex('c5 f8 77'), bytes.fromhex('62 f1 7c 48 10 00')])
def test_truncated_or_unsupported_native_forms_fail_closed(data):
    with pytest.raises(ValueError): decode(data, 0x1000)


@pytest.mark.parametrize('configuration', [{}, {'appId': None}, {'appId': ''}, {'appId': 'a\0b'}])
def test_missing_or_malformed_original_app_id_is_not_guessed(configuration):
    with pytest.raises(ValueError): derive(authored_sdk(), configuration)


@pytest.mark.parametrize('original,changed', [
    ('48 8d 88 80000000', '48 8d 88 88000000'),
    ('4c 8b 41 10', '4c 8b 41 08'),
    ('48 89 4c 24 20', '48 89 54 24 20'),
])
def test_changed_native_field_or_string_ownership_is_not_an_accepted_parameter_description(original, changed):
    raw = authored_sdk(); before, after = bytes.fromhex(original), bytes.fromhex(changed)
    assert raw.count(before) == 1
    with pytest.raises(ValueError): derive(raw.replace(before, after), {'appId': 'authored-demo'})


def test_duplicate_native_protocol_marker_rejects_ambiguous_module():
    raw = bytearray(authored_sdk())
    raw[0x4500:0x450c] = b'PatcherXML0\0'
    with pytest.raises(ValueError): derive(bytes(raw), {'appId': 'authored-demo'})


def test_new_original_suffix_is_read_as_data_and_never_kept_from_a_prior_description():
    raw = authored_sdk()
    prior = derive(raw, {'appId': 'authored-demo'})
    updated = derive(raw.replace(b'fixture!', b'changed!'), {'appId': 'authored-demo'})
    assert prior.key != updated.key and prior.sdk_sha256 != updated.sdk_sha256
    assert prior.iv == updated.iv
