"""Synthetic archives exercise actual range integrity, offsets and patch deletions."""
import hashlib
import struct
import zlib

from Crypto.Cipher import AES
import pytest

from backend import nte_archive_metadata as metadata, nte_publisher_pak as pak, nte_release as release
from backend.preparation_errors import PreparationFailure

KEY = bytes(range(32))
CATALOG = metadata.Catalog('a' * 40, 'b' * 64, {'nte-global': '0x' + KEY.hex(), 'nte-cn': '0x' + bytes(32).hex()})


def string(value, wide=False):
    data = value.encode('utf-16le' if wide else 'utf-8')
    width = 2 if wide else 1
    return struct.pack('<i', -(len(value) + 1) if wide else len(data) + 1) + data + bytes(width)


def package(rows, *, encrypted_index=True, mount='../../../HT/', folder='Content/', declared_padding=False,
            extra_index_bytes=b'', wide_numbers=False):
    """rows: (name, payload, compression block size, encrypted, nonencoded)."""
    cipher = AES.new(KEY, AES.MODE_ECB)
    body, encoded, nonencoded, positions = bytearray(64), bytearray(), [], []
    for name, payload, block_size, encrypted, explicit in rows:
        if payload is None:
            positions.append((name, pak.DELETED))
            continue
        if payload == 'deleted':
            positions.append((name, -len(nonencoded) - 1))
            nonencoded.append(struct.pack('<qqqI', 0, 0, 0, 0) + bytes(20) + struct.pack('<BI', 2, 0))
            continue
        method = int(bool(block_size))
        blocks = [zlib.compress(payload[i:i + block_size]) for i in range(0, len(payload), block_size)] if method else []
        lengths = [len(block) for block in blocks]
        stored = sum(lengths) if method else len(payload)
        offset = len(body)
        header_size = 53 + (4 + 16 * len(blocks) if method else 0)
        # Deliberately unusable duplicate header. The index is authoritative.
        body.extend(b'?' * header_size)
        physical = blocks if method else [payload]
        for block in physical:
            body.extend(cipher.encrypt(block.ljust((len(block) + 15) // 16 * 16, b'\0')) if encrypted else block)
        if explicit:
            positions.append((name, -len(nonencoded) - 1))
            start = header_size
            ranges = b''
            for length in lengths:
                ranges += struct.pack('<qq', start, start + length)
                start += (length + 15) // 16 * 16 if encrypted else length
            nonencoded.append(struct.pack('<qqqI', offset, stored, len(payload), method) + bytes(20) +
                              (struct.pack('<I', len(blocks)) + ranges if method else b'') +
                              struct.pack('<BI', int(encrypted), block_size))
        else:
            positions.append((name, len(encoded)))
            bits = (0 if wide_numbers else 7 << 29) | method << 23 | int(encrypted) << 22 | len(blocks) << 6 | (63 if method else 0)
            encoded.extend(struct.pack('<I', bits))
            if method:
                encoded.extend(struct.pack('<I', block_size))
            encoded.extend(struct.pack('<qq' if wide_numbers else '<II', offset, len(payload)))
            if method:
                encoded.extend(struct.pack('<q' if wide_numbers else '<I', stored))
            if len(blocks) != 1 or encrypted:
                encoded.extend(b''.join(struct.pack('<I', n) for n in lengths))
    def store(data):
        if encrypted_index:
            return cipher.encrypt(data.ljust((len(data) + 15) // 16 * 16, b'\0'))
        return data
    body.extend(bytes((-len(body)) % 16))
    directory_offset = len(body)
    directory = (struct.pack('<i', 1) + string(folder) + struct.pack('<i', len(positions)) +
                 b''.join(string(name, wide='é' in name) + struct.pack('<i', position) for name, position in positions))
    if declared_padding:
        directory += directory[:(-len(directory)) % 16]
    body.extend(store(directory))
    index_offset = len(body)
    index = (string(mount) + struct.pack('<iQi', len(rows), 123, 1) + bytes(36) +
             struct.pack('<iqq', 1, directory_offset, len(directory)) + hashlib.sha1(directory).digest() +
             struct.pack('<i', len(encoded)) + encoded + struct.pack('<i', len(nonencoded)) + b''.join(nonencoded))
    index += extra_index_bytes
    if declared_padding:
        index += index[:(-len(index)) % 16]
    body.extend(store(index))
    body.extend(bytes(16) + bytes([int(encrypted_index)]) + pak.MAGIC + struct.pack('<IQQ', 12, index_offset + 1, len(index)) +
                hashlib.sha1(index).digest() + b'Zlib'.ljust(32, b'\0') + b'Oodle'.ljust(32, b'\0') + bytes(96))
    return bytes(body)


def descriptor(data):
    digest = hashlib.md5(data).hexdigest()
    return release.File(len(data), digest, len(data), digest, 0)


def signature(data):
    crcs = [zlib.crc32(data[i:i + pak.CHUNK]) for i in range(0, len(data), pak.CHUNK)]
    return struct.pack('<III', 0x73832daa, 1, 512) + bytes(512) + struct.pack('<I', len(crcs)) + struct.pack('<' + 'I' * len(crcs), *crcs)


def open_archive(data, tmp_path, monkeypatch, *, region='nte-global'):
    sig = signature(data)
    item, sigitem = descriptor(data), descriptor(sig)
    requests = []
    def read(region, branch, record, position, length):
        requests.append((record.digest, position, length))
        raw = {item.digest: data, sigitem.digest: sig}[record.digest]
        assert 0 < length <= pak.TRANSFER and 0 <= position <= len(raw) - length
        return raw[position:position + length]
    monkeypatch.setattr(release, 'read_range', read)
    source = pak.SignedSource(region, 'PC_150', item, sigitem, tmp_path)
    return pak.Archive(source, CATALOG), requests


@pytest.mark.parametrize('encrypted_index', [True, False])
@pytest.mark.parametrize('wide_numbers', [True, False])
def test_all_supported_entry_encodings_and_single_block_length_exception(tmp_path, monkeypatch, encrypted_index, wide_numbers):
    samples = [('single.bin', b'A voice bank' * 80, 4096, False, False),
               ('multiple.bin', bytes(range(256)) * 50, 4096, encrypted_index, False),
               ('caf\u00e9.bin', b'original recording', 0, encrypted_index, False),
               ('explicit.bin', b'localized text' * 800, 4096, encrypted_index, True)]
    archive, requests = open_archive(package(samples, encrypted_index=encrypted_index, wide_numbers=wide_numbers), tmp_path, monkeypatch)
    for name, payload, *_ in samples:
        assert archive.read('ht/content/' + name.upper()) == payload
    before = len(requests)
    assert archive.read('HT/Content/single.bin') == samples[0][1]
    assert len(requests) == before


def test_ranges_are_coalesced_and_cached_corruption_is_refetched(tmp_path, monkeypatch):
    # Deterministic, incompressible content spanning many 64 KiB checksum blocks.
    payload = b''.join(hashlib.sha256(struct.pack('<I', i)).digest() for i in range(10000))
    archive, requests = open_archive(package([('voice.wem', payload, 0, False, False)]), tmp_path, monkeypatch)
    before = len(requests)
    assert archive.read('HT/Content/voice.wem') == payload
    assert len(requests) == before + 1
    cached = archive.source.root / '0.chunk'
    corrupted = bytearray(cached.read_bytes())
    corrupted[100] ^= 1
    cached.write_bytes(corrupted)
    before = len(requests)
    assert archive.read('HT/Content/voice.wem') == payload
    assert len(requests) == before + 1
    assert archive.source._valid(0, cached.read_bytes())


def test_checksum_covered_encryption_padding_is_bounded_not_mistaken_for_new_index_fields(tmp_path, monkeypatch):
    rows = [('voice.wem', b'original', 0, False, False)]
    archive, _ = open_archive(package(rows, declared_padding=True), tmp_path, monkeypatch)
    assert archive.read('HT/Content/voice.wem') == b'original'
    with pytest.raises(PreparationFailure):
        open_archive(package(rows, declared_padding=True, extra_index_bytes=bytes(16)), tmp_path, monkeypatch)


def test_a_corrupt_range_never_activates_any_chunk_in_that_response(tmp_path, monkeypatch):
    payload = b''.join(hashlib.sha256(struct.pack('<I', i)).digest() for i in range(10000))
    archive, _ = open_archive(package([('voice.wem', payload, 0, False, False)]), tmp_path, monkeypatch)
    read = release.read_range
    def corrupt(*args):
        data = bytearray(read(*args))
        data[-10] ^= 1
        return bytes(data)
    monkeypatch.setattr(release, 'read_range', corrupt)
    with pytest.raises(PreparationFailure):
        archive.read('HT/Content/voice.wem')
    assert not (archive.source.root / '0.chunk').exists()


@pytest.mark.parametrize('deleted', [None, 'deleted'])
def test_patch_deletions_block_fallback_while_explicit_historical_source_survives(tmp_path, monkeypatch, deleted):
    old, _ = open_archive(package([('voice.wem', b'historical voice', 0, False, False)]), tmp_path, monkeypatch)
    newer, _ = open_archive(package([('voice.wem', deleted, 0, False, False)]), tmp_path, monkeypatch)
    chosen, path = pak.overlay([newer, old])['ht/content/voice.wem']
    assert chosen is newer and chosen.entry(path) is None
    with pytest.raises(FileNotFoundError):
        chosen.read(path)
    assert old.read(path) == b'historical voice'


def test_replaced_recording_uses_new_source_without_rewriting_the_historical_cache(tmp_path, monkeypatch):
    old, _ = open_archive(package([('voice.wem', b'first performance', 0, False, False)]), tmp_path, monkeypatch)
    assert old.read('HT/Content/voice.wem') == b'first performance'
    newer, _ = open_archive(package([('voice.wem', b'updated performance', 0, False, False)]), tmp_path, monkeypatch)
    selected, path = pak.overlay([newer, old])['ht/content/voice.wem']
    assert selected.read(path) == b'updated performance'
    assert old.read(path) == b'first performance'
    assert old.source.root != newer.source.root


def test_valid_manifest_and_chunk_crcs_do_not_replace_the_directory_index_checksum(tmp_path, monkeypatch):
    data = bytearray(package([('voice.wem', b'original', 0, False, False)], encrypted_index=False))
    directory = data.index(struct.pack('<i', 1) + string('Content/'))
    data[directory + 8] ^= 1
    # The synthetic server supplies a new valid manifest/.sig for these bytes,
    # but the checksum stored in the primary index still describes the old directory.
    with pytest.raises(PreparationFailure):
        open_archive(bytes(data), tmp_path, monkeypatch)


@pytest.mark.parametrize('folder', ['../Content/', 'Content//', '/../../Content/', 'Content\\'])
def test_unsafe_index_paths_are_not_mounted(tmp_path, monkeypatch, folder):
    with pytest.raises(PreparationFailure):
        open_archive(package([('voice.wem', b'voice', 0, False, False)], folder=folder), tmp_path, monkeypatch)


def test_case_collisions_and_wrong_region_fail_instead_of_guessing(tmp_path, monkeypatch):
    with pytest.raises(PreparationFailure):
        open_archive(package([('A.wem', b'a', 0, False, False), ('a.wem', b'b', 0, False, False)]), tmp_path, monkeypatch)
    with pytest.raises(PreparationFailure):
        open_archive(package([('voice.wem', b'voice', 0, False, False)]), tmp_path, monkeypatch, region='nte-cn')


def test_checksum_and_index_limits_are_enforced_before_reading_arbitrary_ranges(tmp_path, monkeypatch):
    archive, requests = open_archive(package([('voice.wem', b'voice', 0, False, False)]), tmp_path, monkeypatch)
    before = len(requests)
    for position, length in [(-1, 20), (0, True), (0, 0), (0, archive.source.item.size + 1)]:
        with pytest.raises(PreparationFailure):
            archive.source.read(position, length)
    assert len(requests) == before
    data = bytearray(package([('voice.wem', b'voice', 0, False, False)]))
    marker = data.rfind(pak.MAGIC)
    struct.pack_into('<Q', data, marker + 16, pak.INDEX_LIMIT + 1)
    with pytest.raises(PreparationFailure):
        open_archive(bytes(data), tmp_path, monkeypatch)
