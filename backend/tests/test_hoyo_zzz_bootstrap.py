"""An original official release renews request identity without community data."""
import base64
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import hoyo_dispatch_metadata as metadata, hoyo_zzz_bootstrap as original
from backend.tests.test_hoyo_bootstrap_assets import asset_file
from backend.tests.test_zzz_native_key_data import initializer, image
from backend import zzz_hotfix
from Crypto.PublicKey import RSA


def build(region, version):
    return {'channel': 'zzz-' + region, 'version': version, 'build': 'owned-build',
            'manifests': {'game': ('official', 'manifest', 1, 1, 'b' * 32, 'chunks')}}


def document(region, version, seed, endpoint=1):
    prefix, domain, part = {'global': ('OSPRODWin', 'zenlesszonezero.com', 'os'),
                            'cn': ('CNPRODWin', 'juequling.com', 'cn')}[region]
    return [('app_version', {'ApplicationVersion': version, 'ChannelName': prefix,
                             'DispatchVersion': prefix + version, 'DispatchSeed': seed}),
            ('login_setting', {'$Type': 'Foundation.LoginSetting',
                               'dispatch_urls': [f'https://globaldp-prod-{part}0{endpoint}.{domain}/query_dispatch']})]


def frozen(region):
    return {'DispatcherKey': 'owned-frozen-encoded-input', 'GameGatewayURLTemplate': 'owned-frozen-shape',
            metadata._PROVENANCE: {'game': 'zzz', 'region': region, 'policy': 'frozen-initial-seed',
                                   'repository': metadata.REPOSITORY, 'revision': metadata.SEED_REVISION, 'files': {}}}


def source(monkeypatch, data):
    item = SimpleNamespace(size=len(data), digest=hashlib.md5(data).hexdigest(),
                           read=lambda directory, start, length: data[start:start + length])
    monkeypatch.setattr(original.sophon, 'manifest', lambda *args: {original.RESOURCE: item})
    monkeypatch.setattr(metadata, 'fetch', lambda *args, **kwargs: pytest.fail('Community network is blocked'))


@pytest.mark.parametrize('region', ['global', 'cn'])
def test_official_seed_endpoint_and_generation_rotation_keeps_frozen_key_separate(monkeypatch, tmp_path, region):
    initial = frozen(region)
    decoder = metadata.Decoder({'BitSize': 128})
    results = []
    for version, seed, endpoint in [('3.3.0', '0123456789abcdef', 1), ('3.4.0', 'fedcba9876543210', 2)]:
        source(monkeypatch, asset_file([('unrelated', {}), *document(region, version, seed, endpoint)]))
        result = original.renew(initial, build(region, version), region, tmp_path)
        results.append(result)
        assert decoder.text(result['ProtoDispatchKey']) == seed
        assert f'0{endpoint}.' in decoder.text(result['GameDispatchArrayURL'][0])
        assert result['DispatcherKey'] == initial['DispatcherKey']
        proof = metadata.provenance(result)
        assert proof['official']['version'] == version and proof['official']['channel'] == 'zzz-' + region
        assert 'DispatcherKey' in proof['frozen_parameters']
        assert seed not in json.dumps(proof) and 'owned-frozen-encoded-input' not in json.dumps(proof)
    assert results[0]['ProtoDispatchKey'] != results[1]['ProtoDispatchKey']
    assert initial == frozen(region)


@pytest.mark.parametrize('change', ['wrong-region', 'wrong-version', 'mixed-dispatch-version',
                                   'foreign-endpoint', 'wrong-type', 'duplicate-key', 'invalid-seed',
                                   'non-string-endpoint', 'duplicate-endpoint', 'wrong-seed-edition'])
def test_invalid_new_official_config_cannot_replace_prior_parameters(monkeypatch, tmp_path, change):
    prior = frozen('global')
    before = copy.deepcopy(prior)
    docs = document('global', '3.3.0', 'a' * 16)
    if change == 'wrong-region':
        docs = document('cn', '3.3.0', 'a' * 16)
    elif change == 'wrong-version':
        docs[0][1]['ApplicationVersion'] = '3.2.0'
    elif change == 'mixed-dispatch-version':
        docs[0][1]['DispatchVersion'] = 'OSPRODWin3.2.0'
    elif change == 'foreign-endpoint':
        docs[1][1]['dispatch_urls'] = ['https://untrusted.example/query_dispatch']
    elif change == 'wrong-type':
        docs[1][1]['$Type'] = 'Other.LoginSetting'
    elif change == 'duplicate-key':
        docs[0] = ('app_version', b'{"DispatchSeed":"aaaaaaaaaaaaaaaa","DispatchSeed":"bbbbbbbbbbbbbbbb"}')
    elif change == 'invalid-seed':
        docs[0][1]['DispatchSeed'] = 'not a seed'
    elif change == 'non-string-endpoint':
        docs[1][1]['dispatch_urls'] = [{}]
    elif change == 'duplicate-endpoint':
        docs[1][1]['dispatch_urls'] *= 2
    elif change == 'wrong-seed-edition':
        prior[metadata._PROVENANCE]['region'] = 'cn'
        before = copy.deepcopy(prior)
    source(monkeypatch, asset_file(docs))
    with pytest.raises(ValueError):
        original.renew(prior, build('global', '3.3.0'), 'global', tmp_path)
    assert prior == before


def test_zzz_cannot_request_a_changing_community_fallback(tmp_path):
    with pytest.raises(ValueError):
        metadata.load_pinned('zzz', 'global', 'a' * 40, {}, cache_dir=tmp_path)


@pytest.mark.parametrize('region', ['global', 'cn'])
def test_normal_loader_and_settings_derive_rotated_native_key_without_initial_cache(monkeypatch, tmp_path, region):
    monkeypatch.setattr(metadata, 'initial_seed', lambda *a, **k: pytest.fail('No initial/community input allowed'))
    monkeypatch.setattr(metadata, 'fetch', lambda *a, **k: pytest.fail('Community network forbidden'))
    for generation, version in enumerate(('3.3.0', '3.4.0')):
        key = RSA.generate(1024)
        seed = '0123456789abcdef' if generation == 0 else 'fedcba9876543210'
        bodies = {original.RESOURCE: asset_file(document(region, version, seed)),
                  original.NATIVE_RESOURCE: image(b'\x90' * (generation * 713) + initializer(key, 0xa3 + generation),
                                                  rva=0x400000 + generation * 0x27000)}
        files = {name: SimpleNamespace(size=len(raw), digest=hashlib.md5(raw).hexdigest(),
                 chunks=((0, len(raw), len(raw) // 2, 'owned-container', hashlib.md5(raw).hexdigest()),),
                 read=lambda directory, start, length, raw=raw: raw[start:start + length])
                 for name, raw in bodies.items()}
        monkeypatch.setattr(original.sophon, 'manifest', lambda *args: files)
        config, decoder = metadata.load('zzz', region, build=build(region, version), cache_dir=tmp_path)
        proof = metadata.provenance(config)
        assert proof['policy'] == 'official-current-client-data' and proof['frozen_parameters'] == []
        assert decoder.text(config['ProtoDispatchKey']) == seed
        assert len(config['_official_gateway_keys']) == 1
        assert config['_official_gateway_keys'][0].key.n == key.n
        values, keys = zzz_hotfix._settings(region, build(region, version), cache_dir=tmp_path)
        assert values['ProtoDispatchKey'] == seed and keys[0].key.n == key.n
        assert seed not in json.dumps(proof) and 'RSAKeyValue' not in json.dumps(proof)
        assert not list(tmp_path.rglob('config_*.json'))


def test_native_key_preflight_plans_complete_containers_without_reading_their_payload(monkeypatch, tmp_path):
    key = RSA.generate(1024)
    raw = image(initializer(key))
    reads = []
    def read(directory, start, length):
        reads.append((start, length))
        assert start + length <= 0x800
        return raw[start:start + length]
    asset = SimpleNamespace(size=len(raw), digest=hashlib.md5(raw).hexdigest(), read=read,
        chunks=((0, 0x800, 1000, 'header', 'a' * 32),
                (0x800, len(raw) - 0x800, 750, 'whole-key-container', 'c' * 32)))
    monkeypatch.setattr(original.sophon, 'manifest', lambda *args: {original.NATIVE_RESOURCE: asset})
    _, plan, proof = original.native_source_plan(build('global', '3.3.0'), tmp_path)
    assert plan['offset'] == 0x800 and proof['download_bytes_upper_bound'] == 750
    assert proof['cache_bytes_upper_bound'] == len(raw) - 0x800
    assert reads and all(start + length <= plan['offset'] for start, length in reads)


def test_normal_zzz_load_requires_an_official_release_instead_of_a_seed_fallback(tmp_path):
    with pytest.raises(ValueError):
        metadata.load('zzz', 'global', cache_dir=tmp_path)
