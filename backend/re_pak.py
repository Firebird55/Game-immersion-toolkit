"""Bounded, selected-file RE Engine PAK reader, independent of upstream code.

Format evidence and limits are documented in docs/re-pak-runtime.md. Encryption
parameters are supplied as data by the private metadata cache, never embedded
in this module. No external process, SDK, shell or global executable is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import struct
import tempfile
import zlib

MAX_FILES = 2_000_000
MAX_SELECTED = 100_000
MAX_RESOURCE = 256 * 1024 * 1024
MAX_OUTPUT = 2 * 1024 * 1024 * 1024
MAX_CHUNKS = 4_000_000
CHUNK_SIZE = 524288
CHUNK_ATTRIBUTES = {0x1000000, 0x1000400, 0x1000800, 0x1000C00}


@dataclass(frozen=True)
class CipherParameters:
    modulus: int
    exponent: int

    def __post_init__(self):
        if not 1 < self.modulus < (1 << 2048) or not 0 < self.exponent < (1 << 1024):
            raise ValueError('Invalid PAK format parameters')


def murmur32(data: bytes) -> int:
    """MurmurHash3 x86_32, with the format's all-ones seed."""
    mask = 0xffffffff
    value = mask
    for pos in range(0, len(data) // 4 * 4, 4):
        block = int.from_bytes(data[pos:pos + 4], 'little') * 0xcc9e2d51 & mask
        block = ((block << 15) | (block >> 17)) & mask
        value ^= block * 0x1b873593 & mask
        value = ((value << 13) | (value >> 19)) & mask
        value = (value * 5 + 0xe6546b64) & mask
    tail = data[len(data) // 4 * 4:]
    if tail:
        block = int.from_bytes(tail, 'little') * 0xcc9e2d51 & mask
        block = ((block << 15) | (block >> 17)) & mask
        value ^= block * 0x1b873593 & mask
    value ^= len(data)
    value ^= value >> 16
    value = value * 0x85ebca6b & mask
    value ^= value >> 13
    value = value * 0xc2b2ae35 & mask
    return value ^ (value >> 16)


def path_hash(name: str) -> int:
    return (murmur32(name.upper().encode('utf-16le')) << 32
            | murmur32(name.lower().encode('utf-16le')))


def selected_paths(names) -> dict[int, str]:
    result = {}
    for name in names:
        path = PurePosixPath(name)
        if (not name.isascii() or not name.startswith('natives/')
                or path.as_posix() != name or '\\' in name or ':' in name
                or any(part in {'.', '..'} or part.endswith((' ', '.'))
                       or re.fullmatch(r'(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part)
                       for part in path.parts)):
            raise ValueError('Unsafe requested game asset path')
        key = path_hash(name)
        if key in result and result[key] != name:
            raise ValueError('Ambiguous selected PAK file hash')
        result[key] = name
        if len(result) > MAX_SELECTED:
            raise ValueError('Too many selected PAK files')
    if not result:
        raise ValueError('Selective extraction requires files')
    return result


def _read(stream, size: int, total: int) -> bytes:
    if size < 0 or size > total - stream.tell():
        raise ValueError('Truncated PAK data')
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('PAK changed during extraction')
    return data


def _table_decode(data: bytes, encrypted: bytes, cipher: CipherParameters) -> bytes:
    value = pow(int.from_bytes(encrypted, 'little'), cipher.exponent, cipher.modulus)
    key = value.to_bytes(max(1, (value.bit_length() + 8) // 8), 'little')
    if len(key) < 32:
        raise ValueError('Invalid PAK table key')
    return bytes(byte ^ ((pos + key[pos % 32] * key[pos % 29]) & 255)
                 for pos, byte in enumerate(data))


def _resource_decode(data: bytes, cipher: CipherParameters) -> bytes:
    if len(data) < 8 or (len(data) - 8) % 128:
        raise ValueError('Invalid encrypted PAK resource')
    size, = struct.unpack_from('<q', data)
    blocks = (len(data) - 8) // 128
    if not 0 <= size <= MAX_RESOURCE or blocks != (size + 7) // 8:
        raise ValueError('Invalid encrypted PAK resource size')
    output = bytearray(blocks * 8)
    for index in range(blocks):
        pos = 8 + index * 128
        key = int.from_bytes(data[pos:pos + 64], 'little', signed=True)
        value = int.from_bytes(data[pos + 64:pos + 128], 'little', signed=True)
        if key < 0 or value < 0:
            raise ValueError('Invalid encrypted PAK block')
        divisor = pow(key, cipher.exponent, cipher.modulus)
        if not divisor or value // divisor >= (1 << 64):
            raise ValueError('Invalid decrypted PAK block')
        output[index * 8:index * 8 + 8] = (value // divisor).to_bytes(8, 'little')
    return bytes(output[:size])


def _decompress(data: bytes, codec: int, limit: int) -> bytes:
    if codec == 0:
        result = data
    elif codec == 1:
        reader = zlib.decompressobj(-15)
        result = reader.decompress(data, limit + 1)
        if not reader.eof or reader.unused_data or reader.unconsumed_tail:
            raise ValueError('Invalid or oversized PAK deflate stream')
    elif codec == 2:
        import zstandard
        # max_output_size is not a limit when a frame advertises its size.
        # Check that separately before allocating, and reject trailing frames.
        advertised = zstandard.frame_content_size(data)
        if advertised not in (zstandard.CONTENTSIZE_UNKNOWN, zstandard.CONTENTSIZE_ERROR) and advertised > limit:
            raise ValueError('PAK Zstandard output exceeds the reader limit')
        result = zstandard.ZstdDecompressor(max_window_size=MAX_RESOURCE // 1024).decompress(
            data, max_output_size=max(1, limit), allow_extra_data=False)
    else:
        raise ValueError('Unsupported PAK compression')
    if len(result) > limit:
        raise ValueError('PAK resource exceeds the reader limit')
    return result


def _chunk_map(stream, total: int, entry_size=8) -> bytes:
    first, second = struct.unpack('<II', _read(stream, 8, total))
    block_size, count = (first, second) if entry_size == 8 else (second, first)
    if not 0 < block_size <= CHUNK_SIZE or count > MAX_CHUNKS:
        raise ValueError('Invalid PAK chunk map')
    return _read(stream, count * entry_size, total)


def extract_selected(archive: Path, destination: Path, names, *, parameters=None) -> int:
    """Extract selected paths atomically per file, after validating the archive.

    ``parameters(kind)`` returns verified table/resource CipherParameters only
    when that format requires it. Unknown/unselected resources are not read.
    Files from earlier patch layers survive any validation/decompression error.
    """
    selected = selected_paths(names)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with archive.open('rb') as stream, tempfile.TemporaryDirectory(prefix='.pak-', dir=destination) as temporary:
        total = archive.stat().st_size
        magic, major, minor, feature, count, _ = struct.unpack('<4sBBHII', _read(stream, 16, total))
        if magic != b'KPKA' or (major, minor) not in {(2, 0), (4, 0), (4, 1), (4, 2)}:
            raise ValueError('Unsupported PAK header')
        if count > MAX_FILES or feature not in {0, 8, 12, 24, 40, 44, 104}:
            raise ValueError('Unsupported PAK feature or entry count')
        entry_size = 24 if major == 2 else 48
        table = _read(stream, count * entry_size, total)
        chunks = b''
        if feature:
            if parameters is None:
                raise ValueError('Verified PAK format metadata is required')
            _read(stream, 4 if feature == 24 else 9 if feature in {12, 44} else 0, total)
            if feature == 104:
                _chunk_map(stream, total, 16)
            table = _table_decode(table, _read(stream, 128, total), parameters('table'))
            if feature in {40, 44, 104}:
                chunks = _chunk_map(stream, total)
        data_start = stream.tell()
        output_size = 0
        written = []
        seen = set()
        for pos in range(0, len(table), entry_size):
            if major == 2:
                offset, size, lower, upper = struct.unpack_from('<qqII', table, pos)
                compressed, flags = size, 0
            else:
                lower, upper, offset, compressed, size, flags, _ = struct.unpack_from('<IIqqqqQ', table, pos)
            key = upper << 32 | lower
            if key not in selected:
                continue
            if key in seen:
                raise ValueError('Duplicate selected PAK entry')
            seen.add(key)
            if min(offset, compressed, size) < 0 or max(compressed, size) > MAX_RESOURCE:
                raise ValueError('Selected PAK resource exceeds the reader limit')
            output_size += size
            if output_size > MAX_OUTPUT:
                raise ValueError('Selected PAK output exceeds the reader limit')
            if feature in {40, 44, 104} and flags in CHUNK_ATTRIBUTES:
                output = bytearray()
                remaining = compressed
                while remaining:
                    if offset >= len(chunks) // 8:
                        raise ValueError('PAK chunk index is outside its map')
                    low, packed = struct.unpack_from('<II', chunks, offset * 8)
                    address, length = low + ((packed & 0x3ff) << 32), packed >> 10
                    if address < data_start or not 0 < length <= remaining:
                        raise ValueError('Invalid PAK chunk range')
                    stream.seek(address)
                    part = _decompress(_read(stream, length, total), 0 if length == CHUNK_SIZE else 2, CHUNK_SIZE)
                    output.extend(part)
                    if len(output) > size + CHUNK_SIZE - 1:
                        raise ValueError('PAK chunk output exceeds its declared size')
                    remaining -= length
                    offset += 1
                if len(output) < size:
                    raise ValueError('PAK chunk output is shorter than declared')
                content = bytes(output[:size])
            else:
                if offset < data_start:
                    raise ValueError('PAK resource overlaps its metadata')
                stream.seek(offset)
                content = _read(stream, compressed, total)
                encryption = flags >> 16 & 255
                if encryption:
                    if encryption not in {1, 2, 3, 4} or parameters is None:
                        raise ValueError('Unsupported PAK resource encryption')
                    content = _resource_decode(content, parameters('resource'))
                content = _decompress(content, flags & 15, size)
                if len(content) != size:
                    raise ValueError('PAK resource size does not match its entry')
            target = destination / selected[key]
            if not target.resolve().is_relative_to(destination):
                raise ValueError('PAK output escapes destination')
            staged = Path(temporary) / str(len(written))
            staged.write_bytes(content)
            written.append((staged, target))
        # All selected contents have passed validation before existing files change.
        for staged, target in written:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.resolve().is_relative_to(destination):
                raise ValueError('PAK output escapes destination')
            staged.replace(target)
        return len(written)
