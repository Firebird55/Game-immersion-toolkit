"""Experimental, append-only native root schema recovery; no Setup integration.

The caller must authenticate the seed and client against the publisher/retained
source before calling this data-only parser. Source hashes identify inputs;
they do not authenticate them. No downloaded code is loaded or executed here.
Native parents, struct/enum constructors and unsupported layouts stay excluded.
"""
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import re
import struct

import zstandard

MAX_CLIENT = 512 * 1024**2
MAX_SEED = 8 * 1024**2
MAX_EXPANDED = 64 * 1024**2
MAX_NAMES = 500_000
MAX_TYPES = 100_000
MAX_PROPERTIES = 1_000_000
MAX_NATIVE = 32_768
MAX_NATIVE_PROPERTIES = 250_000
MAX_SCAN_MATCHES = 1_000_000
MAX_DEPTH = 16
NATIVE_FLAGS = 0x45  # RF_Public | RF_Transient | RF_MarkAsNative.
# Fixed engine generator tags, not game versions, type names or file offsets.
WIRE_TYPES = {0: 0, 1: 23, 2: 22, 3: 2, 4: 21, 5: 20, 6: 19, 7: 18,
              10: 3, 11: 7, 12: 1, 13: 17, 14: 14, 15: 15, 16: 17,
              17: 4, 18: 4, 19: 12, 20: 5, 21: 10, 22: 8, 23: 24,
              24: 25, 25: 9, 26: 6, 27: 13, 29: 11, 30: 26, 31: 27,
              32: 7, 33: 28}


def _check(value):
    if not value:
        raise ValueError('Unsupported or incomplete experimental NTE schema input')


class _Reader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, size):
        _check(0 <= size <= len(self.data) - self.position)
        result = self.data[self.position:self.position + size]
        self.position += size
        return result

    def number(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]


@dataclass(frozen=True)
class Exclusion:
    name: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class NativeSchemaResult:
    data: bytes = field(repr=False)
    seed_sha256: str
    client_sha256: str
    appended: tuple[str, ...]
    excluded: tuple[Exclusion, ...]
    native_count: int


def _seed(raw):
    _check(isinstance(raw, bytes) and 16 <= len(raw) <= MAX_SEED)
    magic, version, flags, method, packed, expanded = struct.unpack_from('<HBIBII', raw)
    _check(magic == 0x30c4 and version == 4 and flags == 0 and method in (0, 3)
           and packed == len(raw) - 16 and 0 < expanded <= MAX_EXPANDED)
    try:
        if method == 3:
            _check(zstandard.get_frame_parameters(raw[16:]).window_size <= MAX_EXPANDED)
            advertised = zstandard.frame_content_size(raw[16:])
            _check(advertised == zstandard.CONTENTSIZE_UNKNOWN or advertised == expanded)
            body = zstandard.ZstdDecompressor(max_window_size=MAX_EXPANDED // 1024).decompress(
                raw[16:], max_output_size=expanded, allow_extra_data=False)
        else:
            body = raw[16:]
    except zstandard.ZstdError as error:
        raise ValueError('Invalid experimental NTE seed compression') from error
    _check(len(body) == expanded)
    reader = _Reader(body)
    count = reader.number('I')
    _check(0 < count <= MAX_NAMES)
    names = []
    for _ in range(count):
        length = reader.number('H')
        _check(0 < length <= 512)
        try:
            name = reader.take(length).decode('utf-8')
        except UnicodeError as error:
            raise ValueError('Invalid experimental NTE seed name') from error
        _check('\0' not in name)
        names.append(name)
    name_end = reader.position

    def named(optional=False):
        value = reader.number('i')
        _check(optional and value == -1 or 0 <= value < len(names))
        return None if value == -1 else names[value]

    enum_count = reader.number('I')
    _check(enum_count <= MAX_TYPES)
    members = 0
    for _ in range(enum_count):
        named()
        count = reader.number('H')
        members += count
        _check(members <= MAX_PROPERTIES)
        for _ in range(count):
            reader.take(8)
            named()
    struct_offset = reader.position
    struct_count = reader.number('I')
    _check(struct_count <= MAX_TYPES)
    struct_start = reader.position
    types, properties = set(), 0

    def wire(depth=0):
        _check(depth <= MAX_DEPTH)
        kind = reader.number('B')
        _check(kind <= 36 or kind in (0xfd, 0xfe, 0xff))
        if kind == 26:
            wire(depth + 1)
            named(True)
        elif kind == 9:
            named(True)
        elif kind in (8, 25, 28):
            wire(depth + 1)
        elif kind == 24:
            wire(depth + 1)
            wire(depth + 1)

    for _ in range(struct_count):
        name = named()
        # Retained seeds can contain repeated names. Preserve every old record
        # and its existing resolution order; no such name is eligible to append.
        types.add(name)
        named(True)
        total, count = reader.number('H'), reader.number('H')
        properties += count
        _check(properties <= MAX_PROPERTIES)
        occupied = set()
        for _ in range(count):
            index, dimension = reader.number('H'), reader.number('B')
            _check(dimension and index + dimension <= total)
            slots = set(range(index, index + dimension))
            _check(not occupied.intersection(slots))
            occupied.update(slots)
            named()
            wire()
    _check(reader.position == len(body))  # Unknown extensions are not guessed.
    return body, names, name_end, struct_offset, struct_start, struct_count, types


class _PE:
    def __init__(self, data):
        _check(isinstance(data, bytes) and 64 <= len(data) <= MAX_CLIENT and data[:2] == b'MZ')
        self.data = data
        pe = self.unpack('I', 60)[0]
        _check(self.read(pe, 4) == b'PE\0\0')
        machine, count = self.unpack('HH', pe + 4)
        optional_size = self.unpack('H', pe + 20)[0]
        optional = pe + 24
        _check(machine == 0x8664 and 1 <= count <= 96 and optional_size >= 112
               and self.unpack('H', optional)[0] == 0x20b)
        self.read(optional, optional_size + count * 40)
        self.base = self.unpack('Q', optional + 24)[0]
        image_size, headers = self.unpack('II', optional + 56)
        _check(0 < headers <= len(data) and self.base + image_size < 2**64)
        self.sections = []
        for index in range(count):
            entry = optional + optional_size + index * 40
            _, rva, size, offset = self.unpack('IIII', entry + 8)
            flags = self.unpack('I', entry + 36)[0]
            if not size:
                continue
            self.read(offset, size)
            _check(offset >= headers and rva + size <= image_size)
            self.sections.append((self.base + rva, size, offset, flags))
        for index, (va, size, offset, _) in enumerate(self.sections):
            for other_va, other_size, other_offset, _ in self.sections[:index]:
                _check(va + size <= other_va or other_va + other_size <= va)
                _check(offset + size <= other_offset or other_offset + other_size <= offset)
        _check(self.sections)

    def read(self, offset, size):
        _check(0 <= offset <= len(self.data) and 0 <= size <= len(self.data) - offset)
        return self.data[offset:offset + size]

    def unpack(self, fmt, offset):
        return struct.unpack('<' + fmt, self.read(offset, struct.calcsize('<' + fmt)))

    def pointer(self, va, size=1, *, code=False):
        for start, length, offset, flags in self.sections:
            if start <= va and size <= start + length - va:
                if code:
                    return offset + va - start if flags & 0x20000000 else None
                return offset + va - start if flags & 0x40000000 and not flags & 0x20000000 else None
        return None

    def name(self, va):
        offset = self.pointer(va)
        if offset is None:
            return None
        end = self.data.find(b'\0', offset, offset + 257)
        if end < 0 or self.pointer(va, end - offset + 1) is None:
            return None
        value = self.data[offset:end]
        return value.decode('ascii') if re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_]*', value) else None

    def native(self, *, with_callbacks=False, with_layout=False, with_metadata=False):
        results, matches, properties = [], 0, 0
        for _, length, section, flags in sorted(self.sections, key=lambda item: item[2]):
            if flags & 0x20000000 or not flags & 0x40000000:
                continue
            for hit in re.finditer(re.escape(struct.pack('<I', NATIVE_FLAGS)), self.read(section, length)):
                matches += 1
                _check(matches <= MAX_SCAN_MATCHES)
                offset = section + hit.start() - 48
                if offset < section or offset % 8 or offset + 56 > section + length:
                    continue
                outer, parent, ops, name, pointers, count, size, align, _, struct_flags = self.unpack('5QHH3I', offset)
                name = self.name(name)
                if (not name or self.pointer(outer, code=True) is None or
                        parent and self.pointer(parent, code=True) is None or
                        ops and self.pointer(ops, code=True) is None or
                        not size or align not in (1, 2, 4, 8, 16) or size % align or count > 1024 or
                        bool(pointers) != bool(count)):
                    continue
                pointer_offset = self.pointer(pointers, count * 8) if count else None
                if count and pointer_offset is None:
                    continue
                properties += count
                _check(properties <= MAX_NATIVE_PROPERTIES)
                fields, seen, layouts = [], set(), []
                for index in range(count):
                    address = self.unpack('Q', pointer_offset + index * 8)[0]
                    prop = self.pointer(address, 56)
                    if prop is None or address in seen:
                        break
                    seen.add(address)
                    field_name = self.name(self.unpack('Q', prop)[0])
                    generator, object_flags = self.unpack('II', prop + 24)
                    dimension = self.unpack('H', prop + 48)[0]
                    if not field_name or object_flags != NATIVE_FLAGS or not dimension:
                        break
                    enum, callback = False, 0
                    if generator & 63 == 0 or with_callbacks and generator & 63 in (25, 30):
                        if self.pointer(address, 64) is None:
                            break
                        callback = self.unpack('Q', prop + 56)[0]
                        enum = bool(callback)
                    fields.append((field_name, generator, dimension, callback if with_callbacks else enum))
                    if with_metadata:
                        notify = self.unpack('Q', prop + 8)[0]
                        notify_name = self.name(notify) if notify else None
                        property_flags = self.unpack('Q', prop + 16)[0]
                        setter, getter = self.unpack('2Q', prop + 32)
                        member_offset = self.unpack('H', prop + 50)[0]
                        layouts.append((field_name, notify_name, bool(notify), property_flags,
                                        generator, object_flags, dimension, member_offset, setter, getter))
                else:
                    row = (name, parent, ops, struct_flags, tuple(fields))
                    row = row + (size, align) if with_layout else row
                    results.append(row + ((outer, tuple(layouts)),) if with_metadata else row)
                    _check(len(results) <= MAX_NATIVE)
        return results


def _fields(descriptors):
    index = len(descriptors) - 1

    def take(depth=0, child=False):
        nonlocal index
        if depth > MAX_DEPTH or index < 0:
            raise ValueError('malformed_nesting')
        name, generator, dimension, enum = descriptors[index]
        index -= 1
        kind = generator & 63
        if generator & ~0x7f or kind not in WIRE_TYPES:
            raise ValueError('unsupported_generator_tag')
        if enum or kind == 30:
            raise ValueError('enum_constructor')
        if kind == 25:
            raise ValueError('native_struct_constructor')
        if not 1 <= dimension <= 255 or child and dimension != 1:
            raise ValueError('unsupported_dimension')
        encoded = bytes([WIRE_TYPES[kind]])
        if kind in (22, 24, 33):
            encoded += take(depth + 1, True)[2]
        elif kind == 23:
            encoded += take(depth + 1, True)[2] + take(depth + 1, True)[2]
        return name, dimension, encoded

    fields = []
    while index >= 0:
        fields.append(take())
    fields.reverse()
    if sum(f[1] for f in fields) > 65535:
        raise ValueError('property_index_limit')
    if len({f[0].casefold() for f in fields}) != len(fields):
        raise ValueError('duplicate_property_name')
    return fields


def append_native_root_types(seed_usmap: bytes, client_pe: bytes) -> NativeSchemaResult:
    """Append only evidenced standalone native types; never replace seed types.

    This experimental API performs no discovery, downloads, writes, key recovery
    or Setup changes. Unsupported native semantics produce named exclusions.
    A malformed seed/PE or exceeded bound rejects the operation without output.
    """
    body, names, name_end, struct_offset, struct_start, count, known = _seed(seed_usmap)
    native = _PE(client_pe).native()
    duplicates = Counter(row[0].casefold() for row in native)
    known_identities = {name.casefold() for name in known}
    additions, excluded = [], {}

    def exclusions():
        return tuple(Exclusion(name, tuple(sorted(reasons))) for name, reasons in sorted(excluded.items()))

    for name, parent, ops, flags, descriptors in native:
        if name in known:
            continue
        reasons = []
        if name.casefold() in known_identities:
            reasons.append('seed_name_case_conflict')
        if duplicates[name.casefold()] != 1:
            reasons.append('duplicate_native_name')
        if parent:
            reasons.append('native_super_constructor')
        if not ops:
            reasons.append('missing_native_operations')
        if not flags & 1 or flags & ~0x205:
            reasons.append('unsupported_struct_flags')
        try:
            fields = _fields(descriptors)
        except ValueError as error:
            reasons.append(str(error))
        if reasons:
            excluded.setdefault(name, set()).update(reasons)
        else:
            additions.append((name, fields))
    if not additions:
        return NativeSchemaResult(seed_usmap, hashlib.sha256(seed_usmap).hexdigest(),
            hashlib.sha256(client_pe).hexdigest(), (), exclusions(), len(native))
    _check(count + len(additions) <= MAX_TYPES)
    additions.sort(key=lambda item: item[0])
    lookup = {name: index for index, name in enumerate(names)}
    new_names = bytearray()

    def named(value):
        if value not in lookup:
            _check(len(names) < MAX_NAMES)
            lookup[value] = len(names)
            names.append(value)
            encoded = value.encode('utf-8')
            _check(len(new_names) + len(encoded) + 2 <= MAX_SEED)
            new_names.extend(struct.pack('<H', len(encoded)) + encoded)
        return lookup[value]

    appended = bytearray()
    for name, fields in additions:
        appended.extend(struct.pack('<iiHH', named(name), -1, sum(f[1] for f in fields), len(fields)))
        index = 0
        for name, dimension, encoded in fields:
            appended.extend(struct.pack('<HBi', index, dimension, named(name)) + encoded)
            index += dimension
            _check(len(appended) <= MAX_SEED)
    _check(len(body) + len(new_names) + len(appended) + 16 <= MAX_SEED)
    expanded = (struct.pack('<I', len(names)) + body[4:name_end] + new_names +
                body[name_end:struct_offset] + struct.pack('<I', count + len(additions)) +
                body[struct_start:] + appended)
    _check(len(expanded) + 16 <= MAX_SEED)
    data = struct.pack('<HBIBII', 0x30c4, 4, 0, 0, len(expanded), len(expanded)) + expanded
    return NativeSchemaResult(data, hashlib.sha256(seed_usmap).hexdigest(), hashlib.sha256(client_pe).hexdigest(),
        tuple(name for name, _ in additions), exclusions(), len(native))
