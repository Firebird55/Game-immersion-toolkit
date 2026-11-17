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


def resource_catalog(variants, *, types=()):
    # Reuse the independently retained single-bundle fixture's physical tables.
    tail = catalog()[22:]
    type_map = struct.pack('<I', len(types))
    for name, extension in types:
        for value in (name, extension):
            raw = value.encode()
            type_map += struct.pack('<I', len(raw)) + raw
    entry = struct.pack('<QB', 0x1234567890, len(variants))
    entry += b''.join(struct.pack('<BI', selector, packed) for selector, packed in variants)
    return type_map + struct.pack('<I', 1) + entry + tail


@pytest.mark.parametrize('packed', [7, 0x40000007, 0x80000007, 0xc0000007,
                                    0x3ffffff9, 0x7ffffff9, 0xbffffff9, 0xfffffff9])
def test_original_identifier_projection_resolves_tagged_and_signed_locations(packed):
    c = DesignCatalog(resource_catalog(((19, packed),)))
    assert c.assets[0x1234567890] == (1, 19, packed, b'')
    assert c.locate(0x1234567890).bundle == 7
    assert view(bundle()).resolve(c, 0x1234567890, 7) == b'hello'


@pytest.mark.parametrize('variants', [(), ((0, 7), (1, 7)), ((0, 7), (1, 0x40000007)),
                                    ((2, 7), (1, 7), (0, 7))])
def test_absent_or_multiple_variants_never_guess_a_platform_selection(variants):
    c = DesignCatalog(resource_catalog(variants))
    count, selector, packed, alternatives = c.assets[0x1234567890]
    assert count == len(variants)
    assert alternatives == b''.join(struct.pack('<BI', *row) for row in variants[1:])
    with pytest.raises(ValueError):
        c.locate(0x1234567890)


@pytest.mark.parametrize('variants', [((0, 0x40000008),), ((0, 0x3ffffff8),),
                                    ((0, 7), (9, 0x80000008)), ((0, 7), (1, 0))])
def test_every_variant_must_reference_an_owned_physical_bundle(variants):
    with pytest.raises(ValueError):
        DesignCatalog(resource_catalog(variants))


def test_resource_type_extensions_are_retained_without_choosing_ambiguous_types():
    c = DesignCatalog(resource_catalog(((0, 7),), types=(('Example.Data', '.Binary'),)))
    assert c.type_extensions == {'Example.Data': '.Binary'}
    for types in ((('Example.Data', '.A'), ('Example.Data', '.B')),
                  (('', '.A'),), (('Example.Data', ''),), (('Example\0Data', '.A'),)):
        with pytest.raises(ValueError):
            DesignCatalog(resource_catalog(((0, 7),), types=types))


def test_new_variant_records_retain_strict_bounds_and_whole_catalog_eof():
    raw = resource_catalog(((0, 7), (8, 0x40000007), (9, 0x3ffffff9)))
    for invalid in (raw[:-1], raw + b'\0', raw[:18], raw[:29]):
        with pytest.raises(ValueError):
            DesignCatalog(invalid)


def test_physical_short_name_collisions_survive_tag_normalization():
    raw = catalog((0x1234567890, 0x11234567890))
    # Second packed location is the same bundle, with independently tagged bits.
    raw = raw[:32] + struct.pack('<I', 0x40000007) + raw[36:]
    c = DesignCatalog(raw)
    with pytest.raises(ValueError):
        c.locate(0x1234567890)


def test_unselected_variant_cannot_hide_a_short_name_collision():
    raw = resource_catalog(((0, 7), (8, 0x40000007)))
    # A different full identity can own the same shortened name and bundle.
    second = struct.pack('<QBBI', 0x11234567890, 1, 0, 7)
    raw = raw[:4] + struct.pack('<I', 2) + raw[8:27] + second + raw[27:]
    c = DesignCatalog(raw)
    assert len(c.names[7, 0x12345678]) == 2
    with pytest.raises(ValueError):
        c.locate(0x11234567890)
