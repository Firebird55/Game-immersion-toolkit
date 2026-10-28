"""Bounded read-only Death Stranding PC Decima packfiles.

Format evidence: Jayveer/Decima-Explorer (MIT), ArchiveBin and util.h;
ShadelessFox/decima-workshop, DSPackfileProvider. No game data is bundled.
The archive XOR is the documented container format, not account encryption.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
import ctypes
import hashlib
from pathlib import Path
import struct

from .preparation_errors import PreparationFailure

MASK = (1 << 64) - 1
CATEGORIES = ('initial', 'area00', 'beach01', 'remainder', 'area01', 'area02',
              'area04', 'warrior01', 'warrior02', 'warrior03', 'patch')
AUDIO_NAMES = ('english', 'french', 'spanish', 'german', 'italian', 'portuguese',
               'russian', 'polish', 'japanese', 'latamsp', 'latampor', 'greek')


def invalid(message='Unsupported or incomplete Death Stranding original PC data.'):
    return PreparationFailure('deathstranding_format', message +
        ' Verify the original game files in Steam, update the toolkit, and prepare again. Director’s Cut requires a separate reader.')


def _rotate(value, count):
    return ((value << count) | (value >> (64 - count))) & MASK


def _mix(value):
    for factor in (0xff51afd7ed558ccd, 0xc4ceb9fe1a85ec53):
        value = ((value ^ (value >> 33)) * factor) & MASK
    return value ^ (value >> 33)


def murmur(data):
    """MurmurHash3 x64/128, public-domain algorithm, Decima seed 42."""
    a = b = 42
    first, second = 0x87c37b91114253d5, 0x4cf5ad432745937f
    end = len(data) // 16 * 16
    for offset in range(0, end, 16):
        x, y = struct.unpack_from('<QQ', data, offset)
        a ^= (_rotate(x * first & MASK, 31) * second) & MASK
        a = ((_rotate(a, 27) + b) * 5 + 0x52dce729) & MASK
        b ^= (_rotate(y * second & MASK, 33) * first) & MASK
        b = ((_rotate(b, 31) + a) * 5 + 0x38495ab5) & MASK
    tail = data[end:]
    if len(tail) > 8:
        b ^= (_rotate(int.from_bytes(tail[8:], 'little') * second & MASK, 33) * first) & MASK
    if tail:
        a ^= (_rotate(int.from_bytes(tail[:8], 'little') * first & MASK, 31) * second) & MASK
    a ^= len(data); b ^= len(data)
    a = (a + b) & MASK; b = (a + b) & MASK
    a, b = _mix(a), _mix(b)
    a = (a + b) & MASK; b = (a + b) & MASK
    return struct.pack('<QQ', a, b)


def safe_path(value):
    if (not isinstance(value, str) or not value or len(value) > 1024
            or '\\' in value or ':' in value or '\0' in value
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise invalid('Invalid Decima virtual path.')
    return value


def path_hash(value):
    return int.from_bytes(murmur(safe_path(value).encode('utf-8') + b'\0')[:8], 'little')


def pack_name(category, language=None):
    return murmur((category + ('_' + language if language else '')).encode()).hex() + '.bin'


def sources(install):
    root = Path(install).resolve()
    result = []
    for category in CATEGORIES:
        for language in (None, *AUDIO_NAMES) if category != 'patch' else (None,):
            path = root / 'data' / pack_name(category, language)
            if path.is_file():
                if not path.resolve().is_relative_to(root):
                    raise invalid('Death Stranding archive resolves outside the installation.')
                result.append((category, language or '', path))
    return sorted(result, key=lambda row: (row[0] == 'patch', row[0], row[1]))


def _xor_words(words, key, offset):
    salt = struct.pack('<4I', key & 0xffffffff, 0xf41cab62, 0xf376811c, 0xd2a89e3e)
    for i, word in enumerate(struct.unpack('<4I', murmur(salt))):
        words[offset + i] ^= word


def _unmask(data, key):
    words = struct.unpack('<4I', murmur(key))
    salt = (0x6c084a37, 0x7e159d95, 0x3d5af7e8, 0x18aa7d3f)
    digest = hashlib.md5(struct.pack('<4I', *(x ^ y for x, y in zip(words, salt))), usedforsecurity=False).digest()
    # Avoid a Python loop for every byte of a large compressed archive chunk.
    repeated = (digest * ((len(data) + 15) // 16))[:len(data)]
    return (int.from_bytes(data, 'little') ^ int.from_bytes(repeated, 'little')).to_bytes(len(data), 'little')


class Cursor:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, count):
        if not 0 <= count <= len(self.data) - self.pos:
            raise invalid('Truncated Decima resource.')
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result

    def unpack(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))

    def count(self, maximum=1_000_000):
        value, = self.unpack('I')
        if value > maximum:
            raise invalid('Decima resource count exceeds its supported bounds.')
        return value

    def string(self, hashed=True):
        count = self.count(1024 * 1024)
        if count and hashed:
            self.take(4)
        try:
            return self.take(count).decode('utf-8')
        except UnicodeDecodeError as error:
            raise invalid('Invalid Decima UTF-8 text.') from error

    def finish(self):
        if self.pos != len(self.data):
            raise invalid('Decima resource schema changed.')


class Archive:
    def __init__(self, path):
        self.path = Path(path)
        length = self.path.stat().st_size
        with self.path.open('rb') as stream:
            header = stream.read(40)
            if len(header) != 40:
                raise invalid()
            magic, key, *words = struct.unpack('<10I', header)
            if magic not in (0x20304050, 0x21304050):
                raise invalid('Unknown Decima archive version.')
            self.encrypted = magic == 0x21304050
            if self.encrypted:
                _xor_words(words, key, 0); _xor_words(words, key + 1, 4)
            stored_size, self.data_size, files, chunks, maximum = struct.unpack('<QQQII', struct.pack('<8I', *words))
            table_end = 40 + 32 * (files + chunks)
            if (stored_size != length or files > 2_000_000 or chunks > 1_000_000
                    or table_end > length or not 0 < maximum <= 16 * 1024 * 1024):
                raise invalid('Decima archive header is incomplete or changed.')
            self.entries = {}
            for row in struct.iter_unpack('<8I', stream.read(32 * files)):
                row = list(row)
                one, two = row[1], row[7]
                if self.encrypted:
                    _xor_words(row, one, 0); _xor_words(row, two, 4)
                _number, _key, identity, offset, size, _key2 = struct.unpack('<IIQQII', struct.pack('<8I', *row))
                if identity in self.entries or offset + size > self.data_size:
                    raise invalid('Invalid Decima file extent or duplicate identity.')
                self.entries[identity] = (offset, size)
            self.chunks, self.offsets = [], []
            previous_end = 0
            for row in struct.iter_unpack('<8I', stream.read(32 * chunks)):
                row = list(row)
                one, two = row[3], row[7]
                if self.encrypted:
                    _xor_words(row, one, 0); _xor_words(row, two, 4)
                start, size, _key, compressed, packed, _key2 = struct.unpack('<QIIQII', struct.pack('<8I', *row))
                if (start != previous_end or not 0 < size <= maximum
                        or compressed < table_end or not 0 < packed <= maximum + 65536
                        or compressed + packed > length):
                    raise invalid('Invalid Decima compressed chunk bounds.')
                self.offsets.append(start)
                self.chunks.append((start, size, compressed, packed, struct.pack('<QII', start, size, one)))
                previous_end = start + size
            if previous_end != self.data_size:
                raise invalid('Incomplete Decima compressed data.')


class PackSet:
    def __init__(self, install):
        self.install = Path(install).resolve()
        self.entries, self.packs, self.cache = {}, [], OrderedDict()
        self.dll = None
        for category, language, path in sources(self.install):
            archive = Archive(path)
            self.packs.append((category, language, archive))
            for identity, entry in archive.entries.items():
                self.entries[identity] = (archive, entry)
        if not self.packs:
            raise invalid('No original Death Stranding packfiles were found.')

    def has(self, path):
        return path_hash(path) in self.entries

    def _decompress(self, data, size):
        if self.dll is None:
            path = self.install / 'oo2core_7_win64.dll'
            if not path.is_file() or not path.resolve().is_relative_to(self.install) or not hasattr(ctypes, 'WinDLL'):
                raise PreparationFailure('deathstranding_oodle_missing',
                    'Death Stranding requires Windows and its installed oo2core_7_win64.dll. Verify the original game files in Steam and retry.')
            self.dll = ctypes.WinDLL(str(path))
            self.dll.OodleLZ_Decompress.restype = ctypes.c_int64
            self.dll.OodleLZ_Decompress.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int64,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64, ctypes.c_int]
        result = ctypes.create_string_buffer(size)
        if self.dll.OodleLZ_Decompress(data, len(data), result, size, 1, 0, 0, None, 0, None, None, None, 0, 3) != size:
            raise invalid('Death Stranding decompression failed.')
        return result.raw

    def read(self, path, limit=64 * 1024 * 1024, offset=0, length=None):
        archive, (start, size) = self.entries[path_hash(path)]
        length = size - offset if length is None else length
        if (type(offset) is not int or type(length) is not int or offset < 0 or length < 0
                or offset + length > size or length > limit):
            raise invalid('Decima requested resource extent exceeds its bounds.')
        start += offset
        end = start + length
        result = bytearray()
        if not length:
            return b''
        first, last = bisect_right(archive.offsets, start) - 1, bisect_right(archive.offsets, end - 1) - 1
        with archive.path.open('rb') as stream:
            for i in range(first, last + 1):
                key = (archive.path.name, i)
                body = self.cache.pop(key, None)
                begin, count, compressed, packed, crypto = archive.chunks[i]
                if body is None:
                    stream.seek(compressed)
                    body = stream.read(packed)
                    if len(body) != packed:
                        raise invalid('Death Stranding archive changed while reading.')
                    if archive.encrypted:
                        body = _unmask(body, crypto)
                    if packed != count:
                        body = self._decompress(body, count)
                self.cache[key] = body
                while len(self.cache) > 32:
                    self.cache.popitem(last=False)
                result += body[max(0, start - begin):min(count, end - begin)]
        if len(result) != length:
            raise invalid('Incomplete Decima resource read.')
        return bytes(result)

    def manifest(self, with_links=False):
        cursor = Cursor(self.read('prefetch/fullgame.prefetch.core'))
        _kind, size = cursor.unpack('QI')
        if size != len(cursor.data) - 12:
            raise invalid('Death Stranding prefetch schema changed.')
        cursor.take(16)
        count = cursor.count(500_000)
        paths = [safe_path(cursor.string()) for _ in range(count)]
        if cursor.count(500_000) != count or len(set(paths)) != count:
            raise invalid('Invalid Death Stranding prefetch manifest.')
        cursor.take(count * 4)
        links_end = cursor.pos + 4 + cursor.count(5_000_000) * 4
        links = {}
        for path in paths:
            indices = cursor.unpack(str(cursor.count(count)) + 'I')
            if any(index >= count for index in indices):
                raise invalid('Invalid Death Stranding prefetch dependency.')
            if with_links:
                links[path] = [paths[index] for index in indices]
        if cursor.pos != links_end:
            raise invalid('Invalid Death Stranding prefetch dependency count.')
        cursor.finish()
        return (paths, links) if with_links else paths
