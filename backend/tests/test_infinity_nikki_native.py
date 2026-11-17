import base64
from dataclasses import replace
import hashlib
import json
import struct
import unittest

from Crypto.Cipher import AES

from backend.infinity_nikki_native import decode_wrapped_metadata, extract_wrapper_material


def adrp(register, pc, target):
    immediate = ((target & ~4095) - (pc & ~4095)) >> 12
    assert -(1 << 20) <= immediate < (1 << 20)
    immediate &= (1 << 21) - 1
    return 0x90000000 | ((immediate & 3) << 29) | ((immediate >> 2) << 5) | register


def add(register, source, immediate):
    return 0x91000000 | (immediate << 10) | (source << 5) | register


def call(pc, target):
    return 0x94000000 | (((target - pc) >> 2) & 0x3ffffff)


def mov(register, immediate):
    return 0x52800000 | (immediate << 5) | register


def fixture(*, address_shift=0, file_shift=0, ambiguous=False, noise_only=False, wrong_hash=False, seed_offset=128,
            seed_text='authored test seed', suffix=b'fixture material!!'):
    """Authored ELF data only. None of these instruction bytes are executed."""
    ro_offset, text_offset = 0x1000 + file_shift, 0x2000 + file_shift
    ro_address, text_address = 0x20000 + address_shift, 0x50000 + address_shift
    marker, seed, states = ro_address + 32, ro_address + seed_offset, ro_address + 256
    builder, hash_function = text_address + 0x400, text_address + 0x800
    raw = bytearray(0x4200 + file_shift)
    names = b'\0.text\0.rodata\0.shstrtab\0'
    names_offset, shoff = 0x3800 + file_shift, 0x4000 + file_shift
    raw[:16] = b'\x7fELF\x02\x01\x01' + b'\0' * 9
    struct.pack_into('<HHIQQQIHHHHHH', raw, 16, 3, 183, 1, 0, 0, shoff, 0, 64, 56, 0, 64, 4, 3)
    raw[names_offset:names_offset + len(names)] = names
    for index, values in enumerate([
            (0, 0, 0, 0, 0, 0), (1, 1, 6, text_address, text_offset, 0x1000),
            (7, 1, 2, ro_address, ro_offset, 0x400), (15, 3, 0, 0, names_offset, len(names))]):
        struct.pack_into('<II4QII2Q', raw, shoff + index * 64, *values, 0, 0, 8, 0)

    def ro(at, value):
        position = ro_offset + at - ro_address
        raw[position:position + len(value)] = value

    def code(at, words):
        position = text_offset + at - text_address
        struct.pack_into('<' + 'I' * len(words), raw, position, *words)

    seed_bytes = seed_text.encode('utf-16-le')
    assert len(suffix) == 18
    ro(marker, '_XYLUAP_\0'.encode('utf-16-le'))
    ro(seed, seed_bytes + b'\0\0')
    initial = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476]
    if wrong_hash:
        initial[0] ^= 1
    ro(states, struct.pack('<4I', *initial))
    code(hash_function, [adrp(8, hash_function, states), mov(10, 0xe1f0),
        0x72800000 | (1 << 21) | (0xc3d2 << 5) | 10,
        0x3dc00000 | (((states & 4095) // 16) << 10) | (8 << 5), 0xd65f03c0])
    builder_words = [mov(8, 20), call(builder + 4, hash_function)]
    for byte in suffix:
        builder_words.extend([0xf9400000 | (19 << 5) | 8, mov(9, byte),
                              0x38206800 | (20 << 16) | (8 << 5) | 9])
    builder_words.append(0xd65f03c0)
    code(builder, builder_words)

    def consumer(at, source_seed):
        code(at, [adrp(1, at, marker), add(1, 1, marker & 4095), 0xd503201f,
                  adrp(1, at + 12, source_seed), add(1, 1, source_seed & 4095),
                  call(at + 20, text_address + 0xc00), call(at + 24, builder), 0xd65f03c0])

    if not noise_only:
        consumer(text_address + 0x40, seed)
    if ambiguous:
        other_seed = ro_address + 512
        ro(other_seed, 'different authored seed'.encode('utf-16-le') + b'\0\0')
        consumer(text_address + 0x140, other_seed)
    return bytes(raw), seed_bytes, suffix


def extract(raw):
    return extract_wrapper_material(raw, expected_native_sha256=hashlib.sha256(raw).hexdigest())


def wrap(plain, seed, suffix, *, tail=None):
    if tail is None:
        tail = b'\0' * ((-len(plain)) % 16)
    body = plain + tail
    assert len(body) % 16 == 0
    key = (hashlib.sha1(seed).digest() + suffix)[:32]
    return b'_XYLUAP_' + base64.b64encode(AES.new(key, AES.MODE_ECB).encrypt(body))


class NativeTests(unittest.TestCase):
    def test_explicit_crypto_preserves_original_wrapper_cipher_and_nul_rules(self):
        from backend.publisher_crypto import DesktopPublisherCrypto
        material = extract(fixture()[0])
        wrapped = wrap(b'{"generation":"authored"}', material.seed_utf16, material.suffix)
        calls = []
        class Crypto:
            def block_cipher(self, algorithm, mode, key, data):
                calls.append((algorithm, mode, len(key), len(data)))
                return DesktopPublisherCrypto().block_cipher(algorithm, mode, key, data)
        self.assertEqual(decode_wrapped_metadata(wrapped, material, crypto=Crypto()), {'generation': 'authored'})
        self.assertEqual(calls, [('AES', 'ECB', 32, 32)])

    def test_authored_path_survives_virtual_and_file_address_relocations(self):
        for address, file in [(0, 0), (0x1000, 0x100), (-0x10000, 0x80), (0x18700000, 0x400)]:
            with self.subTest(address=address, file=file):
                raw, seed, suffix = fixture(address_shift=address, file_shift=file)
                material = extract(raw)
                self.assertEqual(material.seed_utf16, seed)
                self.assertEqual(material.suffix, suffix)
                self.assertNotIn('authored test', repr(material))
                value = {'DefaultVersion': 'test', 'DelayGroups': {'voice': False}}
                self.assertEqual(decode_wrapped_metadata(wrap(json.dumps(value).encode(), seed, suffix), material), value)

    def test_unverified_changed_source_unknown_owner_and_ambiguous_paths_fail(self):
        raw, _, _ = fixture()
        with self.assertRaises(ValueError):
            extract_wrapper_material(raw, expected_native_sha256='0' * 64)
        changed = bytearray(raw)
        changed[100] ^= 1
        with self.assertRaises(ValueError):
            extract_wrapper_material(bytes(changed), expected_native_sha256=hashlib.sha256(raw).hexdigest())
        for kwargs in ({'ambiguous': True}, {'noise_only': True}, {'wrong_hash': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                extract(fixture(**kwargs)[0])

    def test_source_literal_near_section_end_needs_no_bytes_beyond_its_owner(self):
        raw, seed, suffix = fixture(seed_offset=768)
        material = extract(raw)
        self.assertEqual((material.seed_utf16, material.suffix), (seed, suffix))

    def test_changed_official_material_is_derived_from_the_new_source_generation(self):
        old = extract(fixture()[0])
        raw, seed, suffix = fixture(address_shift=0x94000, seed_text='ordinary update new material',
                                    suffix=b'revised material!!')
        new = extract(raw)
        wrapped = wrap(b'{"DefaultVersion":"next"}', seed, suffix)
        self.assertEqual(decode_wrapped_metadata(wrapped, new), {'DefaultVersion': 'next'})
        self.assertNotEqual(new.source_sha256, old.source_sha256)
        with self.assertRaises(ValueError):
            decode_wrapped_metadata(wrapped, old)

    def test_elf_bounds_architecture_and_required_sections_are_checked(self):
        raw, _, _ = fixture()
        for position, replacement in [(0, b'bad!'), (18, struct.pack('<H', 62)),
                                      (40, struct.pack('<Q', len(raw))), (58, struct.pack('<H', 63))]:
            broken = bytearray(raw)
            broken[position:position + len(replacement)] = replacement
            with self.subTest(position=position), self.assertRaises(ValueError):
                extract(bytes(broken))
        with self.assertRaises(ValueError):
            extract(raw[:60])

    def test_original_first_nul_boundary_allows_uninitialized_last_block_bytes(self):
        raw, seed, suffix = fixture()
        material = extract(raw)
        plain = b'{"value":true}'
        tail = b'\0' + b'x' * ((-len(plain) - 1) % 16)
        self.assertEqual(decode_wrapped_metadata(wrap(plain, seed, suffix, tail=tail), material), {'value': True})
        # Original consumers trim a first NUL, not a guessed PKCS7 value.
        with self.assertRaises(ValueError):
            decode_wrapped_metadata(wrap(plain, seed, suffix, tail=bytes([2]) * 2), material)

    def test_no_nul_exact_block_json_and_nonascii_metadata(self):
        raw, seed, suffix = fixture()
        material = extract(raw)
        plain = b'{"value":123456}'
        self.assertEqual(len(plain), 16)
        self.assertEqual(decode_wrapped_metadata(wrap(plain, seed, suffix), material), {'value': 123456})
        value = {'text': '你好'}
        self.assertEqual(decode_wrapped_metadata(wrap(json.dumps(value, ensure_ascii=False).encode(), seed, suffix), material), value)

    def test_corrupt_wrappers_wrong_material_and_noncanonical_json_fail(self):
        raw, seed, suffix = fixture()
        material = extract(raw)
        for bad in (b'', b'wrong___AAAA', b'_XYLUAP_***', b'_XYLUAP_' + base64.b64encode(b'123')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                decode_wrapped_metadata(bad, material)
        for plain in (b'[]', b'{}', b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":"\xff"}', b'{"a":1}junk'):
            with self.subTest(plain=plain), self.assertRaises(ValueError):
                decode_wrapped_metadata(wrap(plain, seed, suffix), material)
        with self.assertRaises(ValueError):
            decode_wrapped_metadata(wrap(b'{"a":1}', seed, suffix), replace(material, seed_utf16=b'xx'))
        with self.assertRaises(ValueError):
            decode_wrapped_metadata(wrap(b'{"a":1}' + b'\0' * 40, seed, suffix), material)


if __name__ == '__main__':
    unittest.main()
