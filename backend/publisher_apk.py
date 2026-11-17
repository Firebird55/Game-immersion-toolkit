"""Data-only verification of an evidenced publisher APK v2 signing profile.

This is a narrow source-integrity reader, not Android package installation or a
publisher-certificate trust store. The caller must bind metadata and the complete
stream to the same official URL/generation. A valid self-signed APK signer alone
does not establish publisher identity, Global compatibility or game coverage.
"""
from dataclasses import dataclass
import hashlib
import hmac
import struct

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Util.asn1 import DerSequence


CHUNK = 1024**2
MAX_METADATA = 1024**2
V2 = 0x7109871a
V3 = 0xf05368c0
V31 = 0x1b93ad61
RSA_SHA256 = 0x0103


def _require(condition):
    if not condition:
        raise ValueError('Official publisher APK integrity or signing format changed.')


class _Reader:
    def __init__(self, raw):
        _require(isinstance(raw, bytes) and len(raw) <= MAX_METADATA)
        self.raw, self.at = raw, 0

    def take(self, size):
        _require(0 <= size <= len(self.raw) - self.at)
        value = self.raw[self.at:self.at + size]
        self.at += size
        return value

    def lp(self):
        return self.take(struct.unpack('<I', self.take(4))[0])

    def all_lp(self, limit):
        values = []
        while self.at < len(self.raw):
            _require(len(values) < limit)
            values.append(self.lp())
        return values

    def done(self):
        _require(self.at == len(self.raw))


@dataclass(frozen=True)
class Signer:
    content_digest: bytes
    certificate_sha256: str
    signed_zero_tail: bool = False


def signing_metadata(block: bytes, *, allow_signed_zero_tail=False) -> tuple[Signer, ...]:
    """Verify signed metadata only. This does NOT verify APK content integrity.

    Currently only the evidenced v2 RSA/PKCS1-SHA256 profile is accepted. New
    algorithms, v3 or attributes fail closed instead of silently downgrading.
    A source may explicitly permit exactly four signed zero tail bytes: AOSP's
    v2 verifier checks all raw signedData bytes but does not check its remaining
    bytes after the three canonical fields. No other extension is accepted.
    """
    _require(type(allow_signed_zero_tail) is bool and
             isinstance(block, bytes) and 32 <= len(block) <= MAX_METADATA)
    _require(block[-16:] == b'APK Sig Block 42' and
             struct.unpack_from('<Q', block)[0] == len(block) - 8 and
             struct.unpack_from('<Q', block, len(block) - 24)[0] == len(block) - 8)
    pairs, at = {}, 8
    while at < len(block) - 24:
        _require(at + 8 <= len(block) - 24)
        size = struct.unpack_from('<Q', block, at)[0]
        at += 8
        _require(4 <= size <= len(block) - 24 - at)
        identity = struct.unpack_from('<I', block, at)[0]
        _require(identity not in pairs)
        pairs[identity] = block[at + 4:at + size]
        at += size
    _require(at == len(block) - 24 and V2 in pairs and V3 not in pairs and V31 not in pairs)
    outer = _Reader(pairs[V2])
    signers_raw = _Reader(outer.lp()).all_lp(8)
    outer.done()
    _require(bool(signers_raw))
    result = []
    for raw in signers_raw:
        reader = _Reader(raw)
        signed, signatures_raw, public = reader.lp(), reader.lp(), reader.lp()
        reader.done()
        data = _Reader(signed)
        digests_raw, certificates_raw, attributes = data.lp(), data.lp(), data.lp()
        zero_tail = False
        if data.at < len(signed):
            _require(allow_signed_zero_tail and data.take(len(signed) - data.at) == b'\0' * 4)
            zero_tail = True
        data.done()
        _require(not attributes)
        certificates = _Reader(certificates_raw).all_lp(16)
        _require(bool(certificates))
        digests, signatures = [], []
        for records, target in ((digests_raw, digests), (signatures_raw, signatures)):
            for record in _Reader(records).all_lp(16):
                item = _Reader(record)
                algorithm = struct.unpack('<I', item.take(4))[0]
                target.append((algorithm, item.lp()))
                item.done()
        _require([item[0] for item in digests] == [item[0] for item in signatures] == [RSA_SHA256])
        _require(len(digests[0][1]) == 32)
        try:
            cert = DerSequence().decode(certificates[0], strict=True)
            tbs = DerSequence().decode(cert[0], strict=True)
            has_version = isinstance(tbs[0], bytes) and tbs[0][:1] == b'\xa0'
            spki = tbs[6 if has_version else 5]
            _require(spki == public)
            key = RSA.import_key(public)
            _require(key.size_in_bits() >= 2048 and not key.has_private())
            pkcs1_15.new(key).verify(SHA256.new(signed), signatures[0][1])
        except (ValueError, TypeError, IndexError) as error:
            raise ValueError('Official publisher APK signer metadata failed verification.') from error
        result.append(Signer(digests[0][1], hashlib.sha256(certificates[0]).hexdigest(), zero_tail))
    return tuple(result)


@dataclass(frozen=True)
class ApkLayout:
    total: int
    signing_offset: int
    signing_block: bytes
    central_directory: bytes
    eocd: bytes
    allow_signed_zero_tail: bool = False

    def validate(self):
        _require(type(self.total) is int and 0 < self.total <= 4 * 1024**3)
        _require(type(self.signing_offset) is int and 0 <= self.signing_offset < self.total)
        _require(0 < len(self.central_directory) <= MAX_METADATA and
                 22 <= len(self.eocd) <= 65557 and self.eocd[:4] == b'PK\x05\x06')
        fields = struct.unpack_from('<4H2IH', self.eocd, 4)
        disk, cd_disk, entries_disk, entries, cd_size, cd_offset, comment = fields
        _require(disk == cd_disk == 0 and entries_disk == entries and
                 0 < entries < 65535 and cd_size == len(self.central_directory) and
                 cd_offset == self.signing_offset + len(self.signing_block) and
                 cd_offset + cd_size + len(self.eocd) == self.total and
                 comment == len(self.eocd) - 22)
        return signing_metadata(self.signing_block, allow_signed_zero_tail=self.allow_signed_zero_tail)


class _ChunkDigest:
    def __init__(self):
        self.pending = bytearray()
        self.digests = []

    def feed(self, value):
        self.pending.extend(value)
        while len(self.pending) >= CHUNK:
            self._chunk(bytes(self.pending[:CHUNK]))
            del self.pending[:CHUNK]

    def _chunk(self, value):
        self.digests.append(hashlib.sha256(b'\xa5' + struct.pack('<I', len(value)) + value).digest())

    def section_end(self):
        if self.pending:
            self._chunk(bytes(self.pending))
            self.pending.clear()

    def finish(self):
        _require(not self.pending)
        return hashlib.sha256(b'\x5a' + struct.pack('<I', len(self.digests)) + b''.join(self.digests)).digest()


def verify_stream(stream, layout: ApkLayout, *, member=None, member_sink=None, progress=None):
    """Hash the complete APK, retaining only an optional exact compressed member.

    ``member=(offset,size)`` must be separately validated against ZIP central and
    local headers. This does not inflate, execute or install anything. A failed
    verification makes any captured member unusable; callers own cleanup.
    ``progress`` observes fully processed bytes and can persist a private receipt.
    """
    signers = layout.validate()
    if member is not None:
        start, size = member
        _require(type(start) is int and type(size) is int and 0 <= start <= layout.signing_offset and
                 0 < size <= layout.signing_offset - start and member_sink is not None)
    else:
        _require(member_sink is None)
    digest, whole, offset, retained = _ChunkDigest(), hashlib.sha256(), 0, 0

    def read(size):
        nonlocal offset, retained
        value = stream.read(size)
        _require(isinstance(value, bytes) and 0 < len(value) <= size)
        whole.update(value)
        if member is not None:
            left, right = max(offset, member[0]), min(offset + len(value), sum(member))
            if left < right:
                piece = value[left - offset:right - offset]
                _require(member_sink.write(piece) == len(piece))
                retained += len(piece)
        offset += len(value)
        if progress:
            progress(offset)
        return value

    def consume(size, expected=None, hash_content=False):
        at = 0
        while at < size:
            value = read(min(CHUNK, size - at))
            if expected is not None:
                _require(value == expected[at:at + len(value)])
            if hash_content:
                digest.feed(value)
            at += len(value)

    consume(layout.signing_offset, hash_content=True)
    digest.section_end()
    consume(len(layout.signing_block), expected=layout.signing_block)
    consume(len(layout.central_directory), expected=layout.central_directory, hash_content=True)
    digest.section_end()
    consume(len(layout.eocd), expected=layout.eocd)
    patched = bytearray(layout.eocd)
    struct.pack_into('<I', patched, 16, layout.signing_offset)
    digest.feed(patched)
    digest.section_end()
    _require(offset == layout.total and stream.read(1) == b'')
    actual = digest.finish()
    _require(all(hmac.compare_digest(actual, signer.content_digest) for signer in signers))
    _require(member is None or retained == member[1])
    return {'bytes_verified': offset, 'apk_sha256': whole.hexdigest(),
            'v2_content_digest': actual.hex(), 'v2_chunk_count': len(digest.digests),
            'certificate_sha256': [signer.certificate_sha256 for signer in signers],
            'signed_zero_tail_signers': sum(signer.signed_zero_tail for signer in signers),
            'selected_compressed_bytes': retained, 'whole_apk_v2_integrity_verified': True,
            'publisher_certificate_independently_pinned': False}
