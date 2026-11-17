"""Owned PE/descriptors and usmap data; no game binary, mapping or parameters."""
import struct

import pytest
import zstandard

from backend import nte_native_schema as schema


def pack(fmt, *values):
    return struct.pack('<' + fmt, *values)


def seed(*names, compressed=False):
    names = names or ('Retained',)
    body = pack('I', len(names)) + b''.join(pack('H', len(n)) + n.encode() for n in names)
    body += pack('II', 0, len(names))
    for index in range(len(names)):
        body += pack('iiHH', index, -1, 0, 0)
    stored = zstandard.ZstdCompressor().compress(body) if compressed else body
    return pack('HBIBII', 0x30c4, 4, 0, 3 if compressed else 0, len(stored), len(body)) + stored


def rich_seed(compressed):
    names = ('Retained', 'Caption', 'WireEnum', 'Option')
    body = pack('I', len(names)) + b''.join(pack('H', len(n)) + n.encode() for n in names)
    body += pack('IiHQiI', 1, 2, 1, 257, 3, 2)
    # Both pre-existing duplicate records, including typed enum references,
    # retain their original bytes and order.
    for _ in range(2):
        body += pack('iiHHHBi', 0, -1, 1, 1, 0, 1, 1) + pack('BBi', 26, 0, 2)
    stored = zstandard.ZstdCompressor().compress(body) if compressed else body
    return pack('HBIBII', 0x30c4, 4, 0, 3 if compressed else 0, len(stored), len(body)) + stored


def unknown_size_seed():
    names = tuple(f'Owned{i:04}_' + 'X'*500 for i in range(1200))
    body = seed(*names)[16:]
    compressed = zstandard.ZstdCompressor(write_content_size=False).compress(body)
    return body, names, pack('HBIBII', 0x30c4, 4, 0, 3, len(compressed), len(body)) + compressed


def test_unknown_size_zstd_seed_uses_the_actual_pinned_c_backend_byte_window():
    assert zstandard.__version__ == '0.25.0'
    assert zstandard.ZstdDecompressor.__module__ == 'zstandard.backend_c'
    body, names, raw = unknown_size_seed()
    parameters = zstandard.get_frame_parameters(raw[16:])
    assert parameters.content_size == zstandard.CONTENTSIZE_UNKNOWN
    assert zstandard.frame_content_size(raw[16:]) == -1
    assert schema.MAX_EXPANDED//1024 < parameters.window_size <= schema.MAX_EXPANDED
    result = schema._seed(raw)
    assert result[0] == body and tuple(result[1]) == names and result[5] == len(names)


@pytest.mark.parametrize('change', ['frame-window', 'output-length', 'declared-output-cap', 'extra-frame'])
def test_unknown_size_zstd_seed_keeps_window_and_output_bounds(change):
    _body, _names, raw = unknown_size_seed()
    raw = bytearray(raw)
    if change == 'frame-window':
        # Unknown-size frames have a window descriptor after magic + FHD.
        assert raw[20] == 0
        raw[21] = 0x88  # 128 MiB, beyond the retained 64 MiB native-schema cap.
        assert zstandard.get_frame_parameters(raw[16:]).window_size > schema.MAX_EXPANDED
    elif change == 'output-length':
        struct.pack_into('<I', raw, 12, len(_body)-1)
    elif change == 'declared-output-cap':
        struct.pack_into('<I', raw, 12, schema.MAX_EXPANDED+1)
    else:
        raw.extend(zstandard.ZstdCompressor().compress(b'owned trailing frame'))
        struct.pack_into('<I', raw, 8, len(raw)-16)
    with pytest.raises(ValueError):
        schema._seed(bytes(raw))


def test_unknown_size_seed_does_not_accept_the_distinct_invalid_content_size_sentinel(monkeypatch):
    _body, _names, raw = unknown_size_seed()
    monkeypatch.setattr(schema.zstandard, 'frame_content_size', lambda _: -2)
    with pytest.raises(ValueError):
        schema._seed(raw)


def test_unknown_size_seed_retains_unsigned_metadata_api_compatibility(monkeypatch):
    body, _names, raw = unknown_size_seed()
    monkeypatch.setattr(schema.zstandard, 'frame_content_size', lambda _: zstandard.CONTENTSIZE_UNKNOWN)
    assert schema._seed(raw)[0] == body


class PE:
    def __init__(self, *, base=0x140000000, code_rva=0x1000, data_rva=0x2000):
        self.blob = bytearray(0x4600)
        self.base, self.code_rva, self.data_rva = base, code_rva, data_rva
        self.cursor = 0x600
        self.blob[:2] = b'MZ'
        self.put(60, 'I', 0x80)
        self.blob[0x80:0x84] = b'PE\0\0'
        self.put(0x84, 'HH', 0x8664, 2)
        self.put(0x94, 'H', 0xf0)
        optional = 0x98
        self.put(optional, 'H', 0x20b)
        self.put(optional + 24, 'Q', base)
        self.put(optional + 56, 'II', data_rva + 0x4000, 0x400)
        self.section_table = optional + 0xf0
        for index, (name, rva, size, offset, flags) in enumerate([
                (b'.owncode', code_rva, 0x200, 0x400, 0x60000020),
                (b'.owndata', data_rva, 0x4000, 0x600, 0x40000040)]):
            pos = self.section_table + 40 * index
            self.blob[pos:pos + 8] = name
            self.put(pos + 8, 'IIII', size, rva, size, offset)
            self.put(pos + 36, 'I', flags)

    @property
    def code(self):
        return self.base + self.code_rva

    def put(self, offset, fmt, *values):
        data = pack(fmt, *values)
        self.blob[offset:offset + len(data)] = data

    def alloc(self, size):
        self.cursor = (self.cursor + 7) & ~7
        offset = self.cursor
        self.cursor += size
        assert self.cursor <= len(self.blob)
        return offset, self.base + self.data_rva + offset - 0x600

    def name(self, name):
        offset, address = self.alloc(len(name) + 1)
        self.blob[offset:offset + len(name)] = name.encode()
        return address

    def native(self, name, fields=(), *, parent=False, ops=True, flags=1):
        pointers = []
        for field in fields:
            field_name, generator, *options = field
            dimension = options[0] if options else 1
            enum = options[1] if len(options) > 1 else False
            field_name = self.name(field_name)
            offset, address = self.alloc(64)
            self.put(offset, 'Q', field_name)
            self.put(offset + 24, 'II', generator, schema.NATIVE_FLAGS)
            self.put(offset + 48, 'H', dimension)
            self.put(offset + 56, 'Q', self.code if enum else 0)
            pointers.append(address)
        if pointers:
            offset, address = self.alloc(8 * len(pointers))
            self.put(offset, f'{len(pointers)}Q', *pointers)
        else:
            address = 0
        name = self.name(name)
        offset, _ = self.alloc(56)
        self.put(offset, '5QHH3I', self.code, self.code if parent else 0,
                 self.code if ops else 0, name, address, len(pointers), 64, 8, schema.NATIVE_FLAGS, flags)
        return offset

    def bytes(self):
        return bytes(self.blob)


def parsed_structs(raw):
    body, names, _, _, start, count, _ = schema._seed(raw)
    reader = schema._Reader(body)
    reader.position = start

    def wire():
        kind = reader.number('B')
        if kind == 26:
            inner = wire()
            return kind, inner, names[reader.number('i')]
        if kind in (8, 25, 28):
            return kind, wire()
        if kind == 24:
            return kind, wire(), wire()
        return kind

    result = []
    for _ in range(count):
        name = names[reader.number('i')]
        parent, total, fields = reader.number('i'), reader.number('H'), reader.number('H')
        values = []
        for _ in range(fields):
            index, dim = reader.number('H'), reader.number('B')
            values.append((index, dim, names[reader.number('i')], wire()))
        result.append((name, parent, total, values))
    return result


@pytest.mark.parametrize('compressed', [False, True])
def test_append_keeps_every_old_name_enum_and_struct_byte(compressed):
    original = rich_seed(compressed)
    client = PE()
    client.native('FreshCaption', [('Caption', 29), ('Voice', 20)])
    result = schema.append_native_root_types(original, client.bytes())
    assert result.appended == ('FreshCaption',) and not result.excluded
    retained = ('Retained', -1, 1, [(0, 1, 'Caption', (26, 0, 'WireEnum'))])
    assert parsed_structs(result.data) == [retained, retained,
        ('FreshCaption', -1, 2, [(0, 1, 'Caption', 11), (1, 1, 'Voice', 5)])]
    old, _, old_end, enum_start, struct_start, _, _ = schema._seed(original)
    new, _, new_end, new_enum_start, new_struct_start, _, _ = schema._seed(result.data)
    assert new[4:old_end] == old[4:old_end]
    assert new[new_end:new_enum_start] == old[old_end:enum_start]
    assert new[new_struct_start:new_struct_start + len(old) - struct_start] == old[struct_start:]


def test_original_record_cannot_be_overwritten_and_absent_additions_preserve_compression():
    client = PE()
    client.native('Retained', [('Different', 20)])
    original = seed(compressed=True)
    result = schema.append_native_root_types(original, client.bytes())
    assert not result.appended and result.data == original


def test_native_addresses_are_derived_from_pe_sections_not_known_offsets():
    first, relocated = PE(), PE(base=0x180000000, code_rva=0x3000, data_rva=0x8000)
    for pe in (first, relocated):
        pe.native('Fresh', [('Caption', 29)])
    left = schema.append_native_root_types(seed(), first.bytes())
    right = schema.append_native_root_types(seed(), relocated.bytes())
    assert left.data == right.data and left.client_sha256 != right.client_sha256


def test_array_map_set_and_static_dimensions_follow_declared_descriptor_order():
    client = PE()
    # Child names intentionally do not encode their owning field.
    client.native('Containers', [('value', 10), ('key', 3), ('Map', 23),
        ('element', 20), ('Array', 22), ('set_element', 3), ('Set', 24), ('Fixed', 3, 2)])
    result = schema.append_native_root_types(seed(), client.bytes())
    assert parsed_structs(result.data)[-1] == ('Containers', -1, 5, [
        (0, 1, 'Map', (24, 2, 3)), (1, 1, 'Array', (8, 5)),
        (2, 1, 'Set', (25, 2)), (3, 2, 'Fixed', 2)])


@pytest.mark.parametrize('fields,options,reason', [
    ([('Caption', 29)], {'parent': True}, 'native_super_constructor'),
    ([('Child', 25)], {}, 'native_struct_constructor'),
    ([('ByteEnum', 0, 1, True)], {}, 'enum_constructor'),
    ([('Underlying', 0), ('Enum', 30)], {}, 'enum_constructor'),
    ([('Caption', 29)], {'ops': False}, 'missing_native_operations'),
    ([('Caption', 29)], {'flags': 17}, 'unsupported_struct_flags'),
    ([('Caption', 0x100 | 29)], {}, 'unsupported_generator_tag'),
    ([('Caption', 63)], {}, 'unsupported_generator_tag'),
    ([('Array', 22)], {}, 'malformed_nesting'),
    ([('Child', 20, 2), ('Array', 22)], {}, 'unsupported_dimension'),
    ([('Caption', 29, 256)], {}, 'unsupported_dimension'),
    ([('Caption', 29), ('caption', 20)], {}, 'duplicate_property_name'),
])
def test_unsupported_semantics_exclude_the_entire_type(fields, options, reason):
    client = PE()
    client.native('Unresolved', fields, **options)
    original = seed(compressed=True)
    result = schema.append_native_root_types(original, client.bytes())
    assert result.data == original and not result.appended
    assert result.excluded == (schema.Exclusion('Unresolved', (reason,)),)


def test_even_identical_duplicate_native_names_have_no_arbitrary_winner():
    client = PE()
    for _ in range(2):
        client.native('Duplicate', [('Caption', 29)])
    result = schema.append_native_root_types(seed(), client.bytes())
    assert not result.appended
    assert result.excluded == (schema.Exclusion('Duplicate', ('duplicate_native_name',)),)


def test_conflicting_duplicate_reasons_are_merged_without_choosing_one_owner():
    client = PE()
    client.native('Duplicate', [('Caption', 29)])
    client.native('Duplicate', [('Child', 25)], parent=True)
    result = schema.append_native_root_types(seed(), client.bytes())
    assert not result.appended
    assert result.excluded == (schema.Exclusion('Duplicate', (
        'duplicate_native_name', 'native_struct_constructor', 'native_super_constructor')),)


def test_case_variants_do_not_create_an_extra_semantic_type():
    client = PE()
    client.native('retained', [('Caption', 29)])
    result = schema.append_native_root_types(seed(), client.bytes())
    assert not result.appended
    assert result.excluded == (schema.Exclusion('retained', ('seed_name_case_conflict',)),)
    client = PE()
    client.native('Fresh', [('Caption', 29)])
    client.native('fresh', [('Caption', 29)])
    result = schema.append_native_root_types(seed(), client.bytes())
    assert not result.appended and all(item.reasons == ('duplicate_native_name',) for item in result.excluded)


@pytest.mark.parametrize('mutation', ['truncated', 'overlap', 'foreign_machine', 'bad_signature'])
def test_malformed_pe_cannot_produce_a_mapping(mutation):
    client = PE()
    client.native('Fresh', [('Caption', 29)])
    if mutation == 'overlap':
        client.put(client.section_table + 40 + 12, 'I', client.code_rva)
    elif mutation == 'foreign_machine':
        client.put(0x84, 'H', 0x14c)
    elif mutation == 'bad_signature':
        client.blob[0x80] = 0
    raw = client.bytes()[:-1] if mutation == 'truncated' else client.bytes()
    with pytest.raises(ValueError):
        schema.append_native_root_types(seed(), raw)


def test_truncated_property_pointer_array_cannot_leave_a_partial_type():
    client = PE()
    pos = client.native('Incomplete', [('Caption', 29), ('Voice', 20)])
    client.put(pos + 32, 'Q', client.base + client.data_rva + 0x3ffc)
    result = schema.append_native_root_types(seed(), client.bytes())
    assert not result.appended and result.data == seed()


def test_duplicate_property_pointer_cannot_become_two_partial_fields():
    client = PE()
    pos = client.native('Incomplete', [('Caption', 29), ('Voice', 20)])
    pointers = struct.unpack_from('<Q', client.blob, pos + 32)[0]
    location = pointers - client.base - client.data_rva + 0x600
    first = struct.unpack_from('<Q', client.blob, location)[0]
    client.put(location + 8, 'Q', first)
    result = schema.append_native_root_types(seed(), client.bytes())
    assert not result.appended and result.data == seed()


def test_a_name_and_flags_without_native_owner_identity_are_insufficient():
    client = PE()
    pos = client.native('CaptionLookingName', [('Caption', 29)])
    client.put(pos, 'Q', 0)
    assert not schema.append_native_root_types(seed(), client.bytes()).appended


def test_native_size_alignment_must_be_coherent():
    client = PE()
    pos = client.native('Incomplete', [('Caption', 29)])
    client.put(pos + 42, 'H', 65)
    assert not schema.append_native_root_types(seed(), client.bytes()).appended


@pytest.mark.parametrize('mutation', ['short', 'size', 'compression', 'trailing', 'expanded'])
def test_malformed_seed_is_rejected_before_appending(mutation):
    raw = bytearray(seed(compressed=True))
    if mutation == 'short':
        raw = raw[:12]
    elif mutation == 'size':
        struct.pack_into('<I', raw, 8, len(raw))
    elif mutation == 'compression':
        raw[7] = 2
    elif mutation == 'trailing':
        raw += b'ignored'
        struct.pack_into('<I', raw, 8, len(raw) - 16)
    elif mutation == 'expanded':
        struct.pack_into('<I', raw, 12, 1)
    with pytest.raises(ValueError):
        schema.append_native_root_types(bytes(raw), PE().bytes())


def test_caps_bound_client_descriptors_nesting_and_generated_output(monkeypatch):
    client = PE()
    client.native('Fresh', [('Caption', 29)])
    with monkeypatch.context() as patch:
        patch.setattr(schema, 'MAX_CLIENT', len(client.bytes()) - 1)
        with pytest.raises(ValueError):
            schema.append_native_root_types(seed(), client.bytes())
    with monkeypatch.context() as patch:
        patch.setattr(schema, 'MAX_NATIVE_PROPERTIES', 0)
        with pytest.raises(ValueError):
            schema.append_native_root_types(seed(), client.bytes())
    with monkeypatch.context() as patch:
        patch.setattr(schema, 'MAX_SEED', len(seed()) + 1)
        with pytest.raises(ValueError):
            schema.append_native_root_types(seed(), client.bytes())
    nested = PE()
    nested.native('Deep', [('Leaf', 20)] + [(f'Array{i}', 22) for i in range(schema.MAX_DEPTH + 1)])
    result = schema.append_native_root_types(seed(), nested.bytes())
    assert result.excluded == (schema.Exclusion('Deep', ('malformed_nesting',)),)
