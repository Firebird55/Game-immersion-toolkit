"""Owned launcher metadata; no original assets, recordings or game keys."""
import gzip
import json
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from backend import reverse1999_release as release


def resource(version='3.9.0', revision='111.0.1065'):
    urls = []
    for number, (size, expanded) in enumerate(((64, 100), (96, 200))):
        name = (f'123_gameId_60001_pid_77_res_{revision}_app_{version}_total_300'
                f'_origin_{expanded}_size_{size}_md5_{str(number + 1) * 32}_{number}.7z')
        urls.append(f'https://download.bluepoch.com/en/game/{version}/{name}')
    return {'targetVersion': version, 'fullPackage': {
        'packageUrls': urls, 'packageSize': 160, 'packageRealSize': 300}}


def encoded(value):
    return json.dumps({'code': 200, 'data': value}, separators=(',', ':')).encode()


def fixture(version='3.9.0', revision='111.0.1065'):
    calls = []

    def fetch(url, *, body=None):
        calls.append((url, body))
        if url.endswith('/assets/js/api.js'):
            return b'fetch({gameId:60001,pageVersion:"3.9"});'
        if url.endswith('/websites/version-page'):
            assert body == {'gameId': 60001, 'pageVersion': '3.9'}
            return encoded({'pageVersion': '3.9',
                            'doubleEndDownloadUrl': 'https://download.bluepoch.com/en/Reverse1999_owned.exe'})
        assert body == release._body(target=None if url.endswith('/version') else version)
        if url.endswith('/version'):
            return encoded({'latestVersion': version, 'updateMessage': 'Owned announcement'})
        if url.endswith('/resource'):
            return encoded(resource(version, revision))
        raise AssertionError('Unexpected owned route')

    return fetch, calls


def test_normal_discovery_reports_full_client_scope_not_a_fake_dialogue_size():
    fetch, calls = fixture()
    result = release.discover(fetch=fetch)
    assert result['region'] == 'global' and result['platform'] == 'Windows'
    assert result['version'] == '3.9.0' and result['resource_revision'] == '111.0.1065'
    assert result['download_bytes'] == 160 and result['expanded_bytes'] == 300
    assert result['dialogue_download_bytes'] is None
    assert not result['dialogue_preparation_implemented']
    assert result['size_scope'] == 'complete-publisher-client-not-dialogue-selection'
    assert len(calls) == len(result['responses']) == 4
    assert all(item['bytes'] > 0 and len(item['sha256']) == 64 for item in result['responses'])


def test_new_package_revision_and_version_need_no_changed_website_or_toolkit():
    old = release.discover(fetch=fixture()[0])
    hotfix = release.discover(fetch=fixture(revision='111.0.1099')[0])
    new = release.discover(fetch=fixture(version='4.0.0', revision='122.1.1')[0])
    assert len({row['fingerprint'] for row in [old, hotfix, new]}) == 3
    assert new['website_page_version'] == '3.9' and new['version'] == '4.0.0'
    assert [row['part'] for row in new['archives']] == [0, 1]


def test_reordered_package_inventory_and_announcement_do_not_rebuild_identical_data():
    fetch, _ = fixture()

    def reorder(url, **kwargs):
        raw = fetch(url, **kwargs)
        if url.endswith('/resource'):
            data = json.loads(raw)
            data['data']['fullPackage']['packageUrls'].reverse()
            raw = json.dumps(data).encode()
        if url.endswith('/version'):
            data = json.loads(raw); data['data']['updateMessage'] = 'Changed notice only'
            raw = json.dumps(data).encode()
        return raw

    baseline = release.discover(fetch=fetch)
    changed = release.discover(fetch=reorder)
    assert baseline['responses'] != changed['responses']
    assert baseline['fingerprint'] == changed['fingerprint']


@pytest.mark.parametrize('failure', ['target', 'total', 'compressed', 'expanded', 'duplicate',
                                   'host', 'region', 'revision', 'game', 'part-version'])
def test_mixed_or_incomplete_publisher_inventory_cannot_become_a_size_plan(failure):
    value = resource()
    node = value['fullPackage']; urls = node['packageUrls']
    if failure == 'target': value['targetVersion'] = '3.8.0'
    elif failure == 'total': node['packageRealSize'] += 1
    elif failure == 'compressed': node['packageSize'] += 1
    elif failure == 'expanded': node['packageRealSize'] = True
    elif failure == 'duplicate': urls[1] = urls[0]
    elif failure == 'host': urls[0] = urls[0].replace('download.bluepoch.com', 'untrusted.invalid')
    elif failure == 'region': urls[0] = urls[0].replace('/en/game/', '/cn/game/')
    elif failure == 'revision': urls[0] = urls[0].replace('111.0.1065', '112.0.1')
    elif failure == 'game': urls[0] = urls[0].replace('gameId_60001', 'gameId_50001')
    elif failure == 'part-version': urls[0] = urls[0].replace('_app_3.9.0_', '_app_3.8.0_')
    with pytest.raises(ValueError):
        release.package(value, '3.9.0')


def test_bounded_gzip_and_pair_envelopes_support_owned_rotated_format_masks():
    raw = encoded({'latestVersion': '3.9.0'})
    for source in [raw, gzip.compress(raw)]:
        assert release.decode_metadata(source)['data']['latestVersion'] == '3.9.0'
        for mask in [17, 53, 129]:
            transformed = bytearray(source)
            for index in range(0, len(transformed) - 1, 2):
                transformed[index], transformed[index + 1] = (transformed[index + 1] ^ mask,
                                                             transformed[index] ^ mask)
            assert release.decode_metadata(bytes(transformed)) == json.loads(raw)


def test_duplicate_fields_bombs_and_wrong_shapes_are_rejected():
    for raw in [b'{"code":200,"code":500,"data":{}}', b'[]', b'', b'not-json',
                gzip.compress(b' ' * (release.METADATA_LIMIT + 1))]:
        with pytest.raises((ValueError, OSError)):
            release.decode_metadata(raw)


def test_network_fallback_stays_within_the_official_profile_and_never_uses_asset_urls():
    fetch, calls = fixture()

    def outage(url, **kwargs):
        if url.startswith('https://' + release.GLOBAL_UPDATE_HOSTS[0]):
            raise URLError('Owned outage')
        return fetch(url, **kwargs)

    result = release.discover(fetch=outage)
    assert result['version'] == '3.9.0'
    assert any(url.startswith('https://' + release.GLOBAL_UPDATE_HOSTS[1]) for url, _ in calls)
    assert not any(url.endswith('.7z') or url.endswith('.exe') for url, _ in calls)


def test_conflicting_website_bootstrap_is_not_silently_chosen():
    fetch, _ = fixture()
    def changed(url, **kwargs):
        if url.endswith('/api.js'):
            return b'gameId:60001,pageVersion:"3.9",pageVersion:"4.0"'
        return fetch(url, **kwargs)
    with pytest.raises(ValueError, match='ambiguous'):
        release.discover(fetch=changed)


@pytest.mark.parametrize('fault', ['status', 'redirect', 'partial', 'oversize'])
def test_transport_does_not_treat_partial_or_redirected_metadata_as_current(fault):
    url = release.GLOBAL_SITE + '/assets/js/api.js'
    raw = b'owned response'
    response = SimpleNamespace(status=200, headers={'Content-Length': str(len(raw))},
                               geturl=lambda: url, read=lambda limit: raw)
    if fault == 'status': response.status = 206
    elif fault == 'redirect': response.geturl = lambda: 'https://untrusted.invalid/metadata'
    elif fault == 'partial': response.headers['Content-Length'] = str(len(raw) + 1)
    elif fault == 'oversize': response.read = lambda limit: b'x' * (release.METADATA_LIMIT + 1)
    class Context:
        def __enter__(self): return response
        def __exit__(self, *_): return False
    with pytest.raises(ValueError):
        release.request(url, opener=lambda *_a, **_k: Context())
