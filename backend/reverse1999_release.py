"""Public Reverse: 1999 launcher discovery, not complete dialogue preparation.

Package sizes describe the publisher's complete client archives. They must not
be displayed as the size of a yet-unresolved dialogue-only selection.
"""
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.parse import urlencode
import urllib.request


METADATA_LIMIT = 1024 * 1024
MAX_PARTS = 1024
GLOBAL_SITE = 'https://re1999.bluepoch.com'
GLOBAL_UPDATE_HOSTS = ('hotupdate-hw.sl916.com', 'hotupdate-bak-hw.sl916.com')
DOWNLOAD_HOSTS = frozenset(('download.bluepoch.com', 'download-bak.bluepoch.com'))
OPTIONAL_UPDATE_HOSTS = ('optionalres-hw.sl916.com', 'optionalres-bak-hw.sl916.com')
OPTIONAL_DOWNLOAD_HOSTS = frozenset(('optionalres-res-hw.sl916.com',
                                     'optionalres-res-bak-hw.sl916.com'))
VOICE_LOCALES = {'en': 'en', 'zh': 'zh', 'ja': 'jp', 'ko': 'kr'}
PROFILE_REFERENCE = ('Peebify-Launcher/peebify-launcher-lite',
                     '0fdb84bf39d27a5128178475ef728ffb6dd22656',
                     'src-tauri/src/backend/game_profiles.rs')


def _check(condition, message):
    if not condition:
        raise ValueError(message)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _check(key not in result, 'Duplicate publisher metadata field.')
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique)


def _inflate(raw):
    if not raw.startswith(b'\x1f\x8b'):
        return raw
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:
        result = source.read(METADATA_LIMIT + 1)
    _check(len(result) <= METADATA_LIMIT, 'Publisher metadata expands beyond its limit.')
    return result


def decode_metadata(raw):
    """Read the evidenced JSON/gzip and reversible paired-byte wire envelopes.

    The paired-byte mask is recovered from the JSON/gzip framing, not a game
    key literal. Every result still passes strict semantic ownership checks.
    """
    _check(isinstance(raw, bytes) and 0 < len(raw) <= METADATA_LIMIT,
           'Publisher metadata exceeds its wire limit.')
    candidates = [raw]
    if raw.startswith(b'\x1f\x8b'):
        candidates.append(_inflate(raw))
    for candidate in tuple(candidates):
        if len(candidate) < 2:
            continue
        for first, second in (b'{"', b'\x1f\x8b'):
            mask = candidate[0] ^ second
            if candidate[1] ^ mask != first:
                continue
            decoded = bytearray(candidate)
            for position in range(0, len(decoded) - 1, 2):
                decoded[position], decoded[position + 1] = (decoded[position + 1] ^ mask,
                                                           decoded[position] ^ mask)
            try:
                candidates.append(_inflate(bytes(decoded)))
            except (OSError, EOFError, ValueError):
                continue
    for candidate in candidates:
        try:
            value = _json(candidate)
        except (UnicodeError, ValueError):
            continue
        _check(isinstance(value, dict), 'Publisher metadata must be an object.')
        return value
    raise ValueError('Unsupported publisher metadata envelope.')


def _url(url, hosts):
    _check(isinstance(url, str) and 0 < len(url) <= 4096, 'Invalid publisher URL.')
    parsed = urlsplit(url)
    _check(parsed.scheme == 'https' and parsed.hostname in hosts and parsed.port in (None, 443)
           and parsed.username is None and parsed.password is None and not parsed.fragment
           and '\\' not in url and all(ord(char) >= 32 for char in url), 'Untrusted publisher URL.')
    return parsed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('Publisher metadata redirects require renewed source verification.')


def request(url, *, body=None, language='en', opener=None):
    hosts = {urlsplit(GLOBAL_SITE).hostname, *GLOBAL_UPDATE_HOSTS, *OPTIONAL_UPDATE_HOSTS}
    _url(url, hosts)
    payload = None if body is None else json.dumps(body, separators=(',', ':')).encode()
    req = urllib.request.Request(url, data=payload,
        headers={'User-Agent': 'GameImmersionToolkit/1', 'Accept-Encoding': 'identity',
                 'Content-Type': 'application/json', 'lang': language})
    open_request = opener or urllib.request.build_opener(_NoRedirect()).open
    with open_request(req, timeout=30) as response:
        _check(response.status == 200 and response.geturl() == url, 'Incomplete publisher metadata response.')
        raw = response.read(METADATA_LIMIT + 1)
        length = response.headers.get('Content-Length')
        _check(0 < len(raw) <= METADATA_LIMIT and (length is None or length.isdecimal()
               and int(length) == len(raw)), 'Truncated or oversized publisher metadata.')
    return raw


def _version(value):
    _check(isinstance(value, str) and re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,6}){1,3}', value),
           'Invalid publisher version.')
    return value


def _body(current='', target=None):
    _check(current == '' or bool(_version(current)), 'Invalid previous publisher version.')
    if target is not None:
        _version(target)
    fields = ('60001', '2', '4', '200', '6001', current)
    return {'gameId': fields[0], 'osType': 2, 'envType': 4, 'channelId': 200,
            'subChannelId': fields[4], 'currentVersion': current,
            'sign': hashlib.md5('_'.join(fields).encode()).hexdigest(), 'targetVersion': target}


def _data(raw):
    value = decode_metadata(raw)
    _check(type(value.get('code')) is int and value['code'] == 200
           and isinstance(value.get('data'), dict), 'Publisher rejected the update query.')
    return value['data']


def _positive(value):
    _check(type(value) is int and 0 < value < 2**50, 'Invalid publisher package size.')
    return value


@dataclass(frozen=True)
class Archive:
    url: str
    size: int
    expanded_size: int
    md5: str
    part: int
    resource_revision: str


def package(data, expected_version):
    _version(expected_version)
    _check(data.get('targetVersion') == expected_version, 'Publisher package version changed during discovery.')
    full = data.get('fullPackage')
    _check(isinstance(full, dict), 'Publisher did not provide a full client inventory.')
    urls = full.get('packageUrls')
    _check(isinstance(urls, list) and 0 < len(urls) <= MAX_PARTS, 'Invalid publisher package list.')
    archives, identities = [], set()
    for url in urls:
        parsed = _url(url, DOWNLOAD_HOSTS)
        _check(not parsed.query and parsed.path.startswith('/en/game/' + expected_version + '/'),
               'Publisher archive belongs to another region or version.')
        match = re.fullmatch(r'[0-9]+_gameId_60001_pid_[0-9]+_res_([0-9.]+)_app_'
            + re.escape(expected_version) + r'_total_([0-9]+)_origin_([0-9]+)_size_([0-9]+)'
            r'_md5_([a-f0-9]{32})_([0-9]+)\.7z', parsed.path.rsplit('/', 1)[-1])
        _check(match is not None, 'Publisher archive has no supported immutable identity.')
        revision, total, expanded, size, digest, part = match.groups()
        _version(revision)
        total, expanded, size, part = int(total), int(expanded), int(size), int(part)
        _positive(total); _positive(expanded); _positive(size)
        _check(total == full.get('packageRealSize') and part not in identities,
               'Publisher archive size or identity is inconsistent.')
        identities.add(part)
        archives.append(Archive(url, size, expanded, digest, part, revision))
    _check(sum(a.size for a in archives) == _positive(full.get('packageSize'))
           and sum(a.expanded_size for a in archives) == _positive(full.get('packageRealSize'))
           and len({a.resource_revision for a in archives}) == 1,
           'Publisher archive totals or resource revisions disagree.')
    return tuple(sorted(archives, key=lambda a: a.part))


def discover(*, fetch=request):
    """Discover the verified Global Windows launcher inventory, without assets.

    Android may read this portable metadata; consuming Windows archives and
    the independent in-game hotfix inventory are not implemented by this API.
    """
    responses = []

    def read(url, body=None):
        raw = fetch(url, body=body)
        responses.append({'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
        return raw

    script = read(GLOBAL_SITE + '/assets/js/api.js').decode('utf-8')
    matches = re.findall(r'\bpageVersion\s*:\s*["\']([0-9.]+)["\']', script)
    game_ids = re.findall(r'\bgameId\s*:\s*([0-9]+)', script)
    _check(len(matches) == 1 and game_ids == ['60001'], 'Publisher website bootstrap is ambiguous.')
    page_version = _version(matches[0])
    website = _data(read(GLOBAL_SITE + '/activity/official/websites/version-page',
                          {'gameId': 60001, 'pageVersion': page_version}))
    _check(website.get('pageVersion') == page_version, 'Publisher website response belongs to another page.')
    installer = website.get('doubleEndDownloadUrl')
    _url(installer, DOWNLOAD_HOSTS)
    _check(urlsplit(installer).path.startswith('/en/') and installer.endswith('.exe'),
           'Publisher website has no verified Global installer.')
    last = None
    for host in GLOBAL_UPDATE_HOSTS:
        try:
            prefix = 'https://' + host + '/diff-update/'
            version = _version(_data(read(prefix + 'version', _body()))['latestVersion'])
            resource = _data(read(prefix + 'resource', _body(target=version)))
            archives = package(resource, version)
            break
        except (HTTPError, URLError) as error:
            last = error
    else:
        raise last or ValueError('Publisher update service is unavailable.')
    source = {'region': 'global', 'platform': 'Windows', 'version': version,
              'resource_revision': archives[0].resource_revision,
              'archives': [a.__dict__ for a in archives]}
    identity = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {**source, 'schema': 'reverse1999-launcher-inventory-v1', 'fingerprint': identity,
            'download_bytes': sum(a.size for a in archives), 'expanded_bytes': sum(a.expanded_size for a in archives),
            'size_scope': 'complete-publisher-client-not-dialogue-selection',
            'dialogue_download_bytes': None, 'website_page_version': page_version,
            'installer_url': installer, 'responses': responses,
            'profile_reference': PROFILE_REFERENCE, 'dialogue_preparation_implemented': False}


def optional_voices(voice_branch, *, locales=('en', 'zh', 'ja', 'ko'), fetch=request):
    """Read original optional voice ZIP inventories for an evidenced branch.

    The branch comes from original bootstrap data, not a frozen game version.
    English is the Global base voice: its absence from optional packages is not
    missing/silent audio. Its independent base acquisition remains unresolved.
    ZIPs contain both localized banks and videos; sizes have this complete-pack
    scope, not a dialogue-only selection or final decoded-audio disk estimate.
    """
    _check(type(voice_branch) is int and 0 < voice_branch < 10**6, 'Invalid original voice branch.')
    _check(isinstance(locales, (tuple, list)) and 0 < len(locales) <= len(VOICE_LOCALES)
           and all(isinstance(locale, str) and locale in VOICE_LOCALES for locale in locales)
           and len(set(locales)) == len(locales), 'Unsupported or duplicate original voice locale.')
    native = [VOICE_LOCALES[locale] for locale in locales]
    query = urlencode({'os_type': 2, 'lang': ','.join(native),
                       'version': ','.join(f'{voice_branch}.0' for _ in native),
                       'env_type': 4, 'channel_id': 200})
    last = None
    for host in OPTIONAL_UPDATE_HOSTS:
        try:
            source_url = 'https://' + host + '/resource/60001/check?' + query
            raw = fetch(source_url)
            data = decode_metadata(raw)
            break
        except (HTTPError, URLError) as error:
            last = error
    else:
        raise last or ValueError('Publisher optional voice service is unavailable.')
    _check(set(data) <= set(native), 'Publisher returned an unexpected voice namespace.')
    packs = {}
    for locale, language in zip(locales, native):
        if language not in data:
            _check(language == 'en', 'Publisher optional voice inventory is missing; retain the previous catalog.')
            packs[locale] = {'state': 'original-base-pack-required', 'archives': [], 'download_bytes': None}
            continue
        info = data[language]
        _check(isinstance(info, dict), 'Unsupported publisher optional voice schema.')
        version = _version(info.get('latest_ver'))
        _check(version.split('.')[0] == str(voice_branch), 'Voice branch changed; refresh original bootstrap first.')
        bases = []
        for name in ('download_url', 'download_url_bak'):
            base = info.get(name)
            parsed = _url(base, OPTIONAL_DOWNLOAD_HOSTS)
            _check(not parsed.query and re.fullmatch(r'/uploadzip/60001/4/[0-9]+', parsed.path),
                   'Optional voice CDN namespace is not owned by this release profile.')
            bases.append(base)
        rows = info.get('res')
        _check(isinstance(rows, list) and 0 < len(rows) <= MAX_PARTS, 'Publisher optional pack list is missing or oversized.')
        identities, archives = set(), []
        for position, row in enumerate(rows):
            _check(isinstance(row, dict), 'Unsupported publisher optional archive entry.')
            name, digest, order = row.get('name'), row.get('hash'), row.get('order')
            _check(isinstance(name, str) and len(name) <= 512
                   and re.fullmatch(r'[A-Za-z0-9_./-]+\.zip', name)
                   and all(part not in ('', '.', '..') for part in name.split('/'))
                   and name not in identities, 'Unsafe or duplicate optional archive path.')
            _check(isinstance(digest, str) and re.fullmatch('[a-f0-9]{32}', digest)
                   and type(order) is int and 0 < order < 2**31, 'Invalid optional archive digest or update order.')
            identities.add(name)
            archives.append({'url': bases[0] + '/' + name, 'backup_url': bases[1] + '/' + name,
                             'md5': digest, 'size': _positive(row.get('length')),
                             'order': order, 'ordinal': position})
        packs[locale] = {'state': 'original-optional-inventory', 'version': version,
                         'archives': archives, 'download_bytes': sum(row['size'] for row in archives)}
    identity = {'region': 'global', 'platform': 'Windows', 'voice_branch': voice_branch, 'packs': packs}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {**identity, 'schema': 'reverse1999-optional-voice-inventory-v1', 'fingerprint': fingerprint,
            'source_url': source_url, 'source_sha256': hashlib.sha256(raw).hexdigest(),
            'download_bytes': sum(pack['download_bytes'] or 0 for pack in packs.values()),
            'size_scope': 'complete-optional-voice-and-video-pack-not-dialogue-selection',
            'requested_voice_inventory_complete': all(pack['state'] == 'original-optional-inventory' for pack in packs.values()),
            'expanded_bytes': None, 'dialogue_preparation_implemented': False}
