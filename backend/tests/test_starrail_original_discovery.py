"""Original dispatch contracts absent from the route-feed and caption tests."""
import base64
from dataclasses import dataclass
import hashlib
import io
import json
import struct
from urllib.parse import parse_qs, urlsplit

import pytest

from backend import starrail_original_discovery as discovery


def uint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes((value,)))


def text(number, value):
    raw = value.encode() if isinstance(value, str) else value
    return uint(number << 3 | 2) + uint(len(raw)) + raw


def binary_string(value):
    raw = value.encode()
    return struct.pack('>h', len(raw)) + raw


def marker(revision, data):
    raw = bytearray(66)
    raw[:12] = b'SRMI\0\3\0\1' + struct.pack('<I', 66)
    digest = hashlib.md5(data).hexdigest()
    struct.pack_into('<5IQ', raw, 24, revision,
                     *(int(digest[i:i + 8], 16) for i in range(0, 32, 8)), len(data))
    return bytes(raw)


def fixture(tmp_path, monkeypatch):
    kinds = [('ChannelName', 'string'), ('BundleIdentifier', 'string'), ('ProductName', 'string'),
             ('ScriptDefines', 'string'), ('GlobalDispatchUrlList', 'string_array'),
             ('OriginTestGlobalDispatchUrlList', 'string_array'), ('OriginCbGlobalDispatchUrlList', 'string_array'),
             ('OriginLiveGlobalDispatchUrlList', 'string_array'), ('DefaultServerIndex', 'u32')]
    config = b''.join(binary_string(value) for value in ('Overseas', 'owned.fixture', 'Owned', ''))
    config += struct.pack('>I', 1) + binary_string('https://globaldp-prod-os01.starrails.com/query_dispatch')
    config += struct.pack('>4I', 0, 0, 0, 0)
    version = binary_string('V7.8Live') + struct.pack('>3I', 7, 8, 9)
    version += binary_string('PROD') + binary_string('owned-test-seed') + b'\x01'
    native = 'a' * 32
    description = {'native_file_md5': native,
        'bootstrap_files': {'config': 'StarRail_Data/StreamingAssets/ClientConfig.bytes',
            'version': 'StarRail_Data/StreamingAssets/BinaryVersion.bytes', 'native': 'GameAssembly.dll'},
        'client_schema': [{'semantic': name, 'kind': kind} for name, kind in kinds],
        'version_schema': [{'semantic': name, 'kind': kind} for name, kind in (
            ('Branch', 'string'), ('MajorVersion', 'u32'), ('MinorVersion', 'u32'), ('PatchVersion', 'u32'),
            ('PakType', 'string'), ('DispatchSeed', 'string'), (None, 'bool'))],
        'global_dispatch': {'region_list_field': 31, 'region_fields': {
            'name': 9, 'primary_gateway': 11, 'alternate_gateway': 13}},
        'routes': [{'route': route, 'field': field, 'wire_type': 2}
                   for route, field in zip(('design', 'asb', 'base', 'lua'), (51, 67, 90, 82))]}
    @dataclass
    class Asset:
        data: bytes
        digest: str = ''
        def __post_init__(self):
            self.size = len(self.data)
            self.digest = self.digest or hashlib.md5(self.data).hexdigest()
        def read(self, directory, start, length):
            assert self.data != b'native-is-never-read'
            return self.data[start:start + length]
    files = {'StarRail_Data/StreamingAssets/ClientConfig.bytes': Asset(config),
             'StarRail_Data/StreamingAssets/BinaryVersion.bytes': Asset(version),
             'GameAssembly.dll': Asset(b'native-is-never-read', native)}
    monkeypatch.setattr(discovery.sophon, 'manifest', lambda directory, channel, spec, suffixes: files)
    state = {'revision': 101, 'retired': False, 'requests': [], 'gateway_mutation': lambda data: data}
    def request(url):
        state['requests'].append(url)
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        assert not {'uid', 'token', 'account_id', 'device_id'} & query.keys()
        assert query['version'] == ['OSPRODWin7.8.9']
        if parsed.path == '/query_dispatch':
            assert 'dispatch_seed' not in query
            if state['retired']:
                return [(1, 0, 4), (2, 2, b'Update required')]
            region = text(9, 'owned-region')
            region += text(11, 'https://owned-dp01.starrails.com/query_gateway')
            region += text(13, 'https://owned-dp02.starrails.com/query_gateway')
            return discovery.protobuf_fields(text(31, region))
        assert parsed.path == '/query_gateway' and query['dispatch_seed'] == ['owned-test-seed']
        result = b''
        for row in description['routes']:
            folder = 'lua' if row['route'] == 'lua' else 'design_data' if row['route'] == 'design' else 'asb'
            result += text(row['field'], f'https://autopatchos.starrails.com/{folder}/V7.8Live/output_{state["revision"]}_abcd_ef01')
        return discovery.protobuf_fields(state['gateway_mutation'](result))
    monkeypatch.setattr(discovery, '_protobuf_get', request)
    def download(url, *, limit):
        assert limit == 66
        revision = int(url.split('/output_')[1].split('_')[0])
        return marker(revision, url.rsplit('/', 1)[1].encode())
    monkeypatch.setattr(discovery.hotfix, 'download', download)
    build = {'channel': 'starrail-global', 'version': '7.8.9', 'build': 'owned', 'manifests': {'game': []}}
    return build, description, state, files


def test_native_descriptions_follow_changed_tags_routes_and_keep_request_seed_private(tmp_path, monkeypatch):
    build, description, state, _ = fixture(tmp_path, monkeypatch)
    first = discovery.prepare(tmp_path, build, description)
    assert first['hotfix']['indexes']['design'][0] == 101
    state['revision'] = 202
    for row in description['routes']:
        row['field'] += 1000
    second = discovery.prepare(tmp_path, build, description)
    assert second['hotfix']['indexes']['design'][0] == 202
    receipt = (tmp_path / 'starrail-original-discovery/current.json').read_bytes()
    assert b'owned-test-seed' not in receipt and b'dispatch_seed' not in receipt
    assert json.loads(receipt)['native_file_md5'] == description['native_file_md5']
    assert len(state['requests']) == 4


def test_retirement_and_partial_marker_failure_retain_complete_descriptor(tmp_path, monkeypatch):
    build, description, state, _ = fixture(tmp_path, monkeypatch)
    discovery.prepare(tmp_path, build, description)
    path = tmp_path / 'starrail-original-discovery/current.json'
    prior = path.read_bytes()
    state['retired'] = True
    with pytest.raises(discovery.SourceUnavailable, match='no regions'):
        discovery.prepare(tmp_path, build, description)
    assert path.read_bytes() == prior
    state['retired'] = False
    normal = discovery.hotfix.download
    monkeypatch.setattr(discovery.hotfix, 'download',
                        lambda url, **kwargs: b'incomplete' if 'M_LuaV' in url else normal(url, **kwargs))
    with pytest.raises(ValueError):
        discovery.prepare(tmp_path, build, description)
    assert path.read_bytes() == prior


def test_native_identity_mismatch_cannot_use_previous_description(tmp_path, monkeypatch):
    build, description, state, files = fixture(tmp_path, monkeypatch)
    files['GameAssembly.dll'].digest = 'b' * 32
    with pytest.raises(discovery.SourceUnavailable, match='Derive a description'):
        discovery.prepare(tmp_path, build, description)
    assert state['requests'] == [] and not (tmp_path / 'starrail-original-discovery/current.json').exists()


def test_native_supplied_resource_renames_need_no_reader_update(tmp_path, monkeypatch):
    build, description, _, files = fixture(tmp_path, monkeypatch)
    for role, previous in list(description['bootstrap_files'].items()):
        renamed = 'PublisherNewLocation/Next_' + previous.rsplit('/', 1)[-1]
        files[renamed] = files.pop(previous)
        description['bootstrap_files'][role] = renamed
    assert discovery.prepare(tmp_path, build, description)['version'] == build['version']


@pytest.mark.parametrize('change', [
    lambda value: value['client_schema'].__setitem__(0, {'kind': []}),
    lambda value: value['routes'][0].__setitem__('route', []),
    lambda value: value['routes'][0].__setitem__('field', True),
    lambda value: value['routes'][0].__setitem__('field', value['routes'][1]['field']),
    lambda value: value['bootstrap_files'].__setitem__('config', '../ClientConfig.bytes'),
])
def test_invalid_native_descriptions_are_rejected_before_network(tmp_path, monkeypatch, change):
    build, description, state, _ = fixture(tmp_path, monkeypatch)
    change(description)
    with pytest.raises(ValueError):
        discovery.prepare(tmp_path, build, description)
    assert state['requests'] == []


@pytest.mark.parametrize('url', [
    'http://owned.starrails.com/query_dispatch', 'https://owned.starrails.com.evil/query_dispatch',
    'https://owned.starrails.com:8443/query_dispatch', 'https://user@owned.starrails.com/query_dispatch',
    'https://owned.starrails.com/query_gateway', 'https://owned.starrails.com/query_dispatch?other=1',
])
def test_publisher_endpoint_boundaries_reject_other_destinations(url):
    with pytest.raises(ValueError):
        discovery._endpoint(url, 'dispatch', 'starrail-global')


@pytest.mark.parametrize('mutation', [
    lambda data: data + text(51, 'https://autopatchos.starrails.com/design_data/V7.8Live/output_1_ab_cd'),
    lambda data: data.replace(b'autopatchos.starrails.com', b'autopatchos.starrails.evil'),
    lambda data: data.replace(b'/design_data/', b'/../design_data/'),
    lambda data: data[:-1],
])
def test_ambiguous_corrupt_or_unsafe_routes_cannot_publish(tmp_path, monkeypatch, mutation):
    build, description, state, _ = fixture(tmp_path, monkeypatch)
    state['gateway_mutation'] = mutation
    with pytest.raises(ValueError):
        discovery.prepare(tmp_path, build, description)
    assert not (tmp_path / 'starrail-original-discovery/current.json').exists()


@pytest.mark.parametrize('data,schema', [
    (b'\xff\xff', [{'kind': 'string'}]),
    (b'\x00\x03ab', [{'kind': 'string'}]),
    (b'\x02', [{'kind': 'bool'}]),
    (struct.pack('>I', 2**32 - 1), [{'kind': 'string_array'}]),
    (b'\x01extra', [{'kind': 'bool'}]),
    (b'\x00\x01', [{'kind': 'bool', 'semantic': 'Same'}, {'kind': 'bool', 'semantic': 'Same'}]),
])
def test_bootstrap_bounds_and_supplied_description_must_be_unambiguous(data, schema):
    with pytest.raises(ValueError):
        discovery.decode_bootstrap(data, schema)


@pytest.mark.parametrize('data', [b'\x00', b'\x08\x80', b'\x0a\x03ab', b'\x09short', b'\x0b', b'\x88\x00\x01'])
def test_malformed_protobuf_cannot_supply_route_metadata(data):
    with pytest.raises(ValueError):
        discovery.protobuf_fields(data)


def test_response_redirect_and_invalid_base64_are_rejected(monkeypatch):
    class Response(io.BytesIO):
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
        def geturl(self): return self.url
    current = {'url': 'https://original.starrails.com/query_dispatch', 'raw': base64.b64encode(text(1, 'owned'))}
    def open_url(request, timeout):
        result = Response(current['raw'])
        result.url = current['url']
        return result
    monkeypatch.setattr(discovery, 'urlopen', open_url)
    assert discovery._protobuf_get(current['url']) == [(1, 2, b'owned')]
    current['url'] = 'https://other.starrails.com/query_dispatch'
    with pytest.raises(ValueError):
        discovery._protobuf_get('https://original.starrails.com/query_dispatch')
    current.update(url='https://original.starrails.com/query_dispatch', raw=b'not base64!')
    with pytest.raises(ValueError):
        discovery._protobuf_get(current['url'])
