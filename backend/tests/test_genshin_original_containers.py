"""Full identity ownership must precede shortened original object lookup."""
import struct

import pytest

from backend.genshin_original_containers import DataObjects, DesignCatalog, asset_identity


def string(value):
    raw = value.encode()
    return struct.pack('<I', len(raw)) + raw + bytes(-len(raw) % 4)


def catalog(identities=(0x1234567890,), *, kind=1):
    u = lambda n: struct.pack('<I', n)
    rows = b''.join(struct.pack('<QBBI', n, kind, 0, 7) + (bytes(5) if kind == 2 else b'')
                    for n in identities)
    return (u(0) + u(len(identities)) + rows + u(0) + u(0) + u(8) + u(0) + u(0)
            + u(1) + u(3) + u(1) + u(99) + bytes(2)
            + u(1) + u(99) + u(1) + u(7) + u(0) + u(0) + u(0))


def bundle(entries=None, *, payload=b'hello', declared=None, file_id=0, kind=1208):
    entries = entries or [('12345678', 1)]
    body = struct.pack('<I', len(payload)) + payload
    body += bytes(-len(body) % 4)
    name_map = string('') + struct.pack('<I', len(entries))
    for name, pid in entries:
        name_map += string(name) + struct.pack('<iqQ', file_id, pid,
                                              len(payload) if declared is None else declared)
    objects = [(1, kind, body), (2, 1210, name_map)]
    metadata = bytearray(b'2021.3.0f1\0' + struct.pack('<iBI', 19, 0, len(objects)))
    for _, class_id, _ in objects:
        metadata += struct.pack('<iBh', class_id, 0, -1) + bytes(16)
    metadata += struct.pack('<I', len(objects))
    raw = bytearray()
    for identity, _, data in objects:
        metadata += bytes(-len(metadata) % 4)
        metadata += struct.pack('<qIIi', identity, len(raw), len(data), identity - 1)
        raw += data
    header = struct.pack('>4I', len(metadata), 4096 + len(raw), 17, 4096) + bytes(4)
    return header + metadata + bytes(4096 - len(header) - len(metadata)) + raw


def view(raw):
    return DataObjects(len(raw), lambda offset, size: raw[offset:offset + size])


def test_catalog_membership_and_named_data_use_owned_original_ranges():
    c = DesignCatalog(catalog())
    assert c.locate(0x1234567890).package == 'blocks/03/99.blk'
    assert view(bundle(payload='你好'.encode())).resolve(c, 0x1234567890, 7) == '你好'.encode()
    with pytest.raises(ValueError):
        view(bundle()).resolve(c, 0x1234567890, 8)
    with pytest.raises(ValueError):
        view(bundle()).resolve(c, 0x991234567890, 7)


@pytest.mark.parametrize('change', ['duplicate-id', 'short-name-collision', 'unsupported-kind', 'truncated', 'trailing'])
def test_bad_catalog_cannot_supply_an_arbitrary_object(change):
    raw = catalog()
    if change == 'duplicate-id':
        raw = catalog((0x1234567890, 0x1234567890))
    elif change == 'short-name-collision':
        raw = catalog((0x1234567890, 0x11234567890))
    elif change == 'unsupported-kind':
        raw = catalog(kind=2)
    elif change == 'truncated':
        raw = raw[:-1]
    else:
        raw += b'\0'
    with pytest.raises(ValueError):
        DesignCatalog(raw).locate(0x1234567890)


@pytest.mark.parametrize('options', [
    {'entries': [('12345678', 1), ('12345678', 1)]},
    {'entries': [('12345678', 9)]}, {'declared': 6}, {'file_id': 1}, {'kind': 49},
])
def test_bad_name_or_payload_ownership_is_not_a_missing_recording(options):
    with pytest.raises(ValueError):
        view(bundle(**options)).named('12345678')


def test_identity_is_path_sensitive_and_refuses_host_path_traversal():
    assert asset_identity('TextMap/EN/0') != asset_identity('TextMap/JP/0')
    for path in ('../TextMap/EN/0', '/TextMap/EN/0', 'TextMap\\EN\\0', 'TextMap//EN/0'):
        with pytest.raises(ValueError):
            asset_identity(path)


@pytest.mark.parametrize('length,expected', [
    (255, 11248162261283491395), (256, 1994360176020748981),
    (257, 17223251537915079030), (512, 2125996838163321036),
    (513, 8577904185090215197), (768, 13204015650555562916),
    (1024, 284686057055098465),
])
def test_native_identity_uses_owned_doubling_buffer_boundaries(length, expected):
    path = 'A' * (length - len('.MiHoYoBinData'))
    assert asset_identity(path) == expected
