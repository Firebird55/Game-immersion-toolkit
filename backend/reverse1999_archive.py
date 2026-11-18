"""Read the bounded Global archive bootstrap after whole-owner verification."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import lzma
import struct
from typing import Callable
import zlib

from . import reverse1999_bootstrap as unity
from .publisher_transport import CHUNK


START = 32
HEADER_LIMIT = 256 * 1024
TAIL_LIMIT = 2 * HEADER_LIMIT
FOLDER_LIMIT = 32 * 1024 * 1024
EXPANDED_LIMIT = 128 * 1024 * 1024
MEMBER_LIMIT = 4 * 1024 * 1024
BOOTSTRAP = 'reverse1999_Data/resources.assets'


def _require(condition):
    if not condition:
        raise ValueError('Unsupported or invalid original Global archive bootstrap.')


class _Header:
    def __init__(self, raw):
        self.raw, self.position = raw, 0

    def take(self, size):
        _require(0 <= size <= len(self.raw) - self.position)
        begin = self.position
        self.position += size
        return self.raw[begin:self.position]

    def byte(self):
        return self.take(1)[0]

    def expect(self, tag):
        _require(self.byte() == tag)

    def integer(self):
        first, value, mask = self.byte(), 0, 128
        for count in range(8):
            if not first & mask:
                return value | ((first & (mask - 1)) << (count * 8))
            value |= self.byte() << (count * 8)
            mask >>= 1
        return value

    def count(self, maximum, minimum=0):
        count = self.integer()
        _require(minimum <= count <= maximum)
        return count

    def bits(self, count):
        raw = self.take((count + 7) // 8)
        return [bool(raw[k // 8] & (128 >> (k % 8))) for k in range(count)]

    def crcs(self, count):
        flag = self.byte()
        _require(flag in (0, 1))
        present = [True] * count if flag else self.bits(count)
        return [int.from_bytes(self.take(4), 'little') if found else None for found in present]

    def end(self):
        _require(self.position == len(self.raw))


@dataclass(frozen=True)
class _Folder:
    methods: tuple
    output: int
    unpacked: int
    members: tuple


def _streams(reader):
    reader.expect(6)
    position, count = reader.integer(), reader.count(32, 1)
    reader.expect(9)
    packed = tuple(reader.integer() for _ in range(count))
    _require(all(packed))
    tag = reader.byte()
    if tag == 10:
        reader.crcs(count)
        tag = reader.byte()
    _require(tag == 0)
    reader.expect(7)
    reader.expect(11)
    _require(reader.count(32, 1) == count)
    reader.expect(0)
    methods, outputs = [], []
    for _ in range(count):
        coders = []
        for _ in range(reader.count(4, 1)):
            flags = reader.byte()
            _require(0 < flags & 15 <= 8 and not flags & 0xc0)
            method = reader.take(flags & 15)
            if flags & 16:
                _require(reader.integer() == reader.integer() == 1)
            properties = reader.take(reader.count(64)) if flags & 32 else b''
            coders.append((method, properties))
        binds = [(reader.integer(), reader.integer()) for _ in range(len(coders) - 1)]
        used_inputs, used_outputs = {a for a, _ in binds}, {b for _, b in binds}
        _require(len(used_inputs) == len(used_outputs) == len(binds)
                 and all(i < len(coders) for i in used_inputs | used_outputs))
        methods.append(tuple(coders))
        outputs.append(next(i for i in range(len(coders)) if i not in used_outputs))
    reader.expect(12)
    unpacked = [tuple(reader.integer() for _ in methods_of_folder)[output]
                for methods_of_folder, output in zip(methods, outputs, strict=True)]
    tag = reader.byte()
    folder_crcs = [None] * count
    if tag == 10:
        folder_crcs = reader.crcs(count)
        tag = reader.byte()
    _require(tag == 0)
    members = [[(size, crc)] for size, crc in zip(unpacked, folder_crcs, strict=True)]
    tag = reader.byte()
    if tag == 8:
        tag = reader.byte()
        sizes = [1] * count
        if tag == 13:
            sizes = [reader.count(8192, 1) for _ in range(count)]
            _require(sum(sizes) <= 8192)
            tag = reader.byte()
        if tag == 9:
            member_sizes = []
            for n, length in zip(sizes, unpacked, strict=True):
                leading = [reader.integer() for _ in range(n - 1)]
                _require(sum(leading) <= length)
                member_sizes.append([*leading, length - sum(leading)])
            tag = reader.byte()
        else:
            _require(all(n == 1 for n in sizes))
            member_sizes = [[size] for size in unpacked]
        member_crc_count = sum(n for n, crc in zip(sizes, folder_crcs, strict=True) if n != 1 or crc is None)
        if tag == 10:
            member_crcs = iter(reader.crcs(member_crc_count))
            tag = reader.byte()
        else:
            member_crcs = iter([None] * member_crc_count)
        _require(tag == 0)
        members = [[(length, folder_crc if len(lengths) == 1 and folder_crc is not None else next(member_crcs))
                    for length in lengths] for lengths, folder_crc in zip(member_sizes, folder_crcs, strict=True)]
        tag = reader.byte()
    _require(tag == 0)
    return position, packed, tuple(_Folder(*row) for row in zip(methods, outputs, unpacked, members, strict=True))


@dataclass(frozen=True)
class BootstrapQuote:
    packed_offset: int
    packed_size: int
    unpacked_size: int
    dictionary_size: int
    member_offset: int
    member_size: int
    member_crc32: int


def _decode_header(raw, folder):
    _require(len(folder.methods) == 1 and 0 < folder.unpacked <= HEADER_LIMIT)
    method, props = folder.methods[0]
    _require(method == b'\x03\x01\x01' and len(props) == 5 and props[0] < 225)
    prop, dictionary = props[0], int.from_bytes(props[1:], 'little')
    _require(4096 <= dictionary <= FOLDER_LIMIT)
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
        'id': lzma.FILTER_LZMA1, 'dict_size': dictionary, 'lc': prop % 9, 'lp': prop // 9 % 5, 'pb': prop // 45}])
    data = decoder.decompress(raw, max_length=folder.unpacked + 1)
    # The original encoded header uses a 7z LZMA1 stream with a declared output
    # size. Some generations omit the LZMA1 end marker. Its recorded CRC covers
    # the entire decoded header and still has to match.
    _require(len(data) == folder.unpacked and not decoder.unused_data and len(folder.members) == 1)
    _, crc = folder.members[0]
    _require(crc is not None and zlib.crc32(data) == crc)
    return data


def quote_bootstrap(read_at, owner_size):
    """Quote the single supported first-folder member using bounded header reads."""
    def section(offset, size):
        _require(0 <= offset < offset + size <= owner_size and size <= HEADER_LIMIT)
        raw = read_at(offset, size)
        _require(isinstance(raw, bytes) and len(raw) == size)
        return raw

    prefix = section(0, START)
    _require(prefix[:8] == b'7z\xbc\xaf\x27\x1c\x00\x04')
    expected, next_offset, next_size, next_crc = struct.unpack_from('<IQQI', prefix, 8)
    _require(zlib.crc32(prefix[12:]) == expected and START + next_offset + next_size == owner_size)
    next_start = START + next_offset
    _require(next_size <= HEADER_LIMIT and next_start >= START)
    header_raw = section(next_start, next_size)
    _require(zlib.crc32(header_raw) == next_crc)
    packed_limit = next_start
    if header_raw[:1] == b'\x17':
        encoded = _Header(header_raw[1:])
        pos, sizes, folders = _streams(encoded)
        encoded.end()
        _require(len(sizes) == 1 and START + pos + sizes[0] <= next_start and owner_size - START - pos <= TAIL_LIMIT)
        packed_limit = START + pos
        header_raw = _decode_header(section(packed_limit, sizes[0]), folders[0])
    reader = _Header(header_raw)
    reader.expect(1)
    reader.expect(4)
    position, packed_sizes, folders = _streams(reader)
    _require(position == 0 and START + sum(packed_sizes) <= packed_limit)
    reader.expect(5)
    count = reader.count(8192, 1)
    properties = {}
    tag = reader.byte()
    while tag:
        if tag == 25:
            _require(not any(reader.take(reader.count(7))))
        else:
            _require(tag not in properties and len(properties) < 16)
            properties[tag] = reader.take(reader.count(HEADER_LIMIT))
        tag = reader.byte()
    reader.expect(0)
    reader.end()
    names = properties.get(17, b'')
    _require(names[:1] == b'\0')
    paths = names[1:].decode('utf-16-le').split('\0')
    _require(len(paths) == count + 1 and paths[-1] == '' and paths.count(BOOTSTRAP) == 1)
    if 14 in properties:
        flags = _Header(properties[14])
        empty = flags.bits(count)
        flags.end()
    else:
        empty = [False] * count
    _require(sum(not flag for flag in empty) == sum(len(folder.members) for folder in folders))
    entry = paths.index(BOOTSTRAP)
    ordinal = sum(not flag for flag in empty[:entry])
    folder = folders[0]
    _require(not empty[entry] and ordinal < len(folder.members) and folder.output == 0
             and len(folder.methods) == 1 and 0 < folder.unpacked <= EXPANDED_LIMIT and packed_sizes[0] <= FOLDER_LIMIT)
    method, properties = folder.methods[0]
    _require(method == b'\x21' and len(properties) == 1 and properties[0] <= 26)
    dictionary = (2 | (properties[0] & 1)) << (properties[0] // 2 + 11)
    size, crc = folder.members[ordinal]
    _require(48 <= size <= MEMBER_LIMIT and crc is not None)
    return BootstrapQuote(START, packed_sizes[0], folder.unpacked, dictionary,
                          sum(length for length, _ in folder.members[:ordinal]), size, crc)


@dataclass(frozen=True)
class RetainedRange:
    offset: int
    size: int
    read: Callable[[int], bytes] = field(repr=False)


@dataclass(frozen=True)
class VerifiedBootstrap:
    archive_sha256: str
    member: unity.Bootstrap
    raw_asset: bytes = field(repr=False)


def _extract(prefix, quote, check):
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW,
        filters=[{'id': lzma.FILTER_LZMA2, 'dict_size': quote.dictionary_size}])
    end = quote.packed_offset + quote.packed_size
    position, decoded = quote.packed_offset, 0
    target_end = quote.member_offset + quote.member_size
    asset = bytearray()
    while position < end or not decoder.needs_input and not decoder.eof:
        check()
        chunk = b''
        if decoder.needs_input:
            boundary = min(end, position + CHUNK)
            chunk, position = memoryview(prefix)[position:boundary], boundary
        raw = decoder.decompress(chunk, max_length=CHUNK)
        first, last = max(quote.member_offset, decoded), min(target_end, decoded + len(raw))
        if first < last:
            asset.extend(raw[first - decoded:last - decoded])
        decoded += len(raw)
        _require(decoded <= quote.unpacked_size and not decoder.unused_data)
        if decoder.eof:
            _require(position == end)
            break
    _require(decoder.eof and decoded == quote.unpacked_size and len(asset) == quote.member_size
             and zlib.crc32(asset) == quote.member_crc32)
    return bytes(asset)


def verify_bootstrap(archive, quote, transport, *, retained=()):
    """Verify the complete publisher archive while retaining only bounded sections."""
    _require(archive.part == 0 and isinstance(quote, BootstrapQuote) and isinstance(retained, (tuple, list)) and len(retained) <= 32)
    _require(all(isinstance(piece, RetainedRange) and type(piece.offset) is int and type(piece.size) is int
                 and 0 <= piece.offset < piece.offset + piece.size <= archive.size and callable(piece.read) for piece in retained))
    pieces = sorted(retained, key=lambda piece: piece.offset)
    _require(all(left.offset + left.size <= right.offset for left, right in zip(pieces, pieces[1:])))
    _require(quote.packed_offset == START and 0 < quote.packed_size <= FOLDER_LIMIT)
    prefix, tail = bytearray(), bytearray()
    prefix_size = START + quote.packed_size
    md5, sha256 = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    position = 0

    def consume(chunk):
        nonlocal position
        _require(isinstance(chunk, bytes) and 0 < len(chunk) <= CHUNK and position + len(chunk) <= archive.size)
        md5.update(chunk)
        sha256.update(chunk)
        if position < prefix_size:
            prefix.extend(chunk[:prefix_size - position])
        if position + len(chunk) > archive.size - TAIL_LIMIT:
            tail.extend(chunk[max(0, archive.size - TAIL_LIMIT - position):])
        position += len(chunk)

    def gap(end):
        start = position
        if end > start:
            size = end - start
            transport.stream_bytes(archive.url, consume, limit=size, expected_size=size,
                original_range=None if size == archive.size else (start, size, archive.size))
            _require(position == end)

    for piece in pieces:
        gap(piece.offset)
        end = piece.offset + piece.size
        while position < end:
            transport.ctx.check()
            limit = min(CHUNK, end - position)
            chunk = piece.read(limit)
            _require(isinstance(chunk, bytes) and len(chunk) == limit)
            consume(chunk)
    gap(archive.size)
    _require(position == archive.size and md5.hexdigest() == archive.md5)
    transport.ctx.check()

    def section(offset, size):
        if offset + size <= len(prefix):
            return bytes(prefix[offset:offset + size])
        start = offset - (archive.size - len(tail))
        _require(0 <= start <= len(tail) - size)
        return bytes(tail[start:start + size])

    _require(quote_bootstrap(section, archive.size) == quote)
    raw = _extract(prefix, quote, transport.ctx.check)
    member = unity.read(raw, expected_revision=archive.resource_revision, expected_sha256=hashlib.sha256(raw).hexdigest())
    transport.ctx.check()
    return VerifiedBootstrap(sha256.hexdigest(), member, raw)
