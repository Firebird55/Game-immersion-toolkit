"""Bounded NTE v12 archives, checked using the publisher's companion checksums.

The complete .sig is manifest-MD5 checked; its 64 KiB CRCs cover every cached
or downloaded PAK byte used here. Index plaintext additionally requires SHA1.
RSA authenticity is not independently established by this reader.
"""
from dataclasses import dataclass
import hashlib
import re
import struct
from pathlib import PurePosixPath
import zlib

from Crypto.Cipher import AES

from . import nte_release as release
from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure

CHUNK = 65536
TRANSFER = 4 * 1024**2
INDEX_LIMIT = 64 * 1024**2
MEMBER_LIMIT = 512 * 1024**2
MAGIC = b'\xe1\x12\x6f\x5a'
DELETED = -(2**31)


def check(condition):
    if not condition:
        raise PreparationFailure('unsupported_game_format',
            'The NTE publisher archive is incomplete or uses an unsupported format. '
            'Refresh game data and retry; the previous prepared snapshot is retained.')


class Reader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def read(self, size):
        check(type(size) is int and 0 <= size <= len(self.data) - self.position)
        start = self.position
        self.position += size
        return self.data[start:self.position]

    def number(self, layout='i'):
        return struct.unpack('<' + layout, self.read(struct.calcsize('<' + layout)))[0]

    def string(self, max_bytes=8192):
        count = self.number()
        if not count:
            return ''
        width = 1 if count > 0 else 2
        check(abs(count) * width <= max_bytes)
        data = self.read(abs(count) * width)
        check(data.endswith(bytes(width)))
        try:
            return data[:-width].decode('utf-8' if width == 1 else 'utf-16le')
        except UnicodeError:
            check(False)

    def count(self, maximum):
        count = self.number()
        check(0 <= count <= maximum)
        return count

    def finish(self, encrypted=False):
        # Some NTE indexes include the encrypted alignment bytes in their
        # declared length and SHA1. The checksum covers these bytes too.
        remaining = len(self.data) - self.position
        check(remaining == 0 or encrypted and len(self.data) % 16 == 0 and 0 < remaining < 16)


def _file(item, maximum):
    check(all(type(v) is int for v in (item.size, item.object_size, item.offset)))
    check(0 < item.size <= maximum and 0 <= item.offset <= item.object_size - item.size)
    check(all(isinstance(v, str) and re.fullmatch('[0-9a-f]{32}', v)
              for v in (item.digest, item.object_digest)))


class SignedSource:
    """Coalesce missing ranges, and recheck cached bytes against the full .sig."""
    def __init__(self, region, branch, item, signature, cache, progress=lambda _message: None, *, range_reader=None):
        check(region in release.HOSTS and isinstance(branch, str) and
              re.fullmatch(r'PC_[0-9]+|publish_PC', branch))
        _file(item, 1024**4)
        _file(signature, INDEX_LIMIT)
        self.region, self.branch, self.item, self.signature = region, branch, item, signature
        self.range_reader = range_reader
        self.progress = progress
        self.root = cache / region / item.digest / signature.digest
        path = self.root / 'checksums.sig'
        if range_reader is not None:
            from .private_data_paths import _no_links
            _no_links(path)
        data = path.read_bytes() if path.is_file() and path.stat().st_size == signature.size else b''
        if hashlib.md5(data).hexdigest() != signature.digest:
            # Context-owned callers acquire the complete signature in a prior
            # explicit stage. Never escape their transport/consent boundary.
            check(range_reader is None)
            release.save_file(region, branch, signature, path)
            data = path.read_bytes()
        check(len(data) == signature.size and hashlib.md5(data).hexdigest() == signature.digest)
        reader = Reader(data)
        check(reader.number('I') == 0x73832daa and reader.number('I') == 1)
        signature_size = reader.count(16384)
        check(signature_size > 0)
        reader.read(signature_size)  # Opaque RSA field, not an independently verified signature.
        count = reader.count(INDEX_LIMIT // 4)
        check(count == (item.size + CHUNK - 1) // CHUNK)
        self.checksums = reader.read(count * 4)
        check(reader.position == len(data))

    def _valid(self, index, data):
        return (len(data) == min(CHUNK, self.item.size - index * CHUNK) and
                zlib.crc32(data) == struct.unpack_from('<I', self.checksums, index * 4)[0])

    def _cached(self, index):
        path = self.root / f'{index}.chunk'
        if getattr(self, 'range_reader', None) is not None:
            from .private_data_paths import _no_links
            _no_links(path)
        expected = min(CHUNK, self.item.size - index * CHUNK)
        if path.is_file() and path.stat().st_size == expected:
            data = path.read_bytes()
            if self._valid(index, data):
                return data
        return None

    def _store(self, index, data):
        # Another preparation/playback process may have published this same
        # immutable chunk while the request was in flight. Windows readers can
        # deny replacing it; accept only its verified, byte-identical contents.
        if self._cached(index) == data:
            return
        try:
            _atomic_file(self.root / f'{index}.chunk', data)
        except PermissionError:
            if self._cached(index) != data:
                raise

    def read(self, position, size):
        check(type(position) is int and type(size) is int and 0 < size <= MEMBER_LIMIT and
              0 <= position <= self.item.size - size)
        first, end = position // CHUNK, (position + size + CHUNK - 1) // CHUNK
        parts = []
        index = first
        while index < end:
            cached = self._cached(index)
            if cached is not None:
                parts.append(cached)
                index += 1
                continue
            stop = index + 1
            while stop < min(end, index + TRANSFER // CHUNK) and self._cached(stop) is None:
                stop += 1
            begin, finish = index * CHUNK, min(stop * CHUNK, self.item.size)
            self.progress('Downloading verified NTE publisher archive blocks')
            owned = getattr(self, 'range_reader', None)
            data = (owned(self, begin, finish-begin) if owned is not None else
                    release.read_range(self.region, self.branch, self.item, begin, finish - begin))
            check(len(data) == finish - begin)
            blocks = [data[i * CHUNK:(i + 1) * CHUNK] for i in range(stop - index)]
            check(all(self._valid(index + i, part) for i, part in enumerate(blocks)))
            # No part of this response is activated before every chunk passes.
            for i, part in enumerate(blocks):
                self._store(index + i, part)
            parts.extend(blocks)
            index = stop
        start = position - first * CHUNK
        result = b''.join(parts)[start:start + size]
        check(len(result) == size)
        return result


@dataclass(frozen=True)
class Entry:
    offset: int
    size: int
    stored: int
    method: int
    encrypted: bool
    block_size: int
    header_size: int
    blocks: tuple


def _path(mount, folder, name):
    check(mount.startswith('../../../') and name and '/' not in name)
    if mount.endswith('/') and folder.startswith('/'):
        folder = folder[1:]
    path = mount[9:] + folder + name
    check(0 < len(path) <= 8192 and not path.startswith('/') and
          not any(ord(c) < 32 or c in '\\:' for c in path) and
          str(PurePosixPath(path)) == path and '..' not in PurePosixPath(path).parts)
    return path


class Archive:
    """Immutable file locations, including deletion records; no guessed patch order."""
    def __init__(self, source, catalog, *, oodle=None):
        self.source = source
        self._managed_oodle = oodle
        size = source.item.size
        footer = source.read(max(0, size - 512), min(512, size))
        marker = len(footer) - 204
        check(marker >= 17 and footer[marker:marker + 4] == MAGIC)
        check(struct.unpack_from('<I', footer, marker + 4)[0] == 12 and footer[marker - 1] in (0, 1))
        self.encrypted_index = bool(footer[marker - 1])
        key = catalog.verified_key(source.read, size, source.region, source=source)
        self.encryption_guid = footer[marker-17:marker-1]
        self.selected_key = key
        self.cipher = AES.new(bytes.fromhex(key[2:]), AES.MODE_ECB) if key else None
        check(not self.encrypted_index or self.cipher is not None)
        offset, length = struct.unpack_from('<QQ', footer, marker + 8)
        self.index_offset = offset - 1
        main = Reader(self._index(self.index_offset, length, footer[marker + 24:marker + 44]))
        methods = ['None']
        for i in range(5):
            value = footer[marker + 44 + i * 32:marker + 76 + i * 32]
            name, separator, padding = value.partition(b'\0')
            check(separator and not padding.strip(b'\0') and re.fullmatch(rb'[A-Za-z0-9_]*', name))
            methods.append(name.decode('ascii'))
        self.methods = tuple(methods)
        mount = main.string()
        declared = main.count(4_000_000)
        main.read(8)  # Path hash seed; the complete directory is used below.
        path_hash = main.number()
        check(path_hash in (0, 1))
        if path_hash:
            main.read(36)
        check(main.number() == 1)
        directory_offset, directory_size = main.number('q'), main.number('q')
        directory_digest = main.read(20)
        self.encoded = main.read(main.count(INDEX_LIMIT))
        self.nonencoded = tuple(self._nonencoded(main) for _ in range(main.count(declared)))
        main.finish(self.encrypted_index)
        directory = Reader(self._index(directory_offset, directory_size, directory_digest))
        self.locations, self.paths = {}, {}
        count = 0
        for _ in range(directory.count(declared + 1)):
            folder = directory.string()
            for _ in range(directory.count(declared - count)):
                path = _path(mount, folder, directory.string())
                position = directory.number()
                check(path.casefold() not in self.paths)
                check(position == DELETED or 0 <= position < len(self.encoded) or
                      0 <= -position - 1 < len(self.nonencoded))
                self.locations[path] = position
                self.paths[path.casefold()] = path
                count += 1
        check(count == declared)
        directory.finish(self.encrypted_index)

    def _index(self, offset, size, digest):
        check(type(offset) is int and type(size) is int and 0 < size <= INDEX_LIMIT and
              0 <= offset <= self.source.item.size - size)
        stored = (size + 15) // 16 * 16 if self.encrypted_index else size
        data = self.source.read(offset, stored)
        if self.encrypted_index:
            data = self.cipher.decrypt(data)
        data = data[:size]
        check(hashlib.sha1(data).digest() == digest)
        return data

    def _nonencoded(self, reader):
        start = reader.position
        offset, stored, size, method = (reader.number('q'), reader.number('q'), reader.number('q'), reader.number('I'))
        reader.read(20)
        check(0 <= method < len(self.methods))
        raw_blocks = tuple((reader.number('q'), reader.number('q'))
                           for _ in range(reader.count(65535))) if method else ()
        flags, block_size = reader.number('B'), reader.number('I')
        check(not flags & ~3)
        if flags & 2:
            return None
        header = reader.position - start
        blocks = tuple((offset + a, b - a) for a, b in raw_blocks)
        return Entry(offset, size, stored, method, bool(flags & 1), block_size, header, blocks)

    def entry(self, path):
        position = self.locations[self.paths[path.casefold()]]
        if position == DELETED:
            return None
        if position < 0:
            return self.nonencoded[-position - 1]
        reader = Reader(self.encoded)
        reader.position = position
        bits = reader.number('I')
        block_size = reader.number('I') if bits & 63 == 63 else (bits & 63) << 11
        offset = reader.number('I' if bits & (1 << 31) else 'q')
        size = reader.number('I' if bits & (1 << 30) else 'q')
        method = (bits >> 23) & 63
        check(method < len(self.methods) and (method == 0 or self.methods[method]))
        stored = reader.number('I' if bits & (1 << 29) else 'q') if method else size
        count, encrypted = (bits >> 6) & 65535, bool(bits & (1 << 22))
        check(bool(method) == bool(count))
        header = 53 + (4 + 16 * count if method else 0)
        if count == 1:
            block_size = size
        lengths = ((stored,) if count == 1 and not encrypted else
                   tuple(reader.number('I') for _ in range(count)))
        blocks, position = [], offset + header
        for length in lengths:
            blocks.append((position, length))
            position += (length + 15) // 16 * 16 if encrypted else length
        return Entry(offset, size, stored, method, encrypted, block_size, header, tuple(blocks))

    def _parts(self, path):
        entry = self.entry(path)
        if entry is None:
            raise FileNotFoundError('The selected NTE patch deletes this resource.')
        e = entry
        check(0 <= e.offset and 0 <= e.size <= MEMBER_LIMIT and 0 <= e.stored <= MEMBER_LIMIT and
              e.offset + e.header_size <= self.index_offset)
        if e.encrypted:
            check(self.cipher is not None)
        if not e.method:
            check(e.size == e.stored and not e.blocks)
            if not e.size:
                return e, b''
            length = (e.stored + 15) // 16 * 16 if e.encrypted else e.stored
            check(e.offset + e.header_size + length <= self.index_offset)
            data = self.source.read(e.offset + e.header_size, length)
            return e, (self.cipher.decrypt(data) if e.encrypted else data)[:e.size]
        stored_sizes = {sum(n for _, n in e.blocks)}
        if e.encrypted:
            stored_sizes.add(sum((n + 15) // 16 * 16 for _, n in e.blocks))
        check(e.method < len(self.methods) and 0 < e.block_size <= MEMBER_LIMIT and
              len(e.blocks) == (e.size + e.block_size - 1) // e.block_size and
              e.stored in stored_sizes)
        end = e.offset + e.header_size
        for offset, size in e.blocks:
            length = (size + 15) // 16 * 16 if e.encrypted else size
            check(size > 0 and offset == end and offset + length <= self.index_offset)
            end = offset + length
        start = e.offset + e.header_size
        data = self.source.read(start, end - start)
        blocks = []
        for i, (offset, size) in enumerate(e.blocks):
            length = (size + 15) // 16 * 16 if e.encrypted else size
            part = data[offset - start:offset - start + length]
            blocks.append(((self.cipher.decrypt(part) if e.encrypted else part)[:size],
                           min(e.block_size, e.size - i * e.block_size)))
        return e, blocks

    @staticmethod
    def _oodle(blocks):
        from .wuthering_release_pak import _oodle
        try:
            return _oodle(blocks)
        except PreparationFailure as error:
            if error.code != 'missing_decoder':
                raise
            raise PreparationFailure('missing_decoder',
                'Prepare the NTE publisher package decoder in Setup, then retry.') from error
        except ValueError:
            check(False)

    def _decode(self, e, blocks):
        if not e.method:
            return blocks
        method = self.methods[e.method]
        if method == 'Oodle':
            result = self._expand_oodle(blocks)
        elif method in ('Zlib', 'Gzip'):
            parts = []
            for data, size in blocks:
                decoder = zlib.decompressobj(31 if method == 'Gzip' else 15)
                try:
                    decoded = decoder.decompress(data, size + 1)
                except zlib.error:
                    check(False)
                check(len(decoded) == size and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail)
                parts.append(decoded)
            result = b''.join(parts)
        else:
            check(False)
        check(len(result) == e.size)
        return result

    def _expand_oodle(self, blocks):
        decoder = getattr(self, '_managed_oodle', None)
        return decoder(blocks) if decoder is not None else self._oodle(blocks)

    def read(self, path):
        return self._decode(*self._parts(path))

    def read_many(self, paths):
        """Decode small bank batches together, with the same entry/range checks."""
        check(0 < len(paths) <= 256)
        entries = [self.entry(path) for path in paths]
        check(all(e is not None for e in entries) and sum(e.size for e in entries) <= TRANSFER and
              sum(e.stored for e in entries) <= 2 * TRANSFER)
        parts = [self._parts(path) for path in paths]
        compressed = [(i, e, blocks) for i, (e, blocks) in enumerate(parts) if self.methods[e.method] == 'Oodle']
        result = [self._decode(e, blocks) if self.methods[e.method] != 'Oodle' else None for e, blocks in parts]
        if compressed:
            combined = self._expand_oodle([b for _, _, blocks in compressed for b in blocks])
            check(len(combined) == sum(e.size for _, e, _ in compressed))
            offset = 0
            for index, entry, _ in compressed:
                result[index] = combined[offset:offset + entry.size]
                offset += entry.size
        return result


def overlay(archives):
    """The caller supplies evidenced highest-first mount priority, never filenames."""
    result = {}
    for archive in archives:
        for path in archive.locations:
            # A deletion is a winning location too; do not fall through to an
            # older recording. Historical callers retain their original archive.
            result.setdefault(path.casefold(), (archive, path))
    return result
