"""Experimental current class/struct metadata, with explicit anonymous new enums.

Inputs are an immutable semantic seed, an independently generated candidate and
an authenticated original PE. No client code or newer mapping is consulted.
Required closure and frozen-codec validation remain separate activation gates.
"""
from dataclasses import dataclass, field
import hashlib
import struct

from .nte_native_schema import Exclusion, MAX_NAMES, MAX_SEED, MAX_TYPES, _PE, _Reader, _check, _seed
from .nte_seeded_schema import _enum_names, _seed_shapes
from .nte_native_classes import descriptors
from .nte_required_schema import _context, _equivalent


@dataclass(frozen=True)
class NumericEnum:
    owner: str
    property: str
    path: tuple[int, ...]
    underlying: int
    callback: int


@dataclass(frozen=True)
class ClassSchemaResult:
    data: bytes = field(repr=False)
    original_sha256: str
    class_count: int
    appended: tuple[str, ...]
    refreshed: tuple[str, ...]
    numeric_enums: tuple[NumericEnum, ...]
    excluded: tuple[Exclusion, ...]


def _replace(candidate, updates):
    body, names, name_end, enum_end, start, count, known = _seed(candidate)
    added = set(updates) - known
    _check(count + len(added) <= MAX_TYPES)
    lookup, extra = {name: i for i, name in enumerate(names)}, bytearray()
    def named(name):
        if name is None:
            return struct.pack('<i', -1)
        if name not in lookup:
            _check(len(names) < MAX_NAMES)
            lookup[name] = len(names); names.append(name)
            raw = name.encode('utf-8')
            extra.extend(struct.pack('<H', len(raw)) + raw)
        return struct.pack('<i', lookup[name])
    def wire(shape):
        kind = shape[0]
        if kind == 26:
            return bytes([kind]) + wire(shape[1]) + named(shape[2])
        if kind == 9:
            return bytes([kind]) + named(shape[1])
        return bytes([kind]) + b''.join(wire(child) for child in shape[1:])
    def record(row):
        name, parent, total, fields = row
        raw = bytearray(named(name) + named(parent) + struct.pack('<HH', total, len(fields)))
        for index, prop, dimension, shape in fields:
            raw.extend(struct.pack('<HB', index, dimension) + named(prop) + wire(shape))
        return raw
    reader, output = _Reader(body), bytearray()
    reader.position = start
    def skip_wire():
        kind = reader.number('B')
        if kind == 26:
            skip_wire(); reader.take(4)
        elif kind == 9:
            reader.take(4)
        elif kind in (8, 25, 28):
            skip_wire()
        elif kind == 24:
            skip_wire(); skip_wire()
    for _ in range(count):
        begin = reader.position
        name = names[reader.number('i')]
        reader.take(6)
        for _ in range(reader.number('H')):
            reader.take(7); skip_wire()
        output.extend(record(updates[name]) if name in updates else body[begin:reader.position])
    for name in sorted(added):
        output.extend(record(updates[name]))
    _check(reader.position == len(body))
    expanded = (struct.pack('<I', len(names)) + body[4:name_end] + extra + body[name_end:enum_end]
                + struct.pack('<I', count + len(added)) + output)
    _check(len(expanded) + 16 <= MAX_SEED)
    result = struct.pack('<HBIBII', 0x30c4, 4, 0, 0, len(expanded), len(expanded)) + expanded
    _seed(result)
    return result


def refresh(seed_usmap, candidate_usmap, original_pe):
    """Refresh supported current definitions; preserve unknown enum integers.

    An anonymous enum is allowed only in a new field/type without conflicting
    retained constructor evidence. It has no invented enum name or literals;
    the fixed reader preserves the underlying integer as a decimal string.
    Such values cannot supply caller/branch-order semantics.
    """
    body, names, name_end, enum_end, start, count, _ = _seed(seed_usmap)
    seed = _seed_shapes(body, names, start, count)
    current_body, current_names, _, _, current_start, current_count, known = _seed(candidate_usmap)
    current = _seed_shapes(current_body, current_names, current_start, current_count)
    classes = descriptors(_PE(original_pe))
    class_names = {row.name for row in classes}
    targets = {'struct': set(seed), 'enum': _enum_names(body, names, name_end, enum_end)}
    numeric = {}
    _, native, _, describe, ambiguous = _context(original_pe, seed, targets,
        class_declarations=classes, numeric_fields=numeric, normalize_names=True)
    updates, excluded = {}, {}
    known_names = {name.casefold() for name in known}
    for name, row in native.items():
        if name.casefold() in known_names and name not in known:
            excluded[name] = {'seed_name_case_conflict'}
            continue
        if name in known and name not in current:
            excluded[name] = {'duplicate_seed_name'}
            continue
        if name not in class_names and (not row[2] or not row[3] & 1 or row[3] & ~0x205):
            continue
        try:
            existing = describe(name, 1)
            if _equivalent(existing, current.get(name)) and _equivalent(existing, seed.get(name)):
                continue
            found = describe(name, 2)
        except ValueError as error:
            excluded[name] = {str(error)}
            continue
        if not _equivalent(found, current.get(name)):
            updates[name] = found
    for name in ambiguous:
        excluded[name] = {'ambiguous_native_definition'}
    # A new class cannot refer to an absent or excluded new parent definition.
    while True:
        missing = [name for name, row in updates.items() if row[1] and row[1] not in known | updates.keys()]
        if not missing:
            break
        for name in missing:
            del updates[name]; excluded[name] = {'missing_parent_definition'}
    effective = known | updates.keys()
    numeric_rows = tuple(NumericEnum(owner, prop, path, *value) for (owner, prop, path), value in sorted(numeric.items())
                         if owner in effective and owner not in excluded)
    data = _replace(candidate_usmap, updates) if updates else candidate_usmap
    return ClassSchemaResult(data, hashlib.sha256(original_pe).hexdigest(), len(classes),
        tuple(sorted(set(updates) - known)), tuple(sorted(set(updates) & known)), numeric_rows,
        tuple(Exclusion(name, tuple(sorted(reasons))) for name, reasons in sorted(excluded.items())))
