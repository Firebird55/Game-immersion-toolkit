import struct

import pytest

from backend import endfield_timeline_bundle as reader


def profile():
    table = bytes(range(256))
    return reader.Format(tuple(tuple(0 for _ in range(count)) for count in
                               (4, 0, 7, 1, 1, 1, 5, 1, 1, 1, 2, 0, 5, 1)),
                         table, reader._round_keys(table, bytes(16)), bytes(16))


def halves(value, width, rotation):
    scrambled = reader._rol(value, rotation, width)
    mask = (1 << (width // 2)) - 1
    low = scrambled & mask
    return (scrambled >> (width // 2)) ^ low, low


def count(value):
    high, low = halves(value, 32, 18)
    return struct.pack('>HH', high, low)


def bundle(*, size=64, raw=None, name=None, end=False):
    raw = raw if raw is not None else bytearray(64)
    if isinstance(raw, bytearray):
        struct.pack_into('>I', raw, 8, 22)
        struct.pack_into('>Q', raw, 24, len(raw))
    name = name or 'CAB-' + 'a' * 32
    a, c = halves(size, 32, 18)
    b, d = halves(len(raw), 32, 18)
    # Flags combine high and low bytes before rotation.
    flags = reader._rol(c, 2, 16)
    block = struct.pack('>5H', a, b, c, flags ^ ((flags & 255) << 8), d)
    b, e = halves(size, 64, -14)
    node = struct.pack('>IIII', 0, b, 0, 0) + bytes(v ^ i for i, v in enumerate(name.encode())) + b'\0' + struct.pack('>I', e)
    info = count(1) + block + count(1) + node
    c1, c2 = halves(len(info), 32, 18)
    s1, s2 = halves(48 + len(raw) + len(info), 64, 18)
    header = struct.pack('>IIHIIIIH4xHIH', 0, 0, c2, 0, 7, s2, 128 if end else 0, c1, c2, s1, c1)
    return header.ljust(48,b'\0') + (bytes(raw) + info if end else info + bytes(raw))


def test_raw_cab_and_end_positioned_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(reader, '_format', lambda _path: profile())
    for at_end in (True, False):
        name, data = reader.decode_bundle(bundle(end=at_end), tmp_path)
        assert name == 'CAB-' + 'a' * 32 and len(data) == 64 and data[11] == 22
    for bad in (bundle()[:-1], bundle(raw=b'q' * 64), bundle(size=500), bundle(name='CAB-unsafe')):
        with pytest.raises(ValueError):
            reader.decode_bundle(bad, tmp_path)


def test_both_length_encodings_and_sparse_prefix():
    assert reader._inflate(bytes([0x40]) + b'abcd' + b'\x04\x00', 8, False) == b'abcdabcd'
    assert reader._inflate(bytes([0x10]) + b'abcd' + b'\x00\x04', 8, True) == b'abcdabcd'
    for invalid, length in [(b'\x00\x00\x00', 4), (b'\x03ab', 3), (b'\xff', 5)]:
        with pytest.raises(ValueError):
            reader._inflate(invalid, length, True)
    form = profile()
    for size in (1, 17, 255, 256, 257, 570, 4096, 4097):
        plain = bytes(i % 251 for i in range(size))
        transformed = reader._unmask(plain, form)
        assert transformed != plain and reader._unmask(transformed, form) == plain
        if size > 4096:
            assert transformed[4096:] == plain[4096:]


def test_bad_download_cannot_replace_cached_format(monkeypatch, tmp_path):
    original = b'old metadata'
    path = tmp_path / 'format-metadata/endfield-timeline-v1/VFSUtils.cs'
    path.parent.mkdir(parents=True)
    path.write_bytes(original)
    monkeypatch.setattr(reader, 'download', lambda *args, **kwargs: b'unverified')
    with pytest.raises(ValueError, match='checksum'):
        reader._format(tmp_path)
    assert path.read_bytes() == original
