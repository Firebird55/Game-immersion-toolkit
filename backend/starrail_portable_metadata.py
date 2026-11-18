# SPDX-License-Identifier: GPL-3.0-or-later
"""Read selected original Star Rail metadata records from publisher-owned files.

The format descriptions are adapted from HSRGlobalMetadata at
bb66f7c59d73cadcd026d817a011598ea23c5313. See docs/game-audits/starrail.md
for provenance and the remaining runtime type and provider requirements.
"""

from bisect import bisect_right
from contextlib import ExitStack, contextmanager
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
_MAX_PROJECTED_DEFINITIONS = 64
_MAX_LITERAL = 64 * 1024
_LIMITS = {'native': 1024**3, 'metadata': 512 * 1024**2, 'startup': 64 * 1024**2}
_PRIMITIVE_TYPES = {
    0x01: 'void', 0x02: 'bool', 0x03: 'char', 0x04: 'sbyte', 0x05: 'byte', 0x06: 'short',
    0x07: 'ushort', 0x08: 'int', 0x09: 'uint', 0x0a: 'long', 0x0b: 'ulong', 0x0c: 'float',
    0x0d: 'double', 0x0e: 'string', 0x16: 'TypedReference', 0x18: 'IntPtr', 0x19: 'UIntPtr',
    0x1c: 'object',
}
_LAYOUT_TYPE_TAGS = frozenset(range(1, 0x17)) | {
    0x18, 0x19, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x40, 0x41, 0x45, 0x55, 0xff,
}
_DEFAULT_SCHEMA = 'proxy-starrail-selected-field-defaults-v1'
_DEFAULT_ROW = struct.Struct('<iii')
_DEFAULT_BLOCK = _BLOCK // _DEFAULT_ROW.size * _DEFAULT_ROW.size
_DEFAULT_CODECS = {tag: struct.Struct('<' + code) for tag, code in {
    0x02: 'B', 0x03: 'H', 0x04: 'b', 0x05: 'B', 0x06: 'h', 0x07: 'H', 0x08: 'i',
    0x09: 'I', 0x0a: 'q', 0x0b: 'Q', 0x0c: 'f', 0x0d: 'd', 0x18: 'q', 0x19: 'Q',
}.items()}
_ENUM_INTEGER_TAGS = frozenset(range(0x04, 0x0c))
_TYPE_DEFINITION_TAGS = {0x11, 0x12}
_LITERAL_FIELD = 0x0040
_ENUM_BACKING_FIELD = 0x0600
_STATIC_FIELD = 0x0010

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
    'assemblies': (0x158, -532747583),  # Unclassified landmark used as a conservative fence.
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


@dataclass(frozen=True, slots=True)
class TypeDeclaration:
    image_index: int
    name_index: int
    namespace_index: int
    parent: int
    declaring_type: int
    field_start: int
    field_count: int
    method_start: int
    method_count: int
    nested_start: int
    nested_count: int
    generic_container: int
    flags: int
    bitfield: int


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


def _field_range(start, count):
    return _signed((start - 1954887780) & _MASK32), (count + 17485) & 0xffff


def _type_declaration(data, image_index):
    field_start, field_count = _field_range(_integer(data, 0x20), _integer(data, 0x32, 2))
    return TypeDeclaration(image_index, (_integer(data, 0x28) - 369268488) & _MASK32,
                           (_integer(data, 0x24) - 237818487) & _MASK32,
                           _signed((_integer(data, 0x04) - 1224299847) & _MASK32),
                           _signed((_integer(data, 0x0c) - 472568492) & _MASK32), field_start, field_count,
                           _signed(_integer(data, 0x08) ^ 0x1a7af5fe), (_integer(data, 0x34, 2) + 24467) & 0xffff,
                           _signed(_integer(data, 0x3a, 2) ^ 0xb2c0, 16), (_integer(data, 0x43, 1) + 4) & 0xff,
                           _signed((_integer(data, 0x3c, 2) - 44028) & 0xffff, 16),
                           (_integer(data, 0x14) - 17986448) & _MASK32, _integer(data, 0x38))


def _method_key(index):
    factor = (738455933 * ((12769 * index) ^ 0x33914937)) & _MASK64
    return ((((1410124276 * (factor >> 23)) & _MASK64) >> 21) + 1908176993) & _MASK32


def _method_owner(encoded, key):
    return encoded ^ 0x2a5fabe8 ^ key


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
        self.stream = stack.enter_context(self.path.open('rb', buffering=0))
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

    def span(self, rva, *, executable):
        for start, length, offset, code in self.sections:
            if code == executable and start <= rva < start + length:
                delta = rva - start
                return offset + delta, length - delta
        raise MetadataFormatError('PE address ownership')

    def offset(self, rva, size, *, executable):
        offset, available = self.span(rva, executable=executable)
        _require(0 < size <= available, 'PE address ownership')
        return offset

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
            yield windows, image_at, image_count, generic_class_at
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
                arrays = _integer(metadata, 0x70, 8) - image.base
                generic_instances = _integer(metadata, 0x38, 8) - image.base
                method_pointers = _integer(code, 0x40, 8) - image.base
                literal_count = _integer(tables, 0x2c) ^ 0x0bd08dc8
                _require(0 < type_count < _MAX_INDEX and 0 <= literal_count < _MAX_INDEX, 'registration counts')
                image.offset(types, type_count * 8, executable=False)
                image.offset(method_pointers, 8, executable=False)
            except MetadataFormatError:
                continue
            yield type_count, types, arrays, generic_instances, method_pointers, literal_count
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


def _runtime_type_stride(image, table_offset, available, count, cancelled):
    """Apply the pinned tag scoring to the table's file-backed PE owner."""
    samples = min(count, 512)
    scores = {}
    for stride, tag_offset in ((8, 6), (16, 10)):
        hits = unread = 0
        for sample in range(samples):
            _check_cancelled(cancelled)
            index = sample * (count - 1) // (samples - 1) if samples > 1 else 0
            at = index * stride + tag_offset
            if at < available:
                tag = image.source.read(table_offset + at, 1, component='runtime type tag')[0]
                hits += tag in _LAYOUT_TYPE_TAGS
            elif table_offset + at < image.source.size:
                # Bytes in another part of the file cannot supply type tags.
                # Do not let the lack of evidence make a competitor lose.
                unread += 1
        scores[stride] = hits / samples, (hits + unread) / samples
    for stride, other in ((8, 16), (16, 8)):
        score, _ = scores[stride]
        _, other_upper_bound = scores[other]
        if score >= 0.90 and score - other_upper_bound >= 0.20:
            _require(count * stride <= available, 'runtime type table ownership')
            return stride
    raise MetadataFormatError('runtime type layout')


class _Records:
    def __init__(self, files, cancelled):
        self.cancelled = cancelled
        self.field_extent_proved = False
        self.type_layout = None
        self.metadata = files['metadata']
        self.startup = files['startup']
        self.image = _Image(files['native'])
        _require(self.metadata.size >= _HEADER_SIZE and self.metadata.read(0, 4) == _MAGIC, 'global metadata prefix')
        self.windows, images_at, image_count, generic_classes_at = _header(
            self.image, self.metadata, self.startup, cancelled)
        self.generic_classes_at = generic_classes_at
        (self.type_count, self.runtime_types_rva, self.arrays_rva, self.generic_instances_rva,
         self.method_pointers, self.literal_count) = _registrations(self.image, cancelled)
        if generic_classes_at < images_at:
            self.generic_class_extent = images_at - generic_classes_at
        elif generic_classes_at >= images_at + image_count * 40:
            self.generic_class_extent = self.startup.size - generic_classes_at
        else:
            self.generic_class_extent = 0
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

    def type_image(self, index):
        _require(0 <= index < self.definition_count, 'type definition index')
        owner = bisect_right(self.image_starts, index) - 1
        _require(owner >= 0 and index < self.images[owner][1], 'type image ownership')
        _, _, image_index, image = self.images[owner]
        return image_index, image

    def type(self, index):
        image_index, image = self.type_image(index)
        declaration = _type_declaration(self.read('types', index * 70, 70), image_index)
        name = self.name(declaration.name_index)
        _require(name, 'type name')
        return {'name': name, 'namespace': self.name(declaration.namespace_index),
                'image': image, 'image_index': image_index, 'parent': declaration.parent,
                'declaring_type': declaration.declaring_type, 'flags': declaration.flags,
                'field_start': declaration.field_start, 'field_count': declaration.field_count,
                'method_start': declaration.method_start, 'method_count': declaration.method_count,
                'nested_start': declaration.nested_start, 'nested_count': declaration.nested_count,
                'generic_container': declaration.generic_container}

    def field_boundary(self):
        start, _ = self.windows['fields']
        end, _ = self.windows['literal_data']
        length = end - start
        competing = any(start <= offset <= end for role, (offset, _) in self.windows.items()
                        if role not in {'fields', 'assemblies', 'literal_data'})
        _require(not competing and 0 < length <= 8 * _MAX_INDEX and length % 8 == 0,
                 'field declaration boundary')
        return start, length

    def prove_field_extent(self):
        if self.field_extent_proved:
            return
        start, length = self.field_boundary()
        slots = length // 8
        owned = bytearray(slots)
        declared = 0
        # The assembly-related header slot has no proved coordinate. Require
        # every original declaration to tile to the separately owned literal
        # data boundary before extending the conservative field reader.
        for at in range(0, self.definition_count * 70, 70):
            _check_cancelled(self.cancelled)
            raw_start = _integer(self.read('types', at + 0x20, 4), 0)
            raw_count = _integer(self.read('types', at + 0x32, 2), 0, 2)
            first, count = _field_range(raw_start, raw_count)
            if count:
                _require(0 <= first <= slots - count, 'field declaration range')
                stop = first + count
                _require(not any(owned[first:stop]), 'field declaration overlap')
                owned[first:stop] = b'\x01' * count
                declared += count
        _require(declared == slots, 'field declaration gap')
        self.windows['fields'] = start, length
        self.field_extent_proved = True

    def field(self, index, owner_index, owner):
        first = owner['field_start']
        _require(0 <= first <= index < first + owner['field_count'], 'field type ownership')
        if (index + 1) * 8 > self.windows['fields'][1]:
            self.prove_field_extent()
        raw = self.read('fields', index * 8, 8)
        key = -1388221511 - 744344320 * (index + 1954887780)
        type_index = (_integer(raw, 4) + key) & _MASK32
        _require(type_index < self.type_count, 'field type index')
        mapped = _integer(self.read('type_index_map', owner_index * 4, 4), 0)
        offset_index = _integer(self.read('index_table', mapped * 12 + 8, 4), 0)
        offset = _integer(self.read('field_offsets', (offset_index + index - first) * 4, 4), 0)
        name = self.name((_integer(raw, 0) + 716162949 + key) & _MASK32)
        _require(name, 'field name')
        return {'owner': owner_index, 'type': type_index, 'name': name, 'offset': offset}

    def method(self, index, types, remaining_parameters):
        raw = self.read('methods', index * 26, 26)
        key = _method_key(index)
        owner_index = _method_owner(_integer(raw, 0x10), key)
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
        rva = self.method_rva(pointer)
        name = self.name(_integer(raw, 0) ^ 0x0e714bc1 ^ key)
        _require(name, 'method name')
        return {'owner': owner_index, 'name': name, 'return_type': return_type, 'flags': flags,
                'generic_container': _signed(((_integer(raw, 0x14, 2) - 30979) ^ key) & 0xffff, 16),
                'parameters': parameter_rows, 'rva': rva}

    def method_rva(self, pointer):
        if not pointer:
            return 0
        rva = pointer - self.image.base
        self.image.offset(rva, 1, executable=True)
        return rva

    def parameter(self, index):
        raw = self.read('parameters', index * 8, 8)
        key = 1488482466 * (((0x72e1d74b12b * index + 0x1911d05aff5) & _MASK64) >> 11) - 2083554492
        type_index = ((_integer(raw, 0) ^ 0x67e90dc5) - key) & _MASK32
        _require(type_index < self.type_count, 'parameter type index')
        return type_index, self.name(((_integer(raw, 4) ^ 0x7103092e) - key) & _MASK32)

    def runtime_types(self, indices, cancelled):
        _require(all(0 <= index < self.type_count for index in indices), 'runtime type index')
        offset, stride = self.runtime_layout(cancelled)
        rows = {}
        for index in indices:
            _check_cancelled(cancelled)
            rows[index] = self.runtime_row(offset + index * stride, stride)
        return stride, rows

    def runtime_layout(self, cancelled):
        if self.type_layout is None:
            offset, available = self.image.span(self.runtime_types_rva, executable=False)
            stride = _runtime_type_stride(self.image, offset, available, self.type_count, cancelled)
            self.type_layout = offset, stride
        return self.type_layout

    def runtime_words(self, offset, stride):
        data_width = 4 if stride == 8 else 8
        raw = self.image.source.read(offset, data_width + 4, component='runtime type row')
        data = _integer(raw, 0, data_width)
        attributes = _integer(raw, data_width, 2)
        tag, flags = raw[data_width + 2:data_width + 4]
        return data, attributes, tag, flags

    def runtime_row(self, offset, stride):
        data, attributes, tag, flags = self.runtime_words(offset, stride)
        return {'data': data, 'attributes': attributes, 'tag': tag, 'modifiers': flags & 0x3f,
                'by_reference': bool(flags & 0x40), 'pinned': bool(flags & 0x80),
                'target': self.runtime_target(tag, data, stride)}

    def runtime_target(self, tag, data, stride):
        if tag in _PRIMITIVE_TYPES or (tag == 0x0f and data == 0):
            return None
        if tag in _TYPE_DEFINITION_TAGS:
            _require(data < self.definition_count, 'runtime type definition index')
            return 'type_definition', data
        if tag in {0x13, 0x1e}:
            _require(data < self.windows['generic_parameters'][1] // 14, 'runtime generic parameter index')
            return 'generic_parameter', data
        if tag == 0x15:
            _require(data < self.generic_class_extent // 8, 'runtime generic class index')
            return 'generic_class', data
        if tag == 0x14:
            rva = data - self.image.base
            if stride == 8:
                _require(self.arrays_rva > 0 and data < _MAX_INDEX, 'runtime array index')
                rva = self.arrays_rva + data * 32
            self.image.offset(rva, 32, executable=False)
            return 'array_rva', rva
        if tag in {0x0f, 0x10, 0x1d}:
            if stride == 8 and tag != 0x10:
                _require(data < self.type_count, 'runtime referenced type index')
                return 'runtime_index', data
            rva = data - self.image.base
            self.image.offset(rva, stride, executable=False)
            return 'runtime_rva', rva
        raise MetadataFormatError('unsupported runtime type tag')

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


class _FieldDefaults:
    def __init__(self, records):
        self.records = records
        self.offset, self.stride = records.runtime_layout(records.cancelled)
        self.native_types = {}
        self.enum_types = {}
        self.remaining_enum_fields = _MAX_SELECTED

    def native_type(self, index):
        _check_cancelled(self.records.cancelled)
        _require(0 <= index < self.records.type_count, 'default runtime type index')
        if index not in self.native_types:
            row = self.records.runtime_words(self.offset + index * self.stride, self.stride)
            if row[2] in _TYPE_DEFINITION_TAGS:
                _require(row[0] < self.records.definition_count, 'default type definition index')
            self.native_types[index] = row
        return self.native_types[index]

    def row_count(self):
        records = self.records
        start, available = records.windows['field_defaults']
        end, _ = records.windows['index_table']
        length = end - start
        competing = any(start <= offset <= end for role, (offset, _) in records.windows.items()
                        if role not in {'field_defaults', 'index_table'})
        _require(not competing and (length == 0 or length == available) and length % _DEFAULT_ROW.size == 0,
                 'default record table boundary')
        # The competing table owns this row. It must both fit the field-offset
        # index contract and stop the pinned default-record loop.
        fake_type, _, offset_slot = _DEFAULT_ROW.unpack(records.read('index_table', 0, _DEFAULT_ROW.size))
        offset_slots = records.windows['field_offsets'][1] // 4
        _require(0 <= offset_slot < offset_slots and
                 (not 0 <= fake_type <= records.type_count or offset_slot > 10_000_000),
                 'default record table terminator')
        return length // _DEFAULT_ROW.size

    def references(self, requested):
        records = self.records
        records.prove_field_extent()
        slots = records.windows['fields'][1] // 8
        data_size = records.windows['default_data'][1]
        count = self.row_count()
        _require(count <= slots, 'default record count')
        length = count * _DEFAULT_ROW.size
        previous = -1
        matches = {}
        for at in range(0, length, _DEFAULT_BLOCK):
            _check_cancelled(records.cancelled)
            data = records.read('field_defaults', at, min(_DEFAULT_BLOCK, length - at))
            for type_index, offset, field in _DEFAULT_ROW.iter_unpack(data):
                _require(previous < field < slots and field <= 10_000_000, 'default record field order or ownership')
                _require(0 <= type_index < records.type_count, 'default record type index')
                _require(0 <= offset < data_size, 'default record data offset')
                if field in requested:
                    matches[field] = type_index, offset
                previous = field
        return matches

    def enum_underlying(self, index):
        if index not in self.enum_types:
            self.enum_types[index] = self.enum_backing_field(index)
        return self.enum_types[index]

    def enum_backing_field(self, index):
        records = self.records
        bitfield = _integer(records.read('types', index * 70 + 0x38, 4), 0)
        if not bitfield & 2:
            return None
        owner = records.type(index)
        start, count = owner['field_start'], owner['field_count']
        _require(count <= self.remaining_enum_fields and (count == 0 or 0 <= start < _MAX_INDEX),
                 'default enum field extent')
        self.remaining_enum_fields -= count
        backing = []
        for field in range(start, start + count):
            _check_cancelled(records.cancelled)
            row = records.field(field, index, owner)
            if row['name'] == 'value__':
                backing.append(self.native_type(row['type']))
        _require(len(backing) <= 1, 'default enum backing field')
        if backing:
            _, attributes, tag, flags = backing[0]
            if (attributes & _ENUM_BACKING_FIELD == _ENUM_BACKING_FIELD and
                    not attributes & (_LITERAL_FIELD | _STATIC_FIELD) and not flags & 0xc0
                    and tag in _ENUM_INTEGER_TAGS):
                return tag
        return None

    def decode(self, declared, source_index, offset):
        definition, _, tag, flags = declared
        stored_definition, _, stored_tag, stored_flags = self.native_type(source_index)
        _require(not (flags | stored_flags) & 0xc0, 'default record type qualifiers')
        unsupported = {'status': 'unsupported', 'declared_tag': tag, 'storage_tag': stored_tag}
        enum = tag in _TYPE_DEFINITION_TAGS
        if enum:
            kind = self.enum_underlying(definition)
            if kind is None:
                return unsupported
            if stored_tag in _TYPE_DEFINITION_TAGS:
                _require(stored_definition == definition, 'default record enum owner')
                # The pinned decoder reads Int32 for a value/class row. Other
                # enum widths need an explicit primitive storage type.
                if kind != 0x08:
                    return unsupported
            else:
                _require(stored_tag == kind, 'default record enum storage type')
        else:
            if tag not in _DEFAULT_CODECS or stored_tag not in _DEFAULT_CODECS:
                return unsupported
            _require(tag == stored_tag, 'default record storage type')
            kind = tag
        codec = _DEFAULT_CODECS[kind]
        value, = codec.unpack(self.records.read('default_data', offset, codec.size))
        if kind == 0x02:
            value = bool(value)
        elif kind == 0x03:
            value = chr(value)
        result = {'status': 'present', 'kind': _PRIMITIVE_TYPES[kind], 'value': value}
        if enum:
            result['enum_definition'] = definition
        return result

    def selected(self, indices, fields):
        types = {index: self.native_type(fields[index]['type']) for index in indices}
        literals = {index for index, row in types.items() if row[1] & _LITERAL_FIELD}
        references = self.references(literals) if literals else {}
        result = {}
        for index, declared in types.items():
            _check_cancelled(self.records.cancelled)
            if index in references:
                result[index] = self.decode(declared, *references[index])
            else:
                result[index] = {'status': 'absent', 'reason': 'no_row' if index in literals else 'nonliteral'}
        return {'schema': _DEFAULT_SCHEMA, 'records': result}


class _TypeProjection:
    def __init__(self, records, stride, runtime_rows, types, cancelled):
        self.records = records
        self.stride = stride
        self.cancelled = cancelled
        _require(len(runtime_rows) <= 16 and len(types) <= _MAX_PROJECTED_DEFINITIONS, 'type projection roots')
        self.rows = {self.type_rva(index): value for index, value in runtime_rows.items()}
        self.definitions = dict(types)
        self.names = {}
        self.active = set()
        self.arrays = {}
        self.classes = {}
        self.instances = {}
        self.containers = {}
        self.parameters = {}
        self.constraints = {}
        self.constraint_count = 0
        self.nested = {}
        self.nested_parents = {}
        self.nested_count = 0

    def cached(self, cache, key, limit, component, load):
        _check_cancelled(self.cancelled)
        if key not in cache:
            _require(len(cache) < limit, component)
            cache[key] = load(key)
        return cache[key]

    def type_rva(self, index):
        _require(0 <= index < self.records.type_count, 'projected runtime type index')
        return self.records.runtime_types_rva + self.stride * index

    def definition(self, index):
        return self.cached(self.definitions, index, _MAX_PROJECTED_DEFINITIONS,
                           'projected type definition count', self.records.type)

    @staticmethod
    def qualified_name(record):
        return f"{record['namespace']}.{record['name']}" if record['namespace'] else record['name']

    def native_row(self, rva):
        image = self.records.image
        return self.records.runtime_row(image.offset(rva, self.stride, executable=False), self.stride)

    def native_read(self, rva, width, size, component):
        _require(0 < size <= width, component)
        image = self.records.image
        offset = image.offset(rva, width, executable=False)
        return image.source.read(offset, size, component=component)

    def array(self, rva):
        row = self.native_read(rva, 32, 9, 'runtime array header')
        rank = row[8]
        _require(0 < rank <= 32, 'runtime array rank')
        return _integer(row, 0, 8) - self.records.image.base, rank

    def generic_class(self, index):
        _require(0 <= index < self.records.generic_class_extent // 8, 'projected generic class index')
        row = self.records.startup.read(self.records.generic_classes_at + 8 * index, 8,
                                        component='startup generic class')
        return _integer(row, 0, signed=True), _integer(row, 4, signed=True)

    def generic_instance(self, index):
        base = self.records.generic_instances_rva
        _require(base > 0 and 0 <= index < _MAX_INDEX, 'generic instance index')
        row = self.native_read(base + 16 * index, 16, 16, 'runtime generic instance')
        count = _integer(row, 0, signed=True)
        _require(0 <= count <= 8, 'generic instance arity')
        if count == 0:
            return ()
        image_base = self.records.image.base
        data = self.native_read(_integer(row, 8, 8) - image_base, count * 8, count * 8, 'runtime generic arguments')
        return tuple(_integer(data, i * 8, 8) - image_base for i in range(count))

    def parameter(self, index):
        _require(0 <= index < _MAX_INDEX, 'projected generic parameter index')
        row = self.records.read('generic_parameters', 14 * index, 14)
        factor = (0x617fe3cc452c * index + 0x9dc5db71f0eb440) & _MASK64
        factor = (((factor >> 9) + 718849585) ^ 0x5278374d)
        key = ((1252900171 * factor) & _MASK64) >> 15
        name = self.records.name((_integer(row, 0) - key - 1149796643) & _MASK32)
        start = _signed(((_integer(row, 4, 2) ^ 0x69b4) - key) & 0xffff, 16)
        count = _signed(((_integer(row, 6, 2) ^ 0x0fd1) - key) & 0xffff, 16)
        _require(name and 0 <= count <= 32 and (count == 0 or start >= 0), 'generic parameter record')
        return name, start, count

    def generic_parameter(self, index):
        return self.cached(self.parameters, index, 16, 'projected generic parameter count', self.parameter)

    def named(self, rva, depth=0):
        _require(depth <= 16 and rva not in self.active, 'runtime type depth or cycle')
        if rva not in self.names:
            self.active.add(rva)
            try:
                row = self.cached(self.rows, rva, 64, 'projected runtime node count', self.native_row)
                value, height = self.describe(row, depth)
                _require(len(value) <= 4096, 'projected runtime name length')
                self.names[rva] = value, height
            finally:
                self.active.remove(rva)
        value, height = self.names[rva]
        _require(depth + height <= 16, 'runtime type depth or cycle')
        return value, height

    def describe(self, row, depth):
        tag = row['tag']
        if tag in _PRIMITIVE_TYPES:
            return _PRIMITIVE_TYPES[tag], 0
        if row['target'] is None:
            return 'void*', 0  # The only other targetless tag is a null pointer.
        role, index = row['target']
        if role == 'type_definition':
            return self.qualified_name(self.definition(index)), 0
        if role == 'generic_parameter':
            return self.generic_parameter(index)[0], 0
        if role == 'generic_class':
            definition, instance = self.cached(self.classes, index, 8, 'projected generic class count', self.generic_class)
            stem = self.qualified_name(self.definition(definition)).split('`', 1)[0]
            if instance == -1:
                return stem, 0
            args = self.cached(self.instances, instance, 8, 'projected generic instance count', self.generic_instance)
            values = [self.named(rva, depth + 1) for rva in args]
            return f"{stem}<{', '.join(name for name, _ in values)}>", 1 + max((height for _, height in values), default=-1)
        if role == 'array_rva':
            rva, rank = self.cached(self.arrays, index, 8, 'projected array count', self.array)
            name, height = self.named(rva, depth + 1)
            return name + '[' + ',' * (rank - 1) + ']', height + 1
        rva = self.type_rva(index) if role == 'runtime_index' else index
        name, height = self.named(rva, depth + 1)
        suffix = {0x0f: '*', 0x10: '', 0x1d: '[]'}[tag]
        return name + suffix, height + 1

    def container(self, index):
        _require(0 <= index < _MAX_INDEX, 'projected generic container index')
        row = self.records.read('generic_containers', index * 16, 16)
        factor = ((0x3d6913e0af40 * index + 0xa64cad60fa052c0) & _MASK64) >> 23
        factor = ((1997422568 * factor) & _MASK64) >> 11
        key = (((748293795 * factor) & _MASK64) >> 23) & _MASK32
        count = ((_integer(row, 0) - 214875017) & _MASK32) ^ key
        is_method = ((_integer(row, 4) - 1976395631) & _MASK32) ^ key
        start = ((_integer(row, 12) - 248843855) & _MASK32) ^ key
        _require(is_method in {0, 1} and 0 <= count <= 16 and start <= _MAX_INDEX - count,
                 'generic container record')
        return is_method, range(start, start + count)

    def parameter_constraints(self, index):
        name, start, count = self.generic_parameter(index)
        _require(self.constraint_count + count <= 32, 'projected generic constraint count')
        self.constraint_count += count
        constraints = []
        if count:
            data = self.records.read('generic_constraints', start * 4, count * 4)
            for at in range(0, len(data), 4):
                target = _integer(data, at, signed=True)
                constraints.append('' if target == -1 else self.named(self.type_rva(target))[0])
        return name, tuple(constraints)

    def generic(self, roots, *, methods):
        result = {}
        for owner, record in roots.items():
            index = record['generic_container']
            if index == -1:
                continue
            is_method, parameters = self.cached(self.containers, index, 8, 'projected generic container count', self.container)
            _require(is_method == methods, 'generic container owner kind')
            result[owner] = tuple(self.cached(self.constraints, i, 16, 'projected generic parameter count',
                                              self.parameter_constraints) for i in parameters)
        return result

    def nesting(self, index, ancestors):
        _require(index not in ancestors and len(ancestors) <= 16, 'nested type depth or cycle')
        if index in self.nested:
            _, height = self.nested[index]
            _require(len(ancestors) + height <= 16, 'nested type depth or cycle')
            return height
        owner = self.definition(index)
        count = owner['nested_count']
        _require(self.nested_count + count <= 32, 'projected nested type count')
        self.nested_count += count
        start = owner['nested_start']
        _require(count == 0 or start >= 0, 'nested type table index')
        raw = self.records.read('nested_types', start * 4, count * 4) if count else b''
        children = tuple(_integer(raw, at, signed=True) for at in range(0, len(raw), 4))
        _require(len(set(children)) == len(children), 'nested type owner')
        height = 0
        for child in children:
            nested = self.definition(child)
            _require(nested['image_index'] == owner['image_index'] and nested['declaring_type'] != -1
                     and self.nested_parents.setdefault(child, index) == index, 'nested type owner')
            height = max(height, self.nesting(child, (*ancestors, index)) + 1)
        self.nested[index] = children, height
        return height

    def project(self, runtime_indices, types, methods):
        names = {index: self.named(self.type_rva(index))[0] for index in runtime_indices}
        for index in types:
            self.nesting(index, ())
        requested_definitions = {index: self.definitions[index] for index in self.nested}
        type_generics = self.generic(requested_definitions, methods=False)
        method_generics = self.generic(methods, methods=True)
        definitions = {index: self.qualified_name(row) for index, row in self.definitions.items()}
        return {'runtime_names': names, 'definition_names': definitions,
                'type_parameters': type_generics, 'method_parameters': method_generics,
                'nested_types': {index: children for index, (children, _) in self.nested.items() if children}}


@contextmanager
def open_records(inputs, *, cancelled=None):
    """Keep a single authenticated source generation open during a metadata operation."""
    _require(isinstance(inputs, dict) and set(inputs) == set(_LIMITS), 'source inputs')
    with ExitStack() as stack:
        files = {role: _Source(stack, role, inputs[role], cancelled) for role in _LIMITS}
        records = _Records(files, cancelled)
        identity = tuple((role, file.sha256) for role, file in files.items())
        yield records, identity
        for file in files.values():
            _check_cancelled(cancelled)
            file.check_source()


def read_required(inputs, *, type_indices=(), method_indices=(), literal_indices=(), runtime_type_indices=(),
                  field_default_indices=(), project_types=False, cancelled=None):
    """Authenticate all three original inputs and return selected raw records.

    A requested type includes its fields. Methods independently identify their
    defining type and validate membership in that type's method range. Member
    type indices and nesting are preserved for subsequent runtime type joins.
    Explicit runtime type requests decode the PE-backed nodes and validate
    their direct references. Optionally project names, generics and nesting
    through the bounded selected type graph.
    Requested defaults must belong to the selected types' fields. The result
    distinguishes missing and nonliteral fields from unsupported storage kinds.
    No output files or persistent state are created by this operation.
    """
    for indices in (type_indices, method_indices, literal_indices, runtime_type_indices, field_default_indices):
        _require(isinstance(indices, (list, tuple)) and len(indices) <= _MAX_SELECTED
                 and all(type(index) is int and 0 <= index < _MAX_INDEX for index in indices)
                 and len(set(indices)) == len(indices), 'requested indices')
    _require(type_indices or method_indices or literal_indices or runtime_type_indices or field_default_indices,
             'empty request')
    _require(not field_default_indices or type_indices, 'default field ownership')
    _require(type(project_types) is bool, 'type projection request')
    if project_types:
        _require(0 < len(runtime_type_indices) <= 16
                 and len(type_indices) + len(method_indices) <= _MAX_PROJECTED_DEFINITIONS,
                 'type projection roots')
    with open_records(inputs, cancelled=cancelled) as (records, identity):
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
        runtime = {}
        if runtime_type_indices:
            stride, rows = records.runtime_types(runtime_type_indices, cancelled)
            runtime = {'runtime_type_stride': stride, 'runtime_types': rows}
            if project_types:
                runtime['type_projection'] = _TypeProjection(records, stride, rows, types, cancelled).project(
                    runtime_type_indices, types, methods)
        defaults = {}
        if field_default_indices:
            _require(all(index in fields for index in field_default_indices), 'default field ownership')
            defaults['field_defaults'] = _FieldDefaults(records).selected(field_default_indices, fields)
        return {'sha256': dict(identity),
                'types': types, 'fields': fields, 'methods': methods, 'literals': literals, **runtime, **defaults}
