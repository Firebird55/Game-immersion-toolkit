"""Bounded original Nikki v12 PAK directories and two-hash entry framing.

The caller supplies generation-pinned, authenticated source reads and current
native-derived default material. Index/member SHA-1 checks are format integrity,
not a replacement for source authentication. Compression is injected so this
reader never loads an original library or assumes a desktop-only codec.
"""
from dataclasses import dataclass, field
import hashlib
from pathlib import PurePosixPath
import re
import struct

from .infinity_nikki_pak_material import DefaultPakMaterial


INDEX_LIMIT = 64 * 1024**2
MEMBER_LIMIT = 128 * 1024**2
BATCH_LIMIT = 16 * 1024**2


def _check(value):
    if not value:
        raise ValueError('Could not verify the current official Infinity Nikki archive data.')


class _Reader:
    def __init__(self, raw):
        self.raw, self.at = raw, 0

    def take(self, count):
        _check(type(count) is int and 0 <= count <= len(self.raw) - self.at)
        result = self.raw[self.at:self.at + count]
        self.at += count
        return result

    def number(self, kind='i'):
        return struct.unpack('<' + kind, self.take(struct.calcsize('<' + kind)))[0]

    def count(self, limit):
        value = self.number()
        _check(0 <= value <= limit)
        return value

    def string(self):
        count = self.number()
        if not count:
            return ''
        width = 1 if count > 0 else 2
        _check(abs(count) * width <= 8192)
        raw = self.take(abs(count) * width)
        _check(raw[-width:] == bytes(width))
        value = raw[:-width].decode('utf-8' if width == 1 else 'utf-16-le')
        _check('\0' not in value)
        return value

    def finish(self, aligned=False):
        remaining = len(self.raw) - self.at
        _check(remaining == 0 or aligned and len(self.raw) % 16 == 0 and 0 < remaining < 16)


def _path(mount, folder, name):
    _check(mount.startswith('../../../') and name and '/' not in name)
    if mount.endswith('/') and folder.startswith('/'):
        folder = folder[1:]
    value = mount[9:] + folder + name
    _check(0 < len(value) <= 8192 and not value.startswith('/') and
           not any(ord(c) < 32 or c in '\\:' for c in value) and
           str(PurePosixPath(value)) == value and '..' not in PurePosixPath(value).parts)
    return value


@dataclass(frozen=True)
class PakEntry:
    offset: int
    expanded_bytes: int
    stored_bytes: int
    method: int
    encrypted: bool
    block_size: int
    header_bytes: int
    blocks: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class _Member:
    entry: PakEntry
    digest: bytes = field(repr=False)
    parts: object = field(repr=False)


class Archive:
    """Data-only reader; source authentication and patch priority stay external.

    Current evidenced encoded entries are implemented. Nonencoded entries,
    deletion positions and nonzero key GUIDs fail explicitly rather than being
    interpreted as missing or unvoiced resources.
    """
    def __init__(self, read, size, material, *, crypto=None):
        _check(callable(read) and type(size) is int and 221 <= size <= 1024**4 and
               isinstance(material, DefaultPakMaterial) and len(material.parameter) == 32)
        self.source, self.size, self.material, self.crypto = read, size, material, crypto
        footer = self._read(size - 221, 221)
        _check(footer[:16] == bytes(16) and footer[16] in (0, 1) and
               struct.unpack_from('<II', footer, 17) == (0x5a6f12e1, 12))
        self.encrypted_index = bool(footer[16])
        self.index_offset, index_size = struct.unpack_from('<QQ', footer, 25)
        self.data_end = self.index_offset
        methods = ['None']
        for index in range(5):
            field = footer[61 + index * 32:93 + index * 32]
            value, separator, padding = field.partition(b'\0')
            _check(separator and not padding.strip(b'\0') and re.fullmatch(rb'[A-Za-z0-9_]*', value))
            methods.append(value.decode('ascii'))
        self.methods = tuple(methods)
        main = _Reader(self._index(self.index_offset, index_size, footer[41:61]))
        self.mount, declared = main.string(), main.count(4_000_000)
        main.take(8)  # Authored path-hash seed; use the full directory below.
        path_hash = main.number()
        _check(path_hash in (0, 1))
        if path_hash:
            main.take(36)
        _check(main.number() == 1)
        at, length, digest = main.number('q'), main.number('q'), main.take(20)
        self.encoded = main.take(main.count(INDEX_LIMIT))
        _check(main.number() == 0)  # No evidenced nonencoded-entry variant yet.
        main.finish(self.encrypted_index)
        directory = _Reader(self._index(at, length, digest))
        self.locations, self.names = {}, {}
        for _ in range(directory.count(declared + 1)):
            folder = directory.string()
            for _ in range(directory.count(declared - len(self.locations))):
                path = _path(self.mount, folder, directory.string())
                position = directory.number()
                _check(path.casefold() not in self.names and 0 <= position < len(self.encoded))
                self.locations[path], self.names[path.casefold()] = position, path
        _check(len(self.locations) == declared)
        directory.finish(self.encrypted_index)

    def _read(self, at, size):
        _check(type(at) is int and type(size) is int and 0 < size <= MEMBER_LIMIT and 0 <= at <= self.size - size)
        raw = self.source(at, size)
        _check(isinstance(raw, bytes) and len(raw) == size)
        return raw

    def _decrypt(self, raw):
        _check(raw and len(raw) % 16 == 0)
        key = self.material.parameter
        if self.crypto is None:
            from .publisher_crypto import DesktopPublisherCrypto
            self.crypto = DesktopPublisherCrypto()
        decoded = self.crypto.block_cipher('AES', 'ECB', key, raw)
        _check(isinstance(decoded, bytes) and len(decoded) == len(raw))
        raw = bytearray(decoded)
        for at in range(0, len(raw), 16):
            raw[at] ^= key[-1]
            raw[at + 15] ^= key[0]
        return bytes(raw)

    def _index(self, at, size, digest):
        _check(0 < size <= INDEX_LIMIT)
        stored = (size + 15) // 16 * 16 if self.encrypted_index else size
        _check(0 <= at <= self.size - 221 - stored)
        raw = self._read(at, stored)
        raw = (self._decrypt(raw) if self.encrypted_index else raw)[:size]
        _check(hashlib.sha1(raw).digest() == digest)
        return raw

    def entry(self, path):
        _check(isinstance(path, str) and path.casefold() in self.names)
        reader = _Reader(self.encoded)
        reader.at = self.locations[self.names[path.casefold()]]
        bits = reader.number('I')
        block_size = reader.number('I') if bits & 63 == 63 else (bits & 63) << 11
        at = reader.number('I' if bits & (1 << 31) else 'q')
        size = reader.number('I' if bits & (1 << 30) else 'q')
        method = (bits >> 23) & 63
        _check(method < len(self.methods) and self.methods[method])
        # The original Nikki decoder uses bit 22 for the stored-size width and
        # bit 29 for member encryption. Framework entries set both, so those
        # samples alone cannot distinguish this from another game's layout.
        stored = reader.number('I' if bits & (1 << 22) else 'q') if method else size
        count, encrypted = (bits >> 6) & 65535, bool(bits & (1 << 29))
        _check(bool(count) == bool(method) and 0 <= size <= MEMBER_LIMIT and 0 <= stored <= MEMBER_LIMIT)
        header = 73 + (4 + count * 16 if method else 0)  # Two original 20-byte hashes.
        if count == 1:
            block_size = size
        lengths = ((stored,) if count == 1 and not encrypted else
                   tuple(reader.number('I') for _ in range(count)))
        blocks, start = [], at + header
        for length in lengths:
            _check(length > 0)
            blocks.append((start, length))
            start += (length + 15) // 16 * 16 if encrypted else length
        _check(0 <= at and at + header <= self.data_end and
               (not method or 0 < block_size <= MEMBER_LIMIT and count == (size + block_size - 1) // block_size))
        return PakEntry(at, size, stored, method, encrypted, block_size, header, tuple(blocks))

    def _parts(self, path):
        e = self.entry(path)
        header = _Reader(self._read(e.offset, e.header_bytes))
        at, stored, size, method = (header.number('q'), header.number('q'), header.number('q'), header.number('I'))
        header.take(20)  # First original hash's meaning is not inferred.
        digest = header.take(20)
        _check(at in (0, e.offset) and (stored, size, method) == (e.stored_bytes, e.expanded_bytes, e.method))
        blocks = tuple((header.number('q'), header.number('q')) for _ in range(header.count(65535))) if method else ()
        flags, block_size = header.number('B'), header.number('I')
        header.finish()
        _check(flags in (0, 1) and bool(flags) == e.encrypted and len(blocks) == len(e.blocks))
        if method:
            _check(block_size > 0 and (len(blocks) == 1 or block_size == e.block_size))
            _check(all((e.offset + a, b - a) == compact for (a, b), compact in zip(blocks, e.blocks)))
            end = e.offset + e.header_bytes
            total = 0
            parts = []
            for index, (offset, count) in enumerate(e.blocks):
                length = (count + 15) // 16 * 16 if e.encrypted else count
                _check(offset == end and offset + length <= self.data_end)
                raw = self._read(offset, length)
                value = (self._decrypt(raw) if e.encrypted else raw)[:count]
                parts.append((value, min(e.block_size, e.expanded_bytes - index * e.block_size)))
                total += length
                end += length
            _check(total == e.stored_bytes)
            return _Member(e, digest, tuple(parts))
        _check(e.stored_bytes == e.expanded_bytes)
        length = (e.stored_bytes + 15) // 16 * 16 if e.encrypted else e.stored_bytes
        _check(e.offset + e.header_bytes + length <= self.data_end)
        raw = self._read(e.offset + e.header_bytes, length) if length else b''
        result = (self._decrypt(raw) if e.encrypted and raw else raw)[:e.expanded_bytes]
        return _Member(e, digest, result)

    def read_many(self, paths, *, decompress):
        """Decode selected members with one bounded portable-codec invocation.

        The callback receives (method-name, compressed-bytes, expected-size)
        triples and returns concatenated exact decoded bytes. No original VM or
        native module is executed. Every output also needs its authored SHA-1.
        """
        _check(isinstance(paths, (tuple, list)) and 0 < len(paths) <= 256)
        entries = [self.entry(path) for path in paths]
        _check(sum(e.expanded_bytes for e in entries) <= BATCH_LIMIT and
               sum(e.stored_bytes for e in entries) <= BATCH_LIMIT)
        members = [self._parts(path) for path in paths]
        blocks = [(self.methods[m.entry.method], raw, size) for m in members if m.entry.method
                  for raw, size in m.parts]
        expanded = decompress(tuple(blocks)) if blocks else b''
        _check(isinstance(expanded, bytes) and len(expanded) == sum(size for _, _, size in blocks))
        result, offset = [], 0
        for member in members:
            size = member.entry.expanded_bytes
            if member.entry.method:
                raw, offset = expanded[offset:offset + size], offset + size
            else:
                raw = member.parts
            _check(len(raw) == size and hashlib.sha1(raw).digest() == member.digest)
            result.append(raw)
        return tuple(result)

    def read(self, path, *, decompress):
        return self.read_many((path,), decompress=decompress)[0]
