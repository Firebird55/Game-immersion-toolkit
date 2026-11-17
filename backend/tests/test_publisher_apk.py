import hashlib
import base64
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import zipfile

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Util.asn1 import DerSequence

from backend.publisher_apk import ApkLayout, CHUNK, V2, signing_metadata, verify_stream, _certificate_public_key


def lp(value):
    return struct.pack('<I', len(value)) + value


def reference_digest(sections):
    # Independent section/chunk construction, including a non-aligned boundary.
    chunks = [part[at:at + CHUNK] for part in sections for at in range(0, len(part), CHUNK)]
    sums = [hashlib.sha256(b'\xa5' + struct.pack('<I', len(chunk)) + chunk).digest() for chunk in chunks]
    return hashlib.sha256(b'\x5a' + struct.pack('<I', len(sums)) + b''.join(sums)).digest()


class ShortReads(io.BytesIO):
    def read(self, size=-1):
        return super().read(min(size, 50003))


class ApkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = RSA.generate(2048)
        cls.public = cls.key.public_key().export_key(format='DER')
        # An authored test certificate envelope. Only its SPKI is relevant to
        # APK v2; Android does not use a public-CA chain for APK signers.
        tbs = DerSequence([1, b'\x30\x00', b'\x30\x00', b'\x30\x00', b'\x30\x00', cls.public]).encode()
        cls.certificate = DerSequence([tbs, b'\x30\x00', b'\x03\x01\x00']).encode()

    def fixture(self, *, digest_algorithm=0x0103, signature_algorithm=0x0103, attributes=b'', public=None,
                signed_tail=b'', uncovered_tail=b''):
        data = io.BytesIO()
        payload = bytes(range(251)) * 4300
        with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('lib/arm64-v8a/libExample.so', payload)
            archive.writestr('assets/ignored.dat', b'discard this authored fixture')
        raw = data.getvalue()
        old_eocd = raw[-22:]
        cd_size, cd_offset = struct.unpack_from('<II', old_eocd, 12)
        body, cd = raw[:cd_offset], raw[cd_offset:cd_offset + cd_size]
        content_digest = reference_digest([body, cd, old_eocd])
        signed = (lp(lp(struct.pack('<I', digest_algorithm) + lp(content_digest))) +
                  lp(lp(self.certificate)) + lp(attributes) + signed_tail)
        signature = pkcs1_15.new(self.key).sign(SHA256.new(signed))
        signed += uncovered_tail
        signer = lp(signed) + lp(lp(struct.pack('<I', signature_algorithm) + lp(signature))) + lp(public or self.public)
        v2 = lp(lp(signer))
        pair = struct.pack('<Q', len(v2) + 4) + struct.pack('<I', V2) + v2
        size = len(pair) + 24
        block = struct.pack('<Q', size) + pair + struct.pack('<Q', size) + b'APK Sig Block 42'
        eocd = bytearray(old_eocd)
        struct.pack_into('<I', eocd, 16, cd_offset + len(block))
        layout = ApkLayout(len(raw) + len(block), cd_offset, block, cd, bytes(eocd))
        member_start = 30 + len('lib/arm64-v8a/libExample.so')
        return body + block + cd + eocd, layout, (member_start, len(payload)), payload

    def test_complete_digest_and_exact_selected_member_with_short_reads(self):
        raw, layout, member, payload = self.fixture()
        output, progress = io.BytesIO(), []
        result = verify_stream(ShortReads(raw), layout, member=member, member_sink=output, progress=progress.append)
        self.assertEqual(output.getvalue(), payload)
        self.assertEqual(result['apk_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['v2_chunk_count'], 4)
        self.assertEqual(progress[-1], len(raw))
        self.assertTrue(result['whole_apk_v2_integrity_verified'])
        self.assertFalse(result['publisher_certificate_independently_pinned'])

    def test_metadata_signature_alone_does_not_accept_modified_content(self):
        raw, layout, _, _ = self.fixture()
        self.assertEqual(len(signing_metadata(layout.signing_block)), 1)
        broken = bytearray(raw)
        broken[100] ^= 1
        with self.assertRaises(ValueError):
            verify_stream(io.BytesIO(broken), layout)

    def test_each_cached_metadata_section_must_match_stream_generation(self):
        raw, layout, _, _ = self.fixture()
        for at in (layout.signing_offset + 30,
                   layout.signing_offset + len(layout.signing_block) + 10,
                   len(raw) - 5):
            with self.subTest(at=at):
                broken = bytearray(raw)
                broken[at] ^= 1
                with self.assertRaises(ValueError):
                    verify_stream(io.BytesIO(broken), layout)

    def test_truncation_and_unexpected_trailing_bytes_fail(self):
        raw, layout, _, _ = self.fixture()
        for broken in (raw[:100], raw[:-1], raw + b'x'):
            with self.assertRaises(ValueError):
                verify_stream(io.BytesIO(broken), layout)

    def test_algorithm_mismatch_unknown_profile_attributes_and_leaf_key_fail(self):
        for kwargs in ({'digest_algorithm': 0x0104}, {'signature_algorithm': 0x0104},
                       {'digest_algorithm': 0x0104, 'signature_algorithm': 0x0104},
                       {'attributes': b'unsupported'}, {'public': self.public + b'\0'}):
            with self.subTest(kwargs=kwargs):
                _, layout, _, _ = self.fixture(**kwargs)
                with self.assertRaises(ValueError):
                    layout.validate()

    def test_metadata_signature_and_block_size_fail_closed(self):
        _, layout, _, _ = self.fixture()
        for at in (0, 20, len(layout.signing_block) - 25, len(layout.signing_block) - 24):
            block = bytearray(layout.signing_block)
            block[at] ^= 1
            with self.assertRaises(ValueError):
                signing_metadata(bytes(block))

    def test_newer_scheme_or_duplicate_block_identity_is_not_downgraded(self):
        _, layout, _, _ = self.fixture()
        for identity in (V2, 0xf05368c0, 0x1b93ad61):
            extra = struct.pack('<Q', 5) + struct.pack('<I', identity) + b'x'
            middle = layout.signing_block[8:-24] + extra
            size = len(middle) + 24
            block = struct.pack('<Q', size) + middle + struct.pack('<Q', size) + b'APK Sig Block 42'
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                signing_metadata(block)

    def test_bad_layout_member_and_sink_fail(self):
        raw, layout, _, _ = self.fixture()
        bad = ApkLayout(layout.total + 1, layout.signing_offset, layout.signing_block,
                        layout.central_directory, layout.eocd)
        with self.assertRaises(ValueError):
            verify_stream(io.BytesIO(raw), bad)
        for member in ((-1, 5), (0, layout.signing_offset + 1), (0, 0)):
            with self.assertRaises(ValueError):
                verify_stream(io.BytesIO(raw), layout, member=member, member_sink=io.BytesIO())
        with self.assertRaises(ValueError):
            verify_stream(io.BytesIO(raw), layout, member=(0, 5))

    def test_zero_tail_requires_explicit_source_profile_and_is_fully_signed(self):
        raw, layout, _, _ = self.fixture(signed_tail=b'\0' * 4)
        with self.assertRaises(ValueError):
            verify_stream(io.BytesIO(raw), layout)
        opted = ApkLayout(layout.total, layout.signing_offset, layout.signing_block,
                          layout.central_directory, layout.eocd, allow_signed_zero_tail=True)
        result = verify_stream(io.BytesIO(raw), opted)
        self.assertEqual(result['signed_zero_tail_signers'], 1)
        for tail in (b'\0', b'\0' * 3, b'\0' * 5, b'\0' * 8, b'\0\0\1\0'):
            with self.subTest(tail=tail):
                _, layout, _, _ = self.fixture(signed_tail=tail)
                with self.assertRaises(ValueError):
                    signing_metadata(layout.signing_block, allow_signed_zero_tail=True)
        _, layout, _, _ = self.fixture(uncovered_tail=b'\0' * 4)
        with self.assertRaises(ValueError):
            signing_metadata(layout.signing_block, allow_signed_zero_tail=True)

    def test_signed_stripping_protection_attribute_without_v3_is_rejected(self):
        # 0xbeeff00d is AOSP's v2 stripping-protection attribute. A declaration
        # of v3 cannot be accepted without verifying v3; this subset rejects all
        # attributes rather than incorrectly falling back to v2.
        attribute = lp(struct.pack('<II', 0xbeeff00d, 3))
        _, layout, _, _ = self.fixture(attributes=attribute)
        with self.assertRaises(ValueError):
            signing_metadata(layout.signing_block)

    def test_injected_verifier_is_used_before_reading_any_original_bytes(self):
        raw, layout, _, _ = self.fixture()
        calls = []
        class Reject:
            def rsa_verify_sha256(inner, public, signed, signature):
                calls.append((public, signed, signature))
                return False
        stream = io.BytesIO(raw)
        with self.assertRaises(ValueError):
            verify_stream(stream, layout, crypto=Reject())
        self.assertEqual(stream.tell(), 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], self.public)
        # A truthy foreign result does not certify signature acceptance.
        class WrongResult:
            def rsa_verify_sha256(inner, *args): return 1
        with self.assertRaises(ValueError):
            layout.validate(crypto=WrongResult())

    def test_pure_der_binding_supports_original_v1_and_v3_certificates(self):
        self.assertEqual(_certificate_public_key(self.certificate, self.public), 256)
        tbs = DerSequence([b'\xa0\x03\x02\x01\x02', 1, b'\x30\x00', b'\x30\x00',
            b'\x30\x00', b'\x30\x00', self.public]).encode()
        v3 = DerSequence([tbs, b'\x30\x00', b'\x03\x01\x00']).encode()
        self.assertEqual(_certificate_public_key(v3, self.public), 256)
        for bad in (self.certificate + b'\0', b'\x30\x80' + self.certificate[4:],
                    b'\x30\x84\0\0\0\1\0', self.certificate[:-1]):
            with self.subTest(bad=bad[:10]), self.assertRaises(ValueError):
                _certificate_public_key(bad, self.public)
        weak = RSA.generate(1024).public_key().export_key(format='DER')
        tbs = DerSequence([1, b'\x30\x00', b'\x30\x00', b'\x30\x00', b'\x30\x00', weak]).encode()
        certificate = DerSequence([tbs, b'\x30\x00', b'\x03\x01\x00']).encode()
        with self.assertRaises(ValueError):
            _certificate_public_key(certificate, weak)

    def test_closed_source_verifier_import_and_stream_with_no_crypto_namespace(self):
        from backend.publisher_crypto import DesktopPublisherCrypto
        raw, layout, _, _ = self.fixture()
        expected = []
        class Spy:
            def rsa_verify_sha256(inner, *args):
                expected.extend(base64.b64encode(value).decode() for value in args)
                return DesktopPublisherCrypto().rsa_verify_sha256(*args)
        layout.validate(crypto=Spy())
        payload = {'raw': base64.b64encode(raw).decode(), 'expected': expected,
            'total': layout.total, 'offset': layout.signing_offset,
            **{name: base64.b64encode(value).decode() for name, value in
                [('block', layout.signing_block), ('cd', layout.central_directory), ('eocd', layout.eocd)]}}
        script = '''
import base64,importlib.abc,io,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,*args):
  if fullname.split('.')[0] in {'Crypto','java','jnius'}:raise AssertionError('unapproved crypto import')
sys.meta_path.insert(0,Deny())
from backend.publisher_apk import ApkLayout,signing_metadata,verify_stream
p=json.load(sys.stdin);dec=lambda k:base64.b64decode(p[k]);calls=[]
class AuthoredVerifier:
 def rsa_verify_sha256(self,*args):
  assert [base64.b64encode(v).decode() for v in args]==p['expected']
  calls.append(True);return True
c=AuthoredVerifier();layout=ApkLayout(p['total'],p['offset'],dec('block'),dec('cd'),dec('eocd'))
assert len(signing_metadata(dec('block'),crypto=c))==1
assert len(layout.validate(crypto=c))==1
assert verify_stream(io.BytesIO(dec('raw')),layout,crypto=c)['whole_apk_v2_integrity_verified']
assert len(calls)==3 and not any(k=='Crypto' or k.startswith('Crypto.') for k in sys.modules)
print('closed-source authored verifier propagation passed')
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(Path(__file__).resolve().parents[2])],
            input=json.dumps(payload), text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('propagation passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
