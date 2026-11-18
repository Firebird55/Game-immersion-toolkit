import hashlib
import os
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_declaration_census as census
from backend import starrail_portable_metadata as portable
from backend.starrail_portable_metadata import MetadataCancelled, MetadataFormatError, OriginalInput, read_required


# Authored encrypted records with fixed expected values. This fixture contains
# no original client bytes and avoids a production-code roundtrip.
_HEADER = bytes.fromhex(
    '4d4859000000000027b7ee08000000000000000000000000147a3219000000007720034d000000000000000000000000'
    'c2040a230000000000000000fb1f74686b5b683c00000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000000000000000000000000000000000000000000000003f1c53680000000000000000'
    '000000000000000000000000493981430000000000000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000007a06f767'
    'c175b7620000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000c0fbf026add05b01030721100000000000000000f79453250000000012129e32acbf5f0c'
    'c29e7d27000000004f1dc11f0000000000000000385b5c7f000000000000000000000000000000000000000000000000'
    '9d1b241b000000000000000000000000000000000000000000000000000000000000000000000000131a9b725e050837'
    '00000000925ebc7200000000000000000000000000000000359a2f040000000000000000000000000000000000000000'
    '000000000000000000000000ffdda5580dd7c7560000000000000000d0c538620000000000000000'
)
_IMAGE = bytes.fromhex('000000009429cac000000000efd856f700000000db5fc3f400000000000000000000000000000000')
_GLOBAL_ROWS = (
    (0x100,
     '000000004655f948fff57a1aabd22a1c00000000917312010000000000000000653885747fd22c160897022000000000'
     '0000b4bb6ea0000000003f4dfbab0000000000fc0000000000004855f948010a85e5abd22a1c00000000917312010000'
     '000000000000633885747fd22c1688970220000000000000b3bb6da0000000003f4dfbab0000000000fc0000'),
    (0x208,
     'e2e377b049ab27cf'),
    (0x25a,
     '6c06eff13ec406f7a158dc5c7244a07a6de6c1dd7d2b00002c00'),
    (0x298,
     'f31264764a160ec2'),
    (0x300,
     '01000000'),
    (0x334,
     '02000000'),
    (0x368,
     '18000000'),
    (0x380,
     '655c0899a8000000b0aa4f0c000000008118a8a28d631e53d73267000000000012ed7adc4dc300006676dc7100000000'
     '65d604f72e596af9acd6ccc87d260ca5bdf0959f80dcb868bdc24750d7976024aff50c0efe70ddeecef7f2d136094db6'
     'f6f89dab6fcc1560e2f1587464b9862e09fd17000000000000000000000000006b388da583000000'),
    (0x500,
     '0f5f6a27c53747576e080087'),
    (0x580,
     'c76e8ba6ed38ab97e63206bf53c9655ecf35878901847c0bd17d7881a640cde5a97abf66761c862bbc705a3506d72472'
     '8948df45aa25e2f96f400a14fef17a3bb695bb633de6475705796b3aaef6'),
)
_IMAGE_BASE = 0x180000000
_DATA_RVA = 0x80000
_TYPE_RVA = _DATA_RVA + 0x1000


def _registration(native, at):
    rva = 0x1000 + at - 0x400
    for i, target in enumerate((0x260, 0x360, 0x460, 0x480)):
        lea = b'\x48\x8d\x05' + struct.pack('<i', _DATA_RVA + target - (rva + i * 14 + 7))
        native[at + i * 14:at + i * 14 + 14] = lea + b'\x48\x89\x05\0\0\0\0'


def _sources(tmp_path, *, seam=False, ambiguous=None, invalid_pointer=False, excess_parameters=False,
             runtime_rows=bytes(48), runtime_count=3, overlay=b''):
    code_length = 0x40000 if seam else 0x200
    if seam:
        code_length += 0x200
    data_at = 0x400 + code_length
    data_length = 0x1000 + len(runtime_rows)
    native = bytearray(data_at + data_length)
    native[:2] = b'MZ'
    struct.pack_into('<I', native, 60, 0x80)
    struct.pack_into('<4sHH12xH', native, 0x80, b'PE\0\0', 0x8664, 2, 240)
    optional_at = 0x80 + 24
    struct.pack_into('<H', native, optional_at, 0x20b)
    struct.pack_into('<Q', native, optional_at + 24, _IMAGE_BASE)
    struct.pack_into('<I', native, optional_at + 108, 16)
    struct.pack_into('<II', native, optional_at + 136, _DATA_RVA + 0x5c0, 12)
    sections = optional_at + 240
    struct.pack_into('<III', native, sections + 12, 0x1000, code_length, 0x400)
    struct.pack_into('<I', native, sections + 36, 0x20000000)
    struct.pack_into('<III', native, sections + 40 + 12, _DATA_RVA, data_length, data_at)
    _registration(native, 0x40000 - 19 if seam else 0x470)
    native[0x410:0x414] = b'MHY\0'
    native[data_at + 0x40:data_at + 0x40 + len(_HEADER)] = _HEADER
    native[data_at + 0x700:data_at + 0x704] = b'MHY\0'  # Rejected as an invalid header.
    if ambiguous == 'registration':
        _registration(native, 0x4b0)
    elif ambiguous == 'header':
        native[data_at + 0x800:data_at + 0x800 + len(_HEADER)] = _HEADER
    struct.pack_into('<Q', native, data_at + 0x260 + 0x40, _IMAGE_BASE + _DATA_RVA + 0x560)
    struct.pack_into('<I', native, data_at + 0x360 + 0x48, 1455078204 + runtime_count)
    struct.pack_into('<Q', native, data_at + 0x360 + 0x80, _IMAGE_BASE + _TYPE_RVA)
    struct.pack_into('<I', native, data_at + 0x460 + 0x2c, 0x0bd08dca)
    target = _DATA_RVA + 0x5c0 if invalid_pointer else 0x1020
    struct.pack_into('<Q', native, data_at + 0x568, _IMAGE_BASE + target)
    native[data_at + 0x1000:] = runtime_rows
    native.extend(overlay)
    payload = bytearray(0x900)
    for at, row in _GLOBAL_ROWS:
        data = bytes.fromhex(row)
        payload[at:at + len(data)] = data
    if excess_parameters:
        payload[0x25a + 0x18] ^= 0x40
    startup = b'\0' * 0x20 + _IMAGE + b'\0' * (0x240 - 0x20 - len(_IMAGE))
    values = {'native': native, 'metadata': _HEADER + payload, 'startup': startup}
    sources = {}
    for role, value in values.items():
        path = tmp_path / role
        path.write_bytes(value)
        sources[role] = OriginalInput(path, len(value), hashlib.md5(value).hexdigest())
    return sources


def test_selected_records_join_original_owners_and_decode_cross_chunk_registration(tmp_path):
    # The header declares one trailing type byte and three trailing image bytes.
    # The startup generic-class offset is inside the global field row's numeric
    # range. The separate source coordinates keep that global row readable.
    selected = read_required(_sources(tmp_path, seam=True), type_indices=(0,), method_indices=(1,), literal_indices=(0, 1))

    assert selected['types'] == {0: {
        'name': 'Actor', 'namespace': 'Demo', 'image': 'Example.dll', 'image_index': 0,
        'parent': -1, 'declaring_type': -1, 'flags': 1, 'field_start': 1, 'field_count': 1,
        'method_start': 1, 'method_count': 1, 'nested_start': -1, 'nested_count': 0, 'generic_container': -1,
    }}
    assert selected['fields'] == {1: {'owner': 0, 'type': 2, 'name': 'volume', 'offset': 24}}
    assert selected['methods'] == {1: {
        'owner': 0, 'name': 'Read', 'return_type': 1, 'flags': 0x16, 'generic_container': -1,
        'parameters': ((2, 'argument_with_an_original_name_longer_than_the_short_encoding_bound'),),
        'rva': 0x1020,
    }}
    assert selected['literals'] == {
        0: '', 1: 'Data goes through both the word batches and the final lane. 你好, Star Rail.',
    }


@pytest.mark.parametrize(('defect', 'component'), [
    ({'ambiguous': 'registration'}, 'registration locator'),
    ({'ambiguous': 'header'}, 'metadata header locator'),
    ({'invalid_pointer': True}, 'PE address ownership'),
    ({'excess_parameters': True}, 'method parameter count'),
])
def test_authenticated_malformed_native_or_metadata_fails_closed(tmp_path, defect, component):
    with pytest.raises(MetadataFormatError, match=component):
        read_required(_sources(tmp_path, **defect), method_indices=(1,))


def test_unowned_literal_index_stops_at_the_boundary_sentinel(tmp_path):
    sources = _sources(tmp_path)
    with pytest.raises(MetadataFormatError, match='literal index'):
        read_required(sources, literal_indices=(2,))


def test_cancel_and_wrong_identity_leave_the_original_source_and_previous_result_usable(tmp_path):
    sources = _sources(tmp_path)
    previous = read_required(sources, method_indices=(1,))
    assert previous['types'][0]['name'] == 'Actor'
    assert previous['fields'] == {}
    with pytest.raises(MetadataCancelled):
        read_required(sources, method_indices=(1,), cancelled=lambda: True)
    bad = {**sources, 'startup': OriginalInput(sources['startup'].path, sources['startup'].size, '0' * 32)}
    with pytest.raises(MetadataFormatError, match='startup publisher digest'):
        read_required(bad, method_indices=(1,))
    startup = sources['startup']
    wrong_receipt = {**sources, 'startup': OriginalInput(startup.path, startup.size, startup.md5, '0' * 64)}
    with pytest.raises(MetadataFormatError, match='startup source receipt digest'):
        read_required(wrong_receipt, method_indices=(1,))
    assert read_required(sources, method_indices=(1,)) == previous
    assert previous['sha256'] == {
        role: hashlib.sha256(source.path.read_bytes()).hexdigest() for role, source in sources.items()
    }


def test_input_changed_after_authentication_cannot_publish_records(tmp_path, monkeypatch):
    sources = _sources(tmp_path)
    metadata = sources['metadata'].path
    read_type = portable._Records.type

    def change_source_after_read(records, index):
        value = read_type(records, index)
        info = metadata.stat()
        os.utime(metadata, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
        return value

    monkeypatch.setattr(portable._Records, 'type', change_source_after_read)
    with pytest.raises(MetadataFormatError, match='metadata file changed'):
        read_required(sources, type_indices=(0,))


def test_runtime_indices_and_native_pointers_follow_the_authenticated_generation(tmp_path):
    compact = bytes.fromhex('01000000 1000 1d 43 00000000 0000 12 00 00000000 1200 08 81') + bytes(24)
    old_source = _sources(tmp_path, runtime_rows=compact)
    old = read_required(old_source, runtime_type_indices=(0, 1, 2))
    assert old['runtime_type_stride'] == 8
    assert old['runtime_types'] == {
        0: {'data': 1, 'attributes': 16, 'tag': 0x1d, 'modifiers': 3,
            'by_reference': True, 'pinned': False, 'target': ('runtime_index', 1)},
        1: {'data': 0, 'attributes': 0, 'tag': 0x12, 'modifiers': 0,
            'by_reference': False, 'pinned': False, 'target': ('type_definition', 0)},
        2: {'data': 0, 'attributes': 18, 'tag': 0x08, 'modifiers': 1,
            'by_reference': False, 'pinned': True, 'target': None},
    }

    pointer = _IMAGE_BASE + _TYPE_RVA + 16
    wide = struct.pack('<QHBB4x', pointer, 0x1234, 0x0f, 0xc3) + bytes.fromhex(
        '0100000000000000 0000 11 00 00000000 0000000000000000 0000 08 00 00000000')
    current_source = _sources(tmp_path, runtime_rows=wide)
    with pytest.raises(MetadataFormatError, match='native publisher digest'):
        read_required(old_source, runtime_type_indices=(0,))
    current = read_required(current_source, runtime_type_indices=(0, 1))
    assert current['runtime_type_stride'] == 16
    assert current['runtime_types'] == {
        0: {'data': pointer, 'attributes': 0x1234, 'tag': 0x0f, 'modifiers': 3,
            'by_reference': True, 'pinned': True, 'target': ('runtime_rva', _TYPE_RVA + 16)},
        1: {'data': 1, 'attributes': 0, 'tag': 0x11, 'modifiers': 0,
            'by_reference': False, 'pinned': False, 'target': ('type_definition', 1)},
    }


def test_runtime_layout_samples_both_ends_of_a_large_inline_table(tmp_path):
    compact_int = bytes.fromhex('00000000 0000 08 00')
    # Exactly 512 evenly spaced rows have valid compact tags. The other 511
    # alternate with them, so a read of the first 512 rows cannot pass.
    alternating = (compact_int + bytes(8)) * 511 + compact_int
    selected = read_required(_sources(tmp_path, runtime_rows=alternating, runtime_count=1023),
                             runtime_type_indices=(1022,))
    assert selected['runtime_type_stride'] == 8
    assert selected['runtime_types'][1022]['tag'] == 0x08


def test_runtime_layout_rejects_two_plausible_strides(tmp_path):
    rows = bytearray(48)
    for at in (6, 14, 22, 10, 26, 42):
        rows[at] = 0x08
    sources = _sources(tmp_path, runtime_rows=bytes(rows))
    with pytest.raises(MetadataFormatError, match='runtime type layout'):
        read_required(sources, runtime_type_indices=(0,))


def test_runtime_layout_cannot_settle_a_competitor_with_unowned_file_bytes(tmp_path):
    rows = bytes.fromhex('00000000 0000 08 00 00000800 0000 08 00 00000000 0000 08 00')
    sources = _sources(tmp_path, runtime_rows=rows, overlay=bytes(32))
    with pytest.raises(MetadataFormatError, match='runtime type layout'):
        read_required(sources, runtime_type_indices=(0,))


def test_runtime_type_tag_known_to_the_scorer_can_still_be_unsupported(tmp_path):
    rows = bytes.fromhex('00000000 0000 55 00 00000000 0000 08 00 00000000 0000 01 00')
    sources = _sources(tmp_path, runtime_rows=rows)
    with pytest.raises(MetadataFormatError, match='unsupported runtime type tag'):
        read_required(sources, runtime_type_indices=(0,))
    assert read_required(sources, runtime_type_indices=(1,))['runtime_type_stride'] == 8


@pytest.mark.parametrize('target_rva', [0x1020, _TYPE_RVA + 40])
def test_runtime_wide_pointer_needs_a_complete_non_executable_record(tmp_path, target_rva):
    pointer = struct.pack('<QHBB4x', _IMAGE_BASE + target_rva, 0, 0x1d, 0)
    rows = pointer + bytes.fromhex(
        '0000000000000000 0000 08 00 00000000 0000000000000000 0000 01 00 00000000')
    sources = _sources(tmp_path, runtime_rows=rows)
    with pytest.raises(MetadataFormatError, match='PE address ownership'):
        read_required(sources, runtime_type_indices=(0,))


def test_runtime_wide_layout_requires_full_owner_even_when_the_last_tag_fits(tmp_path):
    wide_int = bytes.fromhex('0000000000000000 0000 08 00 00000000')
    rows = (wide_int * 3)[:43]
    with pytest.raises(MetadataFormatError, match='runtime type table ownership'):
        read_required(_sources(tmp_path, runtime_rows=rows), runtime_type_indices=(0,))


def _projection_sources(tmp_path, *, array_rank=3, method_container=False):
    rows = bytes.fromhex('00000000 0000 15 00 00000000 0000 08 00 00000000 0000 14 00')
    sources = _sources(tmp_path, runtime_rows=rows)
    native = bytearray(sources['native'].path.read_bytes())
    metadata = bytearray(sources['metadata'].path.read_bytes())
    startup = bytearray(sources['startup'].path.read_bytes())
    data_at = 0x600
    payload = len(_HEADER)
    image_data = _IMAGE_BASE + _DATA_RVA
    struct.pack_into('<Q', native, data_at + 0x360 + 0x38, image_data + 0x900)
    struct.pack_into('<Q', native, data_at + 0x360 + 0x70, image_data + 0x980)
    struct.pack_into('<i4xQ', native, data_at + 0x900, 2, image_data + 0x940)
    struct.pack_into('<QQ', native, data_at + 0x940, _IMAGE_BASE + _TYPE_RVA + 8, _IMAGE_BASE + _TYPE_RVA + 16)
    struct.pack_into('<QB', native, data_at + 0x980, _IMAGE_BASE + _TYPE_RVA + 8, array_rank)
    struct.pack_into('<ii', startup, 0x20c, 0, 0)
    # The two authored type definitions now own a generic container and a
    # nested member. The parameter's one constraint is the native int row.
    metadata[payload + 0x13a:payload + 0x13e] = bytes.fromhex('c0b2fcab')
    metadata[payload + 0x143] = 0xfd
    metadata[payload + 0x152:payload + 0x156] = bytes.fromhex('acd22a1c')
    container = '616531a7471130100000000028b837a9' if method_container else '616531a7481130100000000028b837a9'
    metadata[payload + 0x7d0:payload + 0x7e0] = bytes.fromhex(container)
    struct.pack_into('<i', metadata, payload + 0x7e0, 1)
    struct.pack_into('<i', metadata, payload + 0x7f0, 1)
    metadata[payload + 0x800:payload + 0x80e] = bytes.fromhex('2f80a4e538975cf1000000000000')
    for role, value in [('native', native), ('metadata', metadata), ('startup', startup)]:
        path = sources[role].path
        path.write_bytes(value)
        sources[role] = OriginalInput(path, len(value), hashlib.md5(value).hexdigest())
    return sources


def test_selected_type_projection_joins_startup_generic_arguments_and_nested_owners(tmp_path):
    projection = read_required(_projection_sources(tmp_path), type_indices=(0,), method_indices=(1,),
                               runtime_type_indices=(0, 2), project_types=True)['type_projection']
    assert projection == {
        'runtime_names': {0: 'Demo.Actor<int, int[,,]>', 2: 'int[,,]'},
        'definition_names': {0: 'Demo.Actor', 1: 'Demo.Other'},
        'type_parameters': {0: (('Other', ('int',)),)},
        'method_parameters': {},
        'nested_types': {0: (1,)},
    }


@pytest.mark.parametrize(('defect', 'component'), [
    ({'array_rank': 0}, 'runtime array rank'),
    ({'method_container': True}, 'generic container owner kind'),
])
def test_type_projection_rejects_invalid_dependent_records(tmp_path, defect, component):
    with pytest.raises(MetadataFormatError, match=component):
        read_required(_projection_sources(tmp_path, **defect), type_indices=(0,), runtime_type_indices=(0,),
                      project_types=True)


def test_type_projection_rejects_cycles_and_overdeep_reference_graphs(tmp_path):
    cycle = bytes.fromhex('01000000 0000 1d 00 00000000 0000 1d 00 00000000 0000 08 00')
    deep = b''.join(struct.pack('<IHBB', i, 0, 0x1d, 0) for i in range(1, 18)) + bytes.fromhex('00000000 0000 08 00')
    for rows, count in ((cycle, 3), (deep, 18)):
        with pytest.raises(MetadataFormatError, match='runtime type depth or cycle'):
            read_required(_sources(tmp_path, runtime_rows=rows, runtime_count=count),
                          runtime_type_indices=(0,), project_types=True)


@pytest.mark.parametrize(('root_count', 'completes'), [(32, True), (33, False)])
def test_type_projection_bounds_the_combined_requested_and_nested_definitions(root_count, completes):
    child_indices = range(root_count, root_count + 32)

    def definition(index):
        return {'name': f'Type{index}', 'namespace': 'Demo', 'image_index': 0,
                'declaring_type': 0 if index in child_indices else -1, 'generic_container': -1,
                'nested_count': 32 if index == 0 else 0, 'nested_start': 0 if index == 0 else -1}

    def read_children(role, offset, size):
        assert (role, offset, size) == ('nested_types', 0, 128)
        return struct.pack('<32i', *child_indices)

    records = SimpleNamespace(type=definition, read=read_children, type_count=1, runtime_types_rva=0x800)
    roots = {index: definition(index) for index in range(root_count)}
    stage = portable._TypeProjection(records, 8, {0: {'tag': 0x08}}, roots, None)
    if completes:
        result = stage.project((0,), roots, {})
        assert result['nested_types'] == {0: tuple(child_indices)}
        assert len(result['definition_names']) == 64
    else:
        with pytest.raises(MetadataFormatError, match='projected type definition count'):
            stage.project((0,), roots, {})


def _field_boundary_sources(tmp_path, other_owner, *, runtime_rows=bytes(48)):
    sources = _sources(tmp_path, runtime_rows=runtime_rows)
    native = bytearray(sources['native'].path.read_bytes())
    metadata = bytearray(sources['metadata'].path.read_bytes())
    # Put the opaque header slot inside Actor's field row. Literal data owns
    # the first actual global boundary after the two declared field slots.
    struct.pack_into('<I', native, 0x640 + 0x158, 532747583 + 0x20c)
    struct.pack_into('<I', native, 0x640 + 0x08, 149860775 + 0x210)
    if other_owner is not None:
        other = len(_HEADER) + 0x100 + 70
        struct.pack_into('<I', metadata, other + 0x20, 1954887780 + other_owner)
        struct.pack_into('<H', metadata, other + 0x32, (1 - 17485) & 0xffff)
    for role, raw in [('native', native), ('metadata', metadata)]:
        path = sources[role].path
        path.write_bytes(raw)
        sources[role] = OriginalInput(path, len(raw), hashlib.md5(raw).hexdigest())
    return sources


def test_complete_declarations_recover_a_field_crossing_the_opaque_header_slot(tmp_path):
    sources = _field_boundary_sources(tmp_path, 0)
    assert read_required(sources, type_indices=(0,))['fields'] == {
        1: {'owner': 0, 'type': 2, 'name': 'volume', 'offset': 24},
    }


@pytest.mark.parametrize(('other_owner', 'failure'), [(None, 'gap'), (1, 'overlap'), (2, 'range')])
def test_field_extension_requires_exact_nonoverlapping_declared_ownership(tmp_path, other_owner, failure):
    sources = _field_boundary_sources(tmp_path, other_owner)
    with pytest.raises(MetadataFormatError, match=f'field declaration {failure}'):
        read_required(sources, type_indices=(0,))


def _default_sources(tmp_path, *, declared=0x08, storage=0x08, payload=b'\xf9\xff\xff\xff',
                     rows=((0, 0, 1),), boundary_type=-1, literal=True, enum_backing=None):
    type_definition = 1 if enum_backing is not None else 0
    native_types = struct.pack('<IHBBIHBBIHBB', type_definition if storage in {0x11, 0x12} else 0, 0, storage, 0,
                               0, 0x0606, enum_backing or 0x08, 0,
                               type_definition, 0x0046 if literal else 0x0006, declared, 0)
    sources = _field_boundary_sources(tmp_path, 0, runtime_rows=native_types)
    native = bytearray(sources['native'].path.read_bytes())
    metadata = bytearray(sources['metadata'].path.read_bytes())
    defaults = b''.join(struct.pack('<iii', *row) for row in rows)
    # A separate owned data window, then the complete record role and its
    # 12-byte index-table witness. The second index row maps Actor's field.
    metadata.extend(payload.ljust(32, b'\0') + defaults + struct.pack('<iiiIII', boundary_type, 0, 0, 0, 0, 2))
    struct.pack_into('<I', native, 0x640 + 0x3c, 1752438875 + 0x900)
    struct.pack_into('<I', native, 0x640 + 0x1fc, 0x6238cdb0 ^ 0x920)
    struct.pack_into('<I', native, 0x640 + 0x9c, 1132541481 + 0x920 + len(defaults))
    if enum_backing is not None:
        at = len(_HEADER)
        metadata[at + 0x100 + 70 + 0x38] = 3  # Other is an enum/value type.
        metadata[at + 0x200:at + 0x208] = bytes.fromhex('52191a8648e0c9a2')
        metadata[at + 0x410:at + 0x418] = bytes.fromhex('b20c5eef719ec0bb')  # Authored value__ name.
    for role, value in [('native', native), ('metadata', metadata)]:
        path = sources[role].path
        path.write_bytes(value)
        sources[role] = OriginalInput(path, len(value), hashlib.md5(value).hexdigest())
    return sources


def _selected_default(sources):
    result = read_required(sources, type_indices=(0,), field_default_indices=(1,))
    assert result['field_defaults']['schema'] == 'proxy-starrail-selected-field-defaults-v1'
    return result['field_defaults']['records'][1]


@pytest.mark.parametrize(('tag', 'payload', 'kind', 'value'), [
    (0x08, b'\xf9\xff\xff\xff', 'int', -7),
    (0x09, b'\xff\xff\xff\xff', 'uint', 4294967295),
    (0x02, b'\x80', 'bool', True),
    (0x03, b'\xa9\x03', 'char', 'Ω'),
    (0x0c, b'\x00\x00\xa0\x3f', 'float', 1.25),
    (0x0d, b'\x00\x00\x00\x00\x00\x00\xf4\xbf', 'double', -1.25),
])
def test_selected_scalar_defaults_preserve_native_width_and_kind(tmp_path, tag, payload, kind, value):
    selected = _selected_default(_default_sources(tmp_path, declared=tag, storage=tag, payload=payload))
    assert selected == {'status': 'present', 'kind': kind, 'value': value}
    assert type(selected['value']) is type(value)


@pytest.mark.parametrize(('storage', 'backing', 'payload', 'kind', 'value'), [
    (0x11, 0x08, b'\xf9\xff\xff\xff', 'int', -7),
    (0x07, 0x07, b'\xff\xff', 'ushort', 65535),
])
def test_enum_defaults_require_the_original_backing_field(tmp_path, storage, backing, payload, kind, value):
    sources = _default_sources(tmp_path, declared=0x11, storage=storage, payload=payload, enum_backing=backing)
    assert _selected_default(sources) == {
        'status': 'present', 'kind': kind, 'value': value, 'enum_definition': 1,
    }


@pytest.mark.parametrize(('declared', 'storage', 'backing'), [
    (0x0e, 0x0e, None), (0x55, 0x55, None), (0x11, 0x11, None), (0x11, 0x11, 0x07),
])
def test_unsupported_default_kinds_stay_explicit_and_skip_payload_reads(tmp_path, monkeypatch, declared, storage, backing):
    sources = _default_sources(tmp_path, declared=declared, storage=storage, enum_backing=backing)
    original = portable._Records.read

    def read(records, role, at, size):
        assert role != 'default_data'
        return original(records, role, at, size)

    monkeypatch.setattr(portable._Records, 'read', read)
    assert _selected_default(sources) == {'status': 'unsupported', 'declared_tag': declared, 'storage_tag': storage}


@pytest.mark.parametrize(('rows', 'literal', 'reason'), [
    (((0, 0, 0),), True, 'no_row'), ((), True, 'no_row'), (((0, 0, 1),), False, 'nonliteral'),
])
def test_missing_row_and_nonliteral_have_distinct_absence_reasons(tmp_path, rows, literal, reason):
    assert _selected_default(_default_sources(tmp_path, rows=rows, literal=literal)) == {
        'status': 'absent', 'reason': reason,
    }


@pytest.mark.parametrize(('options', 'reason'), [
    ({'boundary_type': 0}, 'default record table terminator'),
    ({'rows': ((0, 0, 2),)}, 'default record field order or ownership'),
    ({'rows': ((3, 0, 1),)}, 'default record type index'),
    ({'rows': ((0, 32, 1),)}, 'default record data offset'),
    ({'storage': 0x09}, 'default record storage type'),
    ({'rows': ((0, 31, 1),)}, 'default_data record ownership'),
])
def test_invalid_default_owner_end_type_or_data_fails_closed(tmp_path, options, reason):
    with pytest.raises(MetadataFormatError, match=reason):
        _selected_default(_default_sources(tmp_path, **options))


def test_default_request_must_select_the_field_owner(tmp_path):
    sources = _default_sources(tmp_path)
    with pytest.raises(MetadataFormatError, match='default field ownership'):
        read_required(sources, type_indices=(0,), field_default_indices=(0,))


def test_late_invalid_record_cannot_read_payload_or_publish_stale_defaults(tmp_path, monkeypatch):
    previous = _selected_default(_default_sources(tmp_path))
    broken = _default_sources(tmp_path, rows=((0, 0, 1), (0, 4, 1)))
    original = portable._Records.read

    def read(records, role, at, size):
        assert role != 'default_data'
        return original(records, role, at, size)

    with monkeypatch.context() as scoped:
        scoped.setattr(portable._Records, 'read', read)
        with pytest.raises(MetadataFormatError, match='default record field order or ownership'):
            _selected_default(broken)
    assert previous['value'] == -7
    current = _selected_default(_default_sources(tmp_path, payload=b'\x09\0\0\0'))
    assert current == {'status': 'present', 'kind': 'int', 'value': 9}


def _census_sources(tmp_path, *, shuffled=False, defect=None):
    sources = _field_boundary_sources(tmp_path, 0)
    data = bytearray(sources['metadata'].path.read_bytes())
    native = bytearray(sources['native'].path.read_bytes())
    prefix = len(_HEADER)
    first_type = prefix + 0x100
    if shuffled:
        original = bytes(data[first_type:first_type + 140])
        data[first_type:first_type + 140] = original[70:] + original[:70]
    ranges = [(1, 3), (0, 1)] if shuffled else [(2, 2), (0, 2)]
    if defect == 'method_gap':
        ranges[1] = (0, 1)
    elif defect == 'method_overlap':
        ranges[1] = (0, 3)
    elif defect == 'field_gap':
        struct.pack_into('<H', data, first_type + 70 + 0x32, (-17485) & 0xffff)
    elif defect == 'field_overlap':
        struct.pack_into('<I', data, first_type + 0x20, 1954887780)
        struct.pack_into('<H', data, first_type + 0x32, (2 - 17485) & 0xffff)
    for owner, (start, count) in enumerate(ranges):
        at = first_type + 70 * owner
        struct.pack_into('<I', data, at + 0x08, 0x1a7af5fe ^ start)
        struct.pack_into('<H', data, at + 0x34, (count - 24467) & 0xffff)
    owners = (1, 0, 0, 0) if shuffled else (1, 1, 0, 0)
    # The four original MethodDef payloads carry distinct encoded owner words.
    row_bases = (0xe6c4db28, 0xddc1e66d, 0x9b18ed32, 0x7beb2d97)
    for index, (owner, previous) in enumerate(zip(owners, row_bases, strict=True)):
        struct.pack_into('<I', data, prefix + 0x240 + 26 * index + 0x10, previous ^ owner)
    if defect == 'foreign':
        struct.pack_into('<I', data, prefix + 0x250, row_bases[0])
    pointers = (0x10a0, 0x1030, 0, 0x10a0) if shuffled else (0x1070, 0, 0x1020, 0x1070)
    if defect == 'noncode':
        pointers = (_DATA_RVA + 0x5c0, *pointers[1:])
    struct.pack_into('<4Q', native, 0x600 + 0x560, *(rva + _IMAGE_BASE if rva else 0 for rva in pointers))
    method_end = 0x2a8
    if defect == 'nonaligned_end':
        method_end += 1
    elif defect == 'unclassified_end':
        struct.pack_into('<I', native, 0x640 + 0x158, 532747583 + method_end)
        method_end += 26
    struct.pack_into('<I', native, 0x640 + 0x30, 587858498 + method_end)
    outputs = [('native', native), ('metadata', data)]
    if defect == 'image_tail':
        startup = bytearray(sources['startup'].path.read_bytes())
        startup[0x24] ^= 3  # The authored image covers one of the two TypeDefs.
        outputs.append(('startup', startup))
    for role, raw in outputs:
        path = sources[role].path
        path.write_bytes(raw)
        sources[role] = OriginalInput(path, len(raw), hashlib.md5(raw).hexdigest())
    return sources


@pytest.mark.parametrize('shuffled', [False, True])
def test_census_uses_original_declarations_and_preserves_nulls_and_aliases(tmp_path, shuffled):
    sources = _census_sources(tmp_path, shuffled=shuffled)
    result = census.read_census(sources)
    assert result.definition_count == 2 and result.method_count == 4
    assert result.method_endpoint_role == 'parameters'
    assert result.images == ((0, 'Example.dll'),)
    with portable.open_records(sources) as (records, identity):
        source = records.metadata.stream
        names = [records.name(result.declaration(index).name_index) for index in range(2)]
        assert result.source_sha256 == identity
    assert source.closed
    assert names == (['Other', 'Actor'] if shuffled else ['Actor', 'Other'])
    assert [result.field_owner(i) for i in range(2)] == ([0, 1] if shuffled else [1, 0])
    assert [result.method_owner(i) for i in range(4)] == ([1, 0, 0, 0] if shuffled else [1, 1, 0, 0])
    earlier, latter = (0x1030, 0x10a0) if shuffled else (0x1020, 0x1070)
    assert result.method_rva(2 if shuffled else 1) is None
    assert tuple(result.methods_at(latter)) == (0, 3)
    assert result.next_method_boundary(earlier) == latter
    with pytest.raises(census.CensusUnresolved, match='managed method boundary'):
        result.next_method_boundary(latter)


@pytest.mark.parametrize(('defect', 'reason'), [
    ('method_gap', 'method gap'), ('method_overlap', 'method overlap'),
    ('field_gap', 'field gap'), ('field_overlap', 'field overlap'),
    ('foreign', 'foreign method declaration'), ('noncode', 'PE address ownership'),
])
def test_census_rejects_incomplete_or_foreign_owned_records(tmp_path, defect, reason):
    with pytest.raises(MetadataFormatError, match=reason):
        census.read_census(_census_sources(tmp_path, defect=defect))


@pytest.mark.parametrize('defect', ['nonaligned_end', 'unclassified_end'])
def test_census_reports_an_unproved_method_endpoint(tmp_path, defect):
    with pytest.raises(census.CensusUnresolved, match='method table endpoint'):
        census.read_census(_census_sources(tmp_path, defect=defect))


def test_census_does_not_invent_an_owner_for_trailing_declarations(tmp_path):
    with pytest.raises(census.CensusUnresolved, match='type image ownership'):
        census.read_census(_census_sources(tmp_path, defect='image_tail'))


@pytest.mark.parametrize(('limit', 'resource', 'count'), [
    ('_MAX_DECLARATIONS', 'type definitions', 2), ('_MAX_METHODS', 'method definitions', 4),
])
def test_census_keeps_resource_limits_distinct_from_metadata_ownership(tmp_path, monkeypatch, limit, resource, count):
    monkeypatch.setattr(census, limit, 1)
    with pytest.raises(census.CensusLimitError) as error:
        census.read_census(_census_sources(tmp_path))
    assert (error.value.resource, error.value.count, error.value.limit) == (resource, count, 1)


@pytest.mark.parametrize('change_source', [False, True])
def test_census_rejects_cancellation_or_a_changed_source_before_publication(tmp_path, monkeypatch, change_source):
    sources = _census_sources(tmp_path)
    previous = census.read_census(sources)
    original = portable._Source.read
    cancelled = False

    def read(item, at, size, *, component=None):
        nonlocal cancelled
        data = original(item, at, size, component=component)
        if component == 'census method pointers':
            if change_source:
                path = sources['metadata'].path
                info = path.stat()
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
            else:
                cancelled = True
        return data

    monkeypatch.setattr(portable._Source, 'read', read)
    expected = MetadataFormatError if change_source else MetadataCancelled
    with pytest.raises(expected):
        census.read_census(sources, cancelled=lambda: cancelled)
    assert tuple(previous.methods_at(0x1070)) == (0, 3)


def _image_method_sources(tmp_path, *, shuffled=False, defect=None):
    sources = _census_sources(tmp_path, shuffled=shuffled, defect=defect)
    data = bytearray(sources['metadata'].path.read_bytes())
    prefix = len(_HEADER)
    method_bases = (
        '293beaca7bf903ccde7bd9313779e54728dbc4e6420800006900',
        '6c06eff13ec406f7a158dc5c7244a07a6de6c1dd7d2b00002c00',
        '330d36b761cfdfb1f85185162d4fff7132ed189b283200007300',
        '96cdc557c40f2c519b91f2b6888f5ab1972deb7b83f20000d600',
    )
    for index, encoded in enumerate(method_bases):
        at = prefix + 0x240 + 26 * index
        owner_byte = data[at + 0x10]
        data[at:at + 26] = bytes.fromhex(encoded)
        data[at + 0x10] = owner_byte
    parameter = prefix + (0x2c1 if defect == 'nonaligned_end' else 0x2c0)
    data[parameter:parameter + 8] = bytes.fromhex('f31264764a160ec2')
    if defect == 'encoded_owner':
        data[prefix + 0x240 + 26 * 2 + 0x10] ^= 1
    elif defect in {'nested', 'duplicate_nested', 'missing_nested'}:
        struct.pack_into('<H', data, prefix + 0x13a, 0xb2c0)
        data[prefix + 0x143] = 0xfe if defect == 'duplicate_nested' else 0xfd
        struct.pack_into('<I', data, prefix + 0x152, 472568492)
        child = 0 if defect == 'missing_nested' else 1
        struct.pack_into('<II', data, prefix + 0x7e0, child, child)
    outputs = [('metadata', data)]
    if defect == 'method_window':
        native = bytearray(sources['native'].path.read_bytes())
        struct.pack_into('<I', native, 0x640 + 0x30, 587858498 + 0x2a0)
        outputs.append(('native', native))
    for role, raw in outputs:
        path = sources[role].path
        path.write_bytes(raw)
        sources[role] = OriginalInput(path, len(raw), hashlib.md5(raw).hexdigest())
    return sources


@pytest.mark.parametrize('shuffled', [False, True])
def test_image_method_lookup_reads_original_owner_and_signature_without_native_slots(tmp_path, monkeypatch, shuffled):
    sources = _image_method_sources(tmp_path, shuffled=shuffled)
    sha256 = {role: hashlib.sha256(source.path.read_bytes()).hexdigest() for role, source in sources.items()}
    original = portable._Source.read
    slot_start = 0x600 + 0x560

    def read(item, at, size, *, component=None):
        if item.role == 'native' and hasattr(item, 'sha256'):
            assert at + size <= slot_start or at >= slot_start + 32
        return original(item, at, size, component=component)

    monkeypatch.setattr(portable._Source, 'read', read)
    owner, indices = (1, (0,)) if shuffled else (0, (2, 3))
    result = census.read_image_methods(sources, census.ImageTypeScope(0, (owner,)))
    expected = {'owner': owner, 'name': 'Read', 'return_type': 1, 'flags': 0x16, 'generic_container': -1,
                'parameters': ((2, 'argument_with_an_original_name_longer_than_the_short_encoding_bound'),)}
    assert result == {
        'schema': 'proxy-starrail-image-method-declarations-v1',
        'sha256': sha256,
        'image': {'index': 0, 'name': 'Example.dll'},
        'scope': ({'definition': owner, 'name': 'Actor', 'namespace': 'Demo'},),
        'methods': dict.fromkeys(indices, expected),
    }


def test_image_method_lookup_requires_explicit_authored_nesting(tmp_path):
    sources = _image_method_sources(tmp_path, defect='nested')
    result = census.read_image_methods(sources, census.ImageTypeScope(0, (0, 1)), method_indices=(1,))
    assert result['scope'] == ({'definition': 0, 'name': 'Actor', 'namespace': 'Demo'},
                               {'definition': 1, 'name': 'Other', 'namespace': 'Demo'})
    assert tuple(result['methods']) == (1,)
    assert result['methods'][1]['owner'] == 1
    empty = census.read_image_methods(sources, census.ImageTypeScope(0, (0, 1)), method_indices=())
    assert empty['methods'] == {}
    with pytest.raises(MetadataFormatError, match='method scope image root'):
        census.read_image_methods(sources, census.ImageTypeScope(0, (1,)))


@pytest.mark.parametrize(('defect', 'image', 'path', 'selection', 'reason'), [
    (None, 1, (0,), None, 'method scope image root'),
    (None, 0, (0,), (0,), 'method declaration ownership'),
    (None, 0, (0,), (2, 2), 'requested method declarations'),
    (None, 0, (0, 0), None, 'method declaration scope'),
    ('encoded_owner', 0, (0,), (2,), 'method declaration encoded owner'),
    ('method_window', 0, (0,), (2,), 'method declaration window'),
    ('duplicate_nested', 0, (0, 1), (1,), 'method scope nested ownership'),
    ('missing_nested', 0, (0, 1), (1,), 'method scope nested ownership'),
])
def test_image_method_lookup_rejects_foreign_or_unowned_declarations(tmp_path, defect, image, path, selection, reason):
    sources = _image_method_sources(tmp_path, defect=defect)
    with pytest.raises(MetadataFormatError, match=reason):
        census.read_image_methods(sources, census.ImageTypeScope(image, path), method_indices=selection)


@pytest.mark.parametrize(('defect', 'reason'), [
    ('image_tail', 'type image ownership'), ('nonaligned_end', 'method table endpoint'),
])
def test_image_method_lookup_keeps_complete_census_requirements(tmp_path, defect, reason):
    sources = _image_method_sources(tmp_path, defect=defect)
    result = census.read_image_methods(sources, census.ImageTypeScope(0, (0,)), method_indices=(2,))
    assert result['methods'][2]['name'] == 'Read'
    with pytest.raises(census.CensusUnresolved, match=reason):
        census.read_census(sources)


def test_image_method_lookup_can_select_one_record_above_the_full_owner_budget(tmp_path, monkeypatch):
    sources = _image_method_sources(tmp_path)
    scope = census.ImageTypeScope(0, (0,))
    monkeypatch.setattr(portable, '_MAX_SELECTED', 1)
    with pytest.raises(census.CensusLimitError) as error:
        census.read_image_methods(sources, scope)
    assert (error.value.resource, error.value.count, error.value.limit) == ('selected method declarations', 2, 1)
    assert tuple(census.read_image_methods(sources, scope, method_indices=(3,))['methods']) == (3,)


@pytest.mark.parametrize('change_source', [False, True])
def test_image_method_lookup_rechecks_selection_before_publication(tmp_path, monkeypatch, change_source):
    sources = _image_method_sources(tmp_path)
    scope = census.ImageTypeScope(0, (0,))
    previous = census.read_image_methods(sources, scope, method_indices=(2,))
    original = portable._Source.read
    cancelled = False

    def read(item, at, size, *, component=None):
        nonlocal cancelled
        data = original(item, at, size, component=component)
        if component == 'methods':
            if change_source:
                path = sources['metadata'].path
                info = path.stat()
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
            else:
                cancelled = True
        return data

    monkeypatch.setattr(portable._Source, 'read', read)
    expected = MetadataFormatError if change_source else MetadataCancelled
    with pytest.raises(expected):
        census.read_image_methods(sources, scope, method_indices=(2,), cancelled=lambda: cancelled)
    assert previous['methods'][2]['name'] == 'Read'
