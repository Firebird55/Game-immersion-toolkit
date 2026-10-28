"""Bounded, read-only Fox Engine dialogue containers (SQAR v1, FPK, SBP).

Format references: Atvaark/GzsTool, Atvaark/FoxEngine.TranslationTool and
kapuragu/StpTool. CityHash arithmetic follows google/cityhash. These readers
never execute game scripts or write into an installation.

MIT notices for the format-reference implementations and CityHash:
Copyright (c) 2014-2015 Atvaark; Copyright (c) 2011 Google, Inc.
Copyright (c) 2021 kapuragu.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations

from dataclasses import dataclass
import bisect
import hashlib
from pathlib import Path
import re
import struct
import threading
import zlib

from .preparation_errors import PreparationFailure

MASK = (1 << 64) - 1
K0, K1, K2 = 0xc3a5c85c97cb3127, 0xb492b66fbe98f273, 0x9ae16a3b2f90404f
K3 = 0xc949d7c7509e6557
XOR = (0x41441043, 0x11C22050, 0xD05608C3, 0x532C7319)
DATA_XOR = (0x65229958BB8ADEDB, 0x8812130208453206, 0x2C02F10C4C344955, 0xF38185834887F823)
MAX_READ = 256 * 1024 * 1024


def invalid(message='Unsupported or incomplete Fox Engine dialogue data.'):
    return PreparationFailure('fox_dialogue_format', message +
        ' Finish launcher downloads, verify game files, and update the toolkit before retrying.')


def _rot(value, count):
    value &= MASK
    return ((value >> count) | (value << (64 - count))) & MASK


def _mix(value):
    value &= MASK
    return value ^ (value >> 47)


def _hash16(a, b, multiplier=0x9ddfea08eb382d69):
    a = ((a & MASK) ^ (b & MASK)) * multiplier & MASK
    a ^= a >> 47
    b = ((b & MASK) ^ a) * multiplier & MASK
    b ^= b >> 47
    return b * multiplier & MASK


def city64(data: bytes):
    """Fox's CityHash64 1.0.3 (not the incompatible current CityHash)."""
    n = len(data)
    get = lambda at: struct.unpack_from('<Q', data, at)[0]
    if n <= 16:
        if n > 8:
            a, b = get(0), get(n - 8)
            return _hash16(a, _rot(b + n, n)) ^ b
        if n >= 4:
            a, b = struct.unpack_from('<I', data)[0], struct.unpack_from('<I', data, n - 4)[0]
            return _hash16(n + (a << 3), b)
        if n:
            y, z = data[0] + (data[n // 2] << 8), n + (data[-1] << 2)
            return _mix((y * K2) ^ (z * K3)) * K2 & MASK
        return K2
    if n <= 32:
        a, b, c, d = get(0) * K1 & MASK, get(8), get(n - 8) * K2 & MASK, get(n - 16) * K0 & MASK
        return _hash16(_rot(a - b, 43) + _rot(c, 30) + d, a + _rot(b ^ K3, 20) - c + n)
    if n <= 64:
        z, a = get(24), (get(0) + (n + get(n - 16)) * K0) & MASK
        b, c = _rot(a + z, 52), _rot(a, 37)
        a = (a + get(8)) & MASK
        c = (c + _rot(a, 7)) & MASK
        a = (a + get(16)) & MASK
        vf, vs = (a + z) & MASK, (b + _rot(a, 31) + c) & MASK
        a, z = (get(16) + get(n - 32)) & MASK, get(n - 8)
        b, c = _rot(a + z, 52), _rot(a, 37)
        a = (a + get(n - 24)) & MASK
        c = (c + _rot(a, 7)) & MASK
        a = (a + get(n - 16)) & MASK
        wf, ws = (a + z) & MASK, (b + _rot(a, 31) + c) & MASK
        r = _mix((vf + ws) * K2 + (wf + vs) * K0)
        return _mix(r * K0 + vs) * K2 & MASK

    def weak(at, a, b):
        w, x, y, z = struct.unpack_from('<4Q', data, at)
        a = (a + w) & MASK
        b = _rot(b + a + z, 21)
        c = a
        a = (a + x + y) & MASK
        return (a + z) & MASK, (b + _rot(a, 44) + c) & MASK

    x, y = get(n - 40), (get(n - 16) + get(n - 56)) & MASK
    z = _hash16(get(n - 48) + n, get(n - 24))
    v, w = weak(n - 64, n, z), weak(n - 32, y + K1, x)
    x = (x * K1 + get(0)) & MASK
    for at in range(0, (n - 1) & ~63, 64):
        x = _rot(x + y + v[0] + get(at + 8), 37) * K1 & MASK
        y = _rot(y + v[1] + get(at + 48), 42) * K1 & MASK
        x ^= w[1]
        y = (y + v[0] + get(at + 40)) & MASK
        z = _rot(z + w[0], 33) * K1 & MASK
        v = weak(at, v[1] * K1, x + w[0])
        w = weak(at + 32, z + w[1], y + get(at + 16))
        x, z = z, x
    return _hash16(_hash16(v[0], w[0]) + _mix(y) * K1 + z, _hash16(v[1], w[1]) + x)


def strcode48(text):
    raw = text.encode('ascii')
    seed = (raw[0] << 16) + len(raw) if raw else 0
    return _hash16(city64(raw + b'\0') - K2, seed) & 0xffffffffffff


def strcode32(text):
    return strcode48(text) & 0xffffffff


def path_hash(path, *, extension=True):
    path = path.replace('\\', '/')
    stem, dot, suffix = path.partition('.') if extension else (path, '', '')
    meta = not stem.startswith('/Assets/') or stem.startswith('/Assets/tpptest')
    text = (stem[8:] if stem.startswith('/Assets/') else stem).lstrip('/').encode('ascii')
    seed = int.from_bytes(text[-8:][::-1].ljust(8, b'\0'), 'little')
    result = _hash16(city64(text) - K2, seed) & 0x3ffffffffffff
    if meta:
        result |= 0x4000000000000
    if dot:
        result |= (path_hash(suffix, extension=False) & 0x1fff) << 51
    return result


EXTENSIONS = {path_hash(ext, extension=False) & 0x1fff: ext
              for ext in ('fpk', 'fpkd', 'sbp', 'subp', 'wem', 'bnk', 'lng', 'lng2', 'rdf', 'spch', 'fsm', 'sani')}


def crypt1(data, name_hash, offset=0):
    """Random-access SQAR v1 obfuscation; callers align to eight bytes."""
    if offset % 8:
        raise invalid('Unaligned Fox archive read.')
    import numpy as np
    result = bytearray(data)
    count = len(data) // 8
    if count:
        words = np.frombuffer(result, dtype='<u8', count=count)
        positions = np.arange(offset, offset + count * 8, 8, dtype=np.uint64)
        indices = ((name_hash & 0xffffffff) + positions // 11) % 4
        words ^= np.asarray(DATA_XOR, dtype=np.uint64)[indices]
    if len(data) % 8:
        key = DATA_XOR[((name_hash & 0xffffffff) + (offset + count * 8) // 11) % 4].to_bytes(8, 'little')
        for index in range(len(data) % 8):
            result[count * 8 + index] ^= key[index]
    return bytes(result)


def crypt2(data, key, offset=0):
    if offset % 4:
        raise invalid('Unaligned Fox payload read.')
    # Advance the affine generator in logarithmic time for random-access reads.
    a, b, acc_a, acc_b, steps = 48828125, 278 * key & 0xffffffff, 1, 0, offset // 4
    while steps:
        if steps & 1:
            acc_a, acc_b = a * acc_a & 0xffffffff, (a * acc_b + b) & 0xffffffff
        a, b = a * a & 0xffffffff, (a * b + b) & 0xffffffff
        steps >>= 1
    state = (acc_a * (key | ((key ^ 25974) << 16)) + acc_b) & 0xffffffff
    result = bytearray(data)
    for at in range(0, len(data) - 3, 4):
        struct.pack_into('<I', result, at, struct.unpack_from('<I', result, at)[0] ^ state)
        state = (278 * key + 48828125 * state) & 0xffffffff
    return bytes(result)


class View:
    def __init__(self, size, reader):
        self.size, self._reader = size, reader

    def read(self, offset=0, size=None):
        size = self.size - offset if size is None else size
        if not isinstance(offset, int) or not isinstance(size, int) or offset < 0 or size < 0 or offset + size > self.size or size > MAX_READ:
            raise invalid('Fox data bounds exceed their container.')
        data = self._reader(offset, size)
        if len(data) != size:
            raise invalid('Truncated Fox container.')
        return data

    def slice(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.size:
            raise invalid('Fox child bounds exceed their container.')
        return View(size, lambda at, count: self.read(offset + at, count))

    @classmethod
    def bytes(cls, data):
        return cls(len(data), lambda at, count: data[at:at + count])


@dataclass(frozen=True)
class QarEntry:
    archive: str
    name_hash: int
    offset: int
    size: int
    stored_size: int

    @property
    def extension(self):
        return EXTENSIONS.get(self.name_hash >> 51, 'unknown')

    def reference(self):
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


def archive_paths(install):
    # Patch archives override chunks. Textures cannot contain dialogue.
    master = Path(install) / 'master'
    paths = [*master.glob('*.dat'), *master.glob('[01]/*.dat')]
    return sorted((p for p in paths if re.fullmatch(r'(?:chunk\d+|data\d+|\d{2})\.dat', p.name) and p.is_file()),
                  key=lambda p: (p.parent != master, p.name == 'data1.dat', p.as_posix()))


def fingerprint(install):
    return hashlib.sha256('|'.join(f'{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
                                  for p in archive_paths(install)).encode()).hexdigest()


class FoxArchive:
    def __init__(self, install):
        self.install = Path(install)
        self.entries = {}
        self._handles = {}
        self._lock = threading.RLock()
        for path in archive_paths(self.install):
            file_size = path.stat().st_size
            with path.open('rb') as stream:
                header = stream.read(32)
                if len(header) != 32 or header[:4] != b'SQAR':
                    raise invalid()
                flags = struct.unpack_from('<I', header, 4)[0] ^ XOR[0]
                count = struct.unpack_from('<I', header, 8)[0] ^ XOR[1]
                version = struct.unpack_from('<I', header, 24)[0] ^ XOR[0]
                if version != 1 or count > 2_000_000 or 32 + count * 8 > file_size:
                    raise invalid()
                table = stream.read(count * 8)
                shift = 12 if flags & 0x800 else 10
                offsets = []
                for i in range(count):
                    low, high = struct.unpack_from('<II', table, i * 8)
                    low ^= XOR[(i + i * 8 // 5) % 4]
                    high ^= XOR[(i + (i * 8 + 4) // 5) % 4]
                    offset = (((high << 32) | low) >> 40) << shift
                    offsets.append(offset)
                # Directory order is hash order. Physical order avoids tens of
                # thousands of random disk seeks on installed HDD libraries.
                for offset in sorted(offsets):
                    if offset < 32 + count * 8 or offset + 32 > file_size:
                        raise invalid()
                    stream.seek(offset)
                    raw = stream.read(32)
                    values = struct.unpack('<8I', raw)
                    name_hash = ((values[1] ^ XOR[0]) << 32) | (values[0] ^ XOR[0])
                    # Native PC TPP SQAR v1 stores compressed length first.
                    stored, size = values[2] ^ XOR[1], values[3] ^ XOR[2]
                    if offset + 32 + stored > file_size:
                        raise invalid()
                    self.entries[name_hash] = QarEntry(path.relative_to(self.install).as_posix(), name_hash, offset + 32, size, stored)

    def close(self):
        for stream in self._handles.values():
            stream.close()
        self._handles.clear()

    def __del__(self):
        self.close()

    def view(self, entry):
        if self.entries.get(entry.name_hash) != entry:
            raise invalid('Fox archive reference changed or is not selected by archive precedence.')
        path = (self.install / entry.archive).resolve()
        if not path.is_relative_to(self.install.resolve()):
            raise invalid('Fox archive path escapes its installation.')

        def outer(at, count):
            aligned = at & ~7
            length = min(entry.stored_size - aligned, (at + count + 7 & ~7) - aligned)
            with self._lock:
                stream = self._handles.get(path)
                if stream is None:
                    stream = self._handles[path] = path.open('rb')
                stream.seek(entry.offset + aligned)
                data = stream.read(length)
            return crypt1(data, entry.name_hash, aligned)[at - aligned:at - aligned + count]

        stored = View(entry.stored_size, outer)
        prefix = stored.read(0, min(16, stored.size))
        magic = struct.unpack_from('<I', prefix)[0] if len(prefix) >= 4 else 0
        header_size = {0xa0f8efe6: 8, 0xe3f8efe6: 16}.get(magic, 0)
        payload = stored.slice(header_size, stored.size - header_size)
        if header_size:
            key = struct.unpack_from('<I', prefix, 4)[0]
            encrypted = payload

            def decrypt(at, count):
                aligned = at & ~3
                length = min(encrypted.size - aligned, (at + count + 3 & ~3) - aligned)
                return crypt2(encrypted.read(aligned, length), key, aligned)[at - aligned:at - aligned + count]

            payload = View(encrypted.size, decrypt)
        if entry.size != entry.stored_size:
            decoder = zlib.decompressobj()
            encoded, cache, position, verified = payload, bytearray(), 0, False

            def inflate(at, count):
                nonlocal position, verified
                end = at + count
                if end > MAX_READ:
                    raise invalid('Fox decompression exceeds its memory bound.')
                while len(cache) < end:
                    part = decoder.unconsumed_tail
                    if not part:
                        length = min(65536, encoded.size - position)
                        if not length:
                            raise invalid('Truncated Fox compressed payload.')
                        part = encoded.read(position, length)
                        position += length
                    cache.extend(decoder.decompress(part, end - len(cache)))
                    if decoder.eof and len(cache) < end:
                        raise invalid('Fox decompressed payload is shorter than its directory size.')
                if end == entry.size and not verified:
                    tail = decoder.unconsumed_tail + encoded.read(position, encoded.size - position)
                    if decoder.decompress(tail, 1) or not decoder.eof or decoder.unused_data:
                        raise invalid('Invalid Fox compressed payload.')
                    verified = True
                return bytes(cache[at:end])

            payload = View(entry.size, inflate)
        return payload


def fpk_entries(view):
    header = view.read(0, 48)
    if header[:6] != b'foxfpk' or header[7:10] not in (b'win', b'ste'):
        raise invalid('Unsupported Fox FPK platform.')
    count = struct.unpack_from('<I', header, 36)[0]
    if count > 100000 or 48 + count * 48 > view.size:
        raise invalid()
    table = view.read(48, count * 48)
    for index in range(count):
        offset, size, name_at, name_size = struct.unpack_from('<Q Q Q Q', table, index * 48)
        if not 0 < name_size <= 4096:
            raise invalid()
        name = view.read(name_at, name_size).decode('utf-8', errors='strict')
        if hashlib.md5(name.encode()).digest() != table[index * 48 + 32:index * 48 + 48]:
            # Encrypted path names do not establish a locale or text identity.
            name = 'unresolved/' + table[index * 48 + 32:index * 48 + 48].hex() + '.' + name.rsplit('.', 1)[-1]
        yield name, offset, view.slice(offset, size)


def sbp_entries(view):
    header = view.read(0, 8)
    if header[:4] != b'SBPL' or not 1 <= header[4] <= 8:
        raise invalid('Unsupported Fox soundbank package.')
    for index in range(header[4]):
        kind, offset, size = struct.unpack('<4sII', view.read(8 + index * 12, 12))
        yield kind.rstrip(b'\0').decode('ascii'), offset, view.slice(offset, size)


def stp_entries(view):
    header = view.read(0, 8)
    if header[:4] != b'STPL' or header[6] not in (0, 1):
        raise invalid('Unsupported Fox streamed sound version.')
    count = struct.unpack_from('<H', header, 4)[0]
    stride = 12 if header[6] == 1 else 8
    table = view.read(8, count * stride)
    for index in range(count):
        identity, at = struct.unpack_from('<II', table, index * stride)
        riff = view.read(at, 12)
        if riff[:4] != b'RIFF' or riff[8:12] != b'WAVE':
            raise invalid('Fox streamed sound is not a Wwise RIFF recording.')
        size = struct.unpack_from('<I', riff, 4)[0] + 8
        yield identity, at, view.slice(at, size)


def riff_chunks(view, *, riff=True, alignment=None):
    alignment = riff if alignment is None else alignment
    pos = 12 if riff else 0
    while pos + 8 <= view.size:
        kind, size = struct.unpack('<4sI', view.read(pos, 8))
        chunk = view.slice(pos + 8, size)
        yield kind, pos + 8, chunk
        pos += 8 + size + (size % 2 if alignment else 0)
    if pos != view.size and not (alignment and pos == view.size + 1):
        raise invalid('Fox RIFF chunk bounds are invalid.')


def bnk_entries(view):
    chunks = {kind: (offset, chunk) for kind, offset, chunk in riff_chunks(view, riff=False)}
    if b'BKHD' not in chunks:
        raise invalid('Fox Wwise bank header missing.')
    if b'DIDX' not in chunks:
        return
    if b'DATA' not in chunks or chunks[b'DIDX'][1].size % 12:
        raise invalid('Fox Wwise bank media index incomplete.')
    data_at, data = chunks[b'DATA']
    for identity, at, size in struct.iter_unpack('<III', chunks[b'DIDX'][1].read()):
        yield identity, data_at + at, data.slice(at, size)


def wem_labels(view):
    """Authored RIFF adtl labels, never arbitrary byte-pattern audio matching."""
    labels = []
    for kind, _at, chunk in riff_chunks(view):
        if kind != b'LIST' or chunk.size < 4 or chunk.read(0, 4) != b'adtl':
            continue
        for subkind, _subat, item in riff_chunks(chunk.slice(4, chunk.size - 4), riff=False, alignment=True):
            if subkind == b'labl' and item.size > 4:
                raw = item.read(4, item.size - 4).rstrip(b'\0')
                try:
                    value = raw.decode('ascii')
                except UnicodeDecodeError:
                    continue
                if re.fullmatch(r'[a-zA-Z0-9_]+', value):
                    labels.append(value)
    return labels


def read_subp(data, encoding=None):
    encodings = {0: 'utf-8', 1: 'latin1', 2: 'latin1', 3: 'latin1', 4: 'latin1', 5: 'latin1', 6: 'utf-8', 7: 'iso8859-5'}
    legacy = data[:2] == b'\x01L' and encoding is not None
    if len(data) < 4 or not legacy and (data[0] not in (0x12, 0x13, 0x1b) or data[1] not in encodings):
        raise invalid('Unsupported Fox subtitle package.')
    encoding = encoding or encodings[data[1]]
    count = struct.unpack_from('<H', data, 2)[0]
    if 4 + count * 8 > len(data):
        raise invalid()
    rows = {}
    for key, offset in struct.iter_unpack('<II', data[4:4 + count * 8]):
        if offset < 4 + count * 8 or offset + 12 > len(data):
            raise invalid()
        magic, timings, priority, size, _size2, character, flags = struct.unpack_from('<HBBHHHH', data, offset)
        start = offset + 12 + timings * 4
        if magic != 0x4c01 or start + size > len(data):
            raise invalid()
        try:
            text = data[start:start + size].rstrip(b'\0').decode(encoding)
        except UnicodeDecodeError:
            raise invalid('Fox subtitle encoding does not match its declared locale.') from None
        pages = [part.replace('\n', ' ').replace('\r', ' ').strip() for part in text.split('$')]
        rows[key] = {'pages': [page for page in pages if page], 'character': character, 'flags': flags,
                     'timings': list(struct.iter_unpack('<HH', data[offset + 12:start]))}
    return rows


def read_lang(data):
    if len(data) < 24 or data[:4] != b'LANG' or data[8:12] not in (b'LE\0\0', b'BE\0\0'):
        raise invalid('Unsupported Fox localization table.')
    order = '<' if data[8:12] == b'LE\0\0' else '>'
    version, count, values, keys = struct.unpack_from(order + 'I4xIII', data, 4)
    if version not in (2, 3) or count > 1_000_000 or keys + count * 8 > len(data):
        raise invalid()
    result = {}
    for key, relative in struct.iter_unpack(order + 'II', data[keys:keys + count * 8]):
        at = values + relative + 2
        end = data.find(b'\0', at, min(len(data), at + 1_000_000))
        if not values <= at < keys or end < 0 or end >= keys:
            raise invalid()
        result[key] = data[at:end].decode('utf-8')
    return result


def demo_bindings(view, *, include_subtitles=False):
    """Read authored DemoData movie/audio relations from binary FOX2 entities.

    Only typed scalar fields in the same entity establish a relation. The local
    string table must reproduce its declared Fox hash; encrypted/unresolved
    strings are not guessed from surrounding bytes or neighboring entities.
    Structure reference: Atvaark/FoxTool (MIT).
    """
    header = view.read(0, 32)
    magic, version, count, strings_at, entity_at = struct.unpack_from('<5I', header)
    if magic != 0x786f62f2 or version != 0x35 or count > 1_000_000 or not 32 <= entity_at <= strings_at <= view.size:
        raise invalid('Unsupported Fox scene entity table.')
    fields = {strcode48(name): (name, kind) for name, kind in
              (('demoId', 11), ('demoStreamPath', 12), ('audioPath', 12))}
    if include_subtitles:
        fields[strcode48('subtitleBinaryFile')] = ('subtitleBinaryFile', 20)
    demo_class = strcode48('DemoData')
    entities = []
    for index in range(count):
        header = view.read(entity_at, 64)
        header_size = struct.unpack_from('<H', header)[0]
        class_hash = struct.unpack_from('<Q', header, 28)[0]
        static, dynamic, properties_at, _static_size, size = struct.unpack_from('<HHIII', header, 36)
        if header_size != 64 or header[6:10] != b'ent\0' or size < 64 or entity_at + size > strings_at:
            raise invalid('Invalid Fox scene entity bounds.')
        if class_hash == demo_class:
            values = {'entity': index}
            at = entity_at + properties_at
            if properties_at < 64 or static + dynamic > 4096:
                raise invalid('Invalid Fox scene property table.')
            for _ in range(static + dynamic):
                if at + 32 > entity_at + size:
                    raise invalid('Fox scene property exceeds its entity.')
                name, kind, container, number, data_at, property_size = struct.unpack('<QBBHHH', view.read(at, 16))
                if property_size < 32 or at + property_size > entity_at + size:
                    raise invalid('Invalid Fox scene property bounds.')
                if name in fields:
                    field, expected_kind = fields[name]
                    if field in values or kind != expected_kind or container != 0 or number != 1 or data_at < 32 or data_at + 8 > property_size:
                        raise invalid('Unsupported Fox scene identity property.')
                    values[field] = struct.unpack('<Q', view.read(at + data_at, 8))[0]
                at += property_size
            entities.append(values)
        entity_at += size
    if not entities:
        return []
    strings, at = {}, strings_at
    for _ in range(1_000_000):
        identity = struct.unpack('<Q', view.read(at, 8))[0]
        at += 8
        if not identity:
            break
        size = struct.unpack('<I', view.read(at, 4))[0]
        at += 4
        if size > 1_000_000:
            raise invalid('Fox scene string exceeds its bound.')
        raw = view.read(at, size)
        at += size
        try:
            value = raw.decode('ascii')
        except UnicodeDecodeError:
            continue
        if strcode48(value) == identity:
            if identity in strings and strings[identity] != value:
                raise invalid('Conflicting Fox scene string identities.')
            strings[identity] = value
    else:
        raise invalid('Fox scene string table exceeds its bound.')
    result = []
    for entity in entities:
        movie = strings.get(entity.get('demoStreamPath'), '')
        audio = strings.get(entity.get('audioPath'), '')
        demo = strings.get(entity.get('demoId'), '')
        if not re.fullmatch(r'/Assets/tpp/demo/demo_stream/[a-z0-9_]+\.fsm', movie):
            continue
        audio_match = re.fullmatch(r'/Assets/tpp/sound/external/demo/([a-z0-9_]+)\.mas', audio)
        result.append({'entity': entity['entity'], 'movie': movie,
                       'audio_name': audio_match[1] if audio_match else '',
                       'demo_name': demo if re.fullmatch(r'[a-z0-9_]+', demo) else '',
                       **({'subtitle': strings.get(entity.get('subtitleBinaryFile'), '')}
                          if include_subtitles else {})})
    return result


def fsm_audio(view):
    """Reassemble original SND packets without reading animation or all audio."""
    header = view.read(0, min(16, view.size))
    pos = struct.unpack_from('<I', header, 4)[0] if header[:4] == b'SYS ' else 0
    segments, boundaries, total = [], [], 0
    for _ in range(1_000_000):
        if pos + 8 > view.size:
            raise invalid('Fox movie has no complete END packet.')
        kind, size = struct.unpack('<4sI', view.read(pos, 8))
        if size < 16 or pos + size > view.size or kind not in (b'SND ', b'DEMO', b'END '):
            raise invalid('Unsupported Fox movie packet.')
        if kind == b'END ':
            break
        if kind == b'SND ':
            skip = 32 if not segments else 16
            if size < skip:
                raise invalid()
            boundaries.append(total)
            segments.append((pos + skip, size - skip))
            total += size - skip
        pos += size
    else:
        raise invalid('Fox movie packet count exceeds its bound.')
    if not segments:
        return None

    def read(at, count):
        result = bytearray()
        while count:
            index = bisect.bisect_right(boundaries, at) - 1
            offset, length = segments[index]
            relative = at - boundaries[index]
            take = min(count, length - relative)
            if take <= 0:
                raise invalid()
            result += view.read(offset + relative, take)
            count -= take
            at += take
        return bytes(result)

    audio = View(total, read)
    riff = audio.read(0, 12)
    if riff[:4] != b'RIFF' or riff[8:12] != b'WAVE':
        raise invalid('Fox movie sound packets do not contain a Wwise recording.')
    size = struct.unpack_from('<I', riff, 4)[0] + 8
    return audio.slice(0, size)
