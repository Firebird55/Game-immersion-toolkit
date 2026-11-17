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
import urllib.request


METADATA_LIMIT = 1024 * 1024
MAX_PARTS = 1024
GLOBAL_SITE = 'https://re1999.bluepoch.com'
GLOBAL_UPDATE_HOSTS = ('hotupdate-hw.sl916.com', 'hotupdate-bak-hw.sl916.com')
DOWNLOAD_HOSTS = frozenset(('download.bluepoch.com', 'download-bak.bluepoch.com'))
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
    hosts = {urlsplit(GLOBAL_SITE).hostname, *GLOBAL_UPDATE_HOSTS}
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
