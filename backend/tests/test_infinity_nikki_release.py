import base64
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs
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


def sdk_fixture(aes, cbc):
    return {'appConfig': {'appId': '123456' + ('5' if cbc else '4'), 'clientId': '5678',
        'sdkChannel': '1', 'hostEnv': 2, 'channelEnv': 'prod', 'region': 4,
        'appKey': ['', '', 'ownedFixtureKey42'], 'aesKey': ['', '', ('1' if aes else '2') + 'ownedCipherSeed'],
        'bffHost': ['', '', 'https://passport.infoldgames.com']}}


def fixture_cipher(app, instant, aes, cbc):
    from Crypto.Cipher import AES, DES
    # Independently constructed original-format wire fixture, containing no game data.
    label = app['aesKey'][2] + ('#AES' if aes else '#DES') + ('#CBC' if cbc else '#ECB')
    label += '#PKCS7Padding' + ('#HEX' if instant % 2 == 0 else '#BASE64')
    label += '#' + app['appId'] + '#' + str(instant)
    key = hashlib.md5(label.encode()).hexdigest().encode()
    klass = AES if aes else DES
    if not aes:
        key = key[:8]
    return (klass.new(key, klass.MODE_CBC, key[:klass.block_size]) if cbc
            else klass.new(key, klass.MODE_ECB)), klass.block_size


def sdk_response(app, instant, aes, cbc, value):
    raw = json.dumps(value, separators=(',', ':')).encode()
    cipher, block = fixture_cipher(app, instant, aes, cbc)
    pad = block - len(raw) % block
    sealed = cipher.encrypt(raw + bytes([pad]) * pad)
    data = sealed.hex().upper() if instant % 2 == 0 else base64.b64encode(sealed).decode()
    return json.dumps({'code': 0, 'info': 'OK', 'data': data}).encode()


class SDKResponse:
    status = 200
    def __init__(self, raw):
        self.raw = raw
        self.headers = {'Content-Length': str(len(raw))}
    def __enter__(self): return self
    def __exit__(self, *_args): pass
    def geturl(self): return 'https://passport.infoldgames.com/v1/accessories/gameconfig/patchlist'
    def read(self, size): return self.raw[:size]


@pytest.mark.parametrize('aes,cbc', [(False, False), (False, True), (True, False), (True, True)])
@pytest.mark.parametrize('instant', [100, 101])
def test_anonymous_sdk_transport_follows_source_cipher_modes_without_account_or_host_data(aes, cbc, instant):
    config, identity = sdk_fixture(aes, cbc), encoded_config()[1]
    app = config['appConfig']
    packet = {'game_config_apk': {'apk_version': '9000'}, 'game_config_patch': {'id': 12}}
    def open_request(request, **_kwargs):
        assert request.get_method() == 'POST'
        assert not any(key.lower() in ('authorization', 'cookie') for key in request.headers)
        fields = parse_qs(request.data.decode())
        signature_source = '&'.join(key + '=' + fields[key][0] for key in sorted(fields) if key not in ('sign', 'data'))
        assert fields['sign'] == [hmac.new(b'ownedFixtureKey42', signature_source.encode(), hashlib.md5).hexdigest()]
        cipher, block = fixture_cipher(app, instant, aes, cbc)
        sealed = bytes.fromhex(fields['data'][0]) if instant % 2 == 0 else base64.b64decode(fields['data'][0])
        raw = cipher.decrypt(sealed)
        assert 0 < raw[-1] <= block
        assert json.loads(raw[:-raw[-1]]) == {'DOID': '', 'os_platform': '3', 'sdk_channel': '1',
                                               'channel': '1', 'region': 4, 'env': 'prod'}
        return SDKResponse(sdk_response(app, instant, aes, cbc, packet))
    assert publisher.discover_patchlist(config, identity, opener=open_request, now=instant) == packet


def test_two_manifest_generations_are_fetched_anew_and_not_replaced_by_cached_success():
    config, identity = sdk_fixture(False, False), encoded_config()[1]
    current = {'generation': '9000', 'fail': False}
    def open_request(_request, **_kwargs):
        if current['fail']:
            raise OSError('Synthetic network interruption')
        value = {'game_config_apk': {'apk_version': current['generation']}, 'game_config_patch': {}}
        return SDKResponse(sdk_response(config['appConfig'], 100, False, False, value))
    first = publisher.discover_patchlist(config, identity, opener=open_request, now=100)
    current['generation'] = '9001'
    second = publisher.discover_patchlist(config, identity, opener=open_request, now=100)
    assert first['game_config_apk']['apk_version'] == '9000'
    assert second['game_config_apk']['apk_version'] == '9001'
    current['fail'] = True
    with pytest.raises(OSError):
        publisher.discover_patchlist(config, identity, opener=open_request, now=100)


@pytest.mark.parametrize('aes,cbc', [(False, False), (False, True), (True, False), (True, True)])
@pytest.mark.parametrize('instant', [100, 101])
def test_pure_sdk_exchange_uses_the_explicit_crypto_capability_without_own_network(aes, cbc, instant, monkeypatch):
    from backend.publisher_crypto import DesktopPublisherCrypto
    reference = DesktopPublisherCrypto()
    class Explicit:
        def __init__(self): self.calls = []
        def block_cipher(self, **kwargs):
            self.calls.append((kwargs['algorithm'], kwargs['mode'], kwargs['decrypt']))
            return reference.block_cipher(**kwargs)
    crypto = Explicit()
    config, identity = sdk_fixture(aes, cbc), encoded_config()[1]
    value = {'game_config_apk': {'apk_version': '9000'}, 'game_config_patch': {'id': 12}}
    wire = sdk_response(config['appConfig'], instant, aes, cbc, value)
    monkeypatch.setattr(publisher.urllib.request, 'build_opener', lambda *_: pytest.fail('pure exchange cannot open a connection'))
    monkeypatch.setattr('backend.publisher_crypto.DesktopPublisherCrypto', lambda: pytest.fail('explicit capability was bypassed'))
    exchange = publisher.patchlist_request(config, identity, now=instant, crypto=crypto)
    assert publisher.decode_patchlist_response(wire, config, exchange, crypto=crypto) == value
    assert crypto.calls == [('AES' if aes else 'DES', 'CBC' if cbc else 'ECB', False),
                            ('AES' if aes else 'DES', 'CBC' if cbc else 'ECB', True)]
    assert 'ownedFixtureKey42' not in repr(exchange) and 'X-SDK-DEVICE-ID' not in repr(exchange)


def test_explicit_launcher_crypto_imports_and_decodes_without_desktop_crypto_in_a_fresh_process():
    script = r'''
import base64,builtins,json,sys
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name=='Crypto' or name.startswith('Crypto.'):
        raise AssertionError('Desktop crypto fallback was imported')
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from backend import infinity_nikki_release as source
class Explicit:
    calls=0
    def block_cipher(self,**kw):
        assert kw['algorithm']=='AES' and kw['mode']=='CBC' and kw['decrypt']
        self.calls+=1
        return kw['data']
cap=Explicit()
identity=json.dumps({'launcherAppId':'12345','version':'9.2.7','time':'2026-02-03 04:05:06'}).encode()
expected={'appConfig':{},'gameAuditConfig':{},'gameConfig':{}}
plain=json.dumps(expected).encode();pad=16-len(plain)%16
encoded=base64.b64encode(plain+bytes([pad])*pad)
assert source.decode_launcher_config(encoded,identity,crypto=cap)==expected
assert cap.calls==1 and not any(n=='Crypto' or n.startswith('Crypto.') for n in sys.modules)
'''
    subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[2],
                   check=True, capture_output=True, timeout=30)


@pytest.mark.parametrize('case', ['error', 'duplicate', 'oversize', 'short', 'redirect', 'bad-padding'])
def test_sdk_rejects_failure_ambiguous_truncated_redirected_or_unbounded_metadata(case):
    config, identity = sdk_fixture(False, False), encoded_config()[1]
    def open_request(_request, **_kwargs):
        raw = sdk_response(config['appConfig'], 100, False, False,
                           {'game_config_apk': {}, 'game_config_patch': {}})
        if case == 'error': raw = b'{"code":1002,"info":"args_error"}'
        if case == 'duplicate': raw = raw.replace(b'"code":', b'"code":1,"code":')
        if case == 'oversize': raw = b' ' * (publisher.MAX_RESPONSE + 1)
        if case == 'bad-padding':
            value = json.loads(raw)
            value['data'] = value['data'][:-16] + '00' * 8
            raw = json.dumps(value).encode()
        response = SDKResponse(raw)
        if case == 'short': response.headers['Content-Length'] = str(len(raw) + 1)
        if case == 'redirect': response.geturl = lambda: 'https://example.invalid/manifest'
        return response
    with pytest.raises(ValueError):
        publisher.discover_patchlist(config, identity, opener=open_request, now=100)


def test_sdk_never_dispatches_a_test_or_foreign_host_from_a_changed_launcher_config():
    config, identity = sdk_fixture(False, False), encoded_config()[1]
    config['appConfig']['bffHost'][2] = 'https://example.invalid'
    def forbidden(*_args, **_kwargs): raise AssertionError('Foreign request was dispatched.')
    with pytest.raises(ValueError):
        publisher.discover_patchlist(config, identity, opener=forbidden, now=100)
