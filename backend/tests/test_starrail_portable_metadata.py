import hashlib
import os
import struct

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
    'c29e7d27000000004f1dc11f000000000000000014515c7f000000000000000000000000000000000000000000000000'
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


def _registration(native, at):
    rva = 0x1000 + at - 0x400
    for i, target in enumerate((0x260, 0x360, 0x460, 0x480)):
        lea = b'\x48\x8d\x05' + struct.pack('<i', _DATA_RVA + target - (rva + i * 14 + 7))
        native[at + i * 14:at + i * 14 + 14] = lea + b'\x48\x89\x05\0\0\0\0'


def _sources(tmp_path, *, seam=False, ambiguous=None, invalid_pointer=False, excess_parameters=False):
    code_length = 0x40000 if seam else 0x200
    if seam:
        code_length += 0x200
    data_at = 0x400 + code_length
    native = bytearray(data_at + 0x1000)
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
    struct.pack_into('<III', native, sections + 40 + 12, _DATA_RVA, 0x1000, data_at)
    _registration(native, 0x40000 - 19 if seam else 0x470)
    native[0x410:0x414] = b'MHY\0'
    native[data_at + 0x40:data_at + 0x40 + len(_HEADER)] = _HEADER
    native[data_at + 0x700:data_at + 0x704] = b'MHY\0'  # Rejected as an invalid header.
    if ambiguous == 'registration':
        _registration(native, 0x4b0)
    elif ambiguous == 'header':
        native[data_at + 0x800:data_at + 0x800 + len(_HEADER)] = _HEADER
    struct.pack_into('<Q', native, data_at + 0x260 + 0x40, _IMAGE_BASE + _DATA_RVA + 0x560)
    struct.pack_into('<I', native, data_at + 0x360 + 0x48, 1455078207)
    struct.pack_into('<Q', native, data_at + 0x360 + 0x80, _IMAGE_BASE + _DATA_RVA + 0x520)
    struct.pack_into('<I', native, data_at + 0x460 + 0x2c, 0x0bd08dca)
    target = _DATA_RVA + 0x5c0 if invalid_pointer else 0x1020
    struct.pack_into('<Q', native, data_at + 0x568, _IMAGE_BASE + target)
    payload = bytearray(0x900)
    for at, row in _GLOBAL_ROWS:
        data = bytes.fromhex(row)
        payload[at:at + len(data)] = data
    if excess_parameters:
        payload[0x25a + 0x18] ^= 0x40
    startup = b'\0' * 0x20 + _IMAGE + b'\0' * 0x38
    values = {'native': native, 'metadata': _HEADER + payload, 'startup': startup}
    sources = {}
    for role, value in values.items():
        path = tmp_path / role
        path.write_bytes(value)
        sources[role] = OriginalInput(path, len(value), hashlib.md5(value).hexdigest())
    return sources


def test_selected_records_join_original_owners_and_decode_cross_chunk_registration(tmp_path):
    # The header declares one trailing type byte and three trailing image bytes.
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
