"""Read the publisher's regional launcher pointers without executing a launcher.

This is discovery infrastructure, not a dialogue-data provider. It follows the
official anonymous SDK to current base/hotfix manifest pointers. A launcher URL,
manifest pointer or installer size cannot stand in for a required dialogue
download size or verified text/voice bindings.
"""
from dataclasses import dataclass, field
import base64
import hashlib
from html.parser import HTMLParser
import json
import hmac
import re
import time
import urllib.request
from urllib.parse import quote, unquote, urlsplit
import uuid

from .publisher_http import download


MAX_PAGE = 512 * 1024
MAX_CONFIG = 64 * 1024
MAX_RESPONSE = 128 * 1024
REGIONS = {
    'global': ('https://infinitynikki.infoldgames.com/en/home',
               'x6oversea-game-package.infoldgames.com'),
    'cn': ('https://infinitynikki.nuanpaper.com/home',
           'x6cn-game-package.papegames.com'),
}


def _require(condition):
    if not condition:
        raise ValueError('Infinity Nikki official download metadata is incomplete or has changed format.')


def _region(region):
    _require(isinstance(region, str) and region in REGIONS)
    return REGIONS[region]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _identity(raw):
    _require(isinstance(raw, bytes) and len(raw) <= 4096)
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_object)
    app, version, timestamp = (value[key] for key in ('launcherAppId', 'version', 'time'))
    _require(isinstance(app, str) and re.fullmatch(r'[0-9]{1,16}', app))
    _require(isinstance(version, str) and re.fullmatch(r'[0-9]{1,8}(?:\.[0-9]{1,8}){2,3}', version))
    _require(isinstance(timestamp, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', timestamp))
    return app, version, timestamp


def _crypto_capability(crypto):
    if crypto is None:
        from .publisher_crypto import DesktopPublisherCrypto
        return DesktopPublisherCrypto()
    return crypto


def decode_launcher_config(encoded: bytes, identity: bytes, *, crypto=None) -> dict:
    """Decode data resources from an independently authenticated launcher member.

    The signed Global 1.3.1 format derives its config cipher from that member's
    own launcher identity. No publisher key is embedded here or persisted as a
    separate prerequisite. This function does not authenticate a PE or establish
    a current game generation; callers must establish source provenance first.
    """
    _require(isinstance(encoded, bytes) and 0 < len(encoded) <= MAX_CONFIG)
    _require(isinstance(identity, bytes) and len(identity) <= 4096)
    try:
        app, version, timestamp = _identity(identity)
        seed = app + version.replace('.', '_') + timestamp.replace('-', '/').replace(' ', '-')
        key = hashlib.md5(seed.encode('ascii')).hexdigest().encode('ascii')
        raw = base64.b64decode(encoded, validate=True)
        _require(len(raw) >= 16 and len(raw) % 16 == 0)
        body = _crypto_capability(crypto).block_cipher(algorithm='AES', mode='CBC', key=key,
                                                     data=raw, iv=key[:16], decrypt=True)
        pad = body[-1]
        _require(0 < pad <= 16 and body[-pad:] == bytes([pad]) * pad)
        config = json.loads(body[:-pad].decode('utf-8-sig'), object_pairs_hook=_unique_object)
        _require(isinstance(config, dict) and all(isinstance(config.get(name), dict)
                 for name in ('appConfig', 'gameAuditConfig', 'gameConfig')))
        return config
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Infinity Nikki launcher config resources cannot be read.') from error


class _TransportCipher:
    """Ephemeral source-derived request cipher, never a serialized key cache."""
    def __init__(self, crypto, algorithm, mode, key, block):
        self.crypto, self.algorithm, self.mode, self.key, self.block = crypto, algorithm, mode, key, block

    def _crypt(self, data, decrypt):
        return self.crypto.block_cipher(algorithm=self.algorithm, mode=self.mode, key=self.key, data=data,
            iv=self.key[:self.block] if self.mode == 'CBC' else None, decrypt=decrypt)

    def encrypt(self, data):
        return self._crypt(data, False)

    def decrypt(self, data):
        return self._crypt(data, True)


def _transport_cipher(app, timestamp, *, crypto=None):
    """Reproduce the signed SDK's per-request cipher, never a saved asset key."""
    seed = app['aesKey'][2]
    use_aes, use_cbc, use_hex = ord(seed[0]) % 2 != 0, ord(app['appId'][-1]) % 2 != 0, ord(timestamp[-1]) % 2 == 0
    label = (seed + ('#AES' if use_aes else '#DES') + ('#CBC' if use_cbc else '#ECB') +
             '#PKCS7Padding' + ('#HEX' if use_hex else '#BASE64') + '#' + app['appId'] + '#' + timestamp)
    key = hashlib.md5(label.encode('ascii')).hexdigest().encode('ascii')
    algorithm, block = ('AES', 16) if use_aes else ('DES', 8)
    if not use_aes:
        key = key[:8]
    cipher = _TransportCipher(_crypto_capability(crypto), algorithm, 'CBC' if use_cbc else 'ECB', key, block)
    return cipher, block, use_hex


def _production_app(config):
    app = config['appConfig']
    _require(isinstance(app, dict) and app['hostEnv'] == 2 and app['channelEnv'] == 'prod')
    for name in ('appId', 'clientId', 'sdkChannel'):
        _require(isinstance(app[name], str) and re.fullmatch(r'[0-9]{1,16}', app[name]))
    for name in ('appKey', 'aesKey'):
        _require(isinstance(app[name], list) and len(app[name]) == 3 and
                 isinstance(app[name][2], str) and re.fullmatch(r'[A-Za-z0-9]{1,128}', app[name][2]))
    _require(isinstance(app['bffHost'], list) and len(app['bffHost']) == 3 and
             app['bffHost'][2] == 'https://passport.infoldgames.com')
    _require(type(app['region']) is int and 0 <= app['region'] <= 100)
    return app


@dataclass(frozen=True)
class PatchlistExchange:
    url: str
    data: bytes = field(repr=False)
    headers: dict = field(repr=False)
    timestamp: str = field(repr=False)


def patchlist_request(config: dict, identity: bytes, *, now=None, crypto=None) -> PatchlistExchange:
    """Build original anonymous metadata bytes for a caller-owned transport.

    Only authenticated original launcher resources may supply this configuration.
    No account/session or real host/device identity is collected. The ephemeral
    request does not authorize a connection or certify any returned pointer.
    """
    try:
        app = _production_app(config)
        _, version, _ = _identity(identity)
        instant = int(time.time()) if now is None else now
        _require(type(instant) is int and 0 <= instant < 2**63)
        timestamp = str(instant)
        metadata = {'app_id': app['appId'], 'client_id': app['clientId'], 'clientid': app['clientId'],
                    'lang': 'en', 'sign_type': 'hmac', 'timestamp': timestamp}
        encode = lambda value: quote(value, safe='-._~')
        form = '&'.join(key + '=' + encode(value) for key, value in sorted(metadata.items()))
        signature = hmac.new(app['appKey'][2].encode('ascii'), form.encode('ascii'), hashlib.md5).hexdigest()
        payload = json.dumps({'DOID': '', 'os_platform': '3', 'sdk_channel': app['sdkChannel'],
            'channel': app['sdkChannel'], 'region': app['region'], 'env': app['channelEnv']},
            sort_keys=True, separators=(',', ':')).encode('utf-8')
        cipher, block, use_hex = _transport_cipher(app, timestamp, crypto=crypto)
        pad = block - len(payload) % block
        encrypted = cipher.encrypt(payload + bytes([pad]) * pad)
        encoded = encrypted.hex().upper() if use_hex else base64.b64encode(encrypted).decode('ascii')
        url = app['bffHost'][2] + '/v1/accessories/gameconfig/patchlist'
        return PatchlistExchange(url, (form + '&sign=' + signature + '&data=' + encode(encoded)).encode('ascii'),
            {'Accept-Encoding': 'identity', 'User-Agent': 'GameImmersionToolkit/1',
                'Content-Type': 'application/x-www-form-urlencoded', 'X-SDK-VERSION': '0.0.1',
                'X-SDK-PLATFORM': 'pclauncher', 'X-SDK-CHANNEL': app['sdkChannel'],
                'X-SDK-DEVICE-ID': str(uuid.uuid4()), 'X-SDK-OS-VERSION': '10',
                'X-SDK-APP-VERSION': version, 'X-SDK-DEVICE-BRAND': 'Microsoft', 'X-SDK-DEVICE-MODEL': 'PC'}, timestamp)
    except (UnicodeError, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Infinity Nikki anonymous publisher request cannot be constructed.') from error


def decode_patchlist_response(raw: bytes, config: dict, exchange: PatchlistExchange, *, crypto=None) -> dict:
    """Read the actual request-correlated response without opening a connection."""
    try:
        app = _production_app(config)
        _require(isinstance(exchange, PatchlistExchange) and isinstance(exchange.timestamp, str) and
                 re.fullmatch('[0-9]{1,19}', exchange.timestamp) and int(exchange.timestamp) < 2**63 and
                 exchange.url == app['bffHost'][2] + '/v1/accessories/gameconfig/patchlist')
        _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_RESPONSE)
        cipher, block, use_hex = _transport_cipher(app, exchange.timestamp, crypto=crypto)
        reply = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
        _require(isinstance(reply, dict) and type(reply.get('code')) is int and reply['code'] == 0 and isinstance(reply['data'], str))
        encrypted = bytes.fromhex(reply['data']) if use_hex else base64.b64decode(reply['data'], validate=True)
        _require(0 < len(encrypted) <= MAX_CONFIG and len(encrypted) % block == 0)
        body = cipher.decrypt(encrypted)
        pad = body[-1]
        _require(0 < pad <= block and body[-pad:] == bytes([pad]) * pad)
        value = json.loads(body[:-pad].decode('utf-8'), object_pairs_hook=_unique_object)
        _require(isinstance(value, dict) and isinstance(value.get('game_config_apk'), dict)
                 and isinstance(value.get('game_config_patch'), dict))
        return value
    except (UnicodeError, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Infinity Nikki anonymous publisher manifest metadata cannot be read.') from error


def discover_patchlist(config: dict, identity: bytes, *, opener=None, now=None, crypto=None) -> dict:
    """Legacy discovery entry point; maintained preparation uses its own context I/O."""
    exchange = patchlist_request(config, identity, now=now, crypto=crypto)
    request = urllib.request.Request(exchange.url, data=exchange.data, headers=exchange.headers)
    open_request = opener or urllib.request.build_opener(_NoRedirect()).open
    with open_request(request, timeout=45) as response:
        _require(response.status == 200 and response.geturl() == exchange.url)
        raw = response.read(MAX_RESPONSE + 1)
        length = response.headers.get('Content-Length')
        _require(len(raw) <= MAX_RESPONSE and (length is None or length.isdecimal() and int(length) == len(raw)))
    return decode_patchlist_response(raw, config, exchange, crypto=crypto)


class _NextData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts, self.count, self.active = [], 0, False

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and any(key == 'id' and value == '__NEXT_DATA__' for key, value in attrs):
            _require(len(dict(attrs)) == len(attrs) and not self.active)
            self.count += 1
            _require(self.count == 1 and dict(attrs).get('type') == 'application/json')
            self.active = True

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def _launcher_url(url, region, *, allow_short_link=False):
    _, host = _region(region)
    _require(isinstance(url, str) and 0 < len(url) <= 2048)
    _require(all(ord(char) >= 33 and ord(char) != 127 for char in url))
    parsed = urlsplit(url)
    _require(parsed.scheme == 'https' and parsed.netloc == parsed.hostname and
             not parsed.query and not parsed.fragment)
    path = unquote(parsed.path)
    _require(all(ord(char) >= 32 and ord(char) != 127 for char in path) and
             not any(char in path for char in ('\\', '%')) and
             not any(part in ('.', '..') for part in path.split('/')))
    if allow_short_link and region == 'cn' and parsed.hostname == 'ays.cn':
        _require(re.fullmatch(r'/[A-Za-z0-9]{1,64}', path))
    else:
        _require(parsed.hostname == host and
                 re.fullmatch(r'/xstarter/[0-9]{1,8}/[^/]+\.exe', path))
    return url


def parse_launcher_link(raw: bytes, region='global') -> str:
    """Resolve the exact website field; unrelated links/scripts are not evidence."""
    _region(region)
    _require(isinstance(raw, bytes) and len(raw) <= MAX_PAGE)
    parser = _NextData()
    try:
        parser.feed(raw.decode('utf-8'))
        parser.close()
        _require(parser.count == 1 and not parser.active)
        data = json.loads(''.join(parser.parts), object_pairs_hook=_unique_object)
        entries = data['props']['pageProps']['pageData']['page']['windowsUrl']
        _require(isinstance(entries, list) and len(entries) == 1 and
                 entries[0]['__type'] == 'text')
        return _launcher_url(entries[0]['value'], region, allow_short_link=True)
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Infinity Nikki official website metadata cannot be read.') from error


def android_source_url(url: str) -> str:
    """Accept the original CN direct APK family, without a revision allowlist."""
    _require(isinstance(url, str) and len(url) <= 2048 and
             all(33 <= ord(char) < 127 for char in url))
    parsed = urlsplit(url)
    _require(parsed.scheme == 'https' and parsed.netloc == 'x6cn-game-apk.papegames.com' and
             not parsed.query and not parsed.fragment and
             re.fullmatch(r'/x6cn/adapk/[A-Za-z0-9_.-]+\.apk', parsed.path) and
             '..' not in parsed.path)
    return url


def parse_android_link(raw: bytes) -> str:
    """Read only the publisher's evidenced mainland Android website field.

    This is a source of native bootstrap data, not proof of Global Android
    acceptance, regional game assets or compatibility of any downstream PAK.
    """
    _require(isinstance(raw, bytes) and len(raw) <= MAX_PAGE)
    parser = _NextData()
    try:
        parser.feed(raw.decode('utf-8'))
        parser.close()
        _require(parser.count == 1 and not parser.active)
        data = json.loads(''.join(parser.parts), object_pairs_hook=_unique_object)
        entries = data['props']['pageProps']['pageData']['page']['android']
        _require(isinstance(entries, list) and len(entries) == 1 and entries[0]['__type'] == 'text')
        return android_source_url(entries[0]['value'])
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Could not read the official mainland Android download field.') from error


class _LauncherRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, region):
        self.region, self.count = region, 0

    def redirect_request(self, request, response, code, message, headers, newurl):
        self.count += 1
        _require(self.count <= 4)
        _launcher_url(newurl, self.region, allow_short_link=True)
        redirected = super().redirect_request(request, response, code, message, headers, newurl)
        # urllib's default redirect request becomes GET even for a HEAD source.
        # Retain HEAD so resolving a short link cannot fetch an installer body.
        if redirected is not None and request.get_method() == 'HEAD':
            redirected.method = 'HEAD'
        return redirected


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args):
        raise ValueError('Infinity Nikki official homepage unexpectedly redirected.')


@dataclass(frozen=True)
class LauncherPointer:
    region: str
    url: str
    website_sha256: str


def discover_launcher(region='global') -> LauncherPointer:
    """Fetch current official pointers only; do not download/execute the installer.

    Mainland's publisher-linked short URL is resolved with HEAD and guarded at
    every redirect. A changed website/host fails instead of guessing a mirror.
    """
    homepage, _ = _region(region)
    opener = urllib.request.build_opener(_NoRedirect())
    raw = download(homepage, limit=MAX_PAGE, opener=opener.open)
    url = parse_launcher_link(raw, region)
    if urlsplit(url).hostname == 'ays.cn':
        opener = urllib.request.build_opener(_LauncherRedirect(region))
        request = urllib.request.Request(url, method='HEAD', headers={'Accept-Encoding': 'identity'})
        with opener.open(request, timeout=45) as response:
            _require(response.status == 200)
            url = _launcher_url(response.geturl(), region)
    return LauncherPointer(region, url, hashlib.sha256(raw).hexdigest())
