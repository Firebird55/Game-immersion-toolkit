"""Read-only Quantic Dream PC BigFile tables and bounded metadata blocks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import zlib

MAGIC = b'QUANTICDREAMTABINDEX'
METADATA_LIMIT = 64 * 1024 * 1024


@dataclass(frozen=True)
class Entry:
    index: Path
    kind: int
    identity: int
    offset: int
    size: int
    auxiliary_size: int
    package: int

    @property
    def path(self):
        return self.index.with_suffix('.dat' if self.package == 0 else f'.d{self.package:02}')

    def read(self, limit=None):
        size = self.size if limit is None else min(limit, self.size)
        if self.offset < 0 or self.size < 0 or self.offset + self.size > self.path.stat().st_size:
            raise ValueError('BigFile entry lies outside its installed archive')
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            data = stream.read(size)
        if len(data) != size:
            raise ValueError('BigFile entry is incomplete')
        return data


def read_index(path: Path):
    data = path.read_bytes()
    if len(data) < 104 or data[:20] != MAGIC or data[28:100] != b'ZEP' * 24:
        raise ValueError('Unsupported or incomplete BigFile index')
    version = struct.unpack_from('>I', data, 20)[0]
    if version not in (13, 17):
        raise ValueError('Unsupported BigFile index version')
    count = struct.unpack_from('>I', data, 100)[0]
    if count > 1_000_000 or len(data) != 104 + count * 28:
        raise ValueError('Invalid BigFile entry table bounds')
    rows = []
    for i in range(count):
        kind, flag, identity, offset, size, auxiliary, package = struct.unpack_from('>7I', data, 104 + i * 28)
        if flag != 1 or package > 99:
            raise ValueError('Unsupported BigFile entry flags or package')
        if size:
            rows.append(Entry(path, kind, identity, offset, size, auxiliary, package))
    return rows


def metadata(entry: Entry, *, first_only=False):
    header = entry.read(65536)
    if header.startswith(b'QZIP\0'):
        required = 16 + struct.unpack_from('<I', header, 17)[0] if header[5:13] == b'DC_INFO ' else len(header) - 5
        if required > METADATA_LIMIT:
            raise ValueError('BigFile dependency table exceeds the metadata limit')
        if not first_only and entry.size > METADATA_LIMIT + 5:
            raise ValueError('Uncompressed BigFile metadata exceeds its bounded reader limit')
        return entry.read(required + 5)[5:] if first_only else entry.read()[5:]
    if not header.startswith(b'segs'):
        return header if first_only else entry.read()
    version, count, total, packed = struct.unpack_from('<HHII', header, 4)
    if version != 1 or not 1 <= count <= 1024 or total > METADATA_LIMIT:
        raise ValueError('Unsupported BigFile metadata compression')
    base = (16 + count * 8 + 15) // 16 * 16
    if base + packed > entry.size:
        raise ValueError('Compressed BigFile metadata lies outside its resource')
    table = entry.read(base)
    parts = []
    with entry.path.open('rb') as stream:
        for i in range(count):
            length, original, offset = struct.unpack_from('<HHI', table, 16 + i * 8)
            original = original or 65536
            start = offset & ~1
            if not length or start + length > packed:
                raise ValueError('Invalid compressed BigFile chunk bounds')
            stream.seek(entry.offset + base + start)
            stored = stream.read(length)
            if offset & 1:
                decoder = zlib.decompressobj()
                value = decoder.decompress(stored, original + 1)
                if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                    raise ValueError('Incomplete compressed BigFile metadata chunk')
            else:
                value = stored
            if len(value) != original:
                raise ValueError('BigFile metadata size disagrees with its table')
            parts.append(value)
            if first_only:
                prefix = parts[0]
                required = 16 + struct.unpack_from('<I', prefix, 12)[0] if prefix.startswith(b'DC_INFO ') else len(prefix)
                if required > METADATA_LIMIT:
                    raise ValueError('BigFile dependency table exceeds the metadata limit')
                if sum(map(len, parts)) >= required:
                    break
    result = b''.join(parts)
    if not first_only and len(result) != total:
        raise ValueError('BigFile metadata is incomplete')
    return result


def container_references(data):
    if len(data) < 20 or data[:8] != b'DC_INFO ':
        return []
    version, size, count = struct.unpack_from('<III', data, 8)
    if version != 2 or count > 100000 or 16 + size > len(data):
        raise ValueError('Unsupported data-container dependency table')
    rows, position = [], 20
    for i in range(count):
        if position + 8 > 16 + size:
            raise ValueError('Incomplete data-container dependency')
        kind, identity = struct.unpack_from('<II', data, position)
        position += 8
        language = None
        if kind == 0xffb:
            if position >= 16 + size:
                raise ValueError('Missing authored dialogue language')
            language = data[position]
            position += 1
        rows.append((kind, identity, language))
    if position != 16 + size:
        raise ValueError('Unsupported data-container dependency encoding')
    return rows


def components(data):
    references = container_references(data)
    if not references:
        return []
    position = 16 + struct.unpack_from('<I', data, 12)[0]
    if data[position:position + 8] != b'DC_DATA ' or struct.unpack_from('<I', data, position + 8)[0] != 20:
        raise ValueError('Unsupported BigFile component stream')
    position += 16
    rows = []
    for kind, identity, language in references:
        if position + 18 > len(data):
            raise ValueError('Incomplete BigFile component header')
        size = struct.unpack_from('<I', data, position)[0]
        localized = kind in (0xffb, 0xffc)
        extra = int(localized)
        end = position + 14 + extra + size
        if size < 4 or end > len(data):
            raise ValueError('BigFile component lies outside its metadata')
        actual_language = struct.unpack_from('<H', data, position + 13)[0] if localized else None
        if language is not None and actual_language != language:
            raise ValueError('BigFile dialogue language disagrees with its dependency table')
        rows.append((kind, identity, actual_language, data[position + 18 + extra:end]))
        position = end
    if position != len(data):
        raise ValueError('Unsupported trailing BigFile component data')
    return rows


class Cursor:
    def __init__(self, data):
        self.data, self.position = data, 0

    def read(self, size):
        if size < 0 or self.position + size > len(self.data):
            raise ValueError('Incomplete Quantic localization table')
        value = self.data[self.position:self.position + size]
        self.position += size
        return value

    def integer(self):
        return struct.unpack('<I', self.read(4))[0]

    def string(self, *, unicode=False):
        size = self.integer()
        if size > (8 * 1024 * 1024 if unicode else 1024):
            raise ValueError('Quantic localization string exceeds its format bounds')
        return self.read(size).decode('utf-16-le' if unicode else 'ascii').rstrip('\0')


def localization(data):
    cursor = Cursor(data)
    if cursor.read(8) != b'COM_CONT' or cursor.integer() != 4:
        raise ValueError('Localization has no authored component container')
    count = cursor.integer()
    if count > 100000:
        raise ValueError('Invalid localization dependency count')
    dependencies = []
    for _ in range(count):
        kind, identity = cursor.integer(), cursor.integer()
        flag = cursor.read(1)[0]
        if flag != 1:
            raise ValueError('Unsupported localization dependency encoding')
        dependencies.append((kind, identity))
    if cursor.read(8) != b'LOADCONT' or cursor.integer() != 2 or cursor.read(8) != b'LOCALIZ_' or cursor.integer() != 5:
        raise ValueError('Unsupported Quantic localization component')
    if cursor.read(1) != b'\0':
        raise ValueError('Unsupported localization text encoding')
    languages = cursor.integer()
    if not 1 <= languages <= 40:
        raise ValueError('Invalid Quantic localization language count')
    result = {}
    for _ in range(languages):
        present = cursor.read(1)
        if present not in (b'\0', b'\1'):
            raise ValueError('Invalid localization language identifier')
        code = cursor.string() if present == b'\1' else ''
        count = cursor.integer()
        if count > 100000:
            raise ValueError('Invalid localized text count')
        texts, text_flags = {}, {}
        for _ in range(count):
            key, text = cursor.string(), cursor.string(unicode=True)
            if key in texts and texts[key] != text:
                raise ValueError('Conflicting official localization identities')
            texts[key] = text
            text_flag = cursor.integer()
            if text_flag > 65535:
                raise ValueError(f'Unsupported official localization text flags: {text_flag}')
            if key in text_flags and text_flags[key] != text_flag:
                raise ValueError('Conflicting official localization text flags')
            text_flags[key] = text_flag
        bindings, binding_states = {}, {}
        pairs = cursor.integer()
        if pairs > 100000:
            raise ValueError('Invalid localization alias count')
        for _ in range(pairs):
            key = cursor.string()
            exists = cursor.read(1)
            reference = None
            state = 'none'
            if exists == b'\1':
                external = cursor.read(1)
                if external not in (b'\0', b'\1'):
                    raise ValueError('Unsupported authored localization pointer scope')
                kind, identity = cursor.integer(), cursor.integer()
                state = 'unresolved' if external == b'\1' else 'internal'
                if external == b'\1' and (kind, identity) in dependencies:
                    reference = (kind, identity)
                    state = 'resolved'
            elif exists != b'\0':
                raise ValueError('Unsupported authored localization pointer')
            if key in bindings and bindings[key] != reference:
                raise ValueError('Ambiguous original speech binding')
            if key in binding_states and binding_states[key] != state:
                raise ValueError('Ambiguous original speech pointer state')
            bindings[key] = reference
            binding_states[key] = state
        if code in result:
            raise ValueError('Duplicate official localization language')
        result[code] = {'texts': texts, 'bindings': bindings, 'text_flags': text_flags,
                        'binding_states': binding_states}
    if cursor.position != len(data):
        raise ValueError('Unsupported trailing localization fields')
    return result


def partition(data):
    """Return the authored partition offset reference and subtitle time pairs."""
    if len(data) < 16 or data[:8] != b'PARTITIO' or struct.unpack_from('<I', data, 8)[0] != 2:
        raise ValueError('Unsupported original dialogue partition')
    footer = 16 + struct.unpack_from('<I', data, 12)[0]
    if data[footer:footer + 8] != b'PARTOFFS':
        raise ValueError('Original dialogue has no authored offsets')
    version, length, kind, identity, mode, _ = struct.unpack_from('<6I', data, footer + 8)
    if (version, length, kind, mode) != (2, 16, 4092, 2):
        raise ValueError('Unsupported original dialogue offset reference')
    header = data.rfind(b'HEADER__', footer + 32)
    if header < 0 or header + 28 > len(data):
        raise ValueError('Original dialogue subtitle timings are missing')
    version, length, flag, mode, count = struct.unpack_from('<5I', data, header + 8)
    if (version, flag, mode) != (6, 1, 2) or count > 100000 or length != 12 + count * 8 or header + 16 + length != len(data):
        raise ValueError('Unsupported original dialogue subtitle timing table')
    times = [struct.unpack_from('<2f', data, header + 28 + i * 8) for i in range(count)]
    import math
    if any(not all(map(math.isfinite, pair)) or not 0 <= pair[0] < pair[1] <= 86400 for pair in times):
        raise ValueError('Invalid authored subtitle times')
    return identity, times, footer


def partition_blocks(data, offsets):
    identity, times, footer = partition(data)
    if offsets[:8] != b'TBOFFSET' or len(offsets) < 20:
        raise ValueError('Missing original dialogue chunk table')
    version, count = struct.unpack_from('<2I', offsets, 8)
    if version != 4 or not 1 <= count <= 86400 or len(offsets) != 20 + count * 8:
        raise ValueError('Unsupported original dialogue chunk table')
    starts = struct.unpack_from(f'<{count}I', offsets, 16)
    sizes = struct.unpack_from(f'<{count}I', offsets, 20 + count * 4)
    result = []
    for i, (start, size) in enumerate(zip(starts, sizes)):
        start += 2048
        if size < 32 or start + size > footer or (i and start < 2048 + starts[i-1] + sizes[i-1]):
            raise ValueError('Original dialogue chunk exceeds its authored bounds')
        frame, begin, end, unknown, name_length, block_size = struct.unpack_from('<I2f3I', data, start)
        if frame != i or abs(begin-i) > .001 or (abs(end-i-1) > .001 if i < count-1 else not i < end <= i+1.001) or unknown or name_length not in (4, 8):
            raise ValueError(f'Unsupported original dialogue audio block {i}: {(frame, begin, end, unknown, name_length)}')
        if name_length == 4:
            if data[start+20:start+32] != b'000000000000':
                raise ValueError('Invalid single-stream dialogue header')
            block_size = size - 16
        if not 16 <= block_size <= size - 16 or data[start+24:start+32] != b'00000000':
            raise ValueError('Invalid original dialogue audio block bounds')
        payload = data[start+32:start+16+block_size]
        if not payload or payload[:4] == b'NULL' and len(payload) == 8:
            payload = None
        elif len(payload) < 4 or payload[0] != 255 or payload[1] & 0xe0 != 0xe0:
            raise ValueError('Unsupported original dialogue audio encoding')
        result.append(payload)
    return result
