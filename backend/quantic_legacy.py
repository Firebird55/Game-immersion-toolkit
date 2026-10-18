"""Bounded readers for HEAVY RAIN's big-endian Quantic PC resources."""
from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
import math
import struct
import zlib

from .quantic_assets import METADATA_LIMIT, Cursor, Entry


class Metadata:
    """Read selected logical ranges without inflating unrelated scene assets."""

    def __init__(self, entry: Entry):
        self.entry, self.cache = entry, OrderedDict()
        header = entry.read(16)
        self.segments = []
        if header.startswith(b'QZIP\0'):
            self.size, self.base, self.starts = entry.size - 5, 5, []
            return
        if len(header) != 16 or header[:4] != b'segs':
            raise ValueError('Unsupported HEAVY RAIN metadata encoding')
        version, count, self.size, packed = struct.unpack_from('>HHII', header, 4)
        self.base = (16 + count * 8 + 15) // 16 * 16
        if version != 1 or not count or not self.size or self.base + packed > entry.size:
            raise ValueError('Invalid HEAVY RAIN segmented metadata bounds')
        table, logical = entry.read(self.base), 0
        for i in range(count):
            length, original, offset = struct.unpack_from('>HHI', table, 16 + i * 8)
            original = original or 65536
            if not length or (offset & ~1) + length > packed:
                raise ValueError('HEAVY RAIN metadata chunk exceeds its archive')
            self.segments.append((logical, original, offset & ~1, length, bool(offset & 1)))
            logical += original
        if logical != self.size:
            raise ValueError('HEAVY RAIN metadata size disagrees with its chunk table')
        self.starts = [row[0] for row in self.segments]

    def _stored(self, offset, size):
        with self.entry.path.open('rb') as stream:
            stream.seek(self.entry.offset + offset)
            value = stream.read(size)
        if len(value) != size:
            raise ValueError('HEAVY RAIN archive changed during reading')
        return value

    def _chunk(self, index):
        if index not in self.cache:
            _, original, offset, size, compressed = self.segments[index]
            stored = self._stored(self.base + offset, size)
            if compressed:
                decoder = zlib.decompressobj(-15)
                try:
                    body = decoder.decompress(stored, original + 1)
                except zlib.error as error:
                    raise ValueError('Invalid HEAVY RAIN raw-deflate metadata') from error
                if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                    raise ValueError('Incomplete HEAVY RAIN raw-deflate chunk')
            else:
                body = stored
            if len(body) != original:
                raise ValueError('HEAVY RAIN metadata chunk has an invalid decoded size')
            if len(self.cache) >= 8:
                self.cache.popitem(last=False)
            self.cache[index] = body
        self.cache.move_to_end(index)
        return self.cache[index]

    def read(self, offset, size):
        if offset < 0 or size < 0 or size > METADATA_LIMIT or offset + size > self.size:
            raise ValueError('HEAVY RAIN metadata range exceeds its bounds')
        if not self.segments:
            return self._stored(self.base + offset, size)
        result, end = [], offset + size
        while offset < end:
            index = bisect_right(self.starts, offset) - 1
            start, length, *_ = self.segments[index]
            last = min(end, start + length)
            result.append(self._chunk(index)[offset - start:last - start])
            offset = last
        return b''.join(result)


def references(reader):
    header = reader.read(0, 20)
    if header[:8] != b'DC_INFO ':
        raise ValueError('Missing HEAVY RAIN authored dependency table')
    version, size, count = struct.unpack_from('>III', header, 8)
    if version not in (1, 2) or count > 100000 or size < 4:
        raise ValueError('Unsupported HEAVY RAIN dependency table')
    data, position, result = reader.read(0, 16 + size), 20, []
    for _ in range(count):
        if position + 8 > len(data):
            raise ValueError('Incomplete HEAVY RAIN authored dependency')
        kind, identity = struct.unpack_from('>II', data, position)
        position += 8
        language = None
        if kind == 4091 and version == 2:
            if position == len(data) or data[position] >= 40:
                raise ValueError('Invalid HEAVY RAIN original-voice language')
            language = data[position]
            position += 1
        result.append((kind, identity, language))
    if position != len(data):
        raise ValueError('Unsupported HEAVY RAIN dependency encoding')
    return result, 16 + size


def components(reader, kinds):
    rows, position = references(reader)
    header = reader.read(position, 16)
    if header[:8] != b'DC_DATA ' or struct.unpack_from('>I', header, 8)[0] != 7:
        raise ValueError('Unsupported HEAVY RAIN component stream')
    if position + 16 + struct.unpack_from('>I', header, 12)[0] != reader.size:
        raise ValueError('HEAVY RAIN component stream has invalid bounds')
    position += 16
    for kind, identity, language in rows:
        header = reader.read(position, 14)
        size = struct.unpack_from('>I', header)[0]
        end = position + 10 + size
        if size < 4 or end > reader.size or header[8] != 1:
            raise ValueError('Invalid HEAVY RAIN component bounds or pointer')
        if kind in kinds:
            yield kind, identity, language, reader.read(position + 14, size - 4)
        position = end
    if position != reader.size:
        raise ValueError('Unsupported trailing HEAVY RAIN component data')


class BigCursor(Cursor):
    def integer(self):
        return struct.unpack('>I', self.read(4))[0]


def localization(data, locales=None):
    cursor = BigCursor(data)
    if cursor.read(8) != b'COM_CONT' or cursor.integer() != 3:
        raise ValueError('Missing HEAVY RAIN localization container')
    count, dependencies = cursor.integer(), set()
    if count > 100000:
        raise ValueError('Invalid HEAVY RAIN localization dependency count')
    for _ in range(count):
        kind, identity, external = cursor.integer(), cursor.integer(), cursor.read(1)
        cursor.read(8)  # Authored dependency attributes, not text/audio offsets.
        if external not in (b'\0', b'\1'):
            raise ValueError('Invalid HEAVY RAIN localization dependency pointer')
        if external == b'\1':
            dependencies.add((kind, identity))
    if (cursor.read(8) != b'LOADCONT' or cursor.integer() != 2
            or cursor.read(8) != b'LOCALIZ_' or cursor.integer() != 5 or cursor.read(1) != b'\1'):
        raise ValueError('Unsupported HEAVY RAIN compact localization')
    count, result = cursor.integer(), {}
    if not 1 <= count <= 40:
        raise ValueError('Invalid HEAVY RAIN localization language count')
    for _ in range(count):
        if cursor.read(1) != b'\2':
            raise ValueError('Unsupported HEAVY RAIN language table encoding')
        code, count = cursor.string(), cursor.integer()
        if count > 100000 or code in result:
            raise ValueError('Invalid or duplicate HEAVY RAIN language table')
        rows = [struct.unpack('>7I', cursor.read(28)) for _ in range(count)]
        size = cursor.integer()
        if size > METADATA_LIMIT or size % 2:
            raise ValueError('Invalid HEAVY RAIN official text pool size')
        pool, texts, bindings = cursor.read(size), {}, {}
        for key, offset, length, _flags, pointer, kind, identity in rows:
            if offset % 2 or offset + length * 2 > size or pointer or (not kind and identity):
                raise ValueError('Invalid HEAVY RAIN official text or voice pointer')
            if locales is not None and code not in locales:
                continue
            text = pool[offset:offset + length * 2].decode('utf-16-be').rstrip('\0')
            binding = (kind, identity) if kind and (kind, identity) in dependencies else None
            if key in texts and (texts[key], bindings[key]) != (text, binding):
                raise ValueError('Conflicting HEAVY RAIN official localization identity')
            texts[key], bindings[key] = text, binding
        if locales is None or code in locales:
            result[code] = {'texts': texts, 'bindings': bindings}
    if cursor.position != len(data):
        raise ValueError('Unsupported trailing HEAVY RAIN localization fields')
    return result


def partition(data):
    if len(data) < 16 or data[:8] != b'PARTITIO' or struct.unpack_from('>I', data, 8)[0] != 2:
        raise ValueError('Unsupported HEAVY RAIN original dialogue partition')
    footer = 16 + struct.unpack_from('>I', data, 12)[0]
    if footer + 32 > len(data) or data[footer:footer + 8] != b'PARTOFFS':
        raise ValueError('Missing HEAVY RAIN authored audio offsets')
    version, length, kind, identity, mode, _ = struct.unpack_from('>6I', data, footer + 8)
    if (version, length, kind, mode) != (2, 16, 4092, 1):
        raise ValueError('Unsupported HEAVY RAIN audio offset reference')
    header = data.rfind(b'HEADER__', footer + 32)
    if header < 0 or header + 24 > len(data):
        raise ValueError('Missing HEAVY RAIN authored subtitle timings')
    version, length, flag, count = struct.unpack_from('>4I', data, header + 8)
    if version != 4 or flag != 1 or not 2 <= count <= 100000 or count % 2 or length != 8 + count * 4 or header + 16 + length != len(data):
        raise ValueError('Unsupported HEAVY RAIN subtitle timing table')
    values = struct.unpack_from(f'>{count}f', data, header + 24)
    times = [(start / 1000, end / 1000) for start, end in zip(values[::2], values[1::2])]
    # Shipped timing origins precede zero by up to three 44.1-kHz samples
    # (one Spanish performance), including float32 millisecond roundoff.
    epsilon = 3 / 44100 + 1e-9
    if any(not all(map(math.isfinite, pair)) or not -epsilon <= pair[0] < pair[1] <= 86400 for pair in times):
        raise ValueError('Invalid HEAVY RAIN authored subtitle times')
    return identity, [(max(0, start), end) for start, end in times], footer


def partition_blocks(data, offsets):
    _, _, footer = partition(data)
    if len(offsets) < 20 or offsets[:8] != b'TBOFFSET':
        raise ValueError('Missing HEAVY RAIN original audio chunk table')
    version, count = struct.unpack_from('>2I', offsets, 8)
    if version != 4 or not 1 <= count <= 86400 or len(offsets) != 20 + count * 8:
        raise ValueError('Unsupported HEAVY RAIN original audio chunk table')
    starts = struct.unpack_from(f'>{count}I', offsets, 16)
    sizes = struct.unpack_from(f'>{count}I', offsets, 20 + count * 4)
    result = []
    for i, (start, size) in enumerate(zip(starts, sizes)):
        start += 2048
        if size < 32 or start + size > footer or (i and start < 2048 + starts[i - 1] + sizes[i - 1]):
            raise ValueError('HEAVY RAIN original audio chunk exceeds its authored bounds')
        frame, begin, end, unknown, name_length, block_size = struct.unpack_from('>I2f3I', data, start)
        if (frame != i or abs(begin - i) > .001 or (abs(end - i - 1) > .001 if i < count - 1 else not i < end <= i + 1.001)
                or unknown or name_length not in (4, 8)):
            raise ValueError('Unsupported HEAVY RAIN original audio block')
        if name_length == 4:
            if data[start + 20:start + 32] != b'000000000000':
                raise ValueError('Invalid HEAVY RAIN single-stream audio header')
            block_size = size - 16
        if not 16 <= block_size <= size - 16 or data[start + 24:start + 32] != b'00000000':
            raise ValueError('Invalid HEAVY RAIN original audio block bounds')
        payload = data[start + 32:start + 16 + block_size]
        if not payload or payload[:4] == b'NULL' and len(payload) == 8:
            payload = None
        elif len(payload) < 4 or payload[0] != 255 or payload[1] & 0xe0 != 0xe0:
            raise ValueError('Unsupported HEAVY RAIN original audio encoding')
        result.append(payload)
    return result
