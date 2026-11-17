"""IoStore ranges must not bypass the manifest TOC or stored-block checksums.

Small authored containers exercise integrity, encryption, graph corruption and
historical cache isolation without game assets or a native package parser.
"""
import hashlib
import struct
from types import SimpleNamespace

from Crypto.Cipher import AES
import pytest

from backend import nte_publisher_iostore as io
from backend.nte_release import File
from backend.nte_publisher_pak import Archive
from backend.preparation_errors import PreparationFailure

KEY = bytes(range(32))
INVALID = 0xffffffff


def string(value):
    data = value.encode('utf8') + b'\0'
    return struct.pack('<i', len(data)) + data


def file(data):
    digest = hashlib.md5(data).hexdigest()
    return File(len(data), digest, len(data), digest, 0)


def fixture(*, encrypted=True, version=8, cycle=False, collision=False, compression=False,
            second=b'B' * 15, gap=False):
    plain = b'A' * 80 + second
    chunks = [plain[:64], plain[64:], b'C' * 64]
    cipher = AES.new(KEY, AES.MODE_ECB)
    methods = [b'Oodle'.ljust(32, b'\0')] if compression else []
    stored = []
    records = []
    offset = 0
    for index, data in enumerate(chunks):
        if gap and index == 1:
            offset += 16
        if compression:
            import zlib
            packed = zlib.compress(data)  # A stand-in at the separately tested decoder boundary.
        else:
            packed = data
        padded = packed.ljust((len(packed) + 15) // 16 * 16, b'\0') if encrypted else packed
        value = cipher.encrypt(padded) if encrypted else padded
        records.append(offset.to_bytes(5, 'little') + len(packed).to_bytes(3, 'little') +
                       len(data).to_bytes(3, 'little') + bytes([int(compression)]))
        stored.append(value)
        offset += len(value)
    ucas = stored[0] + (bytes(16) if gap else b'') + b''.join(stored[1:])
    names = ['HT', 'a.uasset', 'A.uasset' if collision else 'b.uasset']
    directory = (string('../../../') + struct.pack('<I', 2) +
        struct.pack('<4I', INVALID, 1, INVALID, INVALID) +
        struct.pack('<4I', 0, 0 if cycle else INVALID, INVALID, 0) +
        struct.pack('<I', 2) + struct.pack('<3I', 1, 1, 0) +
        struct.pack('<3I', 2, INVALID, 1) + struct.pack('<I', len(names)) +
        b''.join(string(n) for n in names))
    if encrypted:
        directory = cipher.encrypt(directory.ljust((len(directory) + 15) // 16 * 16, b'\0'))
    header = bytearray(144)
    header[:16] = io.MAGIC
    header[16] = version
    struct.pack_into('<9I', header, 20, 144, 2, 3, 12, len(methods), 32, 64, len(directory), 1)
    header[80] = 12 | int(encrypted) * 2 | int(compression)
    struct.pack_into('<Q', header, 88, 2**64 - 1)
    offsets = (0).to_bytes(5, 'big') + (80).to_bytes(5, 'big') + (80).to_bytes(5, 'big') + len(second).to_bytes(5, 'big')
    toc = (bytes(header) + bytes(24) + offsets + b''.join(records) + b''.join(methods) +
           struct.pack('<I', 4) + b'signsign' +
           b''.join(hashlib.sha1(b).digest() for b in stored) + directory + bytes(48))
    return toc, ucas


def prepare(monkeypatch, tmp_path, *, toc=None, ucas=None, archive_region='nte-global', **options):
    if toc is None:
        toc, ucas = fixture(**options)
    toc_file, ucas_file = file(toc), file(ucas)
    downloads, ranges = [], []
    def save(region, branch, item, path):
        assert item == toc_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(toc)
        downloads.append(item.digest)
    def read(region, branch, item, at, size):
        assert item == ucas_file
        ranges.append((at, size))
        return ucas[at:at + size]
    monkeypatch.setattr(io.release, 'save_file', save)
    monkeypatch.setattr(io.release, 'read_range', read)
    archive = object.__new__(Archive)
    archive.source = SimpleNamespace(region=archive_region, branch='PC_150')
    archive.cipher = AES.new(KEY, AES.MODE_ECB)
    def open_container():
        return io.Container('nte-global', 'PC_150', toc_file, ucas_file, archive, tmp_path)
    return open_container, downloads, ranges


@pytest.mark.parametrize('encrypted', [False, True])
def test_selected_members_verify_stored_bytes_and_restart_offline(monkeypatch, tmp_path, encrypted):
    open_container, downloads, ranges = prepare(monkeypatch, tmp_path, encrypted=encrypted)
    container = open_container()
    assert container.read('HT/a.uasset') == b'A' * 80
    assert len(ranges) == 1  # Adjacent selected blocks coalesce; the third block is not requested.
    assert container.read('ht/B.UASSET') == b'B' * 15
    assert len(ranges) == 1
    def offline(*args):
        raise AssertionError('Cached immutable source unexpectedly used the network')
    monkeypatch.setattr(io.release, 'save_file', offline)
    monkeypatch.setattr(io.release, 'read_range', offline)
    assert open_container().read('HT/a.uasset') == b'A' * 80
    assert len(downloads) == 1


def test_hybrid_cipher_requires_exact_original_guid_and_unique_default(monkeypatch, tmp_path):
    toc, ucas = fixture()
    open_container, _, _ = prepare(monkeypatch, tmp_path, toc=toc, ucas=ucas)
    control = open_container()
    def archive(key, guid=bytes(16), branch='PC_150'):
        result = object.__new__(Archive)
        result.source = SimpleNamespace(region='nte-global', branch=branch)
        result.selected_key, result.encryption_guid = '0x'+key.hex(), guid
        result.cipher = AES.new(key, AES.MODE_ECB)
        return result
    def selected(candidates):
        return io.Container('nte-global', 'PC_150', control.toc, control.ucas, candidates, tmp_path)
    valid = archive(KEY)
    assert selected([valid]).read('HT/a.uasset') == b'A'*80
    assert selected([valid, archive(bytes(32), bytes([1])*16)]).selected_key == valid.selected_key
    for candidates in ([archive(KEY, bytes([1])*16)], [valid, archive(bytes(32))],
                       [archive(KEY, branch='PC_149')]):
        with pytest.raises(PreparationFailure): selected(candidates)


def test_managed_key_bindings_are_guid_scoped_and_reject_conflicts():
    from backend.nte_assets import _publisher_key_bindings
    keys = ['0x'+KEY.hex(), '0x'+bytes(32).hex()]
    def container(key, guid):
        return SimpleNamespace(encrypted=True, selected_key=key, encryption_guid=guid)
    first = container(keys[0], struct.pack('<4I', 0x12345678, 1, 2, 3))
    second = container(keys[1], bytes(16))
    assert _publisher_key_bindings({'first': first, 'second': second}, keys) == {
        'archive_key_guids': {'12345678000000010000000200000003': 0, '0'*32: 1}}
    with pytest.raises(PreparationFailure):
        _publisher_key_bindings({'first': first, 'wrong': container(keys[1], first.encryption_guid)}, keys)
    assert _publisher_key_bindings({}, keys[0]) == {}


def test_corrupt_cached_block_is_refetched_even_at_the_declared_size(monkeypatch, tmp_path):
    open_container, _, ranges = prepare(monkeypatch, tmp_path)
    container = open_container()
    container.read('HT/a.uasset')
    (container.root / '1.block').write_bytes(bytes(container.blocks[1].length))
    assert open_container().read('HT/b.uasset') == b'B' * 15
    assert len(ranges) == 2


def test_stream_ranges_authenticate_complete_blocks_before_returning_slices(monkeypatch, tmp_path):
    toc, ucas = fixture()
    open_container, _, ranges = prepare(monkeypatch, tmp_path, toc=toc, ucas=ucas)
    container = open_container()
    assert container.read_stored(12, 70) == ucas[12:82]
    assert ranges == [(0, 96)]
    assert container.read_stored(container.ucas.size, 0) == b''
    for at, size in [(-1, 1), (0, io.TRANSFER + 1), (container.ucas.size, 1)]:
        with pytest.raises(PreparationFailure):
            container.read_stored(at, size)


def test_stream_ranges_never_return_unsigned_gaps(monkeypatch, tmp_path):
    open_container, _, ranges = prepare(monkeypatch, tmp_path, gap=True)
    container = open_container()
    with pytest.raises(PreparationFailure):
        container.read_stored(60, 30)
    assert ranges == []
    assert container.read('HT/a.uasset') == b'A' * 80
    assert len(ranges) == 2


def test_corrupt_response_publishes_none_of_its_blocks(monkeypatch, tmp_path):
    open_container, _, _ = prepare(monkeypatch, tmp_path)
    container = open_container()
    def corrupt(region, branch, item, at, size):
        return bytes(size)
    monkeypatch.setattr(io.release, 'read_range', corrupt)
    with pytest.raises(PreparationFailure):
        container.read('HT/a.uasset')
    assert not list(container.root.glob('*.block'))


def test_changed_toc_cache_requires_full_manifest_checksum(monkeypatch, tmp_path):
    open_container, downloads, _ = prepare(monkeypatch, tmp_path)
    container = open_container()
    path = container.root / 'index.utoc'
    path.write_bytes(bytes(path.stat().st_size))
    assert open_container().read('HT/b.uasset') == b'B' * 15
    assert len(downloads) == 2


@pytest.mark.parametrize('options', [{'version': 9}, {'cycle': True}, {'collision': True}])
def test_unknown_format_or_unsafe_directory_fails_before_data_download(monkeypatch, tmp_path, options):
    open_container, _, ranges = prepare(monkeypatch, tmp_path, **options)
    with pytest.raises(PreparationFailure):
        open_container()
    assert ranges == []


def test_regional_cipher_proof_cannot_be_reused_for_another_region(monkeypatch, tmp_path):
    open_container, downloads, ranges = prepare(monkeypatch, tmp_path, archive_region='nte-cn')
    with pytest.raises(PreparationFailure):
        open_container()
    assert downloads == ranges == []


def test_compressed_encrypted_blocks_use_exact_declared_output(monkeypatch, tmp_path):
    from backend import wuthering_release_pak
    import zlib
    monkeypatch.setattr(wuthering_release_pak, '_oodle', lambda blocks: b''.join(zlib.decompress(b) for b, _ in blocks))
    open_container, _, _ = prepare(monkeypatch, tmp_path, compression=True)
    assert open_container().read('HT/a.uasset') == b'A' * 80
    monkeypatch.setattr(wuthering_release_pak, '_oodle', lambda blocks: bytes(sum(n for _, n in blocks) + 1))
    with pytest.raises(PreparationFailure):
        open_container().read('HT/a.uasset')


def test_replaced_recording_does_not_replace_historical_cached_bytes(monkeypatch, tmp_path):
    old_open, _, _ = prepare(monkeypatch, tmp_path)
    old = old_open()
    assert old.read('HT/b.uasset') == b'B' * 15
    new_open, _, _ = prepare(monkeypatch, tmp_path, second=b'D' * 15)
    new = new_open()
    assert new.root != old.root
    assert new.read('HT/b.uasset') == b'D' * 15
    assert old_open().read('HT/b.uasset') == b'B' * 15


def test_large_unselected_chunk_does_not_hide_small_authoring_resources(monkeypatch, tmp_path):
    # A real publisher container also inventories a multi-GB non-authoring
    # chunk. Keep the read cap, but do not reject its entire directory.
    original, _ = fixture(encrypted=False)
    header = bytearray(original[:144])
    directory_size = struct.unpack_from('<I', header, 48)[0]
    directory = original[-48 - directory_size:-48]
    count = 130
    struct.pack_into('<I', header, 28, count)
    struct.pack_into('<I', header, 44, 4 * 1024**2)
    offsets = (0).to_bytes(5, 'big') + (40).to_bytes(5, 'big') + (0).to_bytes(5, 'big') + (513 * 1024**2).to_bytes(5, 'big')
    block = b'A' * 64
    blocks = b''.join((i * 64).to_bytes(5, 'little') + (64).to_bytes(3, 'little') * 2 + b'\0'
                      for i in range(count))
    toc = (bytes(header) + bytes(24) + offsets + blocks + struct.pack('<I', 4) + b'signsign' +
           hashlib.sha1(block).digest() * count + directory + bytes(48))
    open_container, _, ranges = prepare(monkeypatch, tmp_path, toc=toc, ucas=block * count)
    container = open_container()
    assert container.read('HT/a.uasset') == b'A' * 40
    before = list(ranges)
    with pytest.raises(PreparationFailure):
        container.read('HT/b.uasset')
    assert ranges == before
