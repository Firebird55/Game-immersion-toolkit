"""Owned optional-voice inventories; no game assets, voice samples or keys."""
from copy import deepcopy
import json
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from backend import reverse1999_release as release


def inventory(branch=109, revision=130):
    result = {}
    for native in ('zh', 'jp', 'kr'):
        result[native] = {
            'latest_ver': f'{branch}.{revision}',
            'download_url': 'https://optionalres-res-hw.sl916.com/uploadzip/60001/4/63',
            'download_url_bak': 'https://optionalres-res-bak-hw.sl916.com/uploadzip/60001/4/63',
            'res': [
                {'name': f'60001_2_{branch}.1_{native}_1.zip', 'hash': 'a' * 32, 'length': 100, 'order': 1},
                {'name': 'merge/' + 'b' * 32 + '_1.zip', 'hash': 'c' * 32, 'length': 20, 'order': 2},
            ]}
    return result


def fixture(data=None, *, backup=False):
    calls = []
    data = inventory() if data is None else data

    def fetch(url):
        calls.append(url)
        parsed = urlsplit(url)
        assert parsed.path == '/resource/60001/check'
        query = parse_qs(parsed.query)
        assert query['os_type'] == ['2'] and query['channel_id'] == ['200'] and query['env_type'] == ['4']
        native = query['lang'][0].split(',')
        assert len(native) == len(query['version'][0].split(','))
        if backup and parsed.hostname == release.OPTIONAL_UPDATE_HOSTS[0]:
            raise URLError('Owned unavailable host')
        return json.dumps({key: value for key, value in data.items() if key in native}).encode()

    return fetch, calls


def test_current_optional_inventory_uses_original_locale_names_and_keeps_base_english_open():
    fetch, calls = fixture()
    result = release.optional_voices(109, fetch=fetch)
    assert parse_qs(urlsplit(calls[0]).query)['lang'] == ['en,zh,jp,kr']
    assert parse_qs(urlsplit(calls[0]).query)['version'] == ['109.0,109.0,109.0,109.0']
    assert result['packs']['en'] == {'state': 'original-base-pack-required', 'archives': [], 'download_bytes': None}
    assert result['packs']['ja']['download_bytes'] == 120
    assert result['packs']['ko']['version'] == '109.130'
    assert result['download_bytes'] == 360
    assert result['expanded_bytes'] is None and result['dialogue_preparation_implemented'] is False
    assert result['requested_voice_inventory_complete'] is False
    assert result['size_scope'] == 'complete-optional-voice-and-video-pack-not-dialogue-selection'
    assert [row['order'] for row in result['packs']['ja']['archives']] == [1, 2]
    assert all(row['md5'] in ('a' * 32, 'c' * 32) for row in result['packs']['ja']['archives'])


def test_normal_voice_update_and_original_branch_change_do_not_need_adapter_changes():
    first = release.optional_voices(109, fetch=fixture()[0])
    second = release.optional_voices(109, fetch=fixture(inventory(revision=131))[0])
    third = release.optional_voices(110, fetch=fixture(inventory(branch=110, revision=1))[0])
    assert len({first['fingerprint'], second['fingerprint'], third['fingerprint']}) == 3
    assert third['packs']['ja']['version'] == '110.1'


def test_only_requested_languages_are_queried_and_http_failure_uses_publisher_backup():
    fetch, calls = fixture(backup=True)
    result = release.optional_voices(109, locales=('ja',), fetch=fetch)
    assert len(calls) == 2 and set(result['packs']) == {'ja'}
    assert result['requested_voice_inventory_complete'] is True
    assert urlsplit(result['source_url']).hostname == release.OPTIONAL_UPDATE_HOSTS[1]


def test_missing_non_default_voice_and_new_branch_are_actionable_not_unvoiced():
    data = inventory(); data.pop('jp')
    with pytest.raises(ValueError, match='missing'):
        release.optional_voices(109, fetch=fixture(data)[0])
    with pytest.raises(ValueError, match='refresh original bootstrap'):
        release.optional_voices(109, fetch=fixture(inventory(branch=110))[0])


@pytest.mark.parametrize('branch,locales', [(0, ('ja',)), (True, ('ja',)), (109, ('jp',)),
                                        (109, ('ja', 'ja')), (109, ()), ('109', ('ja',))])
def test_unknown_or_ambiguous_request_does_not_trigger_http(branch, locales):
    def fetch(*_args, **_kwargs):
        raise AssertionError('Invalid request performed network access')
    with pytest.raises(ValueError):
        release.optional_voices(branch, locales=locales, fetch=fetch)


@pytest.mark.parametrize('mutate', [
    lambda info: info.update(download_url='https://untrusted.invalid/uploadzip/60001/4/63'),
    lambda info: info.update(download_url_bak='https://optionalres-res-bak-hw.sl916.com/uploadzip/50001/4/63'),
    lambda info: info.update(res=[]),
    lambda info: info['res'].append(deepcopy(info['res'][0])),
    lambda info: info['res'][0].update(name='../outside.zip'),
    lambda info: info['res'][0].update(name='merge/%2e%2e/outside.zip'),
    lambda info: info['res'][0].update(name='merge\\outside.zip'),
    lambda info: info['res'][0].update(hash='not-an-original-digest'),
    lambda info: info['res'][0].update(length=-1),
    lambda info: info['res'][0].update(order=True),
])
def test_unowned_malformed_or_unordered_original_archives_fail_without_downloading(mutate):
    data = inventory(); mutate(data['jp'])
    fetch, calls = fixture(data)
    with pytest.raises(ValueError):
        release.optional_voices(109, fetch=fetch)
    assert len(calls) == 1 and '.zip' not in calls[0]
