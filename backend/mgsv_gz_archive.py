"""Bounded Ground Zeroes GZS archives and original SAB subtitle relations.

Format references: Atvaark/GzsTool v0.2, kapuragu/StpTool and kapuragu/RdfTool (MIT; notices in
fox_dialogue). These differ from TPP SQAR in hashing and both cipher layers.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import struct
import threading

from .fox_dialogue import View, invalid, strcode32, strcode48

EXTENSIONS = {2: 'json', 5: 'fpk', 6: 'fpkd', 32: 'fox', 35: 'fstb', 36: 'lua',
              52: 'ftex', 58: 'pftxs', 70: 'lng', 86: 'fsm', 90: 'sani',
              101: 'sbp', 102: 'mas', 103: 'rdf', 104: 'wem'}


def path_hash(path):
    stem, dot, suffix = path.rpartition('.')
    kind = next((key for key, value in EXTENSIONS.items() if value == suffix), 0)
    return strcode48(stem if kind and dot else path) | kind << 52


def archive_paths(install):
    # data_00 is the opening ASF movie, data_01 textures, data_02 game assets.
    return [p for name in ('data_01.g0s', 'data_02.g0s') if (p := Path(install) / name).is_file()]


def fingerprint(install):
    return hashlib.sha256('|'.join(f'{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
                                  for p in archive_paths(install)).encode()).hexdigest()


def crypt_outer(data, absolute):
    import numpy as np
    positions = np.arange(absolute, absolute + len(data), dtype=np.uint64)
    key = ((positions * 6339797) >> 16).astype(np.uint8)
    return (np.frombuffer(data, dtype=np.uint8) ^ key).tobytes()


def crypt_inner(data, key, offset=0):
    if offset % 4:
        raise invalid('Unaligned Ground Zeroes payload read.')
    a, b, aa, bb, steps = 69069, 207207 * key & 0xffffffff, 1, 0, offset // 4
    while steps:
        if steps & 1:
            aa, bb = a * aa & 0xffffffff, (a * bb + b) & 0xffffffff
        a, b = a * a & 0xffffffff, (a * b + b) & 0xffffffff
        steps >>= 1
    state = (aa * (key | ((key ^ 0xffffcdec) << 16)) + bb) & 0xffffffff
    result = bytearray(data)
    for at in range(0, len(data) - 3, 4):
        struct.pack_into('<I', result, at, struct.unpack_from('<I', result, at)[0] ^ state)
        state = (69069 * state + 207207 * key) & 0xffffffff
    return bytes(result)


@dataclass(frozen=True)
class GzEntry:
    archive: str
    name_hash: int
    offset: int
    size: int

    @property
    def extension(self):
        return EXTENSIONS.get(self.name_hash >> 52, 'unknown')

    def reference(self):
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


class GzArchive:
    def __init__(self, install):
        self.install, self.entries, self._handles = Path(install), {}, {}
        self._lock = threading.RLock()
        for path in archive_paths(install):
            size = path.stat().st_size
            with path.open('rb') as stream:
                if size < 20:
                    raise invalid('Truncated Ground Zeroes archive.')
                stream.seek(-20, 2)
                count, magic, offset, reserved, footer = struct.unpack('<5I', stream.read(20))
                offset *= 16
                if magic != 0x71610000 or reserved or footer != 20 or count > 1000000 or offset + count * 16 > size - 20:
                    raise invalid('Invalid Ground Zeroes archive directory.')
                stream.seek(offset)
                table = stream.read(count * 16)
                for identity, at, length in struct.iter_unpack('<QII', table):
                    at *= 16
                    if at + length > offset:
                        raise invalid('Ground Zeroes entry exceeds its data area.')
                    self.entries[identity] = GzEntry(path.name, identity, at, length)

    def close(self):
        for stream in self._handles.values():
            stream.close()
        self._handles.clear()

    def __del__(self):
        self.close()

    def view(self, entry):
        if self.entries.get(entry.name_hash) != entry:
            raise invalid('Ground Zeroes original archive reference changed.')
        path = (self.install / entry.archive).resolve()
        if not path.is_relative_to(self.install.resolve()):
            raise invalid('Ground Zeroes path escapes its installation.')

        def outer(at, count):
            with self._lock:
                stream = self._handles.get(path)
                if stream is None:
                    stream = self._handles[path] = path.open('rb')
                stream.seek(entry.offset + at)
                data = stream.read(count)
            return crypt_outer(data, entry.offset + at)

        view = View(entry.size, outer)
        prefix = view.read(0, min(8, view.size))
        if prefix[:4] != b'\xe6\xef\xf8\xa0':
            return view
        if len(prefix) < 8:
            raise invalid('Truncated Ground Zeroes encrypted payload header.')
        key = struct.unpack_from('<I', prefix, 4)[0]
        encrypted = view.slice(8, view.size - 8)

        def inner(at, count):
            aligned = at & ~3
            length = min(encrypted.size - aligned, (at + count + 3 & ~3) - aligned)
            return crypt_inner(encrypted.read(aligned, length), key, aligned)[at - aligned:at - aligned + count]

        return View(encrypted.size, inner)


def sab_labels(view):
    header = view.read(0, 8)
    if header[:4] != b'SAL3':
        raise invalid('Unsupported Ground Zeroes sound animation package.')
    count = struct.unpack_from('<I', header, 4)[0]
    if count > 100000 or 8 + count * 16 > view.size:
        raise invalid('Invalid Ground Zeroes sound animation table.')
    entries = list(struct.iter_unpack('<QII', view.read(8, count * 16)))
    bounds = sorted({offset for _key, offset, _zero in entries} | {view.size})
    for identity, offset, zero in entries:
        if zero or not 8 + count * 16 <= offset < view.size:
            raise invalid('Invalid Ground Zeroes subtitle relation bounds.')
        end = bounds[bounds.index(offset) + 1]
        pair = view.slice(offset, end - offset)
        parts = struct.unpack('<I', pair.read(0, 4))[0]
        if parts > 8:
            raise invalid('Invalid Ground Zeroes subtitle relation count.')
        for index in range(parts):
            kind, relative = struct.unpack('<4sI', pair.read(4 + index * 8, 8))
            if kind.rstrip(b'\0') != b'st':
                continue
            raw = pair.read(relative, pair.size - relative)
            if len(raw) < 19:
                raise invalid('Truncated Ground Zeroes subtitle label.')
            end = raw.find(b'\0', 18, 1042)
            if end < 0:
                raise invalid('Ground Zeroes subtitle label is not terminated.')
            label = raw[18:end].decode('ascii')
            yield identity, label


def read_lang(data):
    """GZ LANG v2 has explicit key strings, unlike the TPP hash-only table."""
    if len(data) < 32 or data[:12] != b'LANG\x02\0\0\0LE\0\0':
        raise invalid('Unsupported Ground Zeroes localization table.')
    count, indices, keys, values = struct.unpack_from('<4I', data, 12)
    if count > 1000000 or not 32 <= indices <= indices + count * 8 <= keys <= values <= len(data):
        raise invalid('Invalid Ground Zeroes localization bounds.')
    result = {}
    for key_at, value_at in struct.iter_unpack('<II', data[indices:indices + count * 8]):
        key_at += keys
        value_at += values + 2
        key_end = data.find(b'\0', key_at, values)
        value_end = data.find(b'\0', value_at, min(len(data), value_at + 1000000))
        if not keys <= key_at < key_end < values or not values <= value_at <= value_end < len(data):
            raise invalid('Invalid Ground Zeroes localization string.')
        key = data[key_at:key_end].decode('ascii')
        text = data[value_at:value_end].decode('utf-8')
        result.setdefault(key, set()).add(text)
    return result


def subtitle_events(view):
    """Read native GZ subtitle SANI event tables, not arbitrary matching hashes.

    A supported event has the native subtitle node signature and three typed
    properties. Its msgId is index 1 in its seven-element string-hash pool.
    Unknown events are ignored; malformed known subtitle nodes fail closed.
    Frames establish authored order only, never inferred audio clip lengths.
    """
    pos, events, ended = 0, [], False
    fields = ((strcode32('msgId'), 1, 11), (strcode32('enableTextColorChange'), 0, 10),
              (strcode32('key'), 0, 11))
    for _ in range(100000):
        kind, size = struct.unpack('<4sI', view.read(pos, 8))
        if size < 16 or pos + size > view.size or kind not in (b'DEMO', b'END '):
            raise invalid('Invalid Ground Zeroes subtitle event packet.')
        if kind == b'END ':
            ended = True
            break
        packet = view.slice(pos, size)
        if struct.unpack('<I', packet.read(16, 4))[0] == 2:
            base = 28
            group, count = struct.unpack('<II', packet.read(base, 8))
            if group != strcode32('Normal') or count > 100000 or base + 8 + count * 4 > packet.size:
                raise invalid('Unsupported Ground Zeroes subtitle event group.')
            offsets = list(struct.unpack('<' + 'I' * count, packet.read(base + 8, count * 4)))
            if offsets != sorted(set(offsets)) or offsets and offsets[0] < 8 + count * 4:
                raise invalid('Invalid Ground Zeroes subtitle event offsets.')
            for index, offset in enumerate(offsets):
                end = base + offsets[index + 1] if index + 1 < count else packet.size
                event = packet.slice(base + offset, end - base - offset)
                signature = event.read(0, min(4, event.size))
                if signature != b'\x11\xc0\x79\x23':
                    continue
                raw = event.read()
                if (len(raw) != 112 or raw[4:8] != b'\x01\x0a\0\x07'
                        or tuple(struct.iter_unpack('<IHH', raw[20:44])) != fields
                        or raw[44:56] != struct.pack('<6H', 3, 3, 2, 1, 6, 0)
                        or struct.unpack_from('<Q', raw, 56)[0] != strcode48('')):
                    raise invalid('Unsupported Ground Zeroes typed subtitle event.')
                frame = struct.unpack_from('<I', raw, 8)[0]
                identity = struct.unpack_from('<Q', raw, 64)[0]
                if identity >> 48:
                    raise invalid('Invalid Ground Zeroes subtitle event identity.')
                events.append({'frame': frame, 'subtitle_id': identity & 0xffffffff})
        pos += size
    if not ended:
        raise invalid('Ground Zeroes subtitle event stream has no END packet.')
    return sorted(events, key=lambda event: event['frame'])


def ui_boot_bindings(view):
    """Typed UI boot and language-resource references for narrative panels."""
    header = view.read(0, 32)
    magic, version, count, strings_at, entity_at = struct.unpack_from('<5I', header)
    if magic != 0x786f62f2 or version != 0x35 or count > 1000000 or not 32 <= entity_at <= strings_at <= view.size:
        raise invalid('Unsupported Ground Zeroes UI entity table.')
    classes = {strcode48('LangData'): {'langFile': 20},
               strcode48('TppUICommonBootData'): {'uiFile': 20, 'pauseFlag': 4}}
    entities = []
    for _ in range(count):
        header = view.read(entity_at, 64)
        class_hash = struct.unpack_from('<Q', header, 28)[0]
        static, dynamic, offset, _static_size, size = struct.unpack_from('<HHIII', header, 36)
        if struct.unpack_from('<H', header)[0] != 64 or header[6:10] != b'ent\0' or size < 64 or entity_at + size > strings_at:
            raise invalid('Invalid Ground Zeroes UI entity bounds.')
        if class_hash in classes:
            fields = {strcode48(name): (name, kind) for name, kind in classes[class_hash].items()}
            if offset < 64 or static + dynamic > 4096:
                raise invalid('Invalid Ground Zeroes UI property table.')
            at, values = entity_at + offset, {}
            for _ in range(static + dynamic):
                if at + 32 > entity_at + size:
                    raise invalid('Invalid Ground Zeroes UI property bounds.')
                key, kind, container, number, data_at, length = struct.unpack('<QBBHHH', view.read(at, 16))
                if length < 32 or at + length > entity_at + size:
                    raise invalid('Invalid Ground Zeroes UI property length.')
                if key in fields:
                    name, expected = fields[key]
                    if name in values or kind != expected or container or number != 1 or data_at < 32 or data_at + 8 > length:
                        raise invalid('Unsupported Ground Zeroes UI reference.')
                    values[name] = struct.unpack('<Q', view.read(at + data_at, 8))[0]
                at += length
            entities.append(values)
        entity_at += size
    if not entities:
        return []
    strings, at = {}, strings_at
    for _ in range(1000000):
        key = struct.unpack('<Q', view.read(at, 8))[0]
        at += 8
        if not key:
            break
        size = struct.unpack('<I', view.read(at, 4))[0]
        at += 4
        if size > 1000000:
            raise invalid('Ground Zeroes UI string exceeds its bound.')
        raw = view.read(at, size)
        at += size
        try:
            value = raw.decode('ascii')
        except UnicodeDecodeError:
            continue
        if strcode48(value) == key:
            if key in strings and strings[key] != value:
                raise invalid('Conflicting Ground Zeroes UI string identity.')
            strings[key] = value
    else:
        raise invalid('Ground Zeroes UI string table exceeds its bound.')
    return [{name: value if name == 'pauseFlag' else strings.get(value, '')
             for name, value in entity.items()} for entity in entities]


def quiz_items(data):
    """Inspect the authored quiz item declaration without executing game Lua.

    Each item separately names its numeric answer and two radio events. This
    establishes that choice_N_M is a selectable UI label, not the radio prompt.
    """
    text = data.decode('utf-8')
    text = re.sub(r'--\[\[.*?\]\]', '', text, flags=re.S)
    text = re.sub(r'--[^\n]*', '', text)
    result = set()
    for block in re.findall(r'\bSetupMgsQuizItemTable\s*\(([^()]*)\)', text):
        for item in re.findall(r'\{([^{}]*)\}', block):
            match = re.fullmatch(r'\s*quizId\s*=\s*(\d+)\s*,\s*answerId\s*=\s*([1-5])\s*,\s*'
                r'questionRadioId\s*=\s*"([a-z0-9_]+)"\s*,\s*correctRadioId\s*=\s*"([a-z0-9_]+)"\s*', item)
            if match and 1 <= int(match[1]) <= 20:
                result.add(int(match[1]))
    return result


def fnv32(text):
    value = 2166136261
    for byte in text.encode('ascii'):
        value = ((value * 16777619) ^ byte) & 0xffffffff
    return value


def radio_conditions(view):
    """Authored RDF v1 radio conditions (kapuragu/RdfTool format)."""
    version, count, end = struct.unpack('<HHI', view.read(0, 8))
    if version != 1 or not 8 + count * 8 <= end <= view.size:
        raise invalid('Invalid Ground Zeroes radio data table.')
    table = list(struct.iter_unpack('<II', view.read(8, count * 8)))
    result = set()
    for _identity, offset in table:
        if offset < 8 + count * 8 or offset + 16 > end:
            raise invalid('Invalid Ground Zeroes radio group bounds.')
        group = view.read(offset, 16)
        parts = group[11]
        if offset + 16 + parts * 16 > end:
            raise invalid('Invalid Ground Zeroes radio part bounds.')
        for index in range(parts):
            _event, _character, condition = struct.unpack('<III', view.read(offset + 16 + index * 16, 12))
            result.add(condition)
    return result, count
