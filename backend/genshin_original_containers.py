"""Bounded original design catalog and named MiHoYoBinData object routing.

The caller authenticates whole publisher packages before decoding their container.
Only metadata and requested data objects are read; no Unity runtime is loaded.
Full catalog identities establish membership before shortened names are resolved.
"""
from dataclasses import dataclass
import hashlib
import re
import struct

from .hoyo_bootstrap_assets import object_ranges


MAX_DATA = 64 * 1024**2
MAX_ROWS = 2_000_000


def check(condition):
    if not condition:
        raise ValueError('Unsupported or ambiguous original Genshin design container.')


class Reader:
    def __init__(self, data):
        check(isinstance(data, bytes) and len(data) <= MAX_DATA)
        self.data, self.at = data, 0

    def take(self, size):
        check(type(size) is int and 0 <= size <= len(self.data) - self.at)
        start = self.at
        self.at += size
        return self.data[start:self.at]

    def number(self, kind='I'):
        return struct.unpack('<' + kind, self.take(struct.calcsize('<' + kind)))[0]

    def count(self, limit=MAX_ROWS):
        count = self.number()
        check(count <= limit)
        return count

    def string(self, limit=4096, aligned=False):
        value = self.take(self.count(limit)).decode('utf-8')
        if aligned:
            check(not any(self.take(-self.at % 4)))
        return value

    def end(self):
        check(self.at == len(self.data))


def asset_identity(path):
    """Native design-name identity; the hash is membership, not authentication."""
    check(isinstance(path, str) and 0 < len(path) <= 4096 and '\\' not in path
          and not path.startswith('/') and all(p not in ('', '.', '..') for p in path.split('/')))
    raw = (path + '.MiHoYoBinData').encode('ascii')
    # The owned native hash buffer starts at 256 and doubles until it fits.
    # Exact boundaries have no extra block; this is not multiple-of-256 padding.
    size = 256
    while size < len(raw):
        size *= 2
    raw += bytes(size - len(raw))
    return int.from_bytes(hashlib.md5(raw).digest()[:8], 'little')


def _bundle_identifier(packed):
    """ResourceIndex.GetResourceIdentifier: signed low 30 bits, then absolute."""
    value = packed & ((1 << 30) - 1)
    if value & (1 << 29):
        value -= 1 << 30
    return abs(value)


@dataclass(frozen=True)
class Location:
    bundle: int
    block: int
    group: int
    offset: int
    size: int

    @property
    def package(self):
        return f'blocks/{self.group:02d}/{self.block}.blk'


class DesignCatalog:
    """Strict complete catalog parse; unsupported entries cannot be resolved."""
    def __init__(self, payload):
        r = Reader(payload)
        self.type_extensions = {}
        for _ in range(r.count(10_000)):
            name, extension = r.string(), r.string()
            check(name and extension and name not in self.type_extensions
                  and '\0' not in name and '\0' not in extension)
            self.type_extensions[name] = extension
        self.assets = {}
        references = set()
        for _ in range(r.count()):
            identity, count = struct.unpack('<QB', r.take(9))
            check(identity not in self.assets)
            raw = r.take(count * 5)
            variants = tuple(struct.iter_unpack('<BI', raw))
            references.update(_bundle_identifier(packed) for _selector, packed in variants)
            flags, bundle = variants[0] if variants else (0, 0)
            # Preserve the existing tuple API; the first item is a variant count.
            self.assets[identity] = (count, flags, bundle, raw[5:])
        dependencies = r.count()
        self.header_words = (r.number(), r.number())
        for _ in range(dependencies):
            r.number()
            r.take(r.count() * 4)
        r.take(r.count() * 4)
        r.take(r.count() * 4)
        groups = {}
        for _ in range(r.count(65_536)):
            group = r.number()
            for _ in range(r.count(65_536)):
                block = r.number()
                r.take(2)
                check(block not in groups)
                groups[block] = group
        self.locations = {}
        for _ in range(r.count(65_536)):
            block = r.number()
            check(block in groups)
            for _ in range(r.count()):
                bundle, offset, size = struct.unpack('<III', r.take(12))
                check(bundle not in self.locations)
                self.locations[bundle] = Location(bundle, block, groups[block], offset, size)
        r.take(r.count() * 4)
        r.end()
        check(references <= self.locations.keys())
        self.names = {}
        for identity, row in self.assets.items():
            alternatives = struct.iter_unpack('<BI', row[3])
            bundles = {_bundle_identifier(packed) for _selector, packed in alternatives}
            if row[0]:
                bundles.add(_bundle_identifier(row[2]))
            for bundle in bundles:
                self.names.setdefault((bundle, (identity >> 8) & 0xffffffff), []).append(identity)
        self.sha256 = hashlib.sha256(payload).hexdigest()

    def locate(self, identity):
        check(type(identity) is int and identity in self.assets)
        count, _selector, packed, _alternatives = self.assets[identity]
        bundle = _bundle_identifier(packed)
        # A current platform-selector contract is required before choosing among
        # alternatives, including alternatives which happen to share a bundle.
        check(count == 1 and bundle in self.locations
              and len(self.names[bundle, (identity >> 8) & 0xffffffff]) == 1)
        return self.locations[bundle]


class DataObjects:
    """Metadata-only named-object view over an authenticated decoded bundle."""
    def __init__(self, size, read):
        self.size, self.read = size, read
        rows = object_ranges(size, read)
        self.objects = {int(row['id']): row for row in rows}
        maps = [row for row in rows if row['kind'] == 1210]
        check(len(maps) == 1)
        r = Reader(self._body(maps[0]))
        self.name = r.string(512, aligned=True)
        self.names = {}
        for _ in range(r.count(300_000)):
            name = r.string(512, aligned=True)
            file_id, path_id, declared = struct.unpack('<iqQ', r.take(20))
            self.names.setdefault(name, []).append((file_id, path_id, declared))
        r.end()

    def _body(self, row):
        check(0 < row['size'] <= MAX_DATA and 0 <= row['offset'] <= self.size - row['size'])
        body = self.read(row['offset'], row['size'])
        check(isinstance(body, bytes) and len(body) == row['size'])
        return body

    def named(self, name):
        """Used also for the original catalog root's independently owned name."""
        check(isinstance(name, str) and re.fullmatch('[a-f0-9]{8}', name))
        entries = self.names.get(name, ())
        check(len(entries) == 1)
        file_id, path_id, declared = entries[0]
        check(file_id == 0 and path_id in self.objects)
        row = self.objects[path_id]
        check(row['kind'] == 1208)
        raw = self._body(row)
        check(len(raw) >= 4)
        length = struct.unpack_from('<I', raw)[0]
        check(length == declared and 4 + length <= len(raw)
              and (4 + length + 3) // 4 * 4 == len(raw) and not any(raw[4 + length:]))
        return raw[4:4 + length]

    def resolve(self, catalog, identity, bundle):
        check(isinstance(catalog, DesignCatalog) and catalog.locate(identity).bundle == bundle)
        # The original catalog's full 64-bit identity must own this bundle first.
        return self.named(f'{(identity >> 8) & 0xffffffff:08x}')
