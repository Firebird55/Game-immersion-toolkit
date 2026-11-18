"""Authored two-hash PAK fixtures; no publisher files or key material."""
from dataclasses import replace
import hashlib
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch
import zlib

from Crypto.Cipher import AES

from backend.infinity_nikki_pak import Archive
from backend.infinity_nikki_pak_material import DefaultPakMaterial


MATERIAL = DefaultPakMaterial(bytes(range(32)), 'f' * 64, 0, 0, ())


def number(value, kind='i'):
    return struct.pack('<' + kind, value)


def string(value, wide=False):
    raw = value.encode('utf-16-le' if wide else 'utf-8')
    width = 2 if wide else 1
    return number(-(len(raw) // 2 + 1) if wide else len(raw) + 1) + raw + bytes(width)


def align(raw):
    return raw + bytes((-len(raw)) % 16)


def encrypt(raw):
    raw = bytearray(align(raw))
    for at in range(0, len(raw), 16):
        raw[at] ^= MATERIAL.parameter[-1]
        raw[at + 15] ^= MATERIAL.parameter[0]
    return AES.new(MATERIAL.parameter, AES.MODE_ECB).encrypt(raw)


def fixture(*, encrypted=True, index_encrypted=True, wide=False, long_fields=False,
            failure=None, revision=0, compressed=True):
    payload, encoded = bytearray(), bytearray()
    specs = [('plain.lua', b'authored plain source' + bytes([revision]), False),
             ('empty.lua', b'', False)]
    if compressed:
        specs += [('packed.lua', (b'authored block data' * 300) + bytes([revision]), True)]
    rows = []
    for name, plain, packed in specs:
        offset, position = len(payload), len(encoded)
        blocks = [zlib.compress(plain[i:i + 2048]) for i in range(0, len(plain), 2048)] if packed else []
        count = len(blocks)
        header_size = 73 + (4 + 16 * count if packed else 0)
        ranges, cursor = [], header_size
        for block in blocks:
            ranges.append((cursor, cursor + len(block)))
            cursor += len(align(block)) if encrypted else len(block)
        stored = cursor - header_size if packed else len(plain)
        header = struct.pack('<qqqI', offset, stored, len(plain), int(packed))
        header += bytes(20) + hashlib.sha1(plain).digest()
        if packed:
            header += number(count) + b''.join(struct.pack('<qq', *pair) for pair in ranges)
        header += struct.pack('<BI', int(encrypted), 2048 if packed else 0)
        assert len(header) == header_size
        payload += header
        for block in blocks if packed else [plain]:
            payload += encrypt(block) if encrypted and block else block
        bits = ((0 if long_fields else (3 << 30) | (1 << 22)) | int(encrypted) << 29 |
                int(packed) << 23 | count << 6 | int(packed))
        encoded += number(bits, 'I')
        kind = 'q' if long_fields else 'I'
        encoded += number(offset, kind) + number(len(plain), kind)
        if packed:
            encoded += number(stored, kind)
        if count != 1 or encrypted:
            encoded += b''.join(number(len(block), 'I') for block in blocks)
        rows.append((name, plain, position, offset))
    directory = number(1) + string('/', wide) + number(len(rows))
    for name, _, position, _ in rows:
        selected_name = '../escape' if failure == 'unsafe-name' and position == 0 else name
        if failure == 'duplicate-name' and name == 'empty.lua':
            selected_name = 'PLAIN.lua'
        selected_position = -1 if failure == 'negative-position' and position == 0 else position
        directory += string(selected_name, wide) + number(selected_position)
    directory = align(directory) if index_encrypted else directory
    index_offset = len(payload)
    declared = len(rows) + int(failure == 'declared-count')
    prefix = string('../../../X6Game/Content/Script/', wide) + number(declared) + number(27, 'Q')
    prefix += number(1) + bytes(36) + number(1)
    suffix = number(len(encoded)) + encoded + number(int(failure == 'nonencoded'))
    main_size = len(prefix) + 36 + len(suffix)
    main_size = (main_size + 15) // 16 * 16 if index_encrypted else main_size
    directory_offset = index_offset + main_size
    main = prefix + struct.pack('<qq', directory_offset, len(directory)) + hashlib.sha1(directory).digest() + suffix
    main = align(main) if index_encrypted else main
    assert len(main) == main_size
    payload += encrypt(main) if index_encrypted else main
    payload += encrypt(directory) if index_encrypted else directory
    footer = (bytes(16) + bytes([int(index_encrypted)]) + struct.pack('<IIQQ', 0x5a6f12e1, 12, index_offset, len(main)) +
              hashlib.sha1(main).digest() + b'Oodle'.ljust(32, b'\0') + bytes(128))
    assert len(footer) == 221
    payload += footer
    if failure == 'index-hash':
        payload[index_offset] ^= 1
    elif failure == 'member-hash':
        payload[48] ^= 1
    elif failure == 'member-header':
        payload[8] ^= 1
    elif failure == 'member-payload':
        payload[73] ^= 1
    elif failure == 'block-range':
        payload[rows[-1][3] + 72] ^= 1
    elif failure == 'member-flag':
        payload[68] = 3
    elif failure == 'nonzero-guid':
        payload[-221] = 1
    elif failure == 'unsupported-version':
        payload[-200] = 13
    elif failure == 'bad-method-name':
        payload[-159] = 1
    return bytes(payload), rows


def archive(raw, material=MATERIAL, transform=lambda value: value):
    calls = []

    def read(at, size):
        assert 0 <= at <= len(raw) - size and size > 0
        calls.append((at, size))
        return transform(raw[at:at + size])

    return Archive(read, len(raw), material), calls


def codec(blocks):
    assert all(method == 'Oodle' for method, _, _ in blocks)
    # Authored fixture codec, not an assertion that Oodle is zlib.
    result = [zlib.decompress(raw) for _, raw, _ in blocks]
    assert all(len(raw) == wanted for raw, (_, _, wanted) in zip(result, blocks))
    return b''.join(result)


class OriginalPakTests(unittest.TestCase):
    def test_injected_platform_crypto_owns_all_index_and_member_decryption(self):
        raw, rows = fixture()
        calls = []
        class Crypto:
            def block_cipher(self, algorithm, mode, key, data):
                calls.append((algorithm, mode, len(data)))
                return AES.new(key, AES.MODE_ECB).decrypt(data)
        with patch('backend.publisher_crypto.DesktopPublisherCrypto', side_effect=AssertionError('Desktop fallback used')):
            pak = Archive(lambda at, size: raw[at:at + size], len(raw), MATERIAL, crypto=Crypto())
            self.assertEqual(pak.read('X6Game/Content/Script/packed.lua', decompress=codec), rows[-1][1])
        self.assertGreaterEqual(len(calls), 3)
        self.assertTrue(all(algorithm == 'AES' and mode == 'ECB' and size % 16 == 0 for algorithm, mode, size in calls))
        class BadCrypto:
            def block_cipher(self, *args): return bytearray(len(args[-1]))
        with self.assertRaises(ValueError):
            Archive(lambda at, size: raw[at:at + size], len(raw), MATERIAL, crypto=BadCrypto())

    def test_data_reader_import_has_no_desktop_crypto_dependency(self):
        script = '''import sys
class RejectCrypto:
 def find_spec(self,name,path=None,target=None):
  if name == 'Crypto' or name.startswith('Crypto.'):
   raise AssertionError('Desktop-only crypto imported eagerly')
sys.meta_path.insert(0,RejectCrypto())
from backend.infinity_nikki_pak import Archive
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_two_hash_headers_encoded_directory_and_batched_reads(self):
        for encrypted, index_encrypted, wide, long_fields in [(True, True, False, False),
                (False, False, True, True), (True, False, True, False), (False, True, False, True)]:
            with self.subTest(encrypted=encrypted, index_encrypted=index_encrypted, wide=wide):
                raw, rows = fixture(encrypted=encrypted, index_encrypted=index_encrypted, wide=wide, long_fields=long_fields)
                pak, calls = archive(raw)
                names = ['X6Game/Content/Script/' + row[0] for row in rows]
                self.assertEqual(list(pak.locations), names)
                self.assertEqual(pak.read_many(names, decompress=codec), tuple(row[1] for row in rows))
                self.assertEqual(pak.entry(names[0]).header_bytes, 73)
                self.assertEqual(pak.entry(names[-1]).header_bytes, 125)
                self.assertEqual(pak.read(names[0].upper(), decompress=codec), rows[0][1])
                self.assertTrue(all(at + size <= len(raw) for at, size in calls))

    def test_updated_archive_is_independent_of_old_offsets_and_contents(self):
        original, old_rows = fixture(revision=0)
        updated, rows = fixture(revision=1, long_fields=True, wide=True)
        old, _ = archive(original)
        new, _ = archive(updated)
        path = 'X6Game/Content/Script/packed.lua'
        self.assertNotEqual(old.locations[path], new.locations[path])
        self.assertEqual(new.read(path, decompress=codec), rows[-1][1])
        self.assertNotEqual(old_rows[-1][1], rows[-1][1])

    def test_native_size_width_and_encryption_flags_are_independent(self):
        # In the original Framework both bits were set. These distinct cases
        # exercise Nikki's native decoder branches instead of that ambiguity.
        for encrypted in (False, True):
            for long_fields in (False, True):
                with self.subTest(encrypted=encrypted, wide=long_fields):
                    raw, rows = fixture(encrypted=encrypted, long_fields=long_fields)
                    pak, _ = archive(raw)
                    name = 'X6Game/Content/Script/packed.lua'
                    position = pak.locations[name]
                    bits = struct.unpack_from('<I', pak.encoded, position)[0]
                    self.assertEqual(bool(bits & (1 << 22)), not long_fields)
                    self.assertEqual(bool(bits & (1 << 29)), encrypted)
                    self.assertEqual(pak.entry(name).encrypted, encrypted)
                    self.assertEqual(pak.read(name, decompress=codec), rows[-1][1])

    def test_uncompressed_and_empty_members_do_not_invoke_a_codec(self):
        raw, rows = fixture(compressed=False)
        pak, _ = archive(raw)
        def forbidden(_):
            self.fail('No compressed member was selected.')
        self.assertEqual(pak.read_many(list(pak.locations), decompress=forbidden), tuple(row[1] for row in rows))

    def test_rejects_changed_indexes_unsafe_paths_unknown_variants_and_sources(self):
        for failure in ['index-hash', 'unsafe-name', 'negative-position', 'declared-count', 'duplicate-name',
                        'nonencoded', 'nonzero-guid', 'unsupported-version', 'bad-method-name']:
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                archive(fixture(failure=failure)[0])
        raw, _ = fixture()
        for transform in (lambda value: value[:-1], lambda value: bytearray(value)):
            with self.subTest(short=transform), self.assertRaises(ValueError):
                archive(raw, transform=transform)
        with self.assertRaises(ValueError):
            archive(raw, replace(MATERIAL, parameter=bytes(reversed(range(32)))))

    def test_rejects_member_corruption_and_header_disagreement_before_returning_data(self):
        for failure in ['member-hash', 'member-header', 'member-payload', 'member-flag', 'block-range']:
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                pak, _ = archive(fixture(failure=failure)[0])
                pak.read('X6Game/Content/Script/' + ('packed.lua' if failure == 'block-range' else 'plain.lua'), decompress=codec)

    def test_rejects_wrong_codec_output_missing_paths_and_unbounded_batch(self):
        raw, _ = fixture()
        pak, _ = archive(raw)
        path = 'X6Game/Content/Script/packed.lua'
        for bad in [lambda _: b'', lambda blocks: bytes(sum(size for _, _, size in blocks)), lambda _: 'text']:
            with self.subTest(codec=bad), self.assertRaises(ValueError):
                pak.read(path, decompress=bad)
        for paths in [[], [path] * 257, ['X6Game/Content/Script/missing.lua']]:
            with self.subTest(paths=len(paths)), self.assertRaises(ValueError):
                pak.read_many(paths, decompress=codec)


if __name__ == '__main__':
    unittest.main()
