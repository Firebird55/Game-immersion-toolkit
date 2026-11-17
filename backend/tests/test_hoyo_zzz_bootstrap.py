"""An original official release renews request identity without community data."""
import base64
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import hoyo_dispatch_metadata as metadata, hoyo_zzz_bootstrap as original
from backend.tests.test_hoyo_bootstrap_assets import asset_file


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
