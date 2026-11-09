import hashlib
import shutil
import struct
import zlib

from Crypto.Cipher import AES
import pytest

from backend import wuthering_release_pak as pak


def compressed_member(method, *, corrupt_hash=False, shifted=False):
    data = b'owned dialogue sample' * 130
    block_size = 2048
    plain = [data[:block_size], data[block_size:]]
    blocks = [zlib.compress(part) if method == b'Zlib' else b'\xcc\x06' + part for part in plain]
    header_size = 57 + 16 * len(blocks)
    body = bytearray()
    ranges = []
    for block in blocks:
        start = header_size + len(body)
        ranges.append((start, start + len(block)))
        body.extend(block + bytes(-len(block) % 16))
    cipher = AES.new(bytes(range(16)), AES.MODE_ECB)
    protected = min(2048, len(body))
    stored = cipher.encrypt(bytes(body[:protected])) + bytes(body[protected:])
    if shifted:
        start, end = ranges[-1]
        ranges[-1] = start + 1, end
    header = struct.pack('<QQQI', 0, len(stored), len(data), 1) + hashlib.sha1(stored).digest()
    header += struct.pack('<I', len(blocks)) + b''.join(struct.pack('<QQ', *pair) for pair in ranges)
    header += struct.pack('<BI', 9, block_size)
    archive = header + stored
    if corrupt_hash:
        archive = archive[:-1] + bytes([archive[-1] ^ 1])
    reader = object.__new__(pak.Package)
    reader.cipher, reader.methods = cipher, [b'None', method]
    reader.range = lambda offset, size: archive[offset:offset + size]
    flags = 0xf0400000 | (block_size // 2048) << 16 | len(blocks)
    reader.entries = struct.pack('<IBIII', flags, 2, len(data), 0, len(stored))
    reader.entries += b''.join(struct.pack('<I', len(block)) for block in blocks)
    return reader, data


def test_zlib_multiblock_reads_both_independently_padded_frames():
    package, expected = compressed_member(b'Zlib')
    assert package.extract(0) == expected
    package.entries = package.entries[:-4] + struct.pack('<I', 1)
    with pytest.raises(ValueError):
        package.extract(0)


def test_oodle_multiblock_checks_the_whole_ciphertext_and_decodes_each_member(monkeypatch):
    package, expected = compressed_member(b'Oodle')

    def owned_literal_frames(blocks):
        assert len(blocks) == 2
        for packed, size in blocks:
            assert packed[:2] == b'\xcc\x06' and len(packed) == size + 2
        return b''.join(packed[2:] for packed, size in blocks)

    monkeypatch.setattr(pak, '_oodle', owned_literal_frames)
    assert package.extract(0) == expected
    for option in ('shifted', 'corrupt_hash'):
        broken, _ = compressed_member(b'Oodle', **{option: True})
        with pytest.raises(ValueError):
            broken.extract(0)


@pytest.mark.skipif(not shutil.which('node') or not (pak.CODE_ROOT / 'node_modules/ooz-wasm/index.js').is_file(),
                    reason='source Oodle playback needs the locked Node dependencies')
def test_source_oodle_decompresses_two_owned_literal_frames():
    package, expected = compressed_member(b'Oodle')
    assert package.extract(0) == expected


def test_uncompressed_whole_entry_hash_omits_cipher_alignment():
    raw = b'short unaligned original'
    cipher = AES.new(bytes(range(16)), AES.MODE_ECB)
    stored = cipher.encrypt(raw + bytes(-len(raw) % 16))
    header = struct.pack('<QQQI', 0, len(raw), len(raw), 0) + hashlib.sha1(stored[:len(raw)]).digest() + bytes(5)
    reader = object.__new__(pak.Package)
    reader.cipher, reader.methods = cipher, [b'None']
    reader.entries = struct.pack('<IBII', 0xb0000000, 0, len(raw), 0)
    reader.range = lambda pos, size: (header + stored)[pos:pos + size]
    assert reader.extract(0) == raw
