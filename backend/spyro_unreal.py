"""Bounded readers for Spyro's cooked UE4 pak v4, locres v1 and tagged tables.

Only the shipped, unencrypted schemas are accepted. Nothing is unpacked into
the game directory and asset paths are never treated as filesystem paths.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath
import struct
import zlib

from .preparation_errors import PreparationFailure


def invalid(message='Unsupported or incomplete Spyro dialogue data.'):
    return PreparationFailure('spyro_format', message +
        ' Verify game files in Steam, then update the toolkit and prepare again.')


class Cursor:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise invalid()
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def unpack(self, fmt):
        values = struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))
        return values[0] if len(values) == 1 else values

    def count(self, maximum=100000):
        value = self.unpack('i')
        if not 0 <= value <= maximum:
            raise invalid()
        return value

    def string(self):
        count = self.unpack('i')
        if abs(count) > 4 * 1024 * 1024:
            raise invalid()
        if count == 0:
            return ''
        raw = self.take(abs(count) * (2 if count < 0 else 1))
        ending = b'\0\0' if count < 0 else b'\0'
        if not raw.endswith(ending):
            raise invalid()
        try:
            return raw[:-len(ending)].decode('utf-16-le' if count < 0 else 'utf-8')
        except UnicodeDecodeError:
            raise invalid() from None


@dataclass(frozen=True)
class Entry:
    archive: str
    offset: int
    size: int
    raw_size: int
    method: int
    digest: bytes
    blocks: tuple
    block_size: int
    header_size: int


def _entry(cursor, archive):
    start = cursor.pos
    offset, size, raw_size, method = cursor.unpack('QQQI')
    digest = cursor.take(20)
    if method not in (0, 1):
        raise invalid('Unsupported Spyro pak compression.')
    blocks = tuple(cursor.unpack('QQ') for _ in range(cursor.count(100000))) if method else ()
    encrypted, block_size = cursor.unpack('BI')
    if encrypted or method and (not blocks or not 0 < block_size <= 16 * 1024 * 1024):
        raise invalid('Encrypted or unsupported Spyro pak entry.')
    return Entry(archive, offset, size, raw_size, method, digest, blocks,
                 block_size, cursor.pos - start)


class PakSet:
    def __init__(self, install):
        self.root = install / 'Falcon' / 'Content' / 'Paks'
        self.entries = {}
        for path in sorted(self.root.glob('pakchunk*.pak')):
            total = path.stat().st_size
            if total < 45:
                raise invalid()
            with path.open('rb') as stream:
                stream.seek(-45, 2)
                if stream.read(1) != b'\0':
                    raise invalid('Encrypted Spyro pak directory.')
                footer = Cursor(stream.read(44))
                magic, version, offset, size = footer.unpack('IIQQ')
                expected = footer.take(20)
                if (magic != 0x5A6F12E1 or version != 4 or size > 128 * 1024 * 1024
                        or offset + size != total - 45):
                    raise invalid('Unsupported Spyro pak archive.')
                stream.seek(offset)
                index = stream.read(size)
            if hashlib.sha1(index).digest() != expected:
                raise invalid('Spyro pak directory checksum failed.')
            cursor = Cursor(index)
            mount = cursor.string()
            if not mount.startswith('../../../'):
                raise invalid()
            mount = mount[len('../../../'):]
            for _ in range(cursor.count(1000000)):
                name = mount + cursor.string()
                parts = PurePosixPath(name).parts
                if not parts or name.startswith('/') or any(part in ('..', '.') or ':' in part or '\\' in part for part in parts):
                    raise invalid('Unsafe Spyro pak member name.')
                entry = _entry(cursor, path.name)
                if (entry.offset + entry.header_size + entry.size > offset
                        or any(not entry.offset + entry.header_size <= start < end <= offset for start, end in entry.blocks)
                        or entry.method == 0 and entry.size != entry.raw_size):
                    raise invalid('Spyro pak member exceeds archive bounds.')
                self.entries[name] = entry
            if cursor.pos != len(index):
                raise invalid()
        if not self.entries:
            raise PreparationFailure('spyro_missing_pack', 'Spyro pak archives are missing. Verify the game installation in Steam and select its game folder again.')

    def read(self, name, maximum=64 * 1024 * 1024):
        entry = self.entries.get(name)
        if entry is None or entry.raw_size > maximum:
            raise invalid('Spyro asset is missing or exceeds its size limit.')
        with (self.root / entry.archive).open('rb') as stream:
            stream.seek(entry.offset)
            header = _entry(Cursor(stream.read(entry.header_size)), entry.archive)
            # In-file headers store zero for their own offset.
            if any(getattr(header, field) != getattr(entry, field) for field in
                   ('size', 'raw_size', 'method', 'digest', 'blocks', 'block_size', 'header_size')):
                raise invalid('Spyro archive changed while reading.')
            if not entry.method:
                result = stream.read(entry.size)
            else:
                chunks = []
                remaining = entry.raw_size
                for start, end in entry.blocks:
                    stream.seek(start)
                    compressed = stream.read(end - start)
                    decoder = zlib.decompressobj()
                    try:
                        chunk = decoder.decompress(compressed, min(entry.block_size, remaining) + 1)
                    except zlib.error:
                        raise invalid('Spyro compressed asset is damaged.') from None
                    if (not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
                            or len(chunk) != min(entry.block_size, remaining)):
                        raise invalid('Spyro compressed asset has invalid bounds.')
                    remaining -= len(chunk)
                    chunks.append(chunk)
                result = b''.join(chunks)
        if len(result) != entry.raw_size:
            raise invalid('Spyro asset was truncated.')
        return result


def read_locres(data):
    cursor = Cursor(data)
    if cursor.take(16) != bytes.fromhex('0e147475674a03fc4a15909dc3377f1b') or cursor.unpack('B') != 1:
        raise invalid('Unsupported Spyro localization resource.')
    string_offset = cursor.unpack('Q')
    entries = {}
    for _ in range(cursor.count()):
        namespace = cursor.string()
        for _ in range(cursor.count()):
            key = namespace, cursor.string()
            value = cursor.unpack('II')
            if key in entries:
                raise invalid('Duplicate Spyro localization identity.')
            entries[key] = value
    if cursor.pos != string_offset:
        raise invalid()
    strings = [cursor.string() for _ in range(cursor.count())]
    if cursor.pos != len(data) or any(index >= len(strings) for _hash, index in entries.values()):
        raise invalid()
    return {key: (source_hash, strings[index]) for key, (source_hash, index) in entries.items()}


class Properties(Cursor):
    def __init__(self, data, names):
        super().__init__(data)
        self.names = names

    def name(self):
        index, number = self.unpack('II')
        if index >= len(self.names) or number > 1000000:
            raise invalid()
        name = self.names[index]
        return f'{name}_{number - 1}' if number else name

    def properties(self):
        result = {}
        for _ in range(10000):
            name = self.name()
            if name == 'None':
                return result
            kind = self.name()
            size, index = self.unpack('II')
            subtype, boolean = None, None
            if kind == 'StructProperty':
                subtype = self.name()
                self.take(16)
            elif kind == 'BoolProperty':
                boolean = self.unpack('B')
                if boolean not in (0, 1):
                    raise invalid()
            elif kind in ('ByteProperty', 'EnumProperty', 'ArrayProperty', 'SetProperty'):
                self.name()
            elif kind == 'MapProperty':
                self.name(); self.name()
            if self.unpack('B') != 0 or index != 0 or name in result:
                raise invalid()
            end = self.pos + size
            value = None
            if kind == 'TextProperty':
                _flags, history = self.unpack('IB')
                if history == 0:
                    value = (self.string(), self.string(), self.string())
                elif history != 255:
                    raise invalid('Unsupported Spyro text history.')
            elif kind == 'StructProperty' and subtype == 'SoftObjectPath':
                value = self.name(), self.string()
            elif kind == 'BoolProperty':
                value = bool(boolean)
            elif kind in ('ObjectProperty', 'IntProperty'):
                value = self.unpack('i')
            elif kind == 'FloatProperty':
                value = self.unpack('f')
            elif kind == 'NameProperty':
                value = self.name()
            else:
                self.take(size)
            if self.pos != end:
                raise invalid('Spyro property has invalid bounds.')
            result[name] = value
        raise invalid()


class Package:
    def __init__(self, data):
        cursor = Cursor(data)
        if cursor.unpack('Ii') != (0x9E2A83C1, -7):
            raise invalid('Unsupported Spyro cooked package.')
        if cursor.unpack('4I') != (0, 0, 0, 0):
            raise invalid('Unsupported Spyro package version.')
        self.header_size = cursor.unpack('I')
        cursor.string(); cursor.unpack('I')
        name_count, name_offset = cursor.unpack('II')
        cursor.take(8)
        export_count, export_offset, import_count, import_offset = cursor.unpack('4I')
        if max(name_count, export_count, import_count) > 100000 or self.header_size != len(data):
            raise invalid()
        cursor.pos = name_offset
        self.names = []
        for _ in range(name_count):
            self.names.append(cursor.string()); cursor.take(4)
        props = Properties(data, self.names)
        props.pos = import_offset
        self.imports = []
        for _ in range(import_count):
            package, kind = props.name(), props.name()
            outer, name = props.unpack('i'), props.name()
            self.imports.append((package, kind, outer, name))
        self.exports = []
        cursor.pos = export_offset
        for _ in range(export_count):
            start = cursor.pos
            class_index = cursor.unpack('i')
            cursor.take(24)
            size, offset = cursor.unpack('QQ')
            cursor.take(60)
            if cursor.pos != start + 104 or offset < self.header_size:
                raise invalid()
            self.exports.append((self.import_name(class_index), size, offset - self.header_size))

    def import_name(self, index):
        if not -len(self.imports) <= index < 0:
            raise invalid('Invalid Spyro table object reference.')
        return self.imports[-index - 1][3]

    def import_path(self, index):
        if not -len(self.imports) <= index < 0:
            raise invalid()
        _package, _kind, outer, name = self.imports[-index - 1]
        if outer == 0:
            return name
        return self.import_name(outer)

    def table(self, data):
        if len(self.exports) != 1 or self.exports[0][0] != 'DataTable':
            raise invalid('Unsupported Spyro dialogue table export.')
        _kind, size, offset = self.exports[0]
        if offset != 0 or size + 4 != len(data) or data[-4:] != bytes.fromhex('c1832a9e'):
            raise invalid()
        cursor = Properties(data[:size], self.names)
        header = cursor.properties()
        row_type = self.import_name(header.get('RowStruct', 0))
        if cursor.unpack('I') != 0:
            raise invalid()
        rows = {}
        for _ in range(cursor.count()):
            name = cursor.name()
            if name in rows:
                raise invalid('Duplicate Spyro dialogue row.')
            rows[name] = cursor.properties()
        if cursor.pos != size:
            raise invalid()
        return row_type, rows
