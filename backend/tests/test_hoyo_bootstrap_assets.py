"""Named bootstrap TextAssets require owned metadata and exact stream bounds."""
import json
import struct

import pytest

from backend.hoyo_bootstrap_assets import object_ranges, text_assets


def asset_file(documents, *, version=21, trees=True, identities=None, kind=49):
    metadata = bytearray(b'2021.3.0f1\0' + struct.pack('<iBI', 19, int(trees), 1))
    metadata += struct.pack('<iBh', kind, 0, -1) + (bytes(16) if kind == 114 else b'') + bytes(16)
    if trees:
        metadata += struct.pack('<II', 0, 0)
        if version >= 21:
            metadata += struct.pack('<I', 0)
    metadata += struct.pack('<I', len(documents))
    payload = bytearray()
    for number, (name, value) in enumerate(documents):
        body = bytearray(struct.pack('<I', len(name)) + name.encode())
        body += bytes(-len(body) % 4)
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        body += struct.pack('<I', len(raw)) + raw
        body += bytes(-len(body) % 4)
        metadata += bytes(-len(metadata) % 4)
        metadata += struct.pack('<q', identities[number] if identities else number + 1)
        metadata += struct.pack('<Q' if version == 22 else '<I', len(payload))
        metadata += struct.pack('<Ii', len(body), 0)
        payload += body
    start, header_size = 4096, 48 if version == 22 else 20
    size = start + len(payload)
    header = struct.pack('>4I', len(metadata), size if version < 22 else 0, version,
                         start if version < 22 else 0) + bytes(4)
    if version == 22:
        header += struct.pack('>IQQQ', len(metadata), size, start, 0)
    return header + metadata + bytes(start - header_size - len(metadata)) + payload


@pytest.mark.parametrize('version, trees', [(17, False), (17, True), (21, False), (21, True), (22, False), (22, True)])
def test_named_original_objects_are_read_without_fixed_offsets(version, trees):
    data = asset_file([('unrelated', b'x' * 4000), ('app_version', {'DispatchSeed': 'a' * 16})],
                      version=version, trees=trees)
    reads = []
    def read(start, length):
        reads.append((start, length))
        return data[start:start + length]
    result = text_assets(len(data), read, frozenset({'app_version'}))
    assert json.loads(result['app_version']['payload']) == {'DispatchSeed': 'a' * 16}
    assert result['app_version']['offset'] > 4096
    assert not any(start == 4096 and length > 256 for start, length in reads)


@pytest.mark.parametrize('kind', [1208, 1210])
def test_custom_object_metadata_is_available_without_reading_opaque_contents(kind):
    data = asset_file([('opaque', b'x' * 8000)], version=22, trees=False, kind=kind)
    def metadata_only(start, length):
        assert start + length <= 4096
        return data[start:start + length]
    rows = object_ranges(len(data), metadata_only)
    assert rows == [{'id': '1', 'kind': kind, 'offset': 4096, 'size': len(data) - 4096}]


@pytest.mark.parametrize('change', ['file-size', 'version', 'metadata-size', 'duplicate-id',
                                   'duplicate-name', 'missing', 'utf8', 'truncated-read'])
def test_bad_original_ownership_or_streams_cannot_supply_bootstrap(change):
    documents = [('app_version', {'Version': '1.0.0'})]
    if change in ('duplicate-id', 'duplicate-name'):
        documents.append(('app_version' if change == 'duplicate-name' else 'other', {}))
    if change == 'utf8':
        documents[0] = ('app_version', b'\xff')
    data = bytearray(asset_file(documents, identities=[1, 1] if change == 'duplicate-id' else None))
    if change == 'file-size':
        struct.pack_into('>I', data, 4, len(data) + 1)
    elif change == 'version':
        struct.pack_into('>I', data, 8, 99)
    elif change == 'metadata-size':
        struct.pack_into('>I', data, 0, 9 * 1024**2)
    wanted = frozenset({'login_setting' if change == 'missing' else 'app_version'})
    with pytest.raises((ValueError, UnicodeDecodeError)):
        text_assets(len(data), lambda start, size: bytes(data[start:start + size - int(change == 'truncated-read')]), wanted)
