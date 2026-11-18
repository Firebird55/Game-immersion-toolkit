# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact original Star Rail declaration and method ownership census."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import struct

from . import starrail_portable_metadata as metadata


_SCHEMA = 'proxy-starrail-declaration-census-v1'
_MAX_DECLARATIONS = 100_000
_MAX_METHODS = 1_000_000
_TYPE_RECORD_SIZE = 70
_DECLARATION = struct.Struct('<IIIiiiHiHhBhII')
_RANGE = struct.Struct('<III')
_METHOD_OWNER = struct.Struct('<16xI6x')
_RVA = struct.Struct('<I')
_ADDRESS = struct.Struct('<Q')
_DEFINITION_BITS = 24
_DEFINITION_MASK = (1 << _DEFINITION_BITS) - 1


class CensusLimitError(ValueError):
    def __init__(self, resource, count, limit):
        super().__init__(f'Star Rail census {resource} limit exceeded ({count} > {limit}).')
        self.resource = resource
        self.count = count
        self.limit = limit


class CensusUnresolved(ValueError):
    def __init__(self, component):
        super().__init__(f'Original Star Rail census ownership is unresolved ({component}).')
        self.component = component


@dataclass(frozen=True, slots=True)
class DeclarationCensus:
    source_sha256: tuple
    images: tuple
    _declarations: bytes
    _fields: bytes
    _methods: bytes
    _rvas: bytes
    _addresses: bytes
    method_endpoint_role: str
    schema: str = _SCHEMA

    @property
    def definition_count(self):
        return len(self._declarations) // _DECLARATION.size

    @property
    def method_count(self):
        return len(self._rvas) // _RVA.size

    def declaration(self, definition):
        metadata._require(type(definition) is int and 0 <= definition < self.definition_count, 'census type definition index')
        row = _DECLARATION.unpack_from(self._declarations, definition * _DECLARATION.size)
        return metadata.TypeDeclaration(*row)

    def field_owner(self, field):
        return _owner_at(self._fields, field, 'census field index')

    def method_owner(self, method):
        return _owner_at(self._methods, method, 'census method index')

    def method_rva(self, method):
        metadata._require(type(method) is int and 0 <= method < self.method_count, 'census method index')
        return _RVA.unpack_from(self._rvas, method * _RVA.size)[0] or None

    def _address(self, index):
        return _ADDRESS.unpack_from(self._addresses, index * _ADDRESS.size)[0]

    def _alias_window(self, rva):
        metadata._require(type(rva) is int and 0 < rva <= metadata._MASK32, 'census method RVA')
        entries = range(len(self._addresses) // _ADDRESS.size)

        def address(index):
            return self._address(index) >> _DEFINITION_BITS

        return bisect_left(entries, rva, key=address), bisect_right(entries, rva, key=address)

    def methods_at(self, rva):
        """Yield all original MethodDefs that share this executable slot."""
        first, stop = self._alias_window(rva)
        for index in range(first, stop):
            yield self._address(index) & _DEFINITION_MASK

    def next_method_boundary(self, rva):
        """Return the next distinct method entry from the complete census."""
        first, stop = self._alias_window(rva)
        if first == stop or stop * _ADDRESS.size == len(self._addresses):
            raise CensusUnresolved('managed method boundary')
        return self._address(stop) >> _DEFINITION_BITS


def _limit(resource, count, maximum):
    if count > maximum:
        raise CensusLimitError(resource, count, maximum)


def _owner_at(ranges, item, component):
    metadata._require(type(item) is int and item >= 0, component)
    entries = range(len(ranges) // _RANGE.size)
    index = bisect_right(entries, item, key=lambda i: _RVA.unpack_from(ranges, i * _RANGE.size)[0]) - 1
    metadata._require(index >= 0, component)
    _, stop, owner = _RANGE.unpack_from(ranges, index * _RANGE.size)
    metadata._require(item < stop, component)
    return owner


def _declarations(records):
    count = records.definition_count
    _limit('type definitions', count, _MAX_DECLARATIONS)
    packed = bytearray(count * _DECLARATION.size)
    fields = []
    methods = []
    step = metadata._BLOCK // _TYPE_RECORD_SIZE
    for first in range(0, count, step):
        metadata._check_cancelled(records.cancelled)
        raw = records.read('types', first * _TYPE_RECORD_SIZE, min(step, count - first) * _TYPE_RECORD_SIZE)
        for at in range(0, len(raw), _TYPE_RECORD_SIZE):
            index = first + at // _TYPE_RECORD_SIZE
            image, _ = records.type_image(index)
            row = metadata._type_declaration(raw[at:at + _TYPE_RECORD_SIZE], image)
            _DECLARATION.pack_into(packed, index * _DECLARATION.size, row.image_index, row.name_index,
                                   row.namespace_index, row.parent, row.declaring_type, row.field_start,
                                   row.field_count, row.method_start, row.method_count, row.nested_start,
                                   row.nested_count, row.generic_container, row.flags, row.bitfield)
            if row.field_count:
                fields.append((row.field_start, row.field_start + row.field_count, index))
            if row.method_count:
                methods.append((row.method_start, row.method_start + row.method_count, index))
    return bytes(packed), fields, methods


def _tile(ranges, slots, role):
    ranges.sort()
    result = bytearray(len(ranges) * _RANGE.size)
    previous = 0
    for index, (first, stop, owner) in enumerate(ranges):
        metadata._require(0 <= first < stop <= slots, f'census {role} range')
        metadata._require(first >= previous, f'census {role} overlap')
        metadata._require(first == previous, f'census {role} gap')
        _RANGE.pack_into(result, index * _RANGE.size, first, stop, owner)
        previous = stop
    if previous != slots:
        raise CensusUnresolved(f'{role} declaration endpoint')
    return bytes(result)


def _method_endpoint(records):
    start, length = records.windows['methods']
    roles = [(role, pos) for role, (pos, _) in records.windows.items() if role not in {'methods', 'assemblies'}]
    following = [role for role, pos in roles if pos == start + length]
    if length == 0 or length % _METHOD_OWNER.size or len(following) != 1 or any(pos == start for _, pos in roles):
        raise CensusUnresolved('method table endpoint')
    count = length // _METHOD_OWNER.size
    _limit('method definitions', count, _MAX_METHODS)
    return count, following[0]


def _method_slots(records, ranges, count):
    image = records.image
    pointer_start = image.offset(records.method_pointers, count * _ADDRESS.size, executable=False)
    rvas = bytearray(count * _RVA.size)
    addresses = []
    owner_ranges = _RANGE.iter_unpack(ranges)
    _, stop, owner = next(owner_ranges)
    step = metadata._BLOCK // _METHOD_OWNER.size
    for first in range(0, count, step):
        metadata._check_cancelled(records.cancelled)
        amount = min(step, count - first)
        declarations = records.read('methods', first * _METHOD_OWNER.size, amount * _METHOD_OWNER.size)
        pointers = image.source.read(pointer_start + first * _ADDRESS.size, amount * _ADDRESS.size,
                                     component='census method pointers')
        rows = zip(_METHOD_OWNER.iter_unpack(declarations), _ADDRESS.iter_unpack(pointers), strict=True)
        for index, ((encoded,), (pointer,)) in enumerate(rows, first):
            if index == stop:
                _, stop, owner = next(owner_ranges)
            metadata._require(metadata._method_owner(encoded, metadata._method_key(index)) == owner,
                              'census foreign method declaration')
            rva = records.method_rva(pointer)
            _RVA.pack_into(rvas, index * _RVA.size, rva)
            if rva:
                addresses.append((rva << _DEFINITION_BITS) | index)
    metadata._check_cancelled(records.cancelled)
    addresses.sort()
    packed = bytearray(len(addresses) * _ADDRESS.size)
    for index, address in enumerate(addresses):
        _ADDRESS.pack_into(packed, index * _ADDRESS.size, address)
    return bytes(rvas), bytes(packed)


def read_census(inputs, *, cancelled=None):
    """Publish a compact result after all declarations, slots and source fences pass."""
    with metadata.open_records(inputs, cancelled=cancelled) as (records, identity):
        method_count, endpoint_role = _method_endpoint(records)
        _, field_length = records.field_boundary()
        declarations, field_ranges, method_ranges = _declarations(records)
        fields = _tile(field_ranges, field_length // 8, 'field')
        methods = _tile(method_ranges, method_count, 'method')
        del field_ranges, method_ranges
        rvas, addresses = _method_slots(records, methods, method_count)
        images = tuple((index, name) for _, _, index, name in records.images)
        return DeclarationCensus(identity, images, declarations, fields, methods, rvas, addresses, endpoint_role)
