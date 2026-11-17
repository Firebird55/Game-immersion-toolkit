from dataclasses import replace
import hashlib
import struct
import unittest

from Crypto.Cipher import AES

from backend.infinity_nikki_pak_material import decode_default_index, extract_default_pak_material
from backend.tests.test_infinity_nikki_native import add, adrp, call, fixture as wrapper_fixture


def adr(register, pc, target):
    value = target - pc
    assert -(1 << 20) <= value < (1 << 20)
    value &= (1 << 21) - 1
    return 0x10000000 | ((value & 3) << 29) | ((value >> 2) << 5) | register


def fixture(*, shift=0, file_shift=0, key=None, adrp_binding=False, failure=None, bti=False, copy_form='split-vectors'):
    """Synthetic source graph, not an executable/imported client component."""
    original, _, _ = wrapper_fixture(address_shift=shift, file_shift=file_shift)
    raw = bytearray(original)
    text, text_at, ro, ro_at = 0x50000 + shift, 0x2000 + file_shift, 0x20000 + shift, 0x1000 + file_shift
    storage = 0x30080 + shift
    setter, binding, callback = text + 0xb80, text + 0xc80, text + 0xd00
    key = bytes(range(32)) if key is None else key
    assert len(key) == 32
    vector_a, vector_b = ro + 384, ro + 448
    raw[ro_at + 384:ro_at + 400], raw[ro_at + 448:ro_at + 464] = key[:16], key[16:]
    # A writable PT_LOAD proves the delegate storage; no body bytes are loaded
    # from this BSS-like area when reading the source registration.
    struct.pack_into('<Q', raw, 32, 64)
    struct.pack_into('<H', raw, 56, 1)
    struct.pack_into('<II6Q', raw, 64, 1, 6 if failure != 'readonly-storage' else 4,
                     0, storage & ~4095, 0, 0, 4096, 4096)

    def put(address, words):
        struct.pack_into('<' + 'I' * len(words), raw, text_at + address - text, *words)

    # A SHA-1/index consumer passes the actual 16-byte key GUID to its helper.
    index = text + 0x900
    words = [0xd503201f, 0xd503201f, 0xa94a8e62, 0xd503201f, 0xd503201f,
             call(index + 20, text + 0x980), 0xd503201f, 0xd503201f, 0xd503201f,
             call(index + 36, text + 0x800), 0xd65f03c0]
    if failure == 'no-guid-consumer':
        words[2] = 0xd503201f
    put(index, words)
    put(text + 0x980, [call(text + 0x980, text + 0xa00), 0xd65f03c0])
    put(text + 0xa00, [0x6f00e400, 0xad000000 if failure != 'wrong-output' else 0xad000020,
                       call(text + 0xa08, text + 0xa80), 0xd503201f,
                       call(text + 0xa10, text + 0xa80), 0xd65f03c0])
    put(text + 0xa80, [adrp(0, text + 0xa80, storage), add(0, 0, storage & 4095), 0xd65f03c0])
    object_slot = storage + (8 if failure == 'unrelated-receiver' else 0)
    setter_words = [0xa9bd7bfd, 0xaa0003f3, adrp(20, setter + 8, storage), add(20, 20, storage & 4095),
                    adrp(8, setter + 16, object_slot),
                    0xf9400000 | (((object_slot & 4095) // 8) << 10) | (8 << 5) | 20]
    if failure == 'clobbered-argument':
        setter_words.append(0xaa1f03f3)  # MOV X19,XZR removes the captured input.
    if failure == 'self-move':
        setter_words.append(0xaa1303f3)
    setter_words.extend([0xa9000000 | (2 << 15) | (19 << 10) | (20 << 5), 0xd65f03c0])
    if bti:
        setter_words.insert(0, 0xd503245f)
    put(setter, setter_words)
    if adrp_binding:
        binding_words = [adrp(0, binding, callback), add(0, 0, callback & 4095),
                         call(binding + 8, setter), 0xd65f03c0]
    else:
        binding_words = [adr(0, binding, callback), call(binding + 4, setter), 0xd65f03c0]
    if failure == 'unbound-producer':
        binding_words = [0xd503201f] * len(binding_words)
    if failure == 'wrong-callback-argument':
        binding_words[0] = adr(1, binding, callback)
    put(binding, binding_words)
    # The two vector origins are deliberately noncontiguous. Only output copy
    # coverage and the actual registered path establish the 32-byte parameter.
    callback_words = [adrp(14, callback, vector_a), adrp(15, callback + 4, vector_b),
                      0x3dc00000 | (((vector_a & 4095) // 16) << 10) | (14 << 5) | 3,
                      0x3dc00000 | (((vector_b & 4095) // 16) << 10) | (15 << 5) | 7,
                      0xad000000 | (7 << 10) | 3, 0xd65f03c0]
    if copy_form in ('paired-vectors', 'scalar'):
        raw[ro_at + 384:ro_at + 416] = key
        callback_words = [adrp(14, callback, vector_a), add(14, 14, vector_a & 4095)]
        if copy_form == 'paired-vectors':
            callback_words += [0xad400000 | (7 << 10) | (14 << 5) | 3,
                               0xad000000 | (7 << 10) | 3, 0xd65f03c0]
        else:
            callback_words += [0xa9400000 | (9 << 10) | (14 << 5) | 8,
                               0xa9400000 | (2 << 15) | (11 << 10) | (14 << 5) | 10,
                               0xa9000000 | (9 << 10) | 8,
                               0xa9000000 | (2 << 15) | (11 << 10) | 10, 0xd65f03c0]
    if failure == 'incomplete-producer':
        callback_words[4] = 0xd503201f
    if failure == 'wrong-output-base':
        callback_words[4] |= 1 << 5
    if failure == 'producer-clobber':
        callback_words[4] = 0xaa1f03e0
    if bti:
        callback_words.insert(0, 0xd503245f)
    put(callback, callback_words)
    # An unregistered static-copy lookalike must never enter discovery.
    put(text + 0xe00, [adrp(14, text + 0xe00, vector_a), adrp(15, text + 0xe04, vector_b),
                      *callback_words[2:]])
    return bytes(raw), key


def extract(raw):
    return extract_default_pak_material(raw, expected_native_sha256=hashlib.sha256(raw).hexdigest())


class DefaultPakMaterialTests(unittest.TestCase):
    def test_current_source_registration_survives_addresses_registers_and_linker_relaxation(self):
        for shift, file_shift, adrp_binding in [(0, 0, False), (0x72000, 0x100, True),
                                               (-0x10000, 0x80, False), (0x18000000, 0x400, True)]:
            with self.subTest(shift=shift, file=file_shift):
                raw, key = fixture(shift=shift, file_shift=file_shift, adrp_binding=adrp_binding)
                material = extract(raw)
                self.assertEqual(material.parameter, key)
                self.assertNotIn(repr(key), repr(material))
                self.assertEqual(material.registered_callback, 0x50d00 + shift)
                self.assertNotEqual(material.source_addresses[16], material.source_addresses[15] + 1)

    def test_normal_new_generation_gets_new_authored_parameter_not_an_old_key(self):
        old = extract(fixture()[0])
        raw, expected = fixture(shift=0x69000, key=bytes(reversed(range(32))))
        new = extract(raw)
        self.assertEqual(new.parameter, expected)
        self.assertNotEqual(old.source_sha256, new.source_sha256)
        self.assertNotEqual(old.parameter, new.parameter)

    def test_branch_target_landing_pads_preserve_the_registered_source(self):
        raw, key = fixture(bti=True)
        self.assertEqual(extract(raw).parameter, key)

    def test_paired_vector_and_scalar_copy_forms_preserve_all_output_bytes(self):
        for form in ('paired-vectors', 'scalar'):
            with self.subTest(form=form):
                raw, key = fixture(copy_form=form)
                self.assertEqual(extract(raw).parameter, key)

    def test_boundaries_reject_lookalikes_unrelated_storage_and_unproven_copy_paths(self):
        for failure in ['readonly-storage', 'no-guid-consumer', 'wrong-output', 'unrelated-receiver',
                        'clobbered-argument', 'unbound-producer', 'wrong-callback-argument',
                        'incomplete-producer', 'wrong-output-base', 'producer-clobber']:
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                extract(fixture(failure=failure)[0])
        raw, _ = fixture(failure='self-move')
        self.assertEqual(extract(raw).parameter, bytes(range(32)))

    def test_changed_or_unverified_source_is_not_accepted(self):
        raw, _ = fixture()
        with self.assertRaises(ValueError):
            extract_default_pak_material(raw, expected_native_sha256='0' * 64)
        changed = bytearray(raw)
        changed[0x1000 + 384] ^= 1
        with self.assertRaises(ValueError):
            extract_default_pak_material(bytes(changed), expected_native_sha256=hashlib.sha256(raw).hexdigest())

    def test_original_default_aes_xor_index_and_plaintext_sha1_controls(self):
        material = extract(fixture()[0])
        plain = b'authored index metadata'.ljust(64, b'\0')
        before_cipher = bytearray(plain)
        for n in range(0, len(plain), 16):
            before_cipher[n] ^= material.parameter[-1]
            before_cipher[n + 15] ^= material.parameter[0]
        cipher = AES.new(material.parameter, AES.MODE_ECB).encrypt(before_cipher)
        expected = hashlib.sha1(plain).digest()
        self.assertEqual(decode_default_index(cipher, material, expected, key_guid=bytes(16)), plain)
        from backend.publisher_crypto import DesktopPublisherCrypto
        calls = []
        class Crypto:
            def block_cipher(self, algorithm, mode, key, data):
                calls.append((algorithm, mode, len(key), len(data)))
                return DesktopPublisherCrypto().block_cipher(algorithm, mode, key, data)
        self.assertEqual(decode_default_index(cipher, material, expected, key_guid=bytes(16), crypto=Crypto()), plain)
        self.assertEqual(calls, [('AES', 'ECB', 32, len(cipher))])
        cases = [(cipher[:-1], material, expected), (cipher, material, b'0' * 20),
                 (cipher, replace(material, parameter=bytes(reversed(range(32)))), expected),
                 (AES.new(material.parameter, AES.MODE_ECB).encrypt(plain), material, expected)]
        for value, source, digest in cases:
            with self.subTest(bytes=len(value)), self.assertRaises(ValueError):
                decode_default_index(value, source, digest, key_guid=bytes(16))
        with self.assertRaises(ValueError):
            decode_default_index(cipher, material, expected, key_guid=b'\1' + bytes(15))


if __name__ == '__main__':
    unittest.main()
