"""Read the publisher's regional launcher pointers without executing a launcher.

This is discovery infrastructure, not a game-data provider. A launcher URL or
installer size cannot stand in for the current game's resource manifest, its
dialogue download size, or verified text/voice bindings.
"""
from dataclasses import dataclass
import base64
import hashlib
from html.parser import HTMLParser
import json
import re
import urllib.request
from urllib.parse import unquote, urlsplit

from .publisher_http import download


MAX_PAGE = 512 * 1024
MAX_CONFIG = 64 * 1024
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


def decode_launcher_config(encoded: bytes, identity: bytes) -> dict:
    """Decode data resources from an independently authenticated launcher member.

    The signed Global 1.3.1 format derives its config cipher from that member's
    own launcher identity. No publisher key is embedded here or persisted as a
    separate prerequisite. This function does not authenticate a PE or establish
    a current game generation; callers must establish source provenance first.
    """
    _require(isinstance(encoded, bytes) and 0 < len(encoded) <= MAX_CONFIG)
    _require(isinstance(identity, bytes) and len(identity) <= 4096)
    try:
        value = json.loads(identity.decode('utf-8-sig'), object_pairs_hook=_unique_object)
        app, version, timestamp = (value[key] for key in ('launcherAppId', 'version', 'time'))
        _require(isinstance(app, str) and re.fullmatch(r'[0-9]{1,16}', app))
        _require(isinstance(version, str) and re.fullmatch(r'[0-9]{1,8}(?:\.[0-9]{1,8}){2,3}', version))
        _require(isinstance(timestamp, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', timestamp))
        seed = app + version.replace('.', '_') + timestamp.replace('-', '/').replace(' ', '-')
        key = hashlib.md5(seed.encode('ascii')).hexdigest().encode('ascii')
        raw = base64.b64decode(encoded, validate=True)
        _require(len(raw) >= 16 and len(raw) % 16 == 0)
        from Crypto.Cipher import AES
        body = AES.new(key, AES.MODE_CBC, key[:16]).decrypt(raw)
        pad = body[-1]
        _require(0 < pad <= 16 and body[-pad:] == bytes([pad]) * pad)
        config = json.loads(body[:-pad].decode('utf-8-sig'), object_pairs_hook=_unique_object)
        _require(isinstance(config, dict) and all(isinstance(config.get(name), dict)
                 for name in ('appConfig', 'gameAuditConfig', 'gameConfig')))
        return config
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Infinity Nikki launcher config resources cannot be read.') from error


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
