"""Publisher hotfix indexes and original voice packages for released Star Rail editions."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import re
import struct
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .game_tools import _atomic_file, download
from .hoyo_dialogue import voice_namespace
from .sophon_assets import CHANNELS

ROUTE_INDEX = 'https://raw.githubusercontent.com/PutraZC/HSR-Data/main/hotfix.json'
ROUTES = {'design': ('ExResourceUrl', 'design_data'), 'asb': ('AssetBundleUrl', 'asb'),
          'base': ('ExAssetBundleUrl', 'asb'), 'lua': ('LuaUrl', 'lua')}
INDEXES = {'design': ('design', 'M_DesignV'), 'asb': ('asb', 'Block/M_AsbV'),
           'lua': ('lua', 'M_LuaV'), 'audio': ('asb', 'AudioBlock/M_AudioV')}


def check(condition):
    if not condition:
        raise ValueError('Inconsistent or unsupported released Star Rail hotfix metadata.')


def roots(build):
    hotfix = build['hotfix']
    major, minor, _ = build['version'].split('.')
    host = CHANNELS[build['channel']][3]
    result = {}
    for key, (_, folder) in ROUTES.items():
        path = hotfix['routes'][key]
        check(re.fullmatch(rf'{folder}/V{major}\.{minor}Live/output_[1-9][0-9]*_[0-9a-f]+_[0-9a-f]+', path))
        result[key] = 'https://' + host + '/' + path + '/client/Windows/'
    return result


def marker(raw):
    check(len(raw) == 66 and raw[:8] == b'SRMI\x00\x03\x00\x01' and struct.unpack_from('<I', raw, 8)[0] == len(raw))
    rev, *words = struct.unpack_from('<5I', raw, 24)
    size, = struct.unpack_from('<Q', raw, 44)
    check(rev > 0 and 0 < size <= 128 * 1024**2)
    return rev, ''.join(f'{word:08x}' for word in words), size


def _discover(build, listing):
    region = {'starrail-global': 'OS', 'starrail-cn': 'CN'}[build['channel']]
    routes = listing[region + build['version']]
    hotfix = {'routes': {key: routes[field] for key, (field, _) in ROUTES.items()}}
    urls = roots(build | {'hotfix': hotfix})
    def read(item):
        key, (route, stem) = item
        rev, md5, size = marker(download(urls[route] + stem + '.bytes', limit=66))
        check(rev == int(hotfix['routes'][route].split('/output_')[1].split('_')[0]))
        return key, (rev, md5, size)
    with ThreadPoolExecutor(max_workers=4) as pool:
        hotfix['indexes'] = dict(pool.map(read, INDEXES.items()))
    return hotfix


def discover(build):
    listing = json.loads(download(ROUTE_INDEX, limit=512 * 1024))['HotfixData']
    hotfix = _discover(build, listing)
    if build['channel'] == 'starrail-cn':
        global_fix = _discover(build | {'channel': 'starrail-global'}, listing)
        # The catalog is an extraction of Global. Reuse it in the mainland edition
        # only when the regional publisher indexes contain the same bytes.
        check(global_fix['indexes'] == hotfix['indexes'])
        hotfix['global_audio_routes'] = global_fix['routes']
    return build | {'hotfix': hotfix}


def index(directory, build, name):
    route, stem = INDEXES[name]
    _, digest, size = build['hotfix']['indexes'][name]
    check(re.fullmatch('[0-9a-f]{32}', digest) and 0 < size <= 128 * 1024**2)
    path = directory / 'starrail-indexes' / digest
    if path.is_file() and path.stat().st_size == size:
        data = path.read_bytes()
        if hashlib.md5(data).hexdigest() == digest:
            return data
    url = roots(build)[route] + stem.replace('M_', '') + '_' + digest + '.bytes'
    data = download(url, limit=size)
    check(len(data) == size and hashlib.md5(data).hexdigest() == digest)
    _atomic_file(path, data)
    return data


@dataclass(frozen=True)
class AudioFile:
    name: str
    size: int
    digest: str
    url: str
    alternate: str = ''

    def read(self, directory, start, length):
        check(0 < length <= 64 * 1024**2 and 0 <= start <= self.size - length)
        end = start + length - 1
        path = directory / 'starrail-ranges' / self.digest / f'{start}-{end}'
        if path.is_file() and path.stat().st_size == length + 32:
            raw = path.read_bytes()
            if hashlib.sha256(raw[32:]).digest() == raw[:32]:
                return raw[32:]
        urls = (self.url, self.alternate or self.url)
        for attempt, url in enumerate(urls):
            request = Request(url, headers={'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'})
            try:
                with urlopen(request, timeout=45) as response:
                    check(response.status == 206 and response.geturl() == url
                          and response.headers.get('Content-Range') == f'bytes {start}-{end}/{self.size}'
                          and response.headers.get('ETag', '').lower() == '"' + self.digest + '"')
                    data = response.read(length + 1)
                break
            except HTTPError as error:
                if attempt or error.code not in ((404, 410, 502, 503, 504) if self.alternate else (502, 503, 504)):
                    raise
            except (TimeoutError, ConnectionError, URLError) as error:
                cause = error.reason if isinstance(error, URLError) else error
                if attempt or not isinstance(cause, (TimeoutError, ConnectionError)):
                    raise
        check(len(data) == length)
        if length == self.size:
            check(hashlib.md5(data).hexdigest() == self.digest)
        raw = hashlib.sha256(data).digest() + data
        try:
            _atomic_file(path, raw)
        except PermissionError:
            if not path.is_file() or path.read_bytes() != raw:
                raise
        return data


def audio_roots(build):
    urls = roots(build)
    equivalent = build['hotfix'].get('global_audio_routes')
    if build['channel'] == 'starrail-cn' and equivalent:
        twin = build | {'channel': 'starrail-global', 'hotfix': {'routes': equivalent}}
        return urls, roots(twin)
    return urls, {}


def audio_file(urls, relative, patch, name, size, digest):
    local, alternate = urls
    route = 'asb' if patch else 'base'
    path = 'AudioBlock/' + quote(relative, safe='/()')
    return AudioFile(name, size, digest, local[route] + path, alternate[route] + path if alternate else '')


def files(directory, build, locale, regular):
    lang = voice_namespace('starrail', locale) + '/'
    known = {}
    for path, asset in regular.items():
        known.setdefault(path.split('/Windows/', 1)[1], []).append((path, asset))
    urls = audio_roots(build)
    result = {}
    found = set()
    for line in index(directory, build, 'audio').splitlines():
        item = json.loads(line)
        relative = item['Path']
        if not relative.startswith(lang) or not relative.endswith('.pck'):
            continue
        filename = relative[len(lang):]
        size, digest, patch = item['Size'], item['Md5'], item['Patch']
        check(re.fullmatch(r'[A-Za-z0-9_.-]+\.pck', filename) and '..' not in filename
              and type(size) is int and 0 < size and re.fullmatch('[0-9a-f]{32}', digest)
              and type(patch) is bool and relative not in found)
        found.add(relative)
        matches = [(p, a) for p, a in known.get(relative, ()) if (a.size, a.digest) == (size, digest)]
        if matches:
            result.update(matches)
        else:
            path = 'StarRail_Data/Persistent/Audio/AudioPackage/Windows/' + relative
            result[path] = audio_file(urls, relative, patch, path, size, digest)
    check(result)
    return result
