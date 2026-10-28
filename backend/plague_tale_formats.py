"""Bounded readers for Innocence's UTF-8 TSC, LZ4 PSC and Wwise 132 packages.

Readers operate on the owner's installation; no archive is expanded on disk.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import struct

from .preparation_errors import PreparationFailure


def invalid(message='Unsupported or damaged A Plague Tale: Innocence asset.'):
    return PreparationFailure('plaguetaleinnocence_invalid_asset', message)


def wwise_hash(value):
    result = 2166136261
    for byte in value.lower().encode('utf-8'):
        result = ((result * 16777619) & 0xffffffff) ^ byte
    return result


def read_file(path, limit):
    with Path(path).open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise invalid('Innocence asset exceeds the supported size bound.')
    return data


def text_table(data):
    if len(data) > 16 * 1024 * 1024:
        raise invalid('Innocence localization exceeds the supported bound.')
    try:
        lines = data.decode('utf-8-sig').splitlines()
    except UnicodeError as exc:
        raise invalid('Innocence localization must be UTF-8.') from exc
    if len(lines) < 3 or lines[:2] != ['FreeLanguage', 'ResetEnumTT'] or lines[-1] != 'EndLoadTT':
        raise invalid('Unrecognized Innocence text table.')
    result, numbers = {}, set()
    for line in lines[2:-1]:
        match = re.fullmatch(r'TT (\d+) "(.*)" ([A-Za-z0-9_]+)', line)
        if not match or match[3].upper() in result or int(match[1]) in numbers:
            raise invalid('Malformed or ambiguous Innocence localization entry.')
        numbers.add(int(match[1]))
        result[match[3].upper()] = match[2]
    return result


def script_bundle(data):
    """PSC has unpacked/compressed u32 lengths followed by one raw LZ4 block."""
    if len(data) < 8:
        raise invalid()
    expected, packed = struct.unpack_from('<II', data)
    if packed != len(data) - 8 or not 0 < expected <= 32 * 1024 * 1024:
        raise invalid('Invalid Innocence script lengths.')
    raw, out, position = data[8:], bytearray(), 0

    def length(initial):
        nonlocal position
        value = initial
        if initial == 15:
            while True:
                if position >= len(raw):
                    raise invalid('Truncated Innocence LZ4 length.')
                extra = raw[position]
                position += 1
                value += extra
                if value > expected:
                    raise invalid('Oversized Innocence LZ4 sequence.')
                if extra != 255:
                    break
        return value

    while position < len(raw):
        token = raw[position]
        position += 1
        size = length(token >> 4)
        if position + size > len(raw) or len(out) + size > expected:
            raise invalid()
        out.extend(raw[position:position + size])
        position += size
        if position == len(raw):
            break
        if position + 2 > len(raw):
            raise invalid()
        distance = int.from_bytes(raw[position:position + 2], 'little')
        position += 2
        size = length(token & 15) + 4
        if not 0 < distance <= len(out) or len(out) + size > expected:
            raise invalid()
        for _ in range(size):
            out.append(out[-distance])
    if len(out) != expected:
        raise invalid('Truncated Innocence script bundle.')
    # Engine scripts contain legacy comments; command identifiers are ASCII.
    return out.decode('utf-8', errors='replace')


@dataclass(frozen=True)
class Entry:
    kind: str
    identity: int
    language: str
    offset: int
    size: int


class Package:
    """AKPK language IDs are local to each file, never global locale numbers."""
    def __init__(self, path):
        self.path = Path(path)
        total = self.path.stat().st_size
        with self.path.open('rb') as stream:
            head = stream.read(28)
            if len(head) != 28 or head[:4] != b'AKPK':
                raise invalid('Unrecognized Innocence audio package.')
            size, version, langs, banks, media, external = struct.unpack_from('<6I', head, 4)
            if version != 1 or size != 20 + langs + banks + media + external or not 20 <= size <= 16 * 1024 * 1024 or size + 8 > total:
                raise invalid('Invalid Innocence audio package header.')
            data = stream.read(size - 20)
        if len(data) != size - 20 or langs < 4:
            raise invalid()
        count = struct.unpack_from('<I', data)[0]
        if count > 256 or 4 + count * 8 > langs:
            raise invalid('Invalid Innocence audio language map.')
        languages = {}
        for i in range(count):
            offset, identity = struct.unpack_from('<II', data, 4 + i * 8)
            if offset < 4 + count * 8 or offset % 2 or offset >= langs or identity in languages:
                raise invalid()
            end = offset
            while end + 2 <= langs and data[end:end + 2] != b'\0\0':
                end += 2
            if end + 2 > langs:
                raise invalid()
            try:
                language = data[offset:end].decode('utf-16-le').casefold()
            except UnicodeError as exc:
                raise invalid() from exc
            if not language or language in languages.values():
                raise invalid('Ambiguous Innocence audio language map.')
            languages[identity] = language
        self.languages, self.entries = languages, {}
        position = langs
        for kind, section, width in [('bank', banks, 20), ('media', media, 20), ('external', external, 24)]:
            if section < 4 or position + section > len(data):
                raise invalid()
            count = struct.unpack_from('<I', data, position)[0]
            if section != 4 + count * width:
                raise invalid('Invalid Innocence audio directory length.')
            for i in range(count):
                start = position + 4 + i * width
                identity, block, length, offset, language = struct.unpack_from('<QIIII' if width == 24 else '<IIIII', data, start)
                offset *= block
                if not block or not length or offset < size + 8 or offset + length > total or language not in languages:
                    raise invalid('Innocence audio entry exceeds package bounds.')
                key = kind, identity, languages[language]
                if key in self.entries:
                    raise invalid('Duplicate Innocence audio entry.')
                self.entries[key] = Entry(kind, identity, languages[language], offset, length)
            position += section
        if position != len(data):
            raise invalid()

    def read(self, entry, limit=32 * 1024 * 1024):
        if self.entries.get((entry.kind, entry.identity, entry.language)) != entry or entry.size > limit:
            raise invalid('Invalid Innocence audio member.')
        with self.path.open('rb') as stream:
            stream.seek(entry.offset)
            data = stream.read(entry.size)
        if len(data) != entry.size:
            raise invalid('Innocence audio member changed during reading.')
        return data


def bank_events(data, language, bank_id):
    """Only one Event -> Play -> localized streamed Vorbis sound is admissible."""
    chunks, position = {}, 0
    while position < len(data):
        if position + 8 > len(data):
            raise invalid()
        name, size = struct.unpack_from('<4sI', data, position)
        position += 8
        if name in chunks or position + size > len(data):
            raise invalid()
        chunks[name] = data[position:position + size]
        position += size
    header = chunks.get(b'BKHD', b'')
    if len(header) != 24 or struct.unpack_from('<III', header) != (132, bank_id, wwise_hash(language)):
        raise invalid('Innocence voice bank version, identity or language changed.')
    body = chunks.get(b'HIRC', b'')
    if len(body) < 4:
        raise invalid()
    count = struct.unpack_from('<I', body)[0]
    if count > 500000:
        raise invalid()
    objects, position = {}, 4
    for _ in range(count):
        if position + 5 > len(body):
            raise invalid()
        kind, size = struct.unpack_from('<BI', body, position)
        position += 5
        if size < 4 or position + size > len(body):
            raise invalid()
        payload = body[position:position + size]
        position += size
        identity = struct.unpack_from('<I', payload)[0]
        if identity in objects:
            raise invalid('Duplicate Innocence sound-bank object.')
        objects[identity] = kind, payload
    if position != len(body):
        raise invalid()
    events, unresolved = {}, set()
    for identity, (kind, event) in objects.items():
        if kind != 4:
            continue
        unresolved.add(identity)
        if len(event) != 9 or event[4] != 1:
            continue
        action_kind, action = objects.get(struct.unpack_from('<I', event, 5)[0], (0, b''))
        if action_kind != 3 or len(action) != 18 or action[4:6] != b'\x03\x04' or struct.unpack_from('<I', action, 14)[0] != bank_id:
            continue
        sound_kind, sound = objects.get(struct.unpack_from('<I', action, 6)[0], (0, b''))
        if sound_kind != 2 or len(sound) < 18 or struct.unpack_from('<I', sound, 4)[0] != 0x40001 or sound[8] != 2 or sound[17] != 1:
            continue
        events[identity] = struct.unpack_from('<I', sound, 9)[0]
        unresolved.remove(identity)
    return events, unresolved
