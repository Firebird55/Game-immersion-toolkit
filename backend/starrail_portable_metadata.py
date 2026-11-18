# SPDX-License-Identifier: GPL-3.0-or-later
"""Read selected original Star Rail metadata records from publisher-owned files.

The format descriptions are adapted from HSRGlobalMetadata at
bb66f7c59d73cadcd026d817a011598ea23c5313. See docs/game-audits/starrail.md
for provenance and the remaining runtime type and provider requirements.
"""

from bisect import bisect_right
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import struct

from .prebuilt_readers import _no_links
from .starrail_metadata import _graph_pe


_MAGIC = b'MHY\0'
_HEADER_SIZE = 0x208
_BLOCK = 256 * 1024
_MASK32 = (1 << 32) - 1
_MASK64 = (1 << 64) - 1
_MAX_INDEX = 1 << 24
_MAX_SELECTED = 8192
_MAX_PARAMETERS = 64
_MAX_SELECTED_PARAMETERS = 65536
_MAX_LITERAL = 64 * 1024
_LIMITS = {'native': 1024**3, 'metadata': 512 * 1024**2, 'startup': 64 * 1024**2}

# Image and generic-class offsets refer to startup metadata. The global
# table envelopes use the global payload coordinates after its file prefix.
_OFFSETS = {
    'literal_data': (0x08, -149860775),
    'attribute_ranges': (0x18, -422736276),
    'fields': (0x20, -1292050039),
    'parameters': (0x30, -587858498),
    'default_data': (0x3c, -1752438875),
    'properties': (0x40, 0x3c685cdb),
    'types': (0x84, 0x68531d3f),
    'index_table': (0x9c, -1132541481),
    'generic_methods': (0xec, 0x67f701ba),
    'generic_containers': (0xf0, -1656188401),
    'nested_types': (0x12c, 0x26f0fc20),
    'generic_constraints': (0x130, -22792381),
    'generic_parameters': (0x140, -626232567),
    'field_offsets': (0x148, 0x329e1172),
    'methods': (0x14c, -207601004),
    'images': (0x150, -662544034),
    'assemblies': (0x158, -532747583),
    'generic_classes': (0x164, 0x7f5c5934),
    'type_index_map': (0x180, -455350429),
    'events': (0x1ac, 0x37080d6e),
    'strings': (0x1b4, -1924946706),
    'interfaces': (0x1c8, 0x42f9275),
    'attribute_types': (0x1ec, -1487263151),
    'literals': (0x1f0, 0x56c7d20d),
    'field_defaults': (0x1fc, 0x6238cdb0),
}
# Seven complete RIP-relative instructions and the final store's opcode.
_HEADER = re.compile(re.escape(_MAGIC))
_REGISTRATION = re.compile(rb'(?:\x48\x8d\x05.{4}\x48\x89\x05.{4}){3}\x48\x8d\x05.{4}\x48\x89\x05',
                           re.DOTALL)
_REGISTRATION_SIZE = 52


class MetadataFormatError(ValueError):
    def __init__(self, component):
        super().__init__(f'Invalid original Star Rail metadata ({component}).')
        self.component = component


class MetadataCancelled(ValueError):
    """The caller cancelled this read before a complete result was returned."""


@dataclass(frozen=True, slots=True)
class OriginalInput:
    path: Path
    size: int
    md5: str
    sha256: str | None = None


def _require(condition, component):
    if not condition:
        raise MetadataFormatError(component)


def _check_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise MetadataCancelled('Original Star Rail metadata reading was cancelled.')


def _integer(data, offset, width=4, *, signed=False):
    return int.from_bytes(data[offset:offset + width], 'little', signed=signed)


def _signed(value, bits=32):
    return (value ^ (1 << (bits - 1))) - (1 << (bits - 1))


def _stamp(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _collect_offsets(offsets, data, at, *, seam=0):
    for pattern, matches in offsets.items():
        position = 0
        while match := pattern.search(data, position):
            position = match.start() + 1
            if not seam or match.start() < seam < match.end():
                _require(len(matches) < 64, 'locator candidates')
                matches.append(at + match.start())


class _Source:
    def __init__(self, stack, role, value, cancelled):
        _require(isinstance(value, OriginalInput) and type(value.size) is int
                 and 0 < value.size <= _LIMITS[role] and isinstance(value.md5, str)
                 and re.fullmatch(r'[0-9a-f]{32}', value.md5)
                 and (value.sha256 is None or (isinstance(value.sha256, str)
                      and re.fullmatch(r'[0-9a-f]{64}', value.sha256))), f'{role} identity')
        self.path = Path(value.path).absolute()
        _no_links(self.path)
        info = self.path.stat()
        _require(stat.S_ISREG(info.st_mode) and info.st_size == value.size, f'{role} file')
        self.stream = stack.enter_context(self.path.open('rb'))
        self.size = value.size
        self.role = role
        self.path_stamp = _stamp(info)
        self.handle_stamp = _stamp(os.fstat(self.stream.fileno()))
        # Windows can expose different creation timestamps for path and handle
        # queries. Track each independently and compare their common identity.
        _require(self.path_stamp[:4] == self.handle_stamp[:4], f'{role} file changed')
        self.check_source()
        md5 = hashlib.md5()
        sha256 = hashlib.sha256()
        offsets = {_HEADER: [], _REGISTRATION: []} if role == 'native' else {}
        tail = b''
        overlap = _REGISTRATION_SIZE - 1
        for at in range(0, self.size, _BLOCK):
            _check_cancelled(cancelled)
            block = self.read(at, min(self.size - at, _BLOCK))
            md5.update(block)
            sha256.update(block)
            if offsets:
                # Collect untrusted offsets only. Interpret PE mappings and
                # records through this handle after whole-file authentication.
                if tail:
                    _collect_offsets(offsets, tail + block[:overlap], at - len(tail), seam=len(tail))
                _collect_offsets(offsets, block, at)
                tail = block[-overlap:]
        _require(md5.hexdigest() == value.md5, f'{role} publisher digest')
        self.sha256 = sha256.hexdigest()
        _require(value.sha256 is None or self.sha256 == value.sha256, f'{role} source receipt digest')
        self.check_source()
        self.candidates = offsets

    def check_source(self):
        _no_links(self.path)
        _require(_stamp(os.fstat(self.stream.fileno())) == self.handle_stamp
                 and _stamp(self.path.stat()) == self.path_stamp,
                 f'{self.role} file changed')

    def read(self, at, size, *, component=None):
        component = component or self.role
        _require(0 <= size <= _BLOCK and 0 <= at <= self.size - size, component)
        self.stream.seek(at)
        data = self.stream.read(size)
        _require(len(data) == size, component)
        return data


class _Image:
    def __init__(self, source):
        self.source = source
        try:
            self.base, sections, _, _ = _graph_pe(source.stream)
        except (ValueError, struct.error) as error:
            raise MetadataFormatError('PE mapping') from error
        self.sections = tuple(section for section in sections if section[1])
        for column in (0, 2):
            intervals = sorted((section[column], section[column] + section[1]) for section in self.sections)
            _require(intervals and intervals[0][0] > 0 and all(
                a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), 'PE section overlap')
        _require(0 < self.base <= _MASK64 - _MASK32, 'PE image base')

    def offset(self, rva, size, *, executable):
        hits = [offset + rva - start for start, length, offset, code in self.sections
                if code == executable and 0 < size <= length and start <= rva <= start + length - size]
        _require(len(hits) == 1, 'PE address ownership')
        return hits[0]

    def matches(self, pattern, width, *, executable, cancelled):
        for at in self.source.candidates[pattern]:
            _check_cancelled(cancelled)
            for rva, length, start, code in self.sections:
                if code == executable and start <= at <= start + length - width:
                    yield rva + at - start, at


def _unique(values, component):
    result = None
    for value in values:
        _require(result is None, component)
        result = value
    _require(result is not None, component)
    return result


def _header(image, metadata, startup, cancelled):
    def candidates():
        for _, at in image.matches(_HEADER, _HEADER_SIZE, executable=False, cancelled=cancelled):
            try:
                data = image.source.read(at, _HEADER_SIZE)
                _require(data[:4] == _MAGIC, 'header magic')
                offsets = {}
                for name, (position, operand) in _OFFSETS.items():
                    raw = _integer(data, position)
                    offsets[name] = (raw + operand) & _MASK32 if operand < 0 else raw ^ operand
                image_at = offsets.pop('images')
                # Il2CppType.ComputeName reads generic-class rows from
                # StartupMetadata. Its offset cannot delimit a global table.
                generic_class_at = offsets.pop('generic_classes')
                _require(generic_class_at <= startup.size, 'startup generic-class offset')
                payload = metadata.size - _HEADER_SIZE
                _require(all(offset <= payload for offset in offsets.values()), 'header offsets')
                type_size = _integer(data, 0x1a8) ^ 0x729b1a9e
                image_size = _integer(data, 0x134) ^ 0x10210728
                # The pinned reader counts complete records. The declared byte
                # sizes can include trailing bytes that are outside those rows.
                type_count, image_count = type_size // 70, image_size // 40
                _require(0 < type_count <= _MAX_INDEX, 'header type count')
                _require(0 < image_count <= 4096 and image_at <= startup.size - image_count * 40,
                         'header image range')
                stops = sorted({*offsets.values(), payload})
                windows = {name: (offset, stops[bisect_right(stops, offset)] - offset if offset < payload else 0)
                           for name, offset in offsets.items()}
                _require(type_count * 70 <= windows['types'][1], 'type table ownership')
                windows['types'] = offsets['types'], type_count * 70
            except MetadataFormatError:
                continue
            yield windows, image_at, image_count
    return _unique(candidates(), 'metadata header locator')


def _registrations(image, cancelled):
    def candidates():
        for rva, at in image.matches(_REGISTRATION, 56, executable=True, cancelled=cancelled):
            try:
                data = image.source.read(at, _REGISTRATION_SIZE)
                _require(_REGISTRATION.fullmatch(data), 'registration signature')
                def target(position, size):
                    disp = _integer(data, position + 3, signed=True)
                    return image.source.read(image.offset(rva + position + 7 + disp, size, executable=False), size)

                code = target(0, 0x100)
                metadata = target(14, 0x100)
                tables = target(28, 0x68)
                type_count = (_integer(metadata, 0x48) - 1455078204) & _MASK32
                types = _integer(metadata, 0x80, 8) - image.base
                method_pointers = _integer(code, 0x40, 8) - image.base
                literal_count = _integer(tables, 0x2c) ^ 0x0bd08dc8
                _require(0 < type_count < _MAX_INDEX and 0 <= literal_count < _MAX_INDEX, 'registration counts')
                image.offset(types, type_count * 8, executable=False)
                image.offset(method_pointers, 8, executable=False)
            except MetadataFormatError:
                continue
            yield type_count, method_pointers, literal_count
    return _unique(candidates(), 'registration locator')


def _xor_words(data, length, key, step):
    result = bytearray(len(data))
    for at in range(0, len(data), 8):
        result[at:at + 8] = (_integer(data, at, 8) ^ key).to_bytes(8, 'little')
        key = (key + step) & _MASK64
    try:
        return result[:length].decode('utf-8')
    except UnicodeError as error:
        raise MetadataFormatError('metadata UTF-8') from error


class _Records:
    def __init__(self, files, cancelled):
        self.metadata = files['metadata']
        self.startup = files['startup']
        self.image = _Image(files['native'])
        _require(self.metadata.size >= _HEADER_SIZE and self.metadata.read(0, 4) == _MAGIC, 'global metadata prefix')
        self.windows, images_at, image_count = _header(self.image, self.metadata, self.startup, cancelled)
        self.type_count, self.method_pointers, self.literal_count = _registrations(self.image, cancelled)
        self.definition_count = self.windows['types'][1] // 70
        _require((self.literal_count + 1) * 4 <= self.windows['literals'][1], 'literal index ownership')
        self.images = []
        for index in range(image_count):
            data = self.startup.read(images_at + 40 * index, 40)
            key = (((302843651 * ((57468 * index) ^ 0x7538159e)) ^ 0x6032c9d3) + 784007301) & _MASK32
            start = _integer(data, 0x14) ^ 0x7babeea0 ^ key ^ 0x235aeaf5
            count = _integer(data, 0x04) ^ 0x10fea394 ^ key ^ 0x7c06d18c
            _require(count <= self.definition_count and (count == 0 or start <= self.definition_count - count),
                     'image type range')
            if count:
                name = self.name(_integer(data, 0x0c) ^ 0x4d648371 ^ key)
                _require(name, 'image name')
                self.images.append((start, start + count, index, name))
        self.images.sort()
        _require(self.images and all(a[1] <= b[0] for a, b in zip(self.images, self.images[1:])), 'image type overlap')
        self.image_starts = tuple(image[0] for image in self.images)

    def read(self, role, at, size):
        start, length = self.windows[role]
        _require(0 <= size <= length and 0 <= at <= length - size, f'{role} record ownership')
        return self.metadata.read(_HEADER_SIZE + start + at, size, component=role)

    def name(self, index):
        if index == _MASK32:
            return ''
        large = index >> 31
        at = index & (0x7fffff if large else 0x1ffffff)
        size = (index >> 23) & 0xff if large else (index >> 25) & 0x3f
        if not size:
            return ''
        key = (0x907c49622d94d21a * at + 0x75b679daf67c3f24) & _MASK64
        value = _xor_words(self.read('strings', at, (size + 7) & ~7), size, key, 0x3e693cd23a41fdef)
        _require('\0' not in value, 'metadata name')
        return value

    def type(self, index):
        _require(index < self.definition_count, 'type definition index')
        data = self.read('types', index * 70, 70)
        owner = bisect_right(self.image_starts, index) - 1
        _require(owner >= 0 and index < self.images[owner][1], 'type image ownership')
        _, _, image_index, image = self.images[owner]
        name = self.name((_integer(data, 0x28) - 369268488) & _MASK32)
        _require(name, 'type name')
        return {'name': name, 'namespace': self.name((_integer(data, 0x24) - 237818487) & _MASK32),
                'image': image, 'image_index': image_index,
                'parent': _signed((_integer(data, 0x04) - 1224299847) & _MASK32),
                'declaring_type': _signed((_integer(data, 0x0c) - 472568492) & _MASK32),
                'flags': (_integer(data, 0x14) - 17986448) & _MASK32,
                'field_start': _signed((_integer(data, 0x20) - 1954887780) & _MASK32),
                'field_count': (_integer(data, 0x32, 2) + 17485) & 0xffff,
                'method_start': _signed(_integer(data, 0x08) ^ 0x1a7af5fe),
                'method_count': (_integer(data, 0x34, 2) + 24467) & 0xffff,
                'nested_start': _signed(_integer(data, 0x3a, 2) ^ 0xb2c0, 16),
                'nested_count': (_integer(data, 0x43, 1) + 4) & 0xff,
                'generic_container': _signed((_integer(data, 0x3c, 2) - 44028) & 0xffff, 16)}

    def field(self, index, owner_index, owner):
        raw = self.read('fields', index * 8, 8)
        key = -1388221511 - 744344320 * (index + 1954887780)
        type_index = (_integer(raw, 4) + key) & _MASK32
        _require(type_index < self.type_count, 'field type index')
        mapped = _integer(self.read('type_index_map', owner_index * 4, 4), 0)
        offset_index = _integer(self.read('index_table', mapped * 12 + 8, 4), 0)
        offset = _integer(self.read('field_offsets', (offset_index + index - owner['field_start']) * 4, 4), 0)
        name = self.name((_integer(raw, 0) + 716162949 + key) & _MASK32)
        _require(name, 'field name')
        return {'owner': owner_index, 'type': type_index, 'name': name, 'offset': offset}

    def method(self, index, types, remaining_parameters):
        raw = self.read('methods', index * 26, 26)
        factor = (738455933 * ((12769 * index) ^ 0x33914937)) & _MASK64
        key = (((1410124276 * (factor >> 23)) & _MASK64) >> 21) + 1908176993
        key &= _MASK32
        owner_index = _integer(raw, 0x10) ^ 0x2a5fabe8 ^ key
        if owner_index not in types:
            types[owner_index] = self.type(owner_index)
        owner = types[owner_index]
        _require(0 <= owner['method_start'] <= index < owner['method_start'] + owner['method_count'], 'method type ownership')
        return_type = ((_integer(raw, 0x08) - 1698564893) & _MASK32) ^ key
        _require(return_type < self.type_count, 'method return type')
        start = _integer(raw, 0x04) ^ 0x9889b8 ^ key
        count = _integer(raw, 0x18, 1) ^ 0xa8 ^ (key & 0xff)
        _require(count <= _MAX_PARAMETERS and count <= remaining_parameters, 'method parameter count')
        if count:
            _require(start < _MAX_INDEX and count <= _MAX_INDEX - start, 'method parameter range')
        parameter_rows = tuple(self.parameter(i) for i in range(start, start + count))
        flags = _integer(raw, 0x0c)
        flags = ((flags >> 16) | ((flags << 16) & _MASK32)) ^ ((key & 0xffff) * 0x10001) ^ 0x09f73733
        pointer_at = self.image.offset(self.method_pointers + index * 8, 8, executable=False)
        pointer = _integer(self.image.source.read(pointer_at, 8), 0, 8)
        rva = 0
        if pointer:
            rva = pointer - self.image.base
            self.image.offset(rva, 1, executable=True)
        name = self.name(_integer(raw, 0) ^ 0x0e714bc1 ^ key)
        _require(name, 'method name')
        return {'owner': owner_index, 'name': name, 'return_type': return_type, 'flags': flags,
                'generic_container': _signed(((_integer(raw, 0x14, 2) - 30979) ^ key) & 0xffff, 16),
                'parameters': parameter_rows, 'rva': rva}

    def parameter(self, index):
        raw = self.read('parameters', index * 8, 8)
        key = 1488482466 * (((0x72e1d74b12b * index + 0x1911d05aff5) & _MASK64) >> 11) - 2083554492
        type_index = ((_integer(raw, 0) ^ 0x67e90dc5) - key) & _MASK32
        _require(type_index < self.type_count, 'parameter type index')
        return type_index, self.name(((_integer(raw, 4) ^ 0x7103092e) - key) & _MASK32)

    def literal(self, index):
        _require(index < self.literal_count, 'literal index')
        raw = self.read('literals', index * 4, 8)
        def offset(entry, i):
            factor = (0x32c1cf25bb14 * i + 0x1f0fe259cf0538) & _MASK64
            key = ((604527770 * (factor >> 14)) & _MASK64) >> 8
            return _signed((entry - key) & _MASK32) + 1004094107

        at = offset(_integer(raw, 0), index)
        length = offset(_integer(raw, 4), index + 1) - at
        _require(0 <= length <= _MAX_LITERAL, 'literal length')
        key = (((0xde8c09c836133dbd * index) ^ 0x18d025c96ee74e86) + 0x2c6833cc6f0a9c48) & _MASK64
        # The pinned SIMD offsets equal two, four, six, and eight scalar steps.
        return _xor_words(self.read('literal_data', at, (length + 7) & ~7), length, key, 0x464c46540f730312)


def read_required(inputs, *, type_indices=(), method_indices=(), literal_indices=(), cancelled=None):
    """Authenticate all three original inputs and return selected raw records.

    A requested type includes its fields. Methods independently identify their
    defining type and validate membership in that type's method range. Member
    type indices and nesting are preserved for subsequent runtime type joins.
    No output files or persistent state are created by this operation.
    """
    _require(isinstance(inputs, dict) and set(inputs) == set(_LIMITS), 'source inputs')
    for indices in (type_indices, method_indices, literal_indices):
        _require(isinstance(indices, (list, tuple)) and len(indices) <= _MAX_SELECTED
                 and all(type(index) is int and 0 <= index < _MAX_INDEX for index in indices)
                 and len(set(indices)) == len(indices), 'requested indices')
    _require(type_indices or method_indices or literal_indices, 'empty request')
    with ExitStack() as stack:
        files = {role: _Source(stack, role, inputs[role], cancelled) for role in _LIMITS}
        records = _Records(files, cancelled)
        types = {}
        fields = {}
        for index in type_indices:
            _check_cancelled(cancelled)
            owner = records.type(index)
            types[index] = owner
            count = owner['field_count']
            start = owner['field_start']
            if count:
                _require(0 <= start < _MAX_INDEX and count <= _MAX_INDEX - start
                         and count <= _MAX_SELECTED - len(fields), 'type field range')
            for field in range(start, start + count):
                _require(field not in fields, 'field type ownership')
                fields[field] = records.field(field, index, owner)
        methods = {}
        remaining_parameters = _MAX_SELECTED_PARAMETERS
        for index in method_indices:
            _check_cancelled(cancelled)
            method = records.method(index, types, remaining_parameters)
            remaining_parameters -= len(method['parameters'])
            methods[index] = method
        literals = {}
        literal_bytes = 0
        for index in literal_indices:
            _check_cancelled(cancelled)
            value = records.literal(index)
            literal_bytes += len(value.encode('utf-8'))
            _require(literal_bytes <= 1024**2, 'selected literal bytes')
            literals[index] = value
        for file in files.values():
            _check_cancelled(cancelled)
            file.check_source()
        return {'sha256': {role: file.sha256 for role, file in files.items()},
                'types': types, 'fields': fields, 'methods': methods, 'literals': literals}
