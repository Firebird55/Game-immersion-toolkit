import hashlib
import os
import struct
from types import SimpleNamespace

import pytest

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


def _field_boundary_sources(tmp_path, other_owner):
    sources = _sources(tmp_path)
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
