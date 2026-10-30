"""Synthetic archive fixtures only; no game assets or transcripts."""
from dataclasses import replace
from pathlib import Path
import struct
import zlib

import pytest

from backend import tiger_archive
from backend.tiger_archive import TigerSet, name_hash32


def write_tiger(root, name='bigfile.000.tiger', *, version=4, identity=1, sub=0,
                records=((42, 0xFFFF0001, b'synthetic asset'),)):
    header_size, stride = (52, 24) if version == 4 else (56, 32)
    start = (header_size + stride * len(records) + 15) & ~15
    header = struct.pack('<4s4I', b'TAFS', version, 1, len(records), identity)
    if version == 5:
        header += struct.pack('<I', sub)
    header += b'pcx64-w'.ljust(32, b'\0')
    table, payload, offset = bytearray(), bytearray(), start
    for key, locale, data in records:
        values = (key, locale, len(data), 0, 0, identity, offset)
        if version == 5:
            values = (*values[:-1], sub, offset)
        table.extend(struct.pack('<4IhhI' if version == 4 else '<QQIIhBBI', *values))
        payload.extend(data)
        padding = (-len(payload)) % 16
        payload.extend(b'\0' * padding)
        offset = start + len(payload)
    path = root / name
    path.write_bytes((header + table).ljust(start, b'\0') + payload)
    return path


@pytest.mark.parametrize('version', [4, 5])
def test_read_and_reject_forged_reference(tmp_path, version):
    write_tiger(tmp_path, version=version)
    archives = TigerSet(tmp_path, version)
    entry = next(iter(archives.entries()))
    assert archives.prefix(entry, 9) == b'synthetic'
    assert archives.read(entry) == b'synthetic asset'
    with pytest.raises(ValueError, match='no longer current'):
        archives.read(replace(entry, archive='../outside.tiger'))
    with pytest.raises(ValueError, match='bound'):
        archives.read(entry, max_bytes=2)


def test_cdrm_is_bounded_and_validated(tmp_path):
    data = b'synthetic compressed resource' * 100
    compressed = zlib.compress(data)
    cdrm = struct.pack('<4s3I2I', b'CDRM', 0, 1, 0, len(data) << 8 | 2, len(compressed)).ljust(32, b'\0') + compressed
    path = write_tiger(tmp_path, records=((42, 0xFFFF0001, cdrm),))
    content = bytearray(path.read_bytes())
    struct.pack_into('<I', content, 52 + 8, len(data))
    path.write_bytes(content)
    archives = TigerSet(tmp_path, 4)
    entry = next(iter(archives.entries()))
    assert archives.prefix(entry, 9) == b'synthetic'
    assert archives.read(entry) == data
    content[entry.offset + 32] ^= 0xFF
    path.write_bytes(content)
    with pytest.raises(ValueError, match='compressed'):
        archives.read(entry)


def test_cross_archive_reference_and_patch_priority(tmp_path):
    base = write_tiger(tmp_path)
    patch = write_tiger(tmp_path, 'bigfile.update1.000.000.tiger', identity=2, records=((42, 0xFFFF0001, b'new'),))
    (tmp_path / 'bigfile.000.nfo').write_text('base dlcindex 1 version 1 required 1 package 1 chunk 0')
    (tmp_path / 'bigfile.update1.000.000.nfo').write_text('patch dlcindex 2 version 2 required 1 package 2 chunk 0')
    archives = TigerSet(tmp_path, 4)
    assert archives.read(archives.files[42, 0xFFFF0001]) == b'new'
    content = bytearray(patch.read_bytes())
    # A patch directory can reference the original package's physical bytes.
    struct.pack_into('<I', content, 52 + 8, len(b'synthetic asset'))
    struct.pack_into('<h', content, 52 + 18, 1)
    patch.write_bytes(content)
    archives = TigerSet(tmp_path, 4)
    assert archives.read(archives.files[42, 0xFFFF0001]) == b'synthetic asset'
    base.unlink()
    with pytest.raises(ValueError, match='missing'):
        TigerSet(tmp_path, 4)


def test_missing_part_platform_and_version(tmp_path):
    path = write_tiger(tmp_path)
    content = bytearray(path.read_bytes())
    struct.pack_into('<h', content, 52 + 16, 2)
    path.write_bytes(content)
    with pytest.raises(ValueError):
        TigerSet(tmp_path, 4)
    write_tiger(tmp_path)
    with pytest.raises(ValueError):
        TigerSet(tmp_path, 5)


def test_total_directory_cap_applies_across_archives(tmp_path, monkeypatch):
    write_tiger(tmp_path)
    write_tiger(tmp_path, 'bigfile.update.000.tiger', identity=2)
    monkeypatch.setattr(tiger_archive, 'MAX_DIRECTORY_ENTRIES', 1)
    with pytest.raises(ValueError, match='total directory bound'):
        TigerSet(tmp_path, 4)
    monkeypatch.setattr(tiger_archive, 'MAX_ARCHIVE_FILES', 1)
    with pytest.raises(ValueError, match='archive count'):
        TigerSet(tmp_path, 4)


def test_hash_format_constant():
    assert name_hash32(r'pcx64-w\local\locals.bin') == 0xD33DA77A
