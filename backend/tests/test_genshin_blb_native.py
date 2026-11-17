"""Synthetic native input contracts contain no original game data or keys."""
import base64
import json
import struct
import platform
import sys

import pytest

from backend import genshin_blb_native as native
from backend.genshin_native_x64 import decoder


requires_decoder = pytest.mark.skipif(
    not (sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64')),
    reason='Explicit Windows amd64 decoder closure')


class ToyImage:
    def __init__(self, *, shifted=0, keys=(b'toy-key1',), duplicate=False, truncated=False, broken_gf=False):
        self.base = 0x140000000
        self.text, self.rdata = 0x1000 + shifted, 0x5000 + shifted
        self.sections = {'.text': (self.text, 4096, 0, 4096), '.rdata': (self.rdata, 8192, 4096, 8192)}
        self.executable_sections = ['.text']
        blob = bytearray(12288)
        def put(offset, value):
            blob[4096 + offset:4096 + offset + len(value)] = value
            return self.rdata + offset
        gf = native.standard_tables()
        shift = put(0, bytes(range(48)))
        sbox = put(64, bytes((i * 73 + 11) % 256 for i in range(1024)))
        mul = put(1100, b'12345678')
        log = bytearray(gf['GF256Log']); log[0] = 93
        if broken_gf: log[19] ^= 1
        log = put(1120, log); exp = put(1400, gf['GF256Exp'])
        rc4data = put(1800, bytes((i * 5 + 3) % 256 for i in range(256)))
        self.methods = {}
        rc4 = self.text + 0x800
        def body(start, variant):
            code = bytearray(b'\x90' * variant)
            def lea(prefix, target):
                site = start + len(code)
                code.extend(prefix + struct.pack('<i', target - site - 7))
            def call(target):
                site = start + len(code)
                code.extend(b'\xe8' + struct.pack('<i', target - site - 5))
            return code, lea, call
        for index, key in enumerate(keys):
            assert len(key) == 8
            start = self.text + index * 0x200
            code, lea, call = body(start, 0)
            for op, target in [(b'\x4c\x8d\x1d', sbox), (b'\x4c\x8d\x3d', put(2100 + index * 16, key)),
                               (b'\x4c\x8d\x15', mul), (b'\x4c\x8d\x0d', log),
                               (b'\x4c\x8d\x35', exp), (b'\x48\x8d\x35', shift)]:
                lea(op, target)
            for offset in range(32, 48): code.extend(b'\x0f\xb6\x46' + bytes([offset]))
            for number in (3, 4, 7, 15, 256, 768): code.extend(b'\xb8' + struct.pack('<I', number))
            code.extend(b'\x41\x0f\xb6\x14\x07\x41\x32\x14\x03')
            call(rc4); code.append(0xc3)
            self.methods[start] = bytes(code)
        if duplicate:
            start = self.text + 0x600
            original_start = self.text
            # Relocate every RIP operand and call rather than copy stale addresses.
            original = bytearray(self.methods[original_start])
            for index in (3, 10, 17, 24, 31, 38, len(original) - 5):
                displacement, = struct.unpack_from('<i', original, index)
                struct.pack_into('<i', original, index, displacement + original_start - start)
            self.methods[start] = bytes(original)
        code, lea, call = body(rc4, 0)
        lea(b'\x48\x8d\x15', rc4data)
        code.extend(b'\x41\xb8\x00\x01\x00\x00'); call(self.text + 0xf00)
        for number in (7, 255, 0xab, 9, 2, 1): code.extend(b'\xb8' + struct.pack('<I', number))
        code.extend(b'\x00\x01\x28\x01\x30\x01\x88\x01\x0f\xb6\x01')
        code.extend(b'\x90' * (128 - len(code))); code.append(0xc3)
        self.methods[rc4] = bytes(code)
        for start, value in self.methods.items(): blob[start - self.text:start - self.text + len(value)] = value
        self.data = bytes(blob[:-7000] if truncated else blob)

    def offset(self, rva, size=1):
        matches = [raw + rva - begin for begin, _, raw, count in self.sections.values()
                   if begin <= rva and rva + size <= begin + count]
        if len(matches) != 1 or matches[0] + size > len(self.data): raise ValueError('outside toy image')
        return matches[0]

    def function_start(self, rva):
        return next((start for start, body in self.methods.items() if start <= rva < start + len(body)), None)

    def window(self, start):
        return self.methods[start]

    def instructions(self, start):
        return list(decoder().disasm(self.window(start), self.base + start))


def test_math_is_standard_and_zero_input_sentinel_is_irrelevant():
    tables = native.standard_tables()
    assert native.multiply(0x57, 0x13) == 0xfe
    assert tables['Blb3AESSBox'][0] == 0x63
    assert len(set(tables['GF256Exp'][:255])) == 255
    for value in range(1, 256):
        assert tables['GF256Exp'][tables['GF256Log'][value]] == value


@pytest.mark.parametrize('shifted', [0, 0x12000])
@requires_decoder
def test_original_input_changes_parameters_without_fixed_addresses_or_seed(shifted):
    first, = native.discover_candidates(ToyImage(shifted=shifted))
    second, = native.discover_candidates(ToyImage(shifted=shifted, keys=(b'new-key2',)))
    assert first.sha256 != second.sha256
    assert base64.b64decode(json.loads(second.parameters)['Blb3Key']) == b'new-key2'
    assert first.method_sha256s and len(first.method_sha256s) == 2


@requires_decoder
def test_equivalent_compilations_keep_all_hashes_and_real_variants_stay_ambiguous():
    one, = native.discover_candidates(ToyImage(duplicate=True))
    assert len(one.method_sha256s) == 3
    many = native.discover_candidates(ToyImage(keys=(b'toy-key1', b'new-key2')))
    assert len(many) == 2 and len({row.sha256 for row in many}) == 2


@pytest.mark.parametrize('options', [{'truncated': True}, {'broken_gf': True}])
@requires_decoder
def test_truncated_or_incompatible_originals_never_produce_a_profile(options):
    with pytest.raises(ValueError): native.discover_candidates(ToyImage(**options))


@requires_decoder
def test_reference_budget_fails_closed(monkeypatch):
    monkeypatch.setattr(native, 'MAX_REFERENCES', 1)
    with pytest.raises(ValueError): native.discover_candidates(ToyImage())
