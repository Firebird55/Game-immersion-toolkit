"""Experimental required-schema validation against original native descriptors.

Requested types come from the actual managed reader, never a game/type allowlist
or a newer community mapping. Unrelated exclusions do not veto a required
closure. A successful schema check is not complete narrative coverage or an
authorization to activate a new publisher snapshot.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import re
import struct

from .nte_native_schema import (Exclusion, MAX_NATIVE, MAX_NATIVE_PROPERTIES,
                                MAX_SCAN_MATCHES, MAX_TYPES, NATIVE_FLAGS,
                                _PE, _Reader, _check, _seed)
from .nte_seeded_schema import _enum_names, _join, _native_fields, _seed_shapes

VALIDATOR = 'nte-required-native-v1'


@dataclass(frozen=True)
class RequiredSchema:
    types: tuple[str, ...]
    enums: tuple[str, ...]
    evidence: tuple[tuple[str, str], ...]
    unresolved: tuple[Exclusion, ...]
    schema_sha256: str
    baseline_sha256: str
    client_sha256: str
    validator: str = VALIDATOR

    @property
    def eligible(self):
        return not self.unresolved


def _shape(row):
    """Normalize only unique FName spellings, preserving slot/type identities."""
    if row is None:
        return None
    return row[1], row[2], tuple((i, n.casefold(), d, t) for i, n, d, t in row[3])


def _equivalent(actual, expected):
    if _shape(actual) != _shape(expected):
        return False
    a, b = actual[3], expected[3]
    if len({r[1].casefold() for r in a}) != len(a) or len({r[1].casefold() for r in b}) != len(b):
        return False
    # A whole record cannot acquire its identity only through case folding.
    return not a or any(x[1] == y[1] for x, y in zip(a, b))


def _context(raw, seed, targets):
    pe = _PE(raw)
    rows = pe.native(with_callbacks=True, with_layout=True)
    duplicates = Counter(row[0].casefold() for row in rows)
    native = {r[0]: r for r in rows if duplicates[r[0].casefold()] == 1}
    parsed, votes = {}, defaultdict(lambda: defaultdict(set))
    for name, _, _, _, descriptors, _, _ in rows:
        try:
            parsed[name] = _native_fields(descriptors, pe)
        except ValueError:
            continue
    for name, parent, ops, flags, _, _, _ in rows:
        old, fields = seed.get(name), parsed.get(name)
        if (old is None or fields is None or duplicates[name.casefold()] != 1
                or old[2] != sum(row[1] for row in fields) or len(old[3]) != len(fields)
                or bool(parent) != bool(old[1])):
            continue
        # Retained complete definitions can identify their own existing field
        # targets, including custom serializers. This does not authorize new
        # custom layouts: validation below checks the original baseline's
        # flags, operations, size, alignment and complete field descriptors.
        found, position = [], 0
        for actual, expected in zip(fields, old[3]):
            if (expected[0] != position or actual[0] != expected[1] or actual[1] != expected[2]
                    or not _join(actual[2], expected[3], found, targets)):
                break
            position += actual[1]
        else:
            if parent:
                if old[1] not in seed:
                    continue
                found.append((('struct', parent), old[1]))
            for key, target in found:
                votes[key][target].add(name)
    modes = defaultdict(set)
    for mode, pointer in votes:
        modes[pointer].add(mode)

    def target(mode, pointer, minimum):
        choices = votes.get((mode, pointer), {})
        if len(choices) != 1 or len(modes[pointer]) != 1:
            raise ValueError('unproved_required_constructor')
        name, owners = next(iter(choices.items()))
        if len(owners) < minimum:
            raise ValueError('unproved_required_constructor')
        return name

    def descriptor(name, minimum=1):
        if name not in native or name not in parsed:
            raise ValueError('missing_or_ambiguous_native_descriptor')
        row, fields = native[name], parsed[name]
        def wire(node):
            kind, children, mode, pointer = node
            shape = (kind,) + tuple(wire(child) for child in children)
            return shape + (target(mode, pointer, minimum),) if mode else shape
        result, position = [], 0
        for field_name, dimension, node in fields:
            result.append((position, field_name, dimension, wire(node)))
            position += dimension
        return name, target('struct', row[1], minimum) if row[1] else None, position, result
    ambiguous = {row[0] for row in rows if duplicates[row[0].casefold()] != 1}
    return pe, native, parsed, descriptor, ambiguous


def _enums(pe):
    """Positive original enum-array evidence; no generated MAX synthesis."""
    def text(pointer):
        offset = pe.pointer(pointer)
        if offset is None:
            return None
        end = pe.data.find(b'\0', offset, offset + 512)
        if end <= offset or pe.pointer(pointer, end-offset+1) is None:
            return None
        raw = pe.data[offset:end]
        return raw.decode('ascii') if re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*', raw) else None
    found, matches, member_count = [], 0, 0
    for _, length, section, flags in pe.sections:
        if flags & 0x20000000 or not flags & 0x40000000:
            continue
        for hit in re.finditer(re.escape(struct.pack('<I', NATIVE_FLAGS)), pe.read(section, length)):
            matches += 1
            _check(matches <= MAX_SCAN_MATCHES)
            offset = section + hit.start()-40
            if offset < section or offset % 8 or offset+48 > section+length:
                continue
            outer, display, name, cpp, entries, _, count, enum_flags, form = pe.unpack('5QIHBB', offset)
            name, cpp = text(name), text(cpp)
            if (not name or not cpp or '::' in name or not (cpp == name or form == 1 and cpp.startswith(name+'::'))
                    or pe.pointer(outer, code=True) is None or display and pe.pointer(display, code=True) is None
                    or not 0 < count <= 4096 or enum_flags not in (0, 1) or form not in (0, 1, 2)):
                continue
            array = pe.pointer(entries, count*16)
            if array is None:
                continue
            members = []
            for index in range(count):
                pointer, value = pe.unpack('QQ', array+16*index)  # Preserve signed values' exact 64 bits.
                member = text(pointer)
                if member is None:
                    break
                parts = member.split('::')
                if len(parts) > 1 and '::'.join(parts[:-1]) not in (name, cpp):
                    break
                members.append((value, parts[-1]))
            else:
                if len({n.casefold() for _, n in members}) != len(members):
                    continue
                member_count += count
                _check(member_count <= MAX_NATIVE_PROPERTIES and len(found) < MAX_NATIVE)
                found.append((name, tuple(members), enum_flags, form))
    unique = Counter(row[0].casefold() for row in found)
    return {name: (members, flags, form) for name, members, flags, form in found if unique[name.casefold()] == 1}


def _enum_rows(body, names, start):
    reader = _Reader(body)
    reader.position = start
    rows = []
    for _ in range(reader.number('I')):
        name = names[reader.number('i')]
        rows.append((name, tuple((reader.number('Q'), names[reader.number('i')]) for _ in range(reader.number('H')))))
    counts = Counter(row[0] for row in rows)
    return {name: value for name, value in rows if counts[name] == 1}


def validate(seed_usmap, candidate_usmap, baseline_pe, client_pe, requested, *, reader_classes=None):
    """Validate the actual reader's recursive required closure, without controls.

    Native inputs must already be authenticated against retained original
    publisher identities. Reader classes are attested by the fixed managed
    reader's actual export objects: exact engine class name and managed class.
    They represent a frozen software format contract, not native equivalence.
    The caller must retain reader/source identities alongside this result.
    """
    _check(isinstance(requested, (list, tuple, set)) and 0 < len(requested) <= MAX_TYPES
           and all(isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in requested))
    old_body, old_names, old_ne, old_so, old_ss, old_count, _ = _seed(seed_usmap)
    body, names, ne, _, ss, count, _ = _seed(candidate_usmap)
    seed = _seed_shapes(old_body, old_names, old_ss, old_count)
    candidate = _seed_shapes(body, names, ss, count)
    targets = {'struct': set(seed), 'enum': _enum_names(old_body, old_names, old_ne, old_so)}
    baseline, native_old, parsed_old, describe_old, ambiguous_old = _context(baseline_pe, seed, targets)
    current, native, parsed, describe, ambiguous = _context(client_pe, seed, targets)
    old_enums, current_enums = _enums(baseline), _enums(current)
    seed_enums, candidate_enums = _enum_rows(old_body, old_names, old_ne), _enum_rows(body, names, ne)
    classes = {} if reader_classes is None else reader_classes
    _check(isinstance(classes, dict) and len(classes) <= MAX_TYPES)
    for name, implementation in classes.items():
        _check(isinstance(name, str) and isinstance(implementation, str) and len(implementation) <= 512
               and re.fullmatch(r'CUE4Parse\.UE4\.Assets\.Exports\.(?:[A-Za-z_][A-Za-z0-9_]*\.)*U[A-Za-z_][A-Za-z0-9_]*', implementation)
               and implementation.rsplit('.', 1)[-1] == 'U'+name)
    pending, required, enums, failures, evidence = list(requested), set(), set(), {}, []

    def dependencies(wire):
        kind = wire[0]
        if kind == 9 and wire[1]:
            pending.append(wire[1])
        elif kind == 26:
            if wire[2]: enums.add(wire[2])
            dependencies(wire[1])
        elif kind in (8, 25, 28):
            dependencies(wire[1])
        elif kind == 24:
            dependencies(wire[1]); dependencies(wire[2])

    while pending:
        name = pending.pop()
        if name in required:
            continue
        required.add(name)
        _check(len(required) <= MAX_TYPES)
        row, retained = candidate.get(name), seed.get(name)
        if row is None:
            failures[name] = {'missing_required_definition'}
            continue
        if row[1]: pending.append(row[1])
        for _, _, _, wire in row[3]: dependencies(wire)
        unchanged = _equivalent(row, retained)
        try:
            if name in ambiguous or name in ambiguous_old:
                raise ValueError('ambiguous_required_native_descriptor')
            if name not in native and name not in native_old:
                if not unchanged:
                    raise ValueError('missing_required_native_descriptor')
                if row[2] == 0 and not row[3]:
                    state = 'unchanged_empty_seed'
                elif name in classes:
                    state = 'frozen_reader_class'
                else:
                    raise ValueError('missing_required_native_descriptor')
            elif name not in native or name not in native_old and unchanged:
                raise ValueError('missing_required_native_descriptor')
            elif not native[name][2] or not native[name][3] & 1 or native[name][3] & ~0x205:
                before, after = native_old.get(name), native[name]
                if (not unchanged or before is None or bool(before[1]) != bool(after[1])
                        or bool(before[2]) != bool(after[2]) or before[3] != after[3] or before[5:] != after[5:]
                        or not _equivalent(describe_old(name), retained) or not _equivalent(describe(name), row)):
                    raise ValueError('changed_or_unproved_custom_descriptor')
                state = 'baseline_custom_descriptor'
            else:
                before, after = native_old.get(name), native[name]
                if before and (bool(before[2]) != bool(after[2]) or before[3] != after[3]):
                    raise ValueError('changed_native_serialization_flags')
                if not _equivalent(describe(name, 1 if unchanged else 2), row):
                    raise ValueError('stale_required_layout')
                if unchanged and not _equivalent(describe_old(name), retained):
                    raise ValueError('baseline_seed_mismatch')
                state = 'native_equivalent' if unchanged else 'native_refreshed'
            evidence.append((name, state))
        except ValueError as error:
            failures[name] = {str(error)}
    for name in sorted(enums):
        old, new = old_enums.get(name), current_enums.get(name)
        expected = candidate_enums.get(name)
        if new is None or expected is None:
            failures[name] = {'unproved_required_enum'}
        elif old == new and expected == seed_enums.get(name):
            evidence.append((name, 'baseline_enum_equivalent'))
        elif expected == new[0]:
            evidence.append((name, 'native_enum_refreshed'))
        else:
            failures[name] = {'stale_required_enum'}
    return RequiredSchema(tuple(sorted(required)), tuple(sorted(enums)), tuple(sorted(evidence)),
                          tuple(Exclusion(name, tuple(sorted(reasons))) for name, reasons in sorted(failures.items())),
                          hashlib.sha256(candidate_usmap).hexdigest(), hashlib.sha256(baseline_pe).hexdigest(),
                          hashlib.sha256(client_pe).hexdigest())
