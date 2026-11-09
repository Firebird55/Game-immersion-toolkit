"""Discover the active Global Windows resource generation and read its own tables."""
from functools import lru_cache
import hashlib
import json
import re
import time
import urllib.request
from urllib.parse import urlencode

from . import endfield_metadata, endfield_tables, endfield_vfs as vfs
from .game_tools import _atomic_file, download
from .voice_assets import voice_hash

APP = 'YDUTE5gscDZ229CW'
LAUNCHER = 'https://launcher.gryphline.com/api/game/'
LATEST = LAUNCHER + 'get_latest?' + urlencode(dict(appcode=APP, launcher_appcode='TiaytKBUIEdoEwRT',
    channel=6, sub_channel=6, launcher_sub_channel=6, disk_type=0, patch_encrypt=1))
CDN = 'https://beyond.hg-cdn.com/' + APP
TABLE_GROUP = '42A8FCA6'
FILM_MANIFESTS = {'main': 'b4c65b4ec0eb69de6201a179a4d016ae33f30090002855e8af38bfd7685d3017',
                  'initial': '6ba2549df688cfcf394866beccbb6bbc6904aa28158ef1725582c495fadfb888'}


def _check(condition):
    if not condition:
        raise ValueError('The Endfield publisher resources are incomplete or have changed format.')


def _stamp(raw):
    return 'endfield-' + hashlib.sha256(raw).hexdigest()


def _resource_url(url, role):
    _check(role in ('initial', 'main') and re.fullmatch(re.escape(CDN) +
           r'/[0-9]+\.[0-9]+/resource/Windows/' + role + r'/[0-9]+-[0-9]+_[A-Za-z0-9]+/files', url))
    return url


def discover():
    latest = json.loads(download(LATEST, limit=2 * 1024**2))
    version = latest['version']
    _check(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version))
    minor = version.rsplit('.', 1)[0]
    pack = latest['pkg']['packs'][0]['url']
    suffix = re.match(re.escape(CDN + '/' + minor + '/update/6/6/Windows/' + version) +
                      r'_([a-zA-Z0-9]+)/packs/', pack)
    _check(suffix)
    detail = json.loads(download(LAUNCHER + 'get_latest_resources?' + urlencode(dict(
        appcode=APP, game_version=minor, version=version, platform='Windows', rand_str=suffix[1])), limit=2 * 1024**2))
    layers = {}
    for row in detail['resources']:
        role = row['name']
        if role in ('main', 'initial'):
            base = _resource_url(row['path'], role)
            _check(role not in layers and base.startswith(CDN + '/' + minor + '/') and
                   base.rsplit('/', 2)[1].split('_', 1)[0] == row['version'])
            index = download(base + '/index_' + role + '.json', limit=8 * 1024**2)
            _check(len(index) >= 32)
            layers[role] = {'url': base, 'sha256': hashlib.sha256(index).hexdigest(), 'version': row['version']}
    _check(set(layers) == {'main', 'initial'})
    raw = json.dumps({'version': version, 'layers': layers}, sort_keys=True, separators=(',', ':')).encode()
    return _stamp(raw), raw


@lru_cache(maxsize=2)
def _poll(period):
    return discover()[0]


def fingerprint():
    return _poll(int(time.monotonic() // 45))


@lru_cache(maxsize=12)
def descriptor(tools, stamp):
    _check(isinstance(stamp, str) and re.fullmatch('endfield-[0-9a-f]{64}', stamp))
    path = tools / 'endfield-releases' / stamp
    _check(path.stat().st_size <= 8192)
    raw = path.read_bytes()
    _check(_stamp(raw) == stamp)
    return json.loads(raw)


class RemoteChunk:
    """Bound a seekable package view to one manifest-selected HTTPS object."""
    def __init__(self, url, size):
        self.url, self.size, self.pos = url, size, 0

    def seek(self, offset, whence=0):
        _check(whence in (0, 2))
        self.pos = offset + (self.size if whence == 2 else 0)
        _check(0 <= self.pos <= self.size)

    def tell(self):
        return self.pos

    def read(self, length):
        if not length:
            return b''
        _check(0 < length <= vfs.MAX_VOICE and self.pos <= self.size - length)
        end = self.pos + length - 1
        request = urllib.request.Request(self.url, headers={'Range': f'bytes={self.pos}-{end}', 'Accept-Encoding': 'identity'})
        with urllib.request.urlopen(request, timeout=45) as response:
            _check(response.status == 206 and response.geturl() == self.url and
                   response.headers.get('Content-Range') == f'bytes {self.pos}-{end}/{self.size}')
            data = response.read(length + 1)
        _check(len(data) == length)
        self.pos += length
        return data


@lru_cache(maxsize=48)
def group(tools, stamp, block):
    params = endfield_metadata.parameters(tools)
    directory = TABLE_GROUP if block == 18 else params.directories[block]
    role = 'initial' if block == 1 else 'main'
    base = _resource_url(descriptor(tools, stamp)['layers'][role]['url'], role) + '/VFS/' + directory + '/'
    path = tools / 'endfield-releases' / (stamp + '-' + str(block) + '.blc')
    if path.is_file() and path.stat().st_size <= vfs.MAX_INDEX:
        data = path.read_bytes()
        try:
            return base, vfs.parse_index(data, params, block, suffix='.bytes' if block == 18 else '.pck')
        except ValueError:
            pass
    data = download(base + directory + '.blc', limit=vfs.MAX_INDEX)
    rows = vfs.parse_index(data, params, block, suffix='.bytes' if block == 18 else '.pck')
    _atomic_file(path, data)
    return base, rows


def _source(tools, base, file):
    _check(re.fullmatch(r'[0-9A-F]{32}\.chk', file.chunk))
    stream = RemoteChunk(base + file.chunk, file.chunk_size)
    return vfs.PackageSource(stream, file, endfield_metadata.parameters(tools))


def _whole(tools, base, file):
    digest = file.content_hashes[1]
    path = tools / 'endfield-releases' / 'assets' / digest
    _check(re.fullmatch('[0-9a-f]{32}', digest) and 0 < file.size <= vfs.MAX_VOICE)
    if path.is_file() and path.stat().st_size == file.size:
        data = path.read_bytes()
        if hashlib.md5(data).hexdigest() == digest:
            return data
    data = _source(tools, base, file).read(0, file.size)
    _check(hashlib.md5(data).hexdigest() == digest)
    _atomic_file(path, data)
    return data


class Catalog:
    def __init__(self, tools, stamp):
        self.tools, self.stamp = tools, stamp
        self.base, rows = group(tools, stamp, 18)
        self.files = {row.name: row for row in rows}
        _check(len(self.files) == len(rows))
        self.revision = stamp
        self.revision_title = descriptor(tools, stamp)['version']

    def file(self, relative, *, optional=False):
        name = re.fullmatch(r'TableCfg/([A-Za-z0-9_]+)\.json', relative)
        _check(name)
        file = self.files.get('Data/TableCfg/' + name[1] + '.bytes')
        if file is None and optional:
            return {}
        _check(file is not None)
        return endfield_tables.read(_whole(self.tools, self.base, file), name[1])

    def has_verified_clocks(self):
        layers = descriptor(self.tools, self.stamp)['layers']
        return all(layers[role]['sha256'] == digest for role, digest in FILM_MANIFESTS.items())


def prepare(tools):
    stamp, raw = discover()
    _atomic_file(tools / 'endfield-releases' / stamp, raw)
    return Catalog(tools, stamp)


class _StreamPackage(vfs.Package):
    def _bank(self, identity, offset, size):
        # Authored per-line WEMs are external media. Embedded bank media have
        # separate event bindings and do not establish a spoken sentence.
        return []


@lru_cache(maxsize=16)
def inventory(tools, stamp, dub):
    params = endfield_metadata.parameters(tools)
    entries = {}
    for block in (1, vfs.LOCALE_BLOCKS[dub], 21):
        base, rows = group(tools, stamp, block)
        current, duplicate = {}, set()
        for file in rows:
            if block == 21 and file.name.rsplit('/', 1)[-1] not in ('hotfix_' + dub + '.pck', 'hotfix_main.pck'):
                continue
            package = _StreamPackage(_source(tools, base, file), params)
            for entry in package.entries:
                if entry.identity in current:
                    duplicate.add(entry.identity)
                # Each extraction opens an independent range cursor. Capture
                # and mobile export can read different WEMs concurrently.
                current[entry.identity] = base, file, entry
        entries.update(current)
        for identity in duplicate:
            entries.pop(identity, None)
    return entries


def voice_entries(tools, stamp, dub):
    return {f'{key:016x}': {'publisher': stamp, 'file_id': f'{key:016x}'}
            for key in inventory(tools, stamp, dub)}


def media(tools, stamp, dub, identity, digest=None):
    descriptor(tools, stamp)
    _check(dub in vfs.LOCALE_BLOCKS and 0 <= identity < 2**64)
    path = tools / 'endfield-releases' / 'voices' / stamp / dub / f'{identity:016x}.wem'
    receipt = path.with_suffix('.sha256')
    expected = digest
    if expected is None and receipt.is_file() and receipt.stat().st_size == 64:
        expected = receipt.read_bytes().decode('ascii', errors='replace')
    if expected and path.is_file() and 12 <= path.stat().st_size <= vfs.MAX_VOICE:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() == expected:
            return data
    found = inventory(tools, stamp, dub).get(identity)
    _check(found is not None)
    base, file, entry = found
    data = vfs.read_voice(_source(tools, base, file), endfield_metadata.parameters(tools), entry)
    sha = hashlib.sha256(data).hexdigest()
    _check(len(data) == int.from_bytes(data[4:8], 'little') + 8 and (digest is None or sha == digest))
    _atomic_file(path, data)
    _atomic_file(receipt, sha.encode())
    return data


def extract(tools, audio, dub):
    source = audio['source']
    identity = voice_hash(source)
    _check(source.startswith('voice/' + dub + '/') and source.endswith('.wem')
           and f'{identity:016x}' == audio['file_id'])
    return media(tools, audio['publisher'], dub, identity)
