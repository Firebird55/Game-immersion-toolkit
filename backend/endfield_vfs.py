"""Bounded, compiler-free reading of selected Endfield VFS voice resources.

Only numerical format metadata comes from the private verified tool cache.
Authored voice IDs remain separate from package order and localization text.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import zlib

from Crypto.Cipher import ChaCha20
import numpy as np

MAX_INDEX = 32 * 1024 * 1024
MAX_VOICE = 64 * 1024 * 1024
MAX_ENTRIES = 2_000_000
MAX_PACKAGE = 128 * 1024**3
LOCALE_BLOCKS = {'chinese': 101, 'english': 102, 'japanese': 103, 'korean': 104}


class FormatError(ValueError):
    """An installed resource does not satisfy the evidenced format."""


def _require(condition, message='Unsupported Endfield voice resource structure'):
    if not condition:
        raise FormatError(message)


@dataclass(frozen=True)
class Parameters:
    key: bytes
    directories: dict[int, str]
    multiplier: int
    xor_constant: int
    protocol: int = 3

    def __post_init__(self):
        import re
        _require(len(self.key) == 32 and self.protocol == 3)
        _require(set(self.directories) == {1, 21, 101, 102, 103, 104})
        _require(all(re.fullmatch('[0-9A-F]{8}', value) for value in self.directories.values()))
        _require(len(set(self.directories.values())) == len(self.directories))
        _require(0 < self.multiplier < 2**32 and 0 <= self.xor_constant < 2**32)


def chacha(data, key, nonce, offset=0):
    cipher = ChaCha20.new(key=key, nonce=nonce)
    cipher.seek(64 + offset)
    return cipher.decrypt(data)


def xor_data(data: bytes, seed: int, parameters: Parameters, offset=0) -> bytes:
    """Read an arbitrary aligned or unaligned range of the package stream."""
    _require(offset >= 0)
    if not data:
        return data
    alignment = offset % 4
    count = (alignment + len(data) + 3) // 4
    indices = np.arange(count, dtype=np.uint32)
    indices += np.uint32((seed + offset // 4) & 0xffffffff)
    keys = ((indices & 255) ^ np.uint32(parameters.xor_constant)) * np.uint32(parameters.multiplier)
    for shift in (8, 16, 24):
        keys = (keys ^ ((indices >> shift) & 255)) * np.uint32(parameters.multiplier)
    mask = keys.astype('<u4', copy=False).view(np.uint8)[alignment:alignment + len(data)]
    return (np.frombuffer(data, dtype=np.uint8) ^ mask).tobytes()


class Cursor:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, size):
        _require(0 <= size <= len(self.data) - self.position, 'Truncated Endfield voice index')
        result = self.data[self.position:self.position + size]
        self.position += size
        return result

    def number(self, format):
        return struct.unpack('<' + format, self.take(struct.calcsize('<' + format)))[0]

    def text(self):
        return self.take(self.number('H')).decode('utf-8')

    def count(self):
        value = self.number('i')
        _require(0 <= value <= MAX_ENTRIES)
        return value


@dataclass(frozen=True)
class File:
    name: str
    name_hash: int
    chunk: str
    offset: int
    size: int
    nonce: bytes | None


def parse_index(data: bytes, parameters: Parameters, block: int) -> tuple[File, ...]:
    _require(16 <= len(data) <= MAX_INDEX)
    plain = chacha(data[12:], parameters.key, data[:12])
    _require(zlib.crc32(plain[:-4]) == struct.unpack('<I', plain[-4:])[0], 'Endfield voice index checksum mismatch')
    cursor = Cursor(plain[:-4])
    version = cursor.number('i')
    schema = version if version < 11 else 3
    if version < 11:
        version = cursor.number('i')
    _require(schema in {3, 4, 5} and version >= 0)
    cursor.text()
    cursor.number('q')
    cursor.count()
    _require(cursor.number('q') >= 0)
    _require(cursor.number('B') == block)
    result, total_files = [], 0
    tag_size = {3: 0, 4: 4, 5: 8}[schema]
    for _ in range(cursor.count()):
        chunk = cursor.take(16).hex().upper() + '.chk'
        cursor.take(16)
        chunk_size = cursor.number('q')
        _require(0 <= chunk_size <= MAX_PACKAGE and cursor.number('B') == block)
        cursor.take(tag_size)
        count = cursor.count()
        total_files += count
        _require(total_files <= MAX_ENTRIES)
        for _ in range(count):
            name, name_hash = cursor.text(), cursor.number('q')
            cursor.take(32)
            offset, size = cursor.number('q'), cursor.number('q')
            _require(0 <= offset <= chunk_size and 0 <= size <= chunk_size - offset)
            _require(cursor.number('B') == block)
            encrypted = cursor.number('B')
            _require(encrypted in (0, 1))
            nonce = struct.pack('<iq', parameters.protocol, cursor.number('q')) if encrypted else None
            cursor.take(tag_size)
            if name.lower().endswith('.pck'):
                result.append(File(name, name_hash, chunk, offset, size, nonce))
    _require(len(cursor.data) - cursor.position == (10 if schema == 5 else 0))
    return tuple(result)


class PackageSource:
    """A bounded view of one file in a chunk; packages are never inflated whole."""
    def __init__(self, stream, file: File, parameters: Parameters):
        self.stream, self.file, self.parameters = stream, file, parameters
        self.size = file.size
        stream.seek(0, 2)
        _require(file.size <= MAX_PACKAGE and file.offset + file.size <= stream.tell(), 'Endfield voice chunk is truncated')

    def read(self, offset, size):
        _require(0 <= offset <= self.size and 0 <= size <= min(MAX_VOICE, self.size - offset))
        self.stream.seek(self.file.offset + offset)
        data = self.stream.read(size)
        _require(len(data) == size, 'Endfield voice chunk changed during reading')
        return chacha(data, self.parameters.key, self.file.nonce, offset) if self.file.nonce else data


@dataclass(frozen=True)
class Media:
    identity: int
    offset: int
    size: int
    bank_seed: int | None = None
    bank_offset: int = 0


class Package:
    def __init__(self, source, parameters: Parameters):
        self.source, self.parameters = source, parameters
        initial = source.read(0, 12)
        _require(initial[:4] in (b'AKPK', b':)xD'))
        header_size = struct.unpack_from('<I', initial, 4)[0]
        _require(16 <= header_size <= MAX_INDEX and header_size + 8 <= source.size)
        body = source.read(12, header_size - 4)
        if initial[:4] == b':)xD':
            body = xor_data(body, header_size, parameters)
        else:
            _require(struct.unpack_from('<I', initial, 8)[0] == 1)
        cursor = Cursor(body)
        languages, banks, sounds = (cursor.number('I') for _ in range(3))
        externals = cursor.number('I') if languages + banks + sounds + 16 < header_size else 0
        sizes = (languages, banks, sounds, externals)
        _require(sum(sizes) == len(body) - cursor.position)
        # Language labels do not establish identity. Selected VFS locale and the
        # authored hashed source remain the binding; validate table bounds only.
        language_data = cursor.take(languages)
        if language_data:
            _require(len(language_data) >= 4)
            count = struct.unpack_from('<I', language_data)[0]
            _require(count <= (len(language_data) - 4) // 8)
            for index in range(count):
                offset = struct.unpack_from('<I', language_data, 4 + index * 8)[0]
                _require(4 + count * 8 <= offset < len(language_data))
        entries = []
        for kind, size in enumerate(sizes[1:]):
            for identity, offset, length in self._sector(cursor.take(size), external=kind == 2):
                if kind == 0:
                    entries.extend(self._bank(identity, offset, length))
                elif 0 < length <= MAX_VOICE:
                    entries.append(Media(identity, offset, length))
                _require(len(entries) <= MAX_ENTRIES)
        self.entries = tuple(entries)

    def _sector(self, data, *, external):
        if not data:
            return
        cursor = Cursor(data)
        count = cursor.number('I')
        _require(count <= MAX_ENTRIES)
        if not count:
            _require(len(data) == 4)
            return
        width, remainder = divmod(len(data) - 4, count)
        _require(not remainder and width in (20, 24))
        for _ in range(count):
            identity = cursor.number('I')
            if external and width == 24:
                identity |= cursor.number('I') << 32
            alignment = cursor.number('I')
            size = cursor.number('Q' if width == 24 and not external else 'I')
            offset = cursor.number('I') * (alignment or 1)
            cursor.number('I')
            _require(offset <= self.source.size and size <= self.source.size - offset)
            yield identity, offset, size

    def _bank(self, identity, offset, size):
        def read(position, length):
            _require(0 <= position <= size and 0 <= length <= size - position)
            return xor_data(self.source.read(offset + position, length), identity, self.parameters, position)

        _require(size >= 8 and read(0, 4) == b'BKHD')
        position, sections = 0, {}
        while position < size:
            magic, length = struct.unpack('<4sI', read(position, 8))
            _require(length <= size - position - 8)
            if magic in (b'DIDX', b'DATA'):
                _require(magic not in sections)
                sections[magic] = (position + 8, length)
            position += 8 + length
        if b'DIDX' not in sections:
            return []  # A bank may contain event metadata and no embedded media.
        _require(b'DATA' in sections)
        index_offset, index_size = sections[b'DIDX']
        data_offset, data_size = sections[b'DATA']
        _require(index_size <= MAX_INDEX and index_size % 12 == 0)
        result = []
        for media_id, relative, length in struct.iter_unpack('<III', read(index_offset, index_size)):
            _require(relative <= data_size and length <= data_size - relative)
            if 0 < length <= MAX_VOICE:
                result.append(Media(media_id, offset + data_offset + relative, length, identity, offset))
        return result

    def voice(self, entry: Media) -> bytes:
        data = self.source.read(entry.offset, entry.size)
        if entry.bank_seed is not None:
            data = xor_data(data, entry.bank_seed, self.parameters, entry.offset - entry.bank_offset)
        if data[:4] not in (b'RIFF', b'RIFX', b'PLUG'):
            data = xor_data(data, entry.identity, self.parameters)
        _require(len(data) >= 12 and data[:4] == b'RIFF', 'Unsupported Endfield original voice container')
        return data


def run(assets: Path, parameters: Parameters, action: str, request: dict) -> bytes:
    _require(action in {'inventory', 'voice'} and request.get('language') in LOCALE_BLOCKS)
    blocks = (1, LOCALE_BLOCKS[request['language']], 21)
    if action == 'voice':
        _require(type(request.get('block')) is int and request['block'] in blocks)
    base = assets.parent / 'StreamingAssets' / 'VFS'
    root = assets / 'VFS'
    rows = []
    for block in blocks:
        if action == 'voice' and request['block'] != block:
            continue
        directory = parameters.directories[block]
        index = root / directory / (directory + '.blc')
        try:
            with index.open('rb') as stream:
                data = stream.read(MAX_INDEX + 1)
        except FileNotFoundError:
            continue  # Optional language groups can be absent or empty.
        files = parse_index(data, parameters, block)
        for file in files:
            if action == 'voice' and (request.get('chunk') != file.chunk or request.get('file_hash') != str(file.name_hash)):
                continue
            path = root / directory / file.chunk
            if not path.is_file():
                path = base / directory / file.chunk
            if not path.is_file():
                continue  # Patch indexes may reference a base or absent pack.
            with path.open('rb') as stream:
                package = Package(PackageSource(stream, file, parameters), parameters)
                for entry in package.entries:
                    identity = f'{entry.identity:016x}'
                    if action == 'voice':
                        if identity == request.get('file_id'):
                            return package.voice(entry)
                    else:
                        rows.append({'block': block, 'chunk': file.chunk, 'file_hash': str(file.name_hash),
                                     'file_id': identity, 'size': entry.size})
                        _require(len(rows) <= MAX_ENTRIES)
    _require(action != 'voice', 'Endfield original voice was not found in the selected language package')
    return json.dumps(rows, separators=(',', ':')).encode()
