import base64
import hashlib
import json
from urllib.request import Request

import pytest

from backend import infinity_nikki_release as publisher


def website(url, **extra):
    data = {'props': {'pageProps': {'pageData': {'page': {'windowsUrl': [
        {'__type': 'text', 'value': url, **extra}]}}}}}
    return ('<html><script id="__NEXT_DATA__" type="application/json">' +
            json.dumps(data) + '</script></html>').encode()


GLOBAL = 'https://x6oversea-game-package.infoldgames.com/xstarter/402/InfinityNikkiGlobal%20Launcher_1.3.1.exe'
MAINLAND = 'https://x6cn-game-package.papegames.com/xstarter/402/InfinityNikki%20Launcher_1.3.1.exe'


def encoded_config(body=None):
    from Crypto.Cipher import AES
    identity = {'launcherAppId': '1234567', 'version': '8.12.4', 'time': '2026-01-02 03:04:05'}
    body = body or json.dumps({'appConfig': {'fixture': 'own synthetic data'},
                              'gameAuditConfig': {}, 'gameConfig': {}}).encode()
    seed = '12345678_12_42026/01/02-03:04:05'
    key = hashlib.md5(seed.encode()).hexdigest().encode()
    pad = 16 - len(body) % 16
    raw = AES.new(key, AES.MODE_CBC, key[:16]).encrypt(body + bytes([pad]) * pad)
    return base64.b64encode(raw), json.dumps(identity).encode()


def test_config_cipher_follows_its_own_identity_without_a_persisted_publisher_key():
    encoded, identity = encoded_config()
    assert publisher.decode_launcher_config(encoded, b'\xef\xbb\xbf' + identity)['appConfig']['fixture'] == 'own synthetic data'
    with pytest.raises(ValueError):
        publisher.decode_launcher_config(encoded, identity.replace(b'8.12.4', b'8.12.5'))


@pytest.mark.parametrize('mutate', [
    lambda encoded, identity: (encoded[:-4], identity),
    lambda encoded, identity: (b'!' + encoded[1:], identity),
    lambda encoded, identity: (encoded + b' ' * publisher.MAX_CONFIG, identity),
    lambda encoded, identity: (encoded, identity.replace(b'"version":', b'"version":"1.0.0", "version":')),
    lambda encoded, identity: (encoded, identity.replace(b'8.12.4', b'../8.12.4')),
])
def test_config_source_limits_and_identity_ambiguity_fail_closed(mutate):
    with pytest.raises(ValueError):
        publisher.decode_launcher_config(*mutate(*encoded_config()))


@pytest.mark.parametrize('body', [b'[]', b'{"appConfig":{},"appConfig":{},"gameAuditConfig":{},"gameConfig":{}}',
                                  b'{"appConfig":{},"gameAuditConfig":{}}'])
def test_decoded_config_requires_the_original_unique_resource_schema(body):
    with pytest.raises(ValueError):
        publisher.decode_launcher_config(*encoded_config(body))


def test_future_launcher_pointer_comes_from_the_current_site_without_a_version_list():
    future = GLOBAL.replace('1.3.1', '9.24.170')
    assert publisher.parse_launcher_link(website(future)) == future
    assert publisher.parse_launcher_link(website(MAINLAND), 'cn') == MAINLAND
    assert publisher.parse_launcher_link(website('https://ays.cn/Svhq'), 'cn') == 'https://ays.cn/Svhq'


@pytest.mark.parametrize('url', [
    MAINLAND, 'http://x6oversea-game-package.infoldgames.com/xstarter/402/a.exe',
    'https://x6oversea-game-package.infoldgames.com.evil.invalid/xstarter/402/a.exe',
    'https://user@x6oversea-game-package.infoldgames.com/xstarter/402/a.exe',
    'https://x6oversea-game-package.infoldgames.com:443/xstarter/402/a.exe',
    GLOBAL + '?other=1', GLOBAL + '#other', GLOBAL.replace('402/', '402/%2e%2e/'),
    GLOBAL.replace('402/', '402/%252e%252e/'), GLOBAL.replace('402/', '402/%5c'),
    GLOBAL.replace('402/', '402/%09'), GLOBAL.replace('402/', '402/%00'),
    'https://ays.cn/Svhq', GLOBAL.replace('.exe', '.zip'),
])
def test_launcher_metadata_cannot_switch_region_or_inject_a_different_download(url):
    with pytest.raises(ValueError):
        publisher.parse_launcher_link(website(url))


@pytest.mark.parametrize('mutate', [
    lambda raw: raw + raw,
    lambda raw: raw.replace(b'"props":', b'"props": {}, "props":'),
    lambda raw: raw.replace(b'id="__NEXT_DATA__"', b'id="__NEXT_DATA__" id="other"'),
    lambda raw: raw.replace(b'</script>', b''),
    lambda raw: raw.replace(b'"windowsUrl"', b'"unrelatedUrl"'),
    lambda raw: raw.replace(b'"__type": "text"', b'"__type": "other"'),
    lambda raw: raw + b' ' * publisher.MAX_PAGE,
])
def test_ambiguous_truncated_or_changed_metadata_fails_without_falling_back_to_an_html_link(mutate):
    with pytest.raises(ValueError):
        publisher.parse_launcher_link(mutate(website(GLOBAL)))


def test_short_link_redirects_are_checked_before_network_dispatch():
    handler = publisher._LauncherRedirect('cn')
    request = Request('https://ays.cn/Svhq', method='HEAD')
    target = handler.redirect_request(request, None, 302, 'Found', {}, MAINLAND)
    assert target.full_url == MAINLAND and target.get_method() == 'HEAD'
    with pytest.raises(ValueError):
        handler.redirect_request(request, None, 302, 'Found', {}, GLOBAL)
    handler.count = 4
    with pytest.raises(ValueError):
        handler.redirect_request(request, None, 302, 'Found', {}, MAINLAND)


def test_discovery_never_fetches_installer_payload_or_reports_its_size_as_game_data(monkeypatch):
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        assert kwargs['limit'] == publisher.MAX_PAGE
        return website(GLOBAL)
    monkeypatch.setattr(publisher, 'download', fetch)
    result = publisher.discover_launcher()
    assert calls == [publisher.REGIONS['global'][0]]
    assert result.url == GLOBAL and result.region == 'global'
    assert len(result.website_sha256) == 64
    assert not hasattr(result, 'download_bytes')


def test_homepage_redirect_is_not_accepted_as_fresh_publisher_metadata():
    with pytest.raises(ValueError):
        publisher._NoRedirect().redirect_request(None, None, 302, '', {}, GLOBAL)


@pytest.mark.parametrize('final_url', [MAINLAND, GLOBAL, 'https://ays.cn/not-resolved'])
def test_mainland_resolution_requires_a_final_regional_cdn_without_reading_response_data(monkeypatch, final_url):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def geturl(self): return final_url
        def read(self, *_args): raise AssertionError('Installer bodies must not be read.')
    class Opener:
        def open(self, request, **_kwargs):
            assert request.get_method() == 'HEAD'
            assert request.full_url == 'https://ays.cn/Svhq'
            return Response()
    monkeypatch.setattr(publisher, 'download', lambda *_args, **_kwargs: website('https://ays.cn/Svhq'))
    monkeypatch.setattr(publisher.urllib.request, 'build_opener', lambda *_handlers: Opener())
    if final_url == MAINLAND:
        assert publisher.discover_launcher('cn').url == MAINLAND
    else:
        with pytest.raises(ValueError):
            publisher.discover_launcher('cn')
