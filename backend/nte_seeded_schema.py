"""Experimental native schema extension using retained, unchanged type evidence.

Only complete exact seed/native shape matches may identify a constructor. Each
identity needs at least two independent seed owners in this same client, and
conflicting identities are rejected. No constructor is executed or disassembled.
The caller authenticates both inputs. Normal preparation does not call this API.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import struct

from .nte_native_schema import (Exclusion, MAX_DEPTH, MAX_NAMES, MAX_SEED, MAX_TYPES,
                                NativeSchemaResult, WIRE_TYPES, _PE, _Reader, _check, _seed)


@dataclass(frozen=True)
class CallbackEvidence:
    kind: str
    target: str
    owners: tuple[str, ...]


@dataclass(frozen=True)
class SeededSchemaResult(NativeSchemaResult):
    matched_seed_types: int
    callbacks: tuple[CallbackEvidence, ...]


@dataclass(frozen=True)
class RefreshedSchemaResult(SeededSchemaResult):
    refreshed: tuple[str, ...]


def _seed_shapes(body, names, start, count):
    reader, rows = _Reader(body), []
    reader.position = start

    def named():
        value = reader.number('i')
        return None if value == -1 else names[value]

    def wire(depth=0):
        _check(depth <= MAX_DEPTH)
        kind = reader.number('B')
        if kind == 26:
            return kind, wire(depth + 1), named()
        if kind == 9:
            return kind, named()
        if kind in (8, 25, 28):
            return kind, wire(depth + 1)
        if kind == 24:
            return kind, wire(depth + 1), wire(depth + 1)
        return kind,

    for _ in range(count):
        name, parent = named(), named()
        total, length = reader.number('H'), reader.number('H')
        fields = []
        for _ in range(length):
            index, dimension, field_name = reader.number('H'), reader.number('B'), named()
            fields.append((index, field_name, dimension, wire()))
        rows.append((name, parent, total, fields))
    _check(reader.position == len(body))
    duplicates = Counter(row[0] for row in rows)
    return {row[0]: row for row in rows if duplicates[row[0]] == 1}


def _enum_names(body, names, start, end):
    reader, seen = _Reader(body), Counter()
    reader.position = start
    for _ in range(reader.number('I')):
        seen[names[reader.number('i')]] += 1
        reader.take(reader.number('H') * 12)
    _check(reader.position == end)
    return {name for name, count in seen.items() if count == 1}


def _native_fields(descriptors, pe):
    index = len(descriptors) - 1

    def take(depth=0, child=False):
        nonlocal index
        if depth > MAX_DEPTH or index < 0:
            raise ValueError('malformed_nesting')
        name, generator, dimension, callback = descriptors[index]
        index -= 1
        kind = generator & 63
        if generator & ~0x7f or kind not in WIRE_TYPES:
            raise ValueError('unsupported_generator_tag')
        if not 1 <= dimension <= 255 or child and dimension != 1:
            raise ValueError('unsupported_dimension')
        mode = 'struct' if kind == 25 else 'enum' if kind == 30 or kind == 0 and callback else None
        if mode and (not callback or pe.pointer(callback, code=True) is None):
            raise ValueError('invalid_native_constructor')
        children = ()
        if kind == 0 and callback:
            children = ((0, (), None, 0),)
        elif kind in (22, 24, 30, 33):
            children = (take(depth + 1, True)[2],)
        elif kind == 23:
            children = (take(depth + 1, True)[2], take(depth + 1, True)[2])
        wire = 26 if kind == 0 and callback else WIRE_TYPES[kind]
        if mode == 'enum' and (len(children) != 1 or children[0][0] not in (0, 2, 18, 19, 20, 21, 22, 23)):
            raise ValueError('unsupported_enum_underlying_type')
        return name, dimension, (wire, children, mode, callback)

    fields = []
    while index >= 0:
        fields.append(take())
    fields.reverse()
    if sum(row[1] for row in fields) > 65535:
        raise ValueError('property_index_limit')
    if len({row[0].casefold() for row in fields}) != len(fields):
        raise ValueError('duplicate_property_name')
    return fields


def _join(actual, expected, found, targets):
    kind, children, mode, callback = actual
    if kind != expected[0]:
        return False
    target = expected[-1] if kind in (9, 26) else None
    expected_children = expected[1:-1] if kind == 26 else () if kind == 9 else expected[1:]
    if len(children) != len(expected_children):
        return False
    if mode:
        if not target or target not in targets[mode]:
            return False
        found.append(((mode, callback), target))
    return all(_join(a, e, found, targets) for a, e in zip(children, expected_children))


def append_seeded_native_types(seed_usmap: bytes, client_pe: bytes) -> SeededSchemaResult:
    """Append new types whose callbacks have independent retained-schema witnesses.

    Old definitions and enum values are never replaced. This does not discover
    new enum names/values, decrypt native code, obtain keys or enable Setup.
    A changed seeded shape cannot be a witness. Unwitnessed/conflicting callback
    identities exclude the affected new type rather than inventing a target.
    """
    return _recover(seed_usmap, client_pe, refresh=False)


def refresh_seeded_native_types(seed_usmap: bytes, client_pe: bytes) -> RefreshedSchemaResult:
    """Build a new candidate, replacing only fully resolved current definitions.

    The original seed is immutable. Changed types cannot witness their own new
    layout, and unresolved known types are explicitly reported. Enum values and
    definitions absent from the native structure table still need validation.
    This experimental candidate is not a production preparation contract.
    """
    return _recover(seed_usmap, client_pe, refresh=True)


def _recover(seed_usmap, client_pe, *, refresh):
    body, names, name_end, struct_offset, struct_start, count, known = _seed(seed_usmap)
    seed = _seed_shapes(body, names, struct_start, count)
    targets = {'struct': set(seed), 'enum': _enum_names(body, names, name_end, struct_offset)}
    pe = _PE(client_pe)
    native = pe.native(with_callbacks=True)
    duplicates = Counter(row[0].casefold() for row in native)
    known_identities = {name.casefold() for name in known}
    parsed, excluded = {}, {}
    for name, _, _, _, descriptors in native:
        try:
            parsed[name] = _native_fields(descriptors, pe)
        except ValueError as error:
            excluded.setdefault(name, set()).add(str(error))
    votes, matched = defaultdict(lambda: defaultdict(set)), 0
    for name, parent, ops, flags, _ in native:
        retained, fields = seed.get(name), parsed.get(name)
        if (retained is None or fields is None or duplicates[name.casefold()] != 1
                or not ops or not flags & 1 or flags & ~0x205
                or retained[2] != sum(row[1] for row in fields) or len(retained[3]) != len(fields)
                or bool(parent) != bool(retained[1])):
            continue
        found, position = [], 0
        for actual, expected in zip(fields, retained[3]):
            if (expected[0] != position or actual[0] != expected[1] or actual[1] != expected[2]
                    or not _join(actual[2], expected[3], found, targets)):
                break
            position += actual[1]
        else:
            if parent:
                if retained[1] not in seed:
                    continue
                found.append((('struct', parent), retained[1]))
            matched += 1
            for key, target in found:
                votes[key][target].add(name)
    callback_kinds = defaultdict(set)
    for mode, callback in votes:
        callback_kinds[callback].add(mode)
    bindings = {key: next(iter(targets)) for key, targets in votes.items()
                if len(targets) == 1 and len(next(iter(targets.values()))) >= 2
                and len(callback_kinds[key[1]]) == 1}
    evidence = tuple(sorted((CallbackEvidence(key[0], target, tuple(sorted(votes[key][target])))
                             for key, target in bindings.items()), key=lambda row: (row.kind, row.target, row.owners)))

    def target(mode, callback):
        key = mode, callback
        if key in bindings:
            return bindings[key]
        if len(votes.get(key, {})) > 1 or len(callback_kinds.get(callback, ())) > 1:
            raise ValueError('conflicting_seed_constructor')
        raise ValueError('unwitnessed_native_constructor')

    def resolve(node):
        kind, children, mode, callback = node
        return kind, tuple(resolve(child) for child in children), target(mode, callback) if mode else None

    additions, replacements = [], {}

    def comparable(node):
        kind, children, resolved_target = node
        parts = (kind,) + tuple(comparable(child) for child in children)
        return parts + (resolved_target,) if kind in (9, 26) else parts

    for name, parent, ops, flags, _ in native:
        if name in known and not refresh:
            continue
        reasons = set(excluded.get(name, ()))
        if name not in known and name.casefold() in known_identities:
            reasons.add('seed_name_case_conflict')
        if duplicates[name.casefold()] != 1:
            reasons.add('duplicate_native_name')
        if not ops:
            reasons.add('missing_native_operations')
        if not flags & 1 or flags & ~0x205:
            reasons.add('unsupported_struct_flags')
        fields = parsed.get(name)
        try:
            super_name = target('struct', parent) if parent else None
            resolved = [(field, dimension, resolve(node)) for field, dimension, node in fields] if fields is not None else []
        except ValueError as error:
            reasons.add(str(error))
        if reasons:
            excluded[name] = reasons
        elif name in known:
            retained = seed.get(name)
            if retained is None:
                excluded[name] = {'duplicate_seed_name'}
                continue
            position, current_fields = 0, []
            for field_name, dimension, node in resolved:
                current_fields.append((position, field_name, dimension, comparable(node)))
                position += dimension
            # FName spelling alone does not change the unversioned wire layout.
            # Each current field is already unique under FName comparison.
            old_fields = [(i, n.casefold(), d, t) for i, n, d, t in retained[3]]
            new_fields = [(i, n.casefold(), d, t) for i, n, d, t in current_fields]
            if (super_name, position, new_fields) != (retained[1], retained[2], old_fields):
                replacements[name] = (name, super_name, resolved)
        else:
            additions.append((name, super_name, resolved))
    exclusions = tuple(Exclusion(name, tuple(sorted(reasons))) for name, reasons in sorted(excluded.items()) if refresh or name not in known)
    metadata = (hashlib.sha256(seed_usmap).hexdigest(), hashlib.sha256(client_pe).hexdigest())
    if not additions and not replacements:
        if refresh:
            return RefreshedSchemaResult(seed_usmap, *metadata, (), exclusions, len(native), matched, evidence, ())
        return SeededSchemaResult(seed_usmap, *metadata, (), exclusions, len(native), matched, evidence)
    _check(count + len(additions) <= MAX_TYPES)
    additions.sort(key=lambda row: row[0])
    lookup = {name: index for index, name in enumerate(names)}
    new_names, appended = bytearray(), bytearray()

    def named(value):
        if value is None:
            return struct.pack('<i', -1)
        if value not in lookup:
            _check(len(names) < MAX_NAMES)
            lookup[value] = len(names)
            names.append(value)
            encoded = value.encode('utf-8')
            new_names.extend(struct.pack('<H', len(encoded)) + encoded)
            _check(len(new_names) <= MAX_SEED)
        return struct.pack('<i', lookup[value])

    def wire(node):
        kind, children, resolved_target = node
        data = bytes([kind]) + b''.join(wire(child) for child in children)
        return data + named(resolved_target) if kind in (9, 26) else data

    def record(row):
        name, super_name, fields = row
        data = bytearray(named(name) + named(super_name) + struct.pack('<HH', sum(row[1] for row in fields), len(fields)))
        position = 0
        for field_name, dimension, shape in fields:
            data.extend(struct.pack('<HB', position, dimension) + named(field_name) + wire(shape))
            position += dimension
            _check(len(data) <= MAX_SEED)
        return data

    retained = bytearray()
    reader = _Reader(body)
    reader.position = struct_start

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
        reader.take(6)  # Parent and total slot count.
        length = reader.number('H')
        for _ in range(length):
            reader.take(7)
            skip_wire()
        retained.extend(record(replacements[name]) if name in replacements else body[begin:reader.position])
    for row in additions:
        appended.extend(record(row))
    _check(struct_start + len(new_names) + len(retained) + len(appended) + 16 <= MAX_SEED)
    expanded = (struct.pack('<I', len(names)) + body[4:name_end] + new_names + body[name_end:struct_offset]
                + struct.pack('<I', count + len(additions)) + retained + appended)
    result = struct.pack('<HBIBII', 0x30c4, 4, 0, 0, len(expanded), len(expanded)) + expanded
    if refresh:
        return RefreshedSchemaResult(result, *metadata, tuple(row[0] for row in additions), exclusions,
                                     len(native), matched, evidence, tuple(sorted(replacements)))
    return SeededSchemaResult(result, *metadata, tuple(row[0] for row in additions), exclusions, len(native), matched, evidence)
