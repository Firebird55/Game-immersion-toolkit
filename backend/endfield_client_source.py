"""Read the selected publisher client as bounded, inert metadata.

Ranges are HTTPS source evidence, not a claim that the complete native file was
hashed. A parameter candidate still needs the original VFS CRC/schema gate.
Nothing in this module loads or executes a game library.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from .endfield_private_cache import atomic_bytes as _atomic_file

MAX_CLIENT = 512 * 1024**2
MAX_METADATA = 192 * 1024**2
MAX_RANGE = 64 * 1024**2


def check(condition, reason='Unsupported or incomplete original Endfield client metadata.'):
    if not condition:
        raise ValueError(reason)


def client_identity(latest, *, region, cdn):
    """Keep the original launcher artifact declarations, never a latest alias."""
    check(region in {'global', 'cn'} and isinstance(latest, dict))
    version, package = latest.get('version'), latest.get('pkg', {})
    check(isinstance(version, str) and re.fullmatch(r'\d+\.\d+\.\d+', version))
    base, digest = package.get('file_path'), package.get('game_files_md5')
    channel = {'global': 6, 'cn': 1}[region]
    check(isinstance(base, str) and len(base) <= 512 and re.fullmatch(re.escape(cdn) + '/' +
          re.escape(version.rsplit('.', 1)[0]) + f'/update/{channel}/{channel}/Windows/' +
          re.escape(version) + r'_[A-Za-z0-9]+/files', base))
    check(isinstance(digest, str) and re.fullmatch('[0-9a-f]{32}', digest))
    packs = package.get('packs')
    check(isinstance(packs, list) and 1 <= len(packs) <= 256)
    artifacts = []
    for pack in packs:
        url, md5, size = pack.get('url'), pack.get('md5'), pack.get('package_size')
        check(isinstance(url, str))
        parts = urlsplit(url)
        check(not parts.fragment and not parts.username and not parts.password)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
        check(url.startswith(base[:-6] + '/packs/') and
              re.fullmatch(re.escape(base[:-6]) + r'/packs/[A-Za-z0-9_.-]+', url))
        check(isinstance(md5, str) and re.fullmatch('[0-9a-f]{32}', md5))
        check(isinstance(size, (str, int)) and str(size).isdigit() and 0 < int(size) <= 4 * 1024**3)
        artifacts.append({'url': url, 'md5': md5, 'bytes': int(size)})
    return {'schema': 1, 'region': region, 'version': version, 'url': base,
            'game_files_md5': digest, 'artifacts': artifacts}


def identity_stamp(identity):
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Ranges:
    """Immutable URL/declared-artifact-bound cache with exact range receipts."""

    def __init__(self, tools, identity, relative, *, opener=None):
        check(relative in {'GameAssembly.dll', 'Endfield_Data/il2cpp_data/Metadata/global-metadata.dat'})
        self.identity, self.relative = identity, relative
        self.url = identity['url'] + '/' + relative
        self.maximum = MAX_CLIENT if relative.endswith('.dll') else MAX_METADATA
        self.root = Path(tools) / 'endfield-client-metadata' / identity_stamp(identity) / Path(relative).name
        self.opener = opener or urllib.request.urlopen
        self.size, self.etag = None, None
        self.receipts = []

    def read(self, offset, length):
        check(type(offset) is type(length) is int and 0 <= offset < self.maximum and
              0 < length <= self.maximum - offset)
        if length > MAX_RANGE:
            return b''.join(self.read(offset + at, min(MAX_RANGE, length - at))
                            for at in range(0, length, MAX_RANGE))
        name = f'{offset}-{length}'
        receipt, path = self.root / (name + '.json'), self.root / (name + '.bin')
        try:
            item = json.loads(receipt.read_bytes())
            check(item['source'] == identity_stamp(self.identity) and item['url'] == self.url and
                  item['offset'] == offset and item['bytes'] == length and
                  0 < item['total'] <= self.maximum)
            raw = path.read_bytes()
            check(len(raw) == length and hashlib.sha256(raw).hexdigest() == item['sha256'])
        except (OSError, ValueError, KeyError, TypeError):
            end = offset + length - 1
            headers = {'Range': f'bytes={offset}-{end}', 'Accept-Encoding': 'identity'}
            if self.etag:
                headers['If-Range'] = self.etag
            request = urllib.request.Request(self.url, headers=headers)
            with self.opener(request, timeout=45) as response:
                match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                check(response.status == 206 and response.geturl() == self.url and match and
                      int(match[1]) == offset and int(match[2]) == end and
                      end < int(match[3]) <= self.maximum and
                      int(response.headers.get('Content-Length', '-1')) == length)
                total, etag = int(match[3]), response.headers.get('ETag')
                check(self.size is None or self.size == total, 'Original client size changed during preparation.')
                check(self.size is None or self.etag == etag, 'Original client identity changed during preparation.')
                raw = response.read(length + 1)
                check(len(raw) == length)
            item = {'source': identity_stamp(self.identity), 'url': self.url, 'offset': offset,
                    'bytes': length, 'total': total, 'etag': etag,
                    'sha256': hashlib.sha256(raw).hexdigest(), 'whole_file_hash_verified': False}
            _atomic_file(path, raw)
            _atomic_file(receipt, json.dumps(item, sort_keys=True).encode())
        check(self.size is None or self.size == item['total'])
        check(self.size is None or self.etag == item['etag'])
        self.size, self.etag = item['total'], item['etag']
        self.receipts.append(item)
        return raw


def metadata_sections(source):
    header = struct.unpack('<64I', source.read(0, 256))
    check(header[:2] == (0xfab11baf, 29))
    sections = {name: header[index:index + 2] for name, index in
                [('literals', 2), ('literal_data', 4), ('strings', 6),
                 ('methods', 12), ('parameters', 22), ('fields', 24),
                 ('types', 40), ('images', 42)]}
    for offset, count in sections.values():
        check(256 <= offset <= MAX_METADATA and 0 < count <= MAX_METADATA and offset + count <= MAX_METADATA)
    return sections


class Metadata:
    """The evidenced IL2CPP29 tables; field/method ownership is always authored."""

    def __init__(self, source):
        self.source = source
        self.sections = metadata_sections(source)
        self.strings = self.table('strings')
        self.types, self.methods, self.images = self.table('types'), self.table('methods'), self.table('images')
        check(len(self.types) % 92 == len(self.methods) % 32 == len(self.images) % 40 == 0)
        self.type_count = len(self.types) // 92
        self._literals = self._literal_data = None
        self.owners = {}
        for index in range(self.type_count):
            row = self.type(index)
            name = self.string(row[1]) + '.' + self.string(row[0])
            self.owners.setdefault(name, []).append(index)

    def owner(self, name):
        values = self.owners.get(name, [])
        check(len(values) == 1, 'Original type identity is missing or ambiguous.')
        return values[0]

    def table(self, name):
        return self.source.read(*self.sections[name])

    def string(self, index):
        check(type(index) is int and 0 <= index < len(self.strings))
        end = self.strings.find(b'\0', index, min(len(self.strings), index + 4096))
        check(end >= index)
        return self.strings[index:end].decode('utf-8', 'strict')

    def type(self, index):
        check(type(index) is int and 0 <= index < len(self.types) // 92)
        return struct.unpack_from('<23I', self.types, index * 92)

    def type_name(self, index):
        row = self.type(index)
        return self.string(row[1]) + '.' + self.string(row[0])

    def methods_named(self, owner, name, parameters=None):
        index = self.owner(owner)
        row = self.type(index)
        start, count = row[9], row[17] & 0xffff
        check(start + count <= len(self.methods) // 32)
        found = []
        for number in range(start, start + count):
            values = struct.unpack_from('<6I4H', self.methods, number * 32)
            check(values[1] == index and values[5] >> 24 == 6)
            if self.string(values[0]) == name and (parameters is None or values[-1] == parameters):
                found.append({'index': number, 'owner': owner, 'name': name, 'type': index,
                              'token': values[5], 'parameters': values[-1], 'return_type': values[2]})
        return found

    def method(self, owner, name, parameters=None):
        found = self.methods_named(owner, name, parameters)
        check(len(found) == 1, 'Original method ownership is missing or ambiguous.')
        return found[0]

    def fields(self, owner):
        row = self.type(self.owner(owner))
        start, count = row[8], row[18] & 0xffff
        offset, size = self.sections['fields']
        check(count <= 512 and (start + count) * 12 <= size)
        raw = self.source.read(offset + start * 12, count * 12)
        result = {}
        for ordinal, (name, type_index, token) in enumerate(struct.iter_unpack('<3I', raw)):
            name = self.string(name)
            check(name not in result and token >> 24 == 4)
            result[name] = {'type': type_index, 'ordinal': ordinal, 'index': start + ordinal, 'token': token}
        return result

    def literal(self, index):
        if self._literals is None:
            self._literals, self._literal_data = self.table('literals'), self.table('literal_data')
        check(type(index) is int and 0 <= index < len(self._literals) // 8)
        length, start = struct.unpack_from('<II', self._literals, index * 8)
        check(0 < length <= 4096 and start + length <= len(self._literal_data))
        return self._literal_data[start:start + length].decode('utf-8', 'strict')


class Image:
    """Sparse original PE32+ with chained-unwind ownership; no executable mapping."""

    def __init__(self, source, *, read_tables=True):
        self.source = source
        raw = source.read(0, 4096)
        check(raw[:2] == b'MZ')
        pe, = struct.unpack_from('<I', raw, 0x3c)
        check(0x40 <= pe <= 2048 and raw[pe:pe + 4] == b'PE\0\0')
        machine, count = struct.unpack_from('<HH', raw, pe + 4)
        optional_size, = struct.unpack_from('<H', raw, pe + 20)
        optional = pe + 24
        check(machine == 0x8664 and 1 <= count <= 32 and 240 <= optional_size <= 512 and
              optional + optional_size + count * 40 <= len(raw))
        magic, = struct.unpack_from('<H', raw, optional)
        self.base, = struct.unpack_from('<Q', raw, optional + 24)
        check(magic == 0x20b and self.base > 0 and self.base % 4096 == 0)
        self.sections, self.code_sections, file_ranges, virtual_ranges = {}, set(), [], []
        for index in range(count):
            name, virtual, address, size, offset = struct.unpack_from('<8sIIII', raw, optional + optional_size + index * 40)
            flags, = struct.unpack_from('<I', raw, optional + optional_size + index * 40 + 36)
            name = name.rstrip(b'\0').decode('ascii')
            check(name and name not in self.sections and 0 <= size <= MAX_RANGE * 4 and
                  offset + size <= MAX_CLIENT and address + max(size, virtual) <= 2**32)
            check(all(offset + size <= begin or end <= offset for begin, end in file_ranges) and
                  all(address + max(size, virtual) <= begin or end <= address for begin, end in virtual_ranges),
                  'Overlapping original PE sections.')
            if size:
                file_ranges.append((offset, offset + size))
            virtual_ranges.append((address, address + max(size, virtual)))
            self.sections[name] = (address, virtual, offset, size)
            if flags & 0x20000000:
                self.code_sections.add(name)
        self.buffers = {name: source.read(row[2], row[3]) for name, row in self.sections.items()
                        if read_tables and name in {'.rdata', '.data'} and row[3]}
        check({'.rdata', '.data'} <= self.sections.keys() and
              (not read_tables or set(self.buffers) == {'.rdata', '.data'}))
        # The publisher image retains its original IL2CPP unwind records in
        # .pdata; its runtime exception directory can address a different table.
        # Verify every chosen record against the metadata-selected method root.
        check('.pdata' in self.sections)
        self.pdata_rva, self.pdata_size, self.pdata_offset, _ = self.sections['.pdata']
        check(0 < self.pdata_size <= 24 * 1024**2 and self.pdata_size % 12 == 0)
        check(self.pdata_offset == self.offset(self.base + self.pdata_rva, self.pdata_size))
        self._pdata = {}

    def offset(self, address, length):
        rva = address - self.base
        matches = [offset + rva - begin for begin, virtual, offset, size in self.sections.values()
                   if begin <= rva and rva + length <= begin + size]
        check(len(matches) == 1)
        return matches[0]

    def read(self, address, length):
        for name, raw in self.buffers.items():
            offset = address - self.base - self.sections[name][0]
            if 0 <= offset <= len(raw) - length:
                return raw[offset:offset + length]
        return self.source.read(self.offset(address, length), length)

    def data_read(self, address, length):
        for name, raw in self.buffers.items():
            offset = address - self.base - self.sections[name][0]
            if 0 <= offset <= len(raw) - length:
                return raw[offset:offset + length]
        raise ValueError('Original metadata pointer leaves its declared static data tables.')

    def read_code(self, address, length):
        check(any(self.base + self.sections[name][0] <= address and
                  address + length <= self.base + self.sections[name][0] + self.sections[name][3]
                  for name in self.code_sections), 'Original method leaves its executable PE section.')
        return self.source.read(self.offset(address, length), length)

    def q(self, address):
        return struct.unpack('<Q', self.data_read(address, 8))[0]

    def occurrences(self, needle):
        for name, raw in self.buffers.items():
            at = 0
            while (at := raw.find(needle, at)) >= 0:
                yield self.base + self.sections[name][0] + at
                at += 1

    def boundary(self, address):
        low, high = 0, self.pdata_size // 12 - 1
        for _ in range(22):
            check(low <= high, 'Original method has no unwind boundary.')
            index = (low + high) // 2
            if index not in self._pdata:
                self._pdata[index] = struct.unpack('<3I', self.source.read(self.pdata_offset + index * 12, 12))
            begin, end, unwind = self._pdata[index]
            check(0 < begin < end <= MAX_CLIENT and unwind)
            if address - self.base < begin:
                high = index - 1
            elif address - self.base >= end:
                low = index + 1
            else:
                return begin, end, unwind
        raise ValueError('Original unwind boundary search exceeded its bound.')

    def unwind_owner(self, entry):
        begin, end, unwind = entry
        seen = set()
        while True:
            check(unwind not in seen and len(seen) < 16)
            seen.add(unwind)
            header = self.data_read(self.base + unwind, 4)
            check(header[0] & 7 == 1)
            if header[0] >> 3 & 4:
                begin, end, unwind = struct.unpack('<3I', self.data_read(self.base + unwind +
                        4 + ((header[2] + 1) // 2) * 4, 12))
            else:
                return self.base + begin
