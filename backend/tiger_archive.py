"""Bounded, read-only TAFS v4/v5 archive access for the Tomb Raider games.

Format reference: arcusmaximus/TrRebootModTools, commit
a79c48b75f1ffaaf623dc73a625211bf98ff0504, Shared/Cdc/{Archive,
ArchiveDecompressionStream,Rise/RiseArchive,Shadow/ShadowArchive}.cs.
This implementation never loads external binaries or writes to a game folder.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import struct
import zlib

from .preparation_errors import PreparationFailure

MAX_ENTRY_SIZE = 512 * 1024 * 1024
MAX_ARCHIVE_FILES = 4096
MAX_DIRECTORY_ENTRIES = 2_000_000


def _invalid(message='Unsupported or incomplete TIGER archive.'):
    return PreparationFailure('tiger_archive_format', message +
        ' Finish the launcher update, verify installed game files, and update the toolkit before retrying.')


def _read(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise _invalid()
    return data


def archive_sources(root: Path):
    return sorted((p for p in root.glob('*.tiger') if p.is_file() and
                   not p.name.lower().startswith(('bigfile._mod.', 'bigfile._orig.'))),
                  key=lambda p: p.name.lower())


def fingerprint(root: Path):
    paths = [*archive_sources(root), *sorted(root.glob('*.nfo'))]
    return hashlib.sha256('|'.join(f'{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
                                  for p in paths).encode()).hexdigest()


@dataclass(frozen=True)
class TigerEntry:
    name_hash: int
    locale: int
    archive: str
    offset: int
    size: int
    compressed_size: int
    archive_id: int = 0
    archive_sub_id: int | str = 0

    def reference(self):
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


class TigerSet:
    """Resolve archive IDs and patch priorities before exposing physical spans."""
    def __init__(self, root: Path, version: int):
        self.root, self.version = root.resolve(), version
        if version not in (4, 5):
            raise _invalid()
        self.files = {}
        self.priorities = {}
        self.archives = []
        self._paths = {p.name: p for p in archive_sources(self.root)}
        if len(self._paths) > MAX_ARCHIVE_FILES:
            raise _invalid('The TIGER installation exceeds the supported archive count.')
        if any(not path.resolve().is_relative_to(self.root) for path in self._paths.values()):
            raise _invalid('TIGER archive links must stay inside the selected game folder.')
        self._sizes = {name: path.stat().st_size for name, path in self._paths.items()}
        metadata = {}
        metadata_paths = sorted(self.root.glob('*.nfo'))
        if len(metadata_paths) > MAX_ARCHIVE_FILES:
            raise _invalid('The TIGER installation exceeds the supported metadata count.')
        for path in metadata_paths:
            if not path.resolve().is_relative_to(self.root):
                raise _invalid('TIGER metadata links must stay inside the selected game folder.')
            if path.stat().st_size > 65536:
                raise _invalid('TIGER package metadata exceeds the supported bound.')
            lines = path.read_text(encoding='utf-8-sig').splitlines()
            if not lines:
                raise _invalid()
            values = lines[0].split()[1:]
            if len(values) % 2:
                raise _invalid()
            try:
                props = dict(zip(values[::2], map(int, values[1::2])))
                identity = props['dlcindex']
            except (ValueError, KeyError):
                raise _invalid() from None
            if not props.get('bigfile', 1) or any(line.startswith('custom mod:') for line in lines):
                continue
            priority = (props.get('version', 0), -props.get('required', 1),
                        props.get('package', 0), props.get('chunk', 0))
            if identity in metadata and metadata[identity] != priority:
                raise _invalid('Ambiguous TIGER package metadata.')
            metadata[identity] = priority
        raw, owners = [], {}
        for path in self._paths.values():
            if not path.name.lower().endswith('.000.tiger'):
                continue
            with path.open('rb') as stream:
                magic, actual_version, parts, count, identity = struct.unpack('<4s4I', _read(stream, 20))
                if magic != b'TAFS' or actual_version != version or not 1 <= parts <= 256 or count > MAX_DIRECTORY_ENTRIES:
                    raise _invalid()
                if len(raw) + count > MAX_DIRECTORY_ENTRIES:
                    raise _invalid('The TIGER installation exceeds the supported total directory bound.')
                sub_id = struct.unpack('<I', _read(stream, 4))[0] if version == 5 else 0
                platform = _read(stream, 32).split(b'\0')[0]
                if platform != b'pcx64-w':
                    raise _invalid('This TIGER platform is not supported; select the Windows game installation.')
                if version == 4:
                    # Rise stores the language archive discriminator in its
                    # filename. Cross-package descriptors always use sub-ID 0.
                    match = re.search(r'_([A-Z_]+)\.000\.tiger$', path.name, re.I)
                    sub_id = match[1].upper() if match else 0
                owner = (identity, sub_id)
                if owner in owners:
                    raise _invalid('Duplicate TIGER package identities are ambiguous.')
                owners[owner] = (path, parts)
                entry_size = 24 if version == 4 else 32
                if stream.tell() + count * entry_size > path.stat().st_size:
                    raise _invalid()
                table = _read(stream, count * entry_size)
                self.archives.append({'archive': path.name, 'id': identity, 'sub_id': sub_id, 'count': count})
                priority = (*metadata.get(identity, (0, -1, identity, 0)), str(sub_id))
                for values in struct.iter_unpack('<4IhhI' if version == 4 else '<QQIIhBBI', table):
                    if version == 4:
                        name_hash, locale, size, compressed, part, target_id, offset = values
                        target_sub = sub_id if target_id == identity else 0
                    else:
                        name_hash, locale, size, compressed, part, target_id, target_sub, offset = values
                    raw.append((priority, name_hash, locale, size, compressed, part, target_id, target_sub, offset))
        if not owners:
            raise _invalid('No supported TIGER archives were found in this game folder.')
        for priority, name_hash, locale, size, compressed, part, identity, sub_id, offset in sorted(raw, key=lambda x: x[0]):
            owner = owners.get((identity, sub_id))
            if owner is None:
                raise _invalid('A referenced TIGER archive part or language pack is missing.')
            path, parts = owner
            if not 0 <= part < parts:
                raise _invalid()
            physical = path.name[:-9] + f'{part:03d}.tiger'
            actual = self._paths.get(physical)
            if actual is None or offset > self._sizes[physical] or (size and offset + 4 > self._sizes[physical]):
                raise _invalid('A referenced TIGER archive part is missing or incomplete.')
            self.files[name_hash, locale] = TigerEntry(name_hash, locale, physical, offset, size,
                                                       compressed, identity, sub_id)
            self.priorities[name_hash, locale] = priority

    def entries(self):
        return self.files.values()

    def read(self, entry: TigerEntry, max_bytes=MAX_ENTRY_SIZE, prefix=None):
        if not isinstance(entry, TigerEntry) or self.files.get((entry.name_hash, entry.locale)) != entry:
            raise _invalid('The TIGER asset reference is no longer current.')
        path = self._paths.get(entry.archive)
        if path is None or not path.resolve().is_relative_to(self.root):
            raise _invalid()
        limit = entry.size if prefix is None else min(prefix, entry.size)
        if limit < 0 or limit > max_bytes or entry.size > 2 ** 32 - 1:
            raise _invalid('The TIGER asset exceeds the supported extraction bound.')
        with path.open('rb') as stream:
            stream.seek(entry.offset)
            marker = _read(stream, min(4, entry.size))
            if marker != b'CDRM':
                stream.seek(entry.offset)
                return _read(stream, limit)
            _kind, count, _reserved = struct.unpack('<3I', _read(stream, 12))
            if not 1 <= count <= 65536:
                raise _invalid()
            table = [struct.unpack('<II', _read(stream, 8)) for _ in range(count)]
            if sum(size >> 8 for size, _ in table) != entry.size:
                raise _invalid('TIGER decompression sizes disagree with the archive directory.')
            position = (stream.tell() + 15) & ~15
            # The directory's CompressedSize is zero in the reviewed native
            # archives and ignored by the reference reader. CDRM's chunk table
            # supplies the physical extent instead; validate ALL spans even
            # when a caller requests only the first few decoded bytes.
            layout, total_end = [], position
            for encoded, compressed in table:
                expected = encoded >> 8
                if not 0 < expected <= 0x40000 or not 0 < compressed <= 0x80000 or total_end + compressed > self._sizes[entry.archive]:
                    raise _invalid()
                layout.append((total_end, expected, compressed))
                total_end = (total_end + compressed + 15) & ~15
            output = bytearray()
            for position, expected, compressed in layout:
                stream.seek(position)
                data = _read(stream, compressed)
                if compressed != expected:
                    try:
                        decoder = zlib.decompressobj()
                        data = decoder.decompress(data, expected + 1)
                        if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                            raise _invalid()
                    except zlib.error:
                        raise _invalid('Unsupported TIGER compressed payload.') from None
                if len(data) != expected:
                    raise _invalid()
                output.extend(data[:limit - len(output)])
                if len(output) == limit:
                    return bytes(output)
            return bytes(output)

    def prefix(self, entry, size=64):
        return self.read(entry, max_bytes=size, prefix=size)


def name_hash32(value: str):
    """Rise's case-sensitive CRC-32/MPEG-2 variant with final inversion."""
    crc = 0xFFFFFFFF
    for character in value:
        crc ^= ord(character) << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF
