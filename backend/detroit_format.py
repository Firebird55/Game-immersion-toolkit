"""Bounded readers for Detroit's version-18 PC BigFile resources."""
from __future__ import annotations

import math
import struct

from .quantic_assets import Cursor, Entry, MAGIC, METADATA_LIMIT


def read_index(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Detroit archive index exceeds its limit')
    data = path.read_bytes()
    if (len(data) < 105 or data[:20] != MAGIC or data[20:24] != b'\0\0\0\x12'
            or data[28:100] != b'ZEP' * 24 or data[100] != 0):
        raise ValueError('Unsupported Detroit archive index')
    count = struct.unpack_from('>I', data, 101)[0]
    if not 1 <= count <= 1_000_000 or len(data) != 105 + count * 28:
        raise ValueError('Invalid Detroit archive table bounds')
    result, seen = [], set()
    for kind, flag, identity, offset, size, auxiliary, package in struct.iter_unpack('>7I', data[105:]):
        if flag != 1 or package > 99 or (kind, identity) in seen:
            raise ValueError('Invalid or duplicate Detroit archive entry')
        seen.add((kind, identity))
        if size:
            result.append(Entry(path, kind, identity, offset, size, auxiliary, package))
    return result


def sections(data):
    if len(data) > METADATA_LIMIT:
        raise ValueError('Detroit metadata exceeds its limit')
    cursor, result = Cursor(data), {}
    while cursor.position < len(data):
        tag, version, size = cursor.read(8), cursor.integer(), cursor.integer()
        if tag in result:
            raise ValueError('Duplicate Detroit metadata section')
        result[tag] = (version, cursor.read(size))
    return result


def component_bytes(entry):
    if entry.size > METADATA_LIMIT:
        raise ValueError('Detroit component exceeds its metadata limit')
    return entry.read()


def component(data, section, version, *, legacy=False):
    parts = sections(data)
    if set(parts) != {b'COM_CONT', b'LOADCONT', section} or parts[b'LOADCONT'] != (2, b''):
        raise ValueError('Unsupported Detroit component sections')
    component_version = parts[b'COM_CONT'][0]
    if component_version not in ((4, 5, 6) if legacy else (6,)) or parts[section][0] != version:
        raise ValueError('Unsupported Detroit component version')
    cursor = Cursor(parts[b'COM_CONT'][1])
    count, dependencies = cursor.integer(), set()
    if count > 100000:
        raise ValueError('Detroit component dependency limit exceeded')
    for _ in range(count):
        kind, identity, external = cursor.integer(), cursor.integer(), cursor.read(1)
        if external not in (b'\0', b'\1'):
            raise ValueError('Unsupported Detroit dependency scope')
        if external == b'\1':
            dependencies.add((kind, identity))
    if component_version == 5 and (count or cursor.read(4) != bytes(4)):
        raise ValueError('Unsupported legacy Detroit dependency extension')
    if cursor.position != len(cursor.data):
        raise ValueError('Trailing Detroit dependency data')
    return dependencies, parts[section][1]


def localization(data, codes=None):
    version = sections(data).get(b'LOCALIZ_', (None,))[0]
    if version not in (5, 6):
        raise ValueError('Unsupported Detroit localization version')
    dependencies, body = component(data, b'LOCALIZ_', version, legacy=True)
    cursor, result, seen = Cursor(body), {}, set()
    if version == 5 and cursor.read(1) != b'\0':
        raise ValueError('Unsupported legacy Detroit text encoding')
    count = cursor.integer()
    if not 1 <= count <= 40:
        raise ValueError('Invalid Detroit localization language count')
    for _ in range(count):
        if cursor.read(1) != b'\1':
            raise ValueError('Unsupported Detroit language encoding')
        code, size = cursor.string(), cursor.integer()
        if size > 100000 or code in seen:
            raise ValueError('Invalid or duplicate Detroit language table')
        seen.add(code)
        texts, flags, bindings, states = {}, {}, {}, {}
        for _ in range(size):
            key, text, flag = cursor.string(), cursor.string(unicode=True), cursor.integer()
            if flag > 65535 or key in texts:
                raise ValueError('Invalid or duplicate Detroit text identity')
            texts[key], flags[key] = text, flag
        size = cursor.integer()
        if size > 100000:
            raise ValueError('Invalid Detroit voice alias count')
        for _ in range(size):
            key, present = cursor.string(), cursor.read(1)
            reference, state = None, 'none'
            if present == b'\1':
                external, kind, identity = cursor.read(1), cursor.integer(), cursor.integer()
                if external not in (b'\0', b'\1'):
                    raise ValueError('Unsupported Detroit voice alias scope')
                state = 'unresolved' if external == b'\1' else 'internal'
                if external == b'\1' and (kind, identity) in dependencies:
                    reference, state = (kind, identity), 'resolved'
            elif present != b'\0':
                raise ValueError('Unsupported Detroit voice alias')
            if key in bindings:
                raise ValueError('Duplicate Detroit voice alias')
            bindings[key], states[key] = reference, state
        if codes is None or code in codes:
            result[code] = {'texts': texts, 'text_flags': flags, 'bindings': bindings, 'binding_states': states}
    if cursor.position != len(body):
        raise ValueError('Unsupported trailing Detroit localization fields')
    return result


def voice_binding(data):
    dependencies, header = component(data, b'HEADER__', 8)
    if header != bytes(8):
        raise ValueError('Unsupported Detroit original performance header')
    identities = [identity for kind, identity in dependencies if kind == 1033]
    if len(identities) != 1:
        raise ValueError('Detroit performance has no unique authored sound data')
    return identities[0]


def sound_header(data, total_size):
    """Read a bounded CSNDDATA prefix without loading its original recording."""
    cursor = Cursor(data)
    if cursor.read(5) != b'QZIP\0' or cursor.read(8) != b'CSNDDATA' or cursor.integer() != 0:
        raise ValueError('Unsupported Detroit sound resource')
    if cursor.integer() != total_size - 21:
        raise ValueError('Invalid Detroit sound section bounds')
    if cursor.string() != '18446744073709551615':
        raise ValueError('Unsupported Detroit sound data identifier')
    duration = struct.unpack('<f', cursor.read(4))[0]
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise ValueError('Invalid Detroit original sound duration')
    name, size = cursor.string(), cursor.integer()
    start = cursor.position
    if size < 44 or not start + size + 16 <= total_size <= start + size + 16 + 800000:
        raise ValueError('Detroit original recording exceeds its resource')
    if cursor.read(4) != b'RIFF' or cursor.integer() != size - 8 or cursor.read(4) != b'WAVE':
        raise ValueError('Unsupported Detroit original recording container')
    return name, duration, start, size


def read_range(entry, offset, size):
    if offset < 0 or size < 0 or size > METADATA_LIMIT or offset + size > entry.size:
        raise ValueError('Detroit resource range exceeds its bounds')
    if entry.offset + entry.size > entry.path.stat().st_size:
        raise ValueError('Detroit resource archive is incomplete')
    with entry.path.open('rb') as stream:
        stream.seek(entry.offset + offset)
        value = stream.read(size)
    if len(value) != size:
        raise ValueError('Detroit resource changed during reading')
    return value


def sound_metadata(entry):
    name, duration, start, size = sound_header(entry.read(4096), entry.size)
    tail = read_range(entry, start + size, entry.size - start - size)
    channels, bits, rate, count = struct.unpack_from('<4I', tail)
    if channels not in (1, 2) or bits != 16 or rate != 48000 or count > 100000 or len(tail) != 16 + count * 8:
        raise ValueError('Unsupported Detroit original sound timing footer')
    times = list(struct.iter_unpack('<2f', tail[16:]))
    # A few shipped subtitle holds extend beyond the recording. Keep those
    # authored values; the adapter must choose the complete performance rather
    # than manufacturing a cut outside its decoded source.
    if any(not all(map(math.isfinite, pair)) or not 0 <= pair[0] < pair[1] <= 86400 for pair in times):
        raise ValueError('Invalid Detroit authored subtitle timing')
    return {'name': name, 'duration': duration, 'start': start, 'size': size, 'channels': channels, 'times': times}
