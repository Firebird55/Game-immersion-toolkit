"""Bounded NTE IoStore reads authenticated by the publisher's complete TOC.

The manifest-MD5-checked TOC supplies SHA1 for each stored compression block.
No independent RSA check or complete large-UCAS checksum is claimed. Archive
mount priority and parsing Zen packages belong to the caller, not this reader.
"""
from dataclasses import dataclass
from bisect import bisect_right
import hashlib
import re
import struct

from . import nte_release as release
from .game_tools import _atomic_file
from .nte_publisher_pak import (Archive, Reader, _file, _path, check,
                                INDEX_LIMIT, MEMBER_LIMIT, TRANSFER)
from .preparation_errors import PreparationFailure

MAGIC = b'-==--==--==--==-'


@dataclass(frozen=True)
class Block:
    offset: int
    stored: int
    expanded: int
    method: int
    length: int
    digest: bytes


class Container:
    """One immutable, single-partition signed v8 container; no overlay guesses."""
    def __init__(self, region, branch, toc, ucas, proven_archive, cache):
        check(region in release.HOSTS and isinstance(branch, str) and
              re.fullmatch(r'PC_[0-9]+|publish_PC', branch))
        _file(toc, INDEX_LIMIT)
        _file(ucas, 1024**4)
        check(isinstance(proven_archive, Archive) and
              proven_archive.source.region == region and proven_archive.source.branch == branch)
        self.region, self.branch, self.toc, self.ucas = region, branch, toc, ucas
        self.cipher = proven_archive.cipher
        self.root = cache / region / toc.digest / ucas.digest
        path = self.root / 'index.utoc'
        raw = path.read_bytes() if path.is_file() and path.stat().st_size == toc.size else b''
        if hashlib.md5(raw).hexdigest() != toc.digest:
            release.save_file(region, branch, toc, path)
            raw = path.read_bytes()
        check(len(raw) == toc.size and hashlib.md5(raw).hexdigest() == toc.digest)
        self.raw = raw
        self._index()

    def _index(self):
        raw = self.raw
        check(len(raw) >= 144 and raw[:16] == MAGIC and raw[16] == 8)
        check(raw[17:20] == b'\0' * 3 and raw[82:84] == b'\0' * 2)
        (header, count, block_count, block_width, method_count, method_width,
         self.block_size, directory_size, partitions) = struct.unpack_from('<9I', raw, 20)
        flags = raw[80]
        check(header == 144 and 0 < count <= INDEX_LIMIT // 24 and
              0 < block_count <= INDEX_LIMIT // 20 and block_width == 12 and
              method_count <= 16 and method_width == 32 and
              0 < self.block_size <= TRANSFER and partitions == 1 and
              flags & 4 and flags & ~15 == 0 and raw[81] == 0 and
              raw[100:144] == b'\0' * 44)
        self.encrypted = bool(flags & 2)
        check(not self.encrypted or self.cipher is not None)
        self.chunk_ids = raw[header:header + count * 12]
        offsets = header + count * 12
        check(offsets + count * 10 <= len(raw))
        self.locations = tuple((int.from_bytes(raw[i:i + 5], 'big'),
                                int.from_bytes(raw[i + 5:i + 10], 'big'))
                               for i in range(offsets, offsets + count * 10, 10))
        check(all(0 <= at <= block_count * self.block_size - n
                  for at, n in self.locations))
        seeds = struct.unpack_from('<I', raw, 84)[0]
        overflow = struct.unpack_from('<I', raw, 96)[0]
        check(seeds <= count and overflow <= count)
        reader = Reader(raw)
        reader.read(header + count * 22 + 4 * (seeds + overflow))
        encoded = reader.read(block_count * 12)
        methods = ['None']
        for _ in range(method_count):
            value, separator, padding = reader.read(method_width).partition(b'\0')
            check(separator and not padding.strip(b'\0') and re.fullmatch(rb'[A-Za-z0-9_]+', value))
            methods.append(value.decode('ascii'))
        self.methods = tuple(methods)
        signature_size = reader.count(16384)
        check(signature_size > 0)
        reader.read(2 * signature_size)  # Opaque signatures; the publisher TOC's MD5 was checked.
        digests = reader.read(block_count * 20)
        directory = reader.read(directory_size)
        # v8 carries a 20-byte chunk identity and four metadata bytes per entry.
        check(len(raw) - reader.position == count * 24)
        self.metadata = reader.read(count * 24)
        self.blocks = []
        end = 0
        for i in range(block_count):
            row = encoded[i * 12:(i + 1) * 12]
            at, stored, expanded, method = (int.from_bytes(row[:5], 'little'),
                int.from_bytes(row[5:8], 'little'), int.from_bytes(row[8:11], 'little'), row[11])
            length = (stored + 15) // 16 * 16 if self.encrypted else stored
            check(0 < stored <= TRANSFER and 0 < expanded <= self.block_size and
                  method < len(methods) and (method != 0 or stored == expanded) and
                  end <= at <= self.ucas.size - length and
                  (not self.encrypted or at % 16 == 0))
            self.blocks.append(Block(at, stored, expanded, method, length, digests[i * 20:(i + 1) * 20]))
            end = at + length
        self.blocks = tuple(self.blocks)
        self._offsets = tuple(b.offset for b in self.blocks)
        check(bool(flags & 8) == bool(directory_size))
        self.paths = self._directory(directory) if directory_size else {}

    def _directory(self, data):
        check(not self.encrypted or len(data) % 16 == 0)
        reader = Reader(self.cipher.decrypt(data) if self.encrypted else data)
        mount = reader.string()
        directories = tuple(struct.unpack('<4I', reader.read(16))
                            for _ in range(reader.count(INDEX_LIMIT // 16)))
        files = tuple(struct.unpack('<3I', reader.read(12))
                      for _ in range(reader.count(INDEX_LIMIT // 12)))
        strings = tuple(reader.string() for _ in range(reader.count(INDEX_LIMIT // 4)))
        reader.finish(self.encrypted)
        check(directories)
        invalid = 0xffffffff
        pending, visited, used, paths = [(0, '')], set(), set(), {}
        while pending:
            index, parent = pending.pop()
            check(index < len(directories) and index not in visited)
            visited.add(index)
            name, child, sibling, file = directories[index]
            folder = parent
            if name != invalid:
                check(name < len(strings))
                part = strings[name]
                check('/' not in part and part not in ('.', '..'))
                folder += part + '/' if part else ''
            check(len(folder) <= 8192)
            if child != invalid:
                pending.append((child, folder))
            if sibling != invalid:
                pending.append((sibling, parent))
            while file != invalid:
                check(file < len(files) and file not in used)
                used.add(file)
                name, following, entry = files[file]
                check(name < len(strings) and entry < len(self.locations))
                path = _path(mount, folder, strings[name])
                check(path.casefold() not in paths)
                paths[path.casefold()] = (path, entry)
                file = following
        check(len(visited) == len(directories) and len(used) == len(files))
        return paths

    def _valid(self, index, data):
        block = self.blocks[index]
        return len(data) == block.length and hashlib.sha1(data).digest() == block.digest

    def _cached(self, index):
        path = self.root / f'{index}.block'
        if path.is_file() and path.stat().st_size == self.blocks[index].length:
            data = path.read_bytes()
            if self._valid(index, data):
                return data
        return None

    def stored_blocks(self, first, stop):
        check(type(first) is int and type(stop) is int and 0 <= first < stop <= len(self.blocks))
        check(sum(b.length for b in self.blocks[first:stop]) <= MEMBER_LIMIT)
        result = []
        while first < stop:
            cached = self._cached(first)
            if cached is not None:
                result.append(cached)
                first += 1
                continue
            start = self.blocks[first].offset
            end = first + 1
            limit = start + self.blocks[first].length
            while end < stop and self.blocks[end].offset == limit and self._cached(end) is None:
                if limit + self.blocks[end].length - start > TRANSFER:
                    break
                limit += self.blocks[end].length
                end += 1
            data = release.read_range(self.region, self.branch, self.ucas, start, limit - start)
            parts = [data[b.offset - start:b.offset - start + b.length] for b in self.blocks[first:end]]
            check(len(data) == limit - start and all(self._valid(i, part)
                                                   for i, part in zip(range(first, end), parts)))
            for i, part in zip(range(first, end), parts):
                _atomic_file(self.root / f'{i}.block', part)
            result.extend(parts)
            first = end
        return result

    def read_stored(self, position, size):
        """A managed seekable stream may read only checksum-covered UCAS bytes."""
        check(type(position) is int and type(size) is int and 0 <= size <= TRANSFER and
              0 <= position <= self.ucas.size - size)
        if not size:
            return b''
        first = bisect_right(self._offsets, position) - 1
        check(first >= 0 and position < self.blocks[first].offset + self.blocks[first].length)
        stop = first + 1
        end = self.blocks[first].offset + self.blocks[first].length
        while end < position + size:
            check(stop < len(self.blocks) and self.blocks[stop].offset == end)
            end += self.blocks[stop].length
            stop += 1
        parts = self.stored_blocks(first, stop)
        start = position - self.blocks[first].offset
        result = b''.join(parts)[start:start + size]
        check(len(result) == size)
        return result

    def read(self, path):
        match = self.paths.get(path.casefold())
        if match is None:
            raise KeyError(path)
        offset, size = self.locations[match[1]]
        check(size <= MEMBER_LIMIT)
        if not size:
            return b''
        first, stop = offset // self.block_size, (offset + size + self.block_size - 1) // self.block_size
        stored = self.stored_blocks(first, stop)
        parts = []
        for block, data in zip(self.blocks[first:stop], stored):
            data = (self.cipher.decrypt(data) if self.encrypted else data)[:block.stored]
            if block.method:
                check(self.methods[block.method] == 'Oodle')
                from .wuthering_release_pak import _oodle
                try:
                    data = _oodle([(data, block.expanded)])
                except PreparationFailure as error:
                    if error.code != 'missing_decoder':
                        raise
                    raise PreparationFailure('missing_decoder',
                        'Prepare the NTE publisher package decoder in Setup, then retry.') from error
                except ValueError:
                    check(False)
            check(len(data) == block.expanded)
            parts.append(data)
        start = offset - first * self.block_size
        result = b''.join(parts)[start:start + size]
        check(len(result) == size)
        return result
