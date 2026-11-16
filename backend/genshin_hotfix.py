"""Released Genshin hotfix discovery and original publisher audio, without login.

Public launcher metadata supplies changing bootstrap keys. The regional publisher
HTTPS response and its declared index hashes establish resource coherence; this
does not claim independent RSA signature authentication of the dispatch response.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from . import hoyo_dispatch_metadata as bootstrap
from .game_tools import _atomic_file
from .hoyo_dialogue import voice_namespace
from .sophon_assets import _fields


HOSTS = {'global': 'autopatchhk.yuanshen.com', 'cn': 'autopatchcn.yuanshen.com'}
DISPATCH = {'global': 'oseurodispatch.yuanshen.com', 'cn': 'cngfdispatch.yuanshen.com'}
PREFIX = {'global': 'OSRELWin', 'cn': 'CNRELWin'}
UA = {'User-Agent': 'UnityPlayer/2017.4.30f1 (UnityWebRequest/1.0, libcurl/7.51.0-DEV)',
      'X-Unity-Version': '2017.4.30f1'}
INDEXES = {'res': ('res', 'res_versions_external'), 'base': ('res', 'base_revision'),
           'design': ('design', 'AssetBundles/data_versions'),
           'silence': ('silence', 'AssetBundles/data_versions')}


def check(condition):
    if not condition:
        raise ValueError('Inconsistent or unsupported released Genshin hotfix metadata.')


def fields(raw):
    check(isinstance(raw, bytes) and len(raw) <= 1024 * 1024)
    result = {}
    for key, value in _fields(raw):
        check(key not in result)
        result[key] = value
    return result


def _key(raw, width):
    check(type(width) is int and 128 <= width <= 512 and isinstance(raw, bytes)
          and len(raw) <= bootstrap.LIMIT and b'<!' not in raw)
    root = ET.fromstring(raw)
    check(root.tag == 'RSAKeyValue')
    numbers = [int.from_bytes(base64.b64decode(root.findtext(name), validate=True), 'big')
               for name in ('Modulus', 'Exponent', 'D', 'P', 'Q')]
    key = RSA.construct(numbers)
    check(key.has_private() and key.size_in_bytes() == width)
    return key


def _query(config, decoder, region, version):
    template = decoder.text(config['GameDispatchURL'])
    seed = decoder.text(config['ProtoDispatchKey'])
    check(re.fullmatch('[0-9a-f]{16,128}', seed) and len(template) <= 2048)
    url = template.replace('{0}', DISPATCH[region].split('.')[0]).replace('{1}', PREFIX[region] + version).replace('{2}', seed)
    parsed = urlsplit(url)
    check(parsed.scheme == 'https' and parsed.netloc == DISPATCH[region]
          and parsed.path == '/query_cur_region' and not parsed.fragment and '{' not in url and '}' not in url)
    pairs = parse_qsl(parsed.query, strict_parsing=True)
    query = dict(pairs)
    check(len(pairs) == len(query) and set(query) == {'version', 'lang', 'platform', 'binary', 'time',
          'channel_id', 'sub_channel_id', 'account_type', 'dispatchSeed', 'key_id'}
          and query['version'] == PREFIX[region] + version and query['platform'] == '3' and query['binary'] == '1'
          and all(re.fullmatch('[0-9]{1,10}', query[k]) for k in query if k not in ('version', 'dispatchSeed')))
    check(type(config['ChannelID']) is int and type(config['SubChannelID']) is int
          and 0 <= config['ChannelID'] < 1000 and 0 <= config['SubChannelID'] < 1000)
    # Public resource discovery never supplies an account, UID, login token or aid.
    query.update(channel_id=str(config['ChannelID']), sub_channel_id=str(config['SubChannelID']), account_type='0')
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _dispatch(region, version):
    config, decoder = bootstrap.load('genshin', region)
    url = _query(config, decoder, region, version)
    response = json.loads(bootstrap.fetch(url, limit=1024 * 1024, headers=UA))
    check(isinstance(response, dict) and isinstance(response.get('content'), str)
          and isinstance(response.get('sign'), str))
    encrypted = base64.b64decode(response['content'], validate=True)
    key = _key(decoder.decode(config['DispatcherKey']), config['DispatcherKeyBitLength'])
    width = key.size_in_bytes()
    check(encrypted and len(encrypted) % width == 0)
    cipher = PKCS1_v1_5.new(key)
    chunks = [cipher.decrypt(encrypted[i:i + width], None) for i in range(0, len(encrypted), width)]
    check(all(isinstance(part, bytes) and part for part in chunks))
    root = fields(b''.join(chunks))
    check(root.get(1, 0) == 0 and isinstance(root.get(3), bytes))
    return fields(root[3])


def _version(build):
    region = {'genshin-global': 'global', 'genshin-cn': 'cn'}[build['channel']]
    version = build['version']
    check(isinstance(version, str) and re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', version))
    return region, version, '.'.join(version.split('.')[:2]) + '_live'


def roots(build):
    region, _, branch = _version(build)
    hotfix = build['hotfix']
    result = {}
    for name in ('res', 'design', 'silence', 'audio'):
        revision, suffix = hotfix['revisions'][name]
        check(type(revision) is int and revision > 0 and isinstance(suffix, str)
              and re.fullmatch('[0-9a-f]{1,64}', suffix))
        folder = 'client_game_res' if name in ('res', 'audio') else 'client_design_data'
        ending = '/client_silence/General/' if name == 'silence' else '/client/General/' if name == 'design' else '/client/StandaloneWindows64/'
        result[name] = f'https://{HOSTS[region]}/{folder}/{branch}/output_{revision}_{suffix}' + ending
    return result


def _descriptors(raw, names):
    check(isinstance(raw, bytes) and len(raw) <= 128 * 1024)
    rows = [json.loads(line) for line in raw.splitlines()]
    check(rows and all(isinstance(row, dict) and isinstance(row.get('remoteName'), str) for row in rows))
    selected = {}
    for name in names:
        matches = [row for row in rows if row['remoteName'] == name]
        check(len(matches) == 1)
        item, = matches
        digest, size = item['md5'], item['fileSize']
        check(isinstance(digest, str) and re.fullmatch('[0-9a-f]{32}', digest)
              and type(size) is int and 0 < size <= 8 * 1024 * 1024)
        selected[name] = (digest, size)
    return selected


def _index(build, name):
    route, suffix = INDEXES[name]
    digest, size = build['hotfix']['indexes'][name]
    check(re.fullmatch('[0-9a-f]{32}', digest) and type(size) is int and 0 < size <= 8 * 1024 * 1024)
    raw = bootstrap.fetch(roots(build)[route] + suffix, limit=size)
    check(len(raw) == size and hashlib.md5(raw).hexdigest() == digest)
    return raw


def discover(build):
    region, version, branch = _version(build)
    response = _dispatch(region, version)
    check(response[36] == ('hk4e_global' if region == 'global' else 'hk4e_cn').encode())
    for key, folder in ((8, 'client_game_res'), (9, 'client_design_data')):
        check(response[key] == f'https://{HOSTS[region]}/{folder}/{branch}'.encode())
    res = fields(response[22])
    check(res[6] == branch.encode())
    revisions = {'res': (res[1], res[5].decode('ascii')),
                 'design': (response[14], response[26].decode('ascii')),
                 'silence': (response[18], response[27].decode('ascii'))}
    indexes = _descriptors(res[3], ('res_versions_external', 'base_revision'))
    design = _descriptors(response[19], ('data_versions',))['data_versions']
    silence = _descriptors(response[20], ('data_versions',))['data_versions']
    hotfix = {'revisions': revisions | {'audio': revisions['res']},
              'indexes': {'res': indexes['res_versions_external'], 'base': indexes['base_revision'],
                          'design': design, 'silence': silence}}
    candidate = build | {'hotfix': hotfix}
    # Verify every declared body before accepting a new resource generation.
    with ThreadPoolExecutor(max_workers=4) as pool:
        bodies = dict(pool.map(lambda name: (name, _index(candidate, name)), INDEXES))
    base = bodies['base'].decode('ascii')
    match = re.fullmatch(r'([1-9][0-9]*) ([0-9a-f]{1,64})', base)
    check(match is not None)
    hotfix['revisions']['audio'] = (int(match[1]), match[2])
    return candidate


def index(directory, build, name):
    digest, size = build['hotfix']['indexes'][name]
    check(re.fullmatch('[0-9a-f]{32}', digest) and type(size) is int and 0 < size <= 8 * 1024 * 1024)
    path = directory / 'genshin-indexes' / digest
    if path.is_file() and path.stat().st_size == size:
        raw = path.read_bytes()
        if hashlib.md5(raw).hexdigest() == digest:
            return raw
    raw = _index(build, name)
    _atomic_file(path, raw)
    return raw


BLOCK = 1024 * 1024


@lru_cache(maxsize=16)
def _package_blocks(path, size, digest, _mtime):
    check(path.stat().st_size == size)
    md5, blocks = hashlib.md5(), []
    with path.open('rb') as stream:
        while raw := stream.read(BLOCK):
            md5.update(raw)
            blocks.append(hashlib.sha256(raw).digest())
    check(md5.hexdigest() == digest)
    return tuple(blocks)


def _download_package(asset, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as temporary:
        staged = path.parent / temporary / 'download'
        request = Request(asset.url, headers={'Accept-Encoding': 'identity', **UA})
        digest, count = hashlib.md5(), 0
        with urlopen(request, timeout=45) as response, staged.open('wb') as stream:
            check(response.status == 200 and response.geturl() == asset.url)
            length = response.headers.get('Content-Length')
            check(length is None or length.isdecimal() and int(length) == asset.size)
            while raw := response.read(min(BLOCK, asset.size + 1 - count)):
                count += len(raw)
                check(count <= asset.size)
                digest.update(raw)
                stream.write(raw)
        check(count == asset.size and digest.hexdigest() == asset.digest)
        try:
            staged.replace(path)
        except PermissionError:
            # Another worker can have installed the same immutable package.
            _package_blocks(path, asset.size, asset.digest, path.stat().st_mtime_ns)


@dataclass(frozen=True)
class AudioFile:
    name: str
    size: int
    digest: str
    url: str

    def read(self, directory, start, length):
        check(type(start) is int and type(length) is int and 0 < length <= 64 * 1024**2
              and 0 <= start <= self.size - length)
        check(re.fullmatch('[0-9a-f]{32}', self.digest) and type(self.size) is int and 0 < self.size <= 8 * 1024**3)
        path = directory / 'genshin-packages' / self.digest
        try:
            blocks = _package_blocks(path, self.size, self.digest, path.stat().st_mtime_ns)
        except (FileNotFoundError, ValueError):
            _download_package(self, path)
            blocks = _package_blocks(path, self.size, self.digest, path.stat().st_mtime_ns)
        result = bytearray()
        with path.open('rb') as stream:
            for block in range(start // BLOCK, (start + length - 1) // BLOCK + 1):
                stream.seek(block * BLOCK)
                raw = stream.read(min(BLOCK, self.size - block * BLOCK))
                check(hashlib.sha256(raw).digest() == blocks[block])
                result.extend(raw[max(0, start - block * BLOCK):start + length - block * BLOCK])
        check(len(result) == length)
        return bytes(result)


def files(directory, build, locale, regular):
    region, _, _ = _version(build)
    data = 'GenshinImpact_Data' if region == 'global' else 'YuanShen_Data'
    folder = voice_namespace('genshin', locale) + '/'
    known = {}
    for name, asset in regular.items():
        known.setdefault(name.split('/AudioAssets/', 1)[1], []).append((name, asset))
    urls = roots(build)
    result, found = {}, set()
    for line in index(directory, build, 'res').splitlines():
        item = json.loads(line)
        relative = item['remoteName']
        if not relative.startswith(folder) or not relative.endswith('.pck'):
            continue
        filename = relative[len(folder):]
        size, digest, patch = item['fileSize'], item['md5'], item.get('isPatch', False)
        check(re.fullmatch(r'[A-Za-z0-9_.-]+\.pck', filename) and '..' not in filename
              and type(size) is int and 0 < size and re.fullmatch('[0-9a-f]{32}', digest)
              and type(patch) is bool and relative not in found)
        found.add(relative)
        matches = [(name, asset) for name, asset in known.get(relative, ()) if (asset.size, asset.digest) == (size, digest)]
        if matches:
            result.update(matches)
        else:
            name = data + '/Persistent/AudioAssets/' + relative
            root = urls['res' if patch else 'audio']
            result[name] = AudioFile(name, size, digest, root + 'AudioAssets/' + relative)
    check(result)
    return result


def movie_files(directory, build, regular):
    urls = roots(build)
    known = {}
    for name, asset in regular.items():
        known.setdefault(name.rsplit('/', 1)[1], []).append(asset)
    result = {}
    for line in index(directory, build, 'res').splitlines():
        item = json.loads(line)
        relative = item['remoteName']
        if not relative.startswith('StandaloneWindows64/') or not relative.endswith('.usm'):
            continue
        filename = relative.split('/', 1)[1]
        size, digest, patch = item['fileSize'], item['md5'], item.get('isPatch', False)
        check(re.fullmatch(r'[A-Za-z0-9_.-]+\.usm', filename) and '..' not in filename
              and filename.casefold() not in {name.casefold() + '.usm' for name in result}
              and type(size) is int and size > 0 and re.fullmatch('[0-9a-f]{32}', digest)
              and type(patch) is bool)
        matches = [asset for asset in known.get(filename, ()) if (asset.size, asset.digest) == (size, digest)]
        check(len(matches) <= 1)
        root = urls['res' if patch else 'audio']
        result[filename[:-4]] = matches[0] if matches else AudioFile(filename, size, digest, root + 'VideoAssets/' + relative)
    check(result)
    return result
