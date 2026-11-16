"""Owned native descriptors and retained schema witnesses; no client execution."""
import struct

import pytest

from backend import nte_native_schema as native, nte_seeded_schema as seeded
from backend.tests.test_nte_native_schema import PE, pack, rich_seed


def seed(rows):
    names = ['Mood', 'Calm', 'Alert']
    def add(name):
        if name is not None and name not in names:
            names.append(name)
    def collect(shape):
        for part in shape[1:]:
            collect(part) if isinstance(part, tuple) else add(part)
    for name, parent, fields in rows:
        add(name); add(parent)
        for prop, dimension, shape in fields:
            add(prop); collect(shape)
    def named(name):
        return pack('i', -1 if name is None else names.index(name))
    def wire(shape):
        return bytes([shape[0]]) + b''.join(wire(part) if isinstance(part, tuple) else named(part) for part in shape[1:])
    body = pack('I', len(names)) + b''.join(pack('H', len(n)) + n.encode() for n in names)
    body += pack('I', 1) + named('Mood') + pack('HQ', 2, 0) + named('Calm') + pack('Q', 1) + named('Alert')
    body += pack('I', len(rows))
    for name, parent, fields in rows:
        body += named(name) + named(parent) + pack('HH', sum(row[1] for row in fields), len(fields))
        index = 0
        for prop, dimension, shape in fields:
            body += pack('HB', index, dimension) + named(prop) + wire(shape)
            index += dimension
    return pack('HBIBII', 0x30c4, 4, 0, 0, len(body), len(body)) + body


def shapes(raw):
    body, names, _, _, start, count, _ = native._seed(raw)
    return seeded._seed_shapes(body, names, start, count)


def callback(client, descriptor, index, pointer):
    pointer_array, = struct.unpack_from('<Q', client.blob, descriptor + 32)
    array_offset = pointer_array - client.base - client.data_rva + 0x600
    field, = struct.unpack_from('<Q', client.blob, array_offset + 8 * index)
    offset = field - client.base - client.data_rva + 0x600
    client.put(offset + 56, 'Q', pointer)


def fixture(*, witnesses=2, base=0x140000000, code_rva=0x1000, data_rva=0x2000,
            direct_enum=False, drift=None):
    client = PE(base=base, code_rva=code_rva, data_rva=data_rva)
    position, mood, parent = client.code + 16, client.code + 32, client.code + 48
    fields = [('Position', 1, (9, 'Vector')), ('Mood', 1, (26, (0,), 'Mood'))]
    retained = [('Vector', None, []), ('Base', None, [])]
    descriptors = []
    for number in range(witnesses):
        name = 'Existing' + str(number)
        expected = fields
        actual = [('Position', 25), ('Mood', 0, 1, True)] if direct_enum else [
            ('Position', 25), ('UnderlyingType', 0), ('Mood', 30)]
        if drift and number == 1:
            expected = drift(fields)
        retained.append((name, 'Base', expected))
        desc = client.native(name, actual, parent=True)
        client.put(desc + 8, 'Q', parent)
        callback(client, desc, 0, position)
        callback(client, desc, 1 if direct_enum else 2, mood)
        descriptors.append(desc)
    new = client.native('NewCaption', [('Positions', 25), ('Positions', 22), ('Mood', 0, 1, True)], parent=True)
    client.put(new + 8, 'Q', parent)
    callback(client, new, 0, position)
    callback(client, new, 2, mood)
    return seed(retained), client, descriptors, new


@pytest.mark.parametrize('direct_enum', [False, True])
@pytest.mark.parametrize('layout', [(0x140000000, 0x1000, 0x2000), (0x180000000, 0x3000, 0x7000)])
def test_seeded_callbacks_preserve_parent_nested_types_and_enum_identity_without_code_execution(direct_enum, layout):
    original, client, _, _ = fixture(direct_enum=direct_enum, base=layout[0], code_rva=layout[1], data_rva=layout[2])
    # Arbitrary protected code bytes are never decoded, loaded or executed.
    client.blob[0x400:0x600] = b'\xcc' * 0x200
    before = bytes(client.blob)
    result = seeded.append_seeded_native_types(original, before)
    assert result.appended == ('NewCaption',)
    added = shapes(result.data)['NewCaption']
    assert added[1:3] == ('Base', 2)
    assert [row[3] for row in added[3]] == [(8, (9, 'Vector')), (26, (0,), 'Mood')]
    assert len(result.callbacks) == 3 and all(len(row.owners) == 2 for row in result.callbacks)
    assert shapes(result.data).keys() == shapes(original).keys() | {'NewCaption'}
    # Root-only recovery keeps its original conservative behavior.
    assert native.append_native_root_types(original, before).data == original
    old_body, _, old_names_end, old_struct_offset, old_struct_start, _, _ = native._seed(original)
    body, _, names_end, struct_offset, struct_start, _, _ = native._seed(result.data)
    assert body[names_end:struct_offset] == old_body[old_names_end:old_struct_offset]
    assert body[struct_start:struct_start + len(old_body) - old_struct_start] == old_body[old_struct_start:]
    assert bytes(client.blob) == before


def test_one_owner_or_repeated_occurrence_cannot_certify_constructor_identity():
    original, client, _, _ = fixture(witnesses=1)
    result = seeded.append_seeded_native_types(original, client.bytes())
    assert result.data == original and not result.callbacks
    assert any('unwitnessed_native_constructor' in row.reasons for row in result.excluded)


@pytest.mark.parametrize('drift', [
    lambda fields: [('RenamedPosition', *fields[0][1:]), fields[1]],
    lambda fields: [('Position', 2, fields[0][2]), fields[1]],
    lambda fields: [('Position', 1, (10,)), fields[1]],
    lambda fields: list(reversed(fields)),
])
def test_changed_seed_shape_cannot_be_a_witness(drift):
    original, client, _, _ = fixture(drift=drift)
    result = seeded.append_seeded_native_types(original, client.bytes())
    assert not result.appended and result.data == original


def test_conflicting_seed_targets_are_excluded_instead_of_choosing_a_majority():
    original, client, _, _ = fixture(witnesses=3)
    rows = shapes(original)
    rewritten = []
    for name, parent, _, fs in rows.values():
        fields = [(field, dim, (9, 'Other') if name == 'Existing2' and field == 'Position' else wire)
                  for _, field, dim, wire in fs]
        rewritten.append((name, parent, fields))
    rewritten.append(('Other', None, []))
    result = seeded.append_seeded_native_types(seed(rewritten), client.bytes())
    assert not result.appended
    assert 'conflicting_seed_constructor' in next(row.reasons for row in result.excluded if row.name == 'NewCaption')


@pytest.mark.parametrize('tamper', ['data_pointer', 'unknown_callback', 'mixed_enum_struct', 'non_integral_enum', 'unsupported_flags'])
def test_invalid_or_unwitnessed_callbacks_never_emit_partial_new_type(tamper):
    original, client, witnesses, new = fixture()
    if tamper == 'data_pointer':
        callback(client, new, 0, client.base + client.data_rva)
    elif tamper == 'unknown_callback':
        callback(client, new, 0, client.code + 80)
    elif tamper == 'mixed_enum_struct':
        for desc in witnesses:
            callback(client, desc, 2, client.code + 16)
        callback(client, new, 2, client.code + 16)
    elif tamper == 'non_integral_enum':
        pointer_array, = struct.unpack_from('<Q', client.blob, witnesses[1] + 32)
        array_offset = pointer_array - client.base - client.data_rva + 0x600
        prop, = struct.unpack_from('<Q', client.blob, array_offset + 8)
        client.put(prop - client.base - client.data_rva + 0x600 + 24, 'I', 10)
    else:
        client.put(witnesses[1] + 52, 'I', 0x80000001)
    result = seeded.append_seeded_native_types(original, client.bytes())
    assert result.data == original and not result.appended


def test_existing_duplicate_definitions_and_unknown_inputs_retain_strict_validation():
    source = rich_seed(True)
    client = PE()
    result = seeded.append_seeded_native_types(source, client.bytes())
    assert result.data == source and not result.appended
    with pytest.raises(ValueError):
        seeded.append_seeded_native_types(source + b'extra', client.bytes())


@pytest.mark.parametrize('target_problem', ['duplicate_struct', 'missing_enum'])
def test_ambiguous_or_undefined_retained_target_cannot_certify_new_reference(target_problem):
    original, client, _, _ = fixture()
    if target_problem == 'duplicate_struct':
        rows = [(name, parent, [(field, dim, wire) for _, field, dim, wire in fields])
                for name, parent, total, fields in shapes(original).values()]
        original = seed([*rows, ('Vector', None, [])])
    else:
        # This remains a syntactically valid retained mapping, but the property
        # refers to Mood while the sole enum definition now has another name.
        _, _, names_end, _, _, _, _ = native._seed(original)
        changed = bytearray(original)
        struct.pack_into('<i', changed, 16 + names_end + 4, 1)
        original = bytes(changed)
    result = seeded.append_seeded_native_types(original, client.bytes())
    assert result.data == original and not result.appended


@pytest.mark.parametrize('limit', ['MAX_NAMES', 'MAX_TYPES', 'MAX_SEED'])
def test_generated_mapping_bounds_reject_without_partial_output(monkeypatch, limit):
    original, client, _, _ = fixture()
    _, names, _, _, _, count, _ = native._seed(original)
    bound = len(names) if limit == 'MAX_NAMES' else count if limit == 'MAX_TYPES' else len(original) + 1
    monkeypatch.setattr(seeded, limit, bound)
    before = client.bytes()
    with pytest.raises(ValueError):
        seeded.append_seeded_native_types(original, before)
    assert client.bytes() == before
