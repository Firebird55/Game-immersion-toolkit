"""Authored APKs exercise metadata reads without executing any member.

The earlier verifier tests protect whole-carrier cryptography. These tests add
the missing ZIP owner/header and pre-read resource bounds at its public input.
"""
import io
import struct
import unittest
import zipfile
import zlib

from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15

from backend import publisher_apk as apk
from backend.publisher_apk_zip import ApkMetadata
from backend.tests import test_publisher_apk as authored


class ApkMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        authored.ApkTests.setUpClass()
        cls.signer = authored.ApkTests

    def fixture(self, *, names=None, comment=b'', mutate=None, signed_tail=b''):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, value, method in names or [
                    ('AndroidManifest.xml', b'authored manifest only', 8),
                    ('lib/arm64-v8a/libExample.so', bytes(range(251)) * 300, 8),
                    ('assets/caf\u00e9.dat', b'authored stored member', 0)]:
                archive.writestr(name, value, compress_type=method)
            archive.comment = comment
        raw = bytearray(output.getvalue())
        if mutate:
            mutate(raw)
        # Find the actual EOCD by the authored comment length, including false
        # signatures in comments. Signing covers the original ZIP body and CD.
        end = len(raw) - 22 - len(comment)
        original_eocd = bytes(raw[end:])
        size, offset = struct.unpack_from('<II', original_eocd, 12)
        body, directory = bytes(raw[:offset]), bytes(raw[offset:offset + size])
        digest = authored.reference_digest([body, directory, original_eocd])
        lp = authored.lp
        signed = lp(lp(struct.pack('<I', apk.RSA_SHA256) + lp(digest))) + lp(lp(self.signer.certificate)) + lp(b'') + signed_tail
        signature = pkcs1_15.new(self.signer.key).sign(SHA256.new(signed))
        signer = lp(signed) + lp(lp(struct.pack('<I', apk.RSA_SHA256) + lp(signature))) + lp(self.signer.public)
        v2 = lp(lp(signer))
        pair = struct.pack('<QI', len(v2) + 4, apk.V2) + v2
        block = struct.pack('<Q', len(pair) + 24) + pair + struct.pack('<Q', len(pair) + 24) + b'APK Sig Block 42'
        eocd = bytearray(original_eocd)
        struct.pack_into('<I', eocd, 16, offset + len(block))
        return body + block + directory + eocd

    def reader(self, raw, **options):
        calls = []
        def read(start, size):
            calls.append((start, size))
            return raw[start:start + size]
        return ApkMetadata(read, len(raw), **options), calls

    def test_exact_member_owner_and_whole_verifier_share_layout(self):
        raw = self.fixture(comment=b'authored PK\x05\x06 misleading comment')
        archive, calls = self.reader(raw)
        value = archive.member('AndroidManifest.xml', read=True, maximum=4096)
        self.assertEqual(value, b'authored manifest only')
        member = archive.member('lib/arm64-v8a/libExample.so', maximum=100000)
        packed = io.BytesIO()
        result = apk.verify_stream(authored.ShortReads(raw), archive.layout, member=member, member_sink=packed)
        self.assertTrue(result['whole_apk_v2_integrity_verified'])
        self.assertEqual(zlib.decompress(packed.getvalue(), -15), bytes(range(251)) * 300)
        self.assertEqual(archive.member('assets/caf\u00e9.dat', read=True), b'authored stored member')
        self.assertEqual(archive.metadata_bytes, sum(size for _, size in calls))
        for start, witness in archive.witnesses:
            self.assertEqual(raw[start:start + len(witness)], witness)

    def test_original_cp437_local_name_uses_its_actual_encoded_length(self):
        def original_name(raw):
            raw[:] = raw.replace(b'cafe', b'caf\x82')
        archive, _ = self.reader(self.fixture(names=[('cafe', b'legacy name', 0)], mutate=original_name))
        self.assertEqual(archive.member('caf\u00e9', read=True), b'legacy name')

    def test_large_directory_is_assembled_across_tail_without_member_bodies(self):
        raw = self.fixture(names=[(f'assets/long-name-{i:04}.dat', b'x', 0) for i in range(1600)])
        archive, calls = self.reader(raw)
        self.assertEqual(len(archive.entries), 1600)
        self.assertTrue(any(size > 10000 and start < len(raw) - 65557 for start, size in calls))
        self.assertLess(archive.metadata_bytes, len(raw))

    def test_metadata_budget_precedes_callback_and_exact_bytes_required(self):
        raw = self.fixture()
        calls = []
        with self.assertRaises(ValueError):
            ApkMetadata(lambda start, size: calls.append((start, size)), len(raw), maximum_metadata=1)
        self.assertEqual(calls, [])
        for result in (raw[:-1], bytearray(raw), None):
            with self.subTest(kind=type(result).__name__), self.assertRaises(ValueError):
                ApkMetadata(lambda *_: result, len(raw))
        archive, calls = self.reader(raw)
        before = len(calls)
        archive.maximum_metadata = archive.metadata_bytes
        with self.assertRaises(ValueError):
            archive.member('AndroidManifest.xml')
        self.assertEqual(len(calls), before)

    def test_selected_plain_limit_precedes_local_or_deflate_reads(self):
        raw = self.fixture(names=[('bomb', b'x' * 200000, 8)])
        archive, calls = self.reader(raw, maximum_metadata=65536)
        before = len(calls)
        for options in ({'maximum': 100}, {'read': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                archive.member('bomb', **options)
        self.assertEqual(len(calls), before)

    def test_header_name_crc_size_method_flags_must_agree(self):
        raw = self.fixture()
        for offset in (6, 8, 14, 18, 22, 26, 30):
            with self.subTest(offset=offset):
                broken = bytearray(raw)
                broken[offset] ^= 1
                archive, _ = self.reader(bytes(broken))
                with self.assertRaises(ValueError):
                    archive.member('AndroidManifest.xml', read=True)

    def test_directory_duplicates_paths_truncation_and_split_zip_fail(self):
        for name in ('../secret', '/absolute', 'a/../b', 'C:bad'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.reader(self.fixture(names=[(name, b'x', 0)]))
        # Windows' ZipInfo normalizes backslashes; inject the original bytes.
        with self.assertRaises(ValueError):
            self.reader(self.fixture(names=[('a/b', b'x', 0)]).replace(b'a/b', b'a\\b'))
        def cd_field(offset, fmt, value):
            def change(raw):
                directory = struct.unpack_from('<I', raw, len(raw) - 6)[0]
                struct.pack_into(fmt, raw, directory + offset, value)
            return change
        for offset, fmt, value in ((34, '<H', 1), (20, '<I', 0xffffffff),
                                   (24, '<I', 0xffffffff), (42, '<I', 0xffffffff), (28, '<H', 65535)):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.reader(self.fixture(mutate=cd_field(offset, fmt, value)))
        # Equal-length names keep framing intact, but duplicate semantic owners.
        raw = self.fixture(names=[('one', b'x', 0), ('two', b'y', 0)])
        raw = raw.replace(b'two', b'one')
        with self.assertRaises(ValueError):
            self.reader(raw)
        for raw in (b'x' * 22, self.fixture()[:-1]):
            with self.assertRaises(ValueError):
                self.reader(raw)

    def test_selected_encryption_descriptor_or_method_is_not_silently_read(self):
        for flags, method in ((1, 0), (8, 8), (0, 99)):
            raw = bytearray(self.fixture())
            directory = raw.index(b'PK\x01\x02')
            struct.pack_into('<HH', raw, directory + 8, flags, method)
            archive, _ = self.reader(bytes(raw))
            with self.subTest(flags=flags, method=method), self.assertRaises(ValueError):
                archive.member('AndroidManifest.xml', read=True)

    def test_member_crc_and_deflate_eof_fail_even_before_whole_verification(self):
        raw = self.fixture(names=[('stored', b'abc', 0), ('deflated', b'x' * 200, 8)])
        archive, _ = self.reader(raw)
        for name in ('stored', 'deflated'):
            start, _ = archive.member(name)
            broken = bytearray(raw)
            broken[start] ^= 255
            changed, _ = self.reader(bytes(broken))
            with self.subTest(name=name), self.assertRaises(ValueError):
                changed.member(name, read=True)
        def trailing(raw):
            directory = struct.unpack_from('<I', raw, len(raw) - 6)[0]
            packed = struct.unpack_from('<I', raw, 18)[0]
            # Padding claimed as part of Deflate is forbidden by its EOF rule.
            raw[30 + len('deflated') + packed:30 + len('deflated') + packed] = b'x'
            struct.pack_into('<I', raw, 18, packed + 1)
            directory += 1
            struct.pack_into('<I', raw, directory + 20, packed + 1)
            struct.pack_into('<I', raw, len(raw) - 6, directory)
        changed, _ = self.reader(self.fixture(names=[('deflated', b'x' * 200, 8)], mutate=trailing))
        with self.assertRaises(ValueError):
            changed.member('deflated', read=True)

    def test_signature_dialect_remains_strict_default_and_whole_required(self):
        raw = self.fixture(signed_tail=b'\0' * 4)
        with self.assertRaises(ValueError):
            self.reader(raw)
        archive, _ = self.reader(raw, allow_signed_zero_tail=True)
        result = apk.verify_stream(io.BytesIO(raw), archive.layout)
        self.assertEqual(result['signed_zero_tail_signers'], 1)
        broken = bytearray(raw)
        broken[35] ^= 1
        with self.assertRaises(ValueError):
            apk.verify_stream(io.BytesIO(broken), archive.layout)


if __name__ == '__main__':
    unittest.main()
