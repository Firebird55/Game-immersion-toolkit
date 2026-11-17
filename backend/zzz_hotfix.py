"""Released ZZZ updater inventories, separate from the launcher base packages."""
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
import base64
import hashlib
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import re
import struct
from tempfile import TemporaryDirectory
import threading
from urllib.error import URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure
from .xxhash64 import xxhash64, xxhash64_stream

BASE = 'ZenlessZoneZero_Data/StreamingAssets/'
PERSISTENT = 'ZenlessZoneZero_Data/Persistent/'
MAX_FILE = 256 * 1024**2
MAX_INDEX = 32 * 1024**2
MAX_STREAM_FILE = 8 * 1024**3
VERIFY_BLOCK_SIZE = 1024**2
INDEXES = {'design': ('design', 'data_version'), 'catalog': ('resource', 'res_version'),
           'audio': ('resource', 'audio_version'), 'base': ('resource', 'base_revision'),
           'silence': ('silence', 'silence_version')}
EDITIONS = {
    'zzz-global': {'region': 'global', 'prefix': 'OSPRODWin', 'area': 'oversea',
                   'host': 'autopatchos.zenlesszonezero.com', 'dispatch': 'os', 'domain': 'zenlesszonezero.com'},
    'zzz-cn': {'region': 'cn', 'prefix': 'CNPRODWin', 'area': 'cn',
               'host': 'autopatchcn.juequling.com', 'dispatch': 'cn', 'domain': 'juequling.com'},
}


def check(condition):
    if not condition:
        raise ValueError('Inconsistent or unsupported released ZZZ update metadata.')


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('The ZZZ update endpoint redirected unexpectedly.')


def _request(url, headers, maximum):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity', **headers})
    with build_opener(_NoRedirect()).open(request, timeout=30) as response:
        check(response.status == 200 and response.geturl() == url)
        raw = response.read(maximum + 1)
        length = response.headers.get('Content-Length')
        check(len(raw) <= maximum and (length is None or length.isdecimal() and int(length) == len(raw)))
        return raw


def _query(template, *values):
    check(isinstance(template, str) and len(template) <= 1024 and template.startswith('?'))
    for index, value in enumerate(values):
        template = template.replace('{' + str(index) + '}', value)
    check('{' not in template and '}' not in template and '#' not in template)
    pairs = parse_qsl(template[1:], keep_blank_values=True, strict_parsing=True)
    headers = dict(pairs)
    reserved = {'host', 'authorization', 'proxy_authorization', 'cookie', 'content_length',
                'transfer_encoding', 'connection', 'user_agent', 'accept_encoding'}
    check(0 < len(pairs) <= 16 and len(pairs) == len(headers) and 'version' in headers
          and all(re.fullmatch('[a-z][a-z0-9_]{0,47}', name) and name not in reserved for name in headers)
          and all(re.fullmatch('[A-Za-z0-9_.-]{1,128}', value) for value in headers.values()))
    return template, headers


def _settings(region='global'):
    from .hoyo_dispatch_metadata import load
    check(region in ('global', 'cn'))
    config, decoder = load('zzz', region)
    names = ('GameDispatchChannelName', 'GameDispatchURLTemplate', 'GameGatewayURLTemplate',
             'GameDispatchDefaultName', 'ProtoDispatchKey')
    values = {name: decoder.text(config[name]) for name in names}
    endpoints = config['GameDispatchArrayURL']
    check(isinstance(endpoints, list) and 0 < len(endpoints) <= 8)
    values['endpoints'] = [decoder.text(value) for value in endpoints]
    # The public launcher metadata contains a second wrapped data object for
    # the gateway decoder and its authored platform/area. Never persist it.
    packed = decoder.decode(decoder.text(config['DispatcherKey']))
    check(16 <= len(packed) <= 16 * 1024)
    identity, area = struct.unpack_from('<hh', packed, len(packed) - 4)
    check(0 < identity <= 128 and 0 < area <= 128)
    width = (identity + area) * 2
    start = len(packed) - 4 - width
    check(start >= 32 and width <= start)
    tail = bytearray(packed[start:-4])
    for index in range(width):
        offset = 0x10 | (start % (width - index))
        check(offset < start)
        tail[index] ^= packed[offset]
    check(tail[:identity * 2].decode('utf-16le') == 'StandaloneWindows64'
          and tail[identity * 2:].decode('utf-16le') == {'global': 'oversea', 'cn': 'cn'}[region])
    check(packed[0] == 0x30)
    size = packed[1]
    count = size & 127
    if size < 128:
        end = 2 + size
    else:
        check(0 < count <= 4 and 2 + count <= start and packed[2] != 0)
        end = 2 + count + int.from_bytes(packed[2:2 + count], 'big')
    check(end == start)
    from Crypto.PublicKey import RSA
    key = RSA.import_key(packed[:end])
    check(key.has_private() and 1024 <= key.size_in_bits() <= 4096)
    return values, key


def _endpoint(url, *, gateway=False, channel='zzz-global'):
    edition = EDITIONS[channel]
    parsed = urlsplit(url)
    domain = re.escape(edition['domain'])
    host = (rf'prod-gf-[a-z]{{2,8}}\.{domain}' if gateway else
            rf'globaldp-prod-{edition["dispatch"]}0[1-9]\.{domain}')
    check(parsed.scheme == 'https' and re.fullmatch(host, parsed.netloc)
          and parsed.path == ('/query_gateway' if gateway else '/query_dispatch')
          and not parsed.query and not parsed.fragment)
    return url


def _cdn(url, kind, version, channel='zzz-global'):
    edition = EDITIONS[channel]
    parsed = urlsplit(url)
    directory = 'game_res' if kind == 'resource' else 'design_data'
    client = 'client_silence' if kind == 'silence' else 'client'
    branch = '.'.join(version.split('.')[:2]) + '_live'
    pattern = rf'/{directory}/{re.escape(branch)}/output_([1-9][0-9]*)_[0-9a-f]{{6,64}}/{client}/'
    match = re.fullmatch(pattern, parsed.path)
    check(parsed.scheme == 'https' and parsed.netloc == edition['host']
          and match and not parsed.query and not parsed.fragment)
    return int(match[1]), url + 'StandaloneWindows64/' + edition['area'] + '/'


def _spec(row):
    check(isinstance(row, dict) and {'fileName', 'fileSize', 'fileMD5'} <= set(row))
    name, size, digest = row['fileName'], row['fileSize'], row['fileMD5']
    if isinstance(size, str) and size.isdecimal():
        size = int(size)
    check(isinstance(name, str) and re.fullmatch('[A-Za-z0-9_-]{1,128}', name)
          and type(size) is int and 0 < size <= MAX_INDEX
          and isinstance(digest, str) and digest.isdecimal() and 0 <= int(digest) < 1 << 64)
    return {'name': name, 'size': size, 'hash': digest}


def discover(build):
    check(build['channel'] in EDITIONS and re.fullmatch(r'[1-9][0-9]*\.[0-9]+\.[0-9]+', build['version']))
    edition = EDITIONS[build['channel']]
    values, key = _settings(edition['region'])
    prefix = edition['prefix']
    check(values['GameDispatchChannelName'] == prefix)
    query, headers = _query(values['GameDispatchURLTemplate'], prefix, build['version'])
    check(headers['version'] == prefix + build['version'])
    endpoints = [_endpoint(value, channel=build['channel']) for value in values['endpoints']]
    for number, endpoint in enumerate(endpoints):
        try:
            listing = json.loads(_request(endpoint + query, headers, 128 * 1024))
            break
        except (URLError, TimeoutError, ConnectionError):
            if number == len(endpoints) - 1:
                raise
    regions = listing.get('region_list')
    check(listing.get('retcode') == 0 and isinstance(regions, list) and 0 < len(regions) <= 16)
    matches = [row for row in regions if row.get('name') == values['GameDispatchDefaultName']]
    check(len(matches) == 1 and matches[0].get('retcode') == 0)
    endpoint = _endpoint(matches[0]['dispatch_url'], gateway=True, channel=build['channel'])
    query, headers = _query(values['GameGatewayURLTemplate'], prefix, build['version'], values['ProtoDispatchKey'])
    check(headers['version'] == prefix + build['version'])
    envelope = json.loads(_request(endpoint + query, headers, 1024 * 1024))
    encrypted = base64.b64decode(envelope['content'], validate=True)
    width = key.size_in_bytes()
    check(0 < len(encrypted) <= 512 * 1024 and len(encrypted) % width == 0)
    from Crypto.Cipher import PKCS1_v1_5
    cipher = PKCS1_v1_5.new(key)
    chunks = [cipher.decrypt(encrypted[pos:pos + width], b'') for pos in range(0, len(encrypted), width)]
    check(all(chunks))
    reply = json.loads(b''.join(chunks))
    check(reply.get('retcode') == 0)
    # Discard unrelated gateway/account configuration, including client secrets.
    config = reply['cdn_conf_ext']
    roots, indexes, revisions = {}, {}, {}
    for kind, field, revision in (('design', 'design_data', 'data_revision'),
                                   ('resource', 'game_res', 'res_revision'),
                                   ('silence', 'silence_data', 'silence_revision')):
        source = config[field]
        _, roots[kind] = _cdn(source['base_url'], kind, build['version'], build['channel'])
        revisions[kind] = str(source[revision])
        check(revisions[kind].isdecimal())
        rows = json.loads(source['md5_files'])
        check(isinstance(rows, list) and 0 < len(rows) <= 64)
        specs = [_spec(row) for row in rows]
        check(len({row['name'] for row in specs}) == len(specs))
        for name, (root, filename) in INDEXES.items():
            if root == kind:
                found = [row for row in specs if row['name'] == filename]
                check(len(found) == 1)
                indexes[name] = found[0]
    check(str(config['game_res']['audio_revision']).isdecimal())
    hotfix = {'roots': roots, 'indexes': indexes, 'revisions': revisions,
              'audio_revision': str(config['game_res']['audio_revision'])}
    raw = _index_bytes(build | {'hotfix': hotfix}, 'base')
    base = raw.decode('ascii')
    check(re.fullmatch('[1-9][0-9]*_[0-9a-f]{6,64}', base))
    return build | {'hotfix': hotfix | {'base_revision': base}}


def _index_bytes(build, name):
    hotfix = build['hotfix']
    root, filename = INDEXES[name]
    suffix = 'StandaloneWindows64/' + EDITIONS[build['channel']]['area'] + '/'
    _, url = _cdn(hotfix['roots'][root].removesuffix(suffix), root, build['version'], build['channel'])
    spec = hotfix['indexes'][name]
    check(spec['name'] == filename)
    raw = _request(url + filename, {}, spec['size'])
    check(len(raw) == spec['size'] and xxhash64(raw) == int(spec['hash']))
    return raw


def index(directory, build, name):
    spec = build['hotfix']['indexes'][name]
    path = Path(directory) / 'zzz-indexes' / (name + '-' + spec['hash'])
    if path.is_file() and path.stat().st_size == spec['size']:
        raw = path.read_bytes()
        if xxhash64(raw) == int(spec['hash']):
            return raw
    raw = _index_bytes(build, name)
    _atomic_file(path, raw)
    return raw


def rows(directory, build, name):
    result = json.loads(index(directory, build, name))
    check(isinstance(result, dict) and result.get('remoteParentDir') == '')
    entries = result['files']
    check(isinstance(entries, list) and 0 < len(entries) <= 100_000)
    for name in ('basePackages', 'baseOnlyPackages', 'baseOnlyTitles'):
        packages = result.get(name)
        check(isinstance(packages, list) and len(packages) <= 4096
              and all(type(value) is int and 0 <= value < 1 << 31 for value in packages))
    seen = set()
    for row in entries:
        path, size, digest = row['remoteName'], row['fileSize'], row['md5']
        check(isinstance(path, str) and re.fullmatch('[A-Za-z0-9_./-]{1,512}', path)
              and '..' not in path.split('/') and not path.startswith('/') and path not in seen
              and type(size) is int and 0 < size <= MAX_STREAM_FILE and type(row['isPatch']) is bool
              and isinstance(digest, str) and digest.isdecimal() and 0 <= int(digest) < 1 << 64)
        seen.add(path)
    return entries


def _stamp(stat):
    # Windows can report different cached birth times through stat and fstat
    # after a rename. Integrity comes from the full hash and checked blocks.
    return stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino


class PublisherDownloadInterrupted(PreparationFailure):
    def __init__(self):
        super().__init__('metadata_download_interrupted',
            'The original game-data download was interrupted. Check the connection; '
            'preparation will retry automatically, or retry now in Games & Languages.')


def _blocks(handle, size, *, download=False):
    """Read exact verification blocks with bounded reads, including a final EOF."""
    def read(length):
        try:
            return handle.read(length)
        except (IncompleteRead, ConnectionError, TimeoutError) as error:
            if download:
                raise PublisherDownloadInterrupted() from error
            raise

    for offset in range(0, size, VERIFY_BLOCK_SIZE):
        wanted = min(VERIFY_BLOCK_SIZE, size - offset)
        block = bytearray()
        while len(block) < wanted:
            part = read(wanted - len(block))
            if download and isinstance(part, bytes) and not part:
                raise PublisherDownloadInterrupted()
            check(isinstance(part, bytes) and 0 < len(part) <= wanted - len(block))
            block.extend(part)
        yield bytes(block)
    check(read(1) == b'')


def _check_file(path, size, digest, stamp=None):
    blocks = []
    with Path(path).open('rb') as handle:
        before = _stamp(os.fstat(handle.fileno()))
        check(before[0] == size and (stamp is None or before == stamp))
        def parts():
            for block in _blocks(handle, size):
                blocks.append(hashlib.sha256(block).digest())
                yield block
        check(xxhash64_stream(parts()) == digest and _stamp(os.fstat(handle.fileno())) == before)
    return before, tuple(blocks)


class _VerifiedFiles:
    """Only verified block digests stay in memory, never whole update packages."""
    def __init__(self):
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def remember(self, path, size, digest, stamp, blocks):
        key = path, size, digest, stamp, VERIFY_BLOCK_SIZE
        with self._lock:
            self._entries[key] = blocks
            self._entries.move_to_end(key)
            while len(self._entries) > 4:
                self._entries.popitem(last=False)
        return blocks

    def __call__(self, path, size, digest, stamp):
        key = path, size, digest, stamp, VERIFY_BLOCK_SIZE
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key]
        verified, blocks = _check_file(path, size, digest, stamp)
        return self.remember(path, size, digest, verified, blocks)

    def cache_clear(self):
        with self._lock:
            self._entries.clear()


_verified_file = _VerifiedFiles()


def _read_range(path, size, start, length, stamp, blocks):
    result = bytearray()
    end = start + length
    with path.open('rb') as handle:
        check(_stamp(os.fstat(handle.fileno())) == stamp)
        position = start // VERIFY_BLOCK_SIZE * VERIFY_BLOCK_SIZE
        handle.seek(position)
        while position < end:
            block = handle.read(min(VERIFY_BLOCK_SIZE, size - position))
            check(len(block) == min(VERIFY_BLOCK_SIZE, size - position)
                  and hashlib.sha256(block).digest() == blocks[position // VERIFY_BLOCK_SIZE])
            result.extend(block[max(0, start - position):min(len(block), end - position)])
            position += len(block)
        check(len(result) == length and _stamp(os.fstat(handle.fileno())) == stamp)
    return bytes(result)


def _stream_response(url, size):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity'})
    response = build_opener(_NoRedirect()).open(request, timeout=30)
    try:
        check(response.status == 200 and response.geturl() == url)
        length = response.headers.get('Content-Length')
        check(length is None or length.isdecimal() and int(length) == size)
    except Exception:
        response.close()
        raise
    return response


def _download_file(path, url, size, digest):
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='zzz-update-', dir=path.parent) as directory:
        staged = Path(directory) / 'download'
        blocks = []
        with _stream_response(url, size) as response, staged.open('xb') as output:
            def parts():
                for block in _blocks(response, size, download=True):
                    check(output.write(block) == len(block))
                    blocks.append(hashlib.sha256(block).digest())
                    yield block
            check(xxhash64_stream(parts()) == digest)
        blocks = tuple(blocks)
        try:
            staged.replace(path)
        except PermissionError as error:
            # Another worker can publish the same immutable object while a
            # Windows reader holds it without delete sharing. Reuse only a
            # complete publisher-hash and block-identical file, never just stat.
            try:
                stamp, existing = _check_file(path, size, digest)
                check(existing == blocks)
            except (OSError, ValueError):
                raise error from None
        else:
            stamp = _stamp(path.stat())
            check(stamp[0] == size)
        _verified_file.remember(str(path), size, digest, stamp, blocks)
    return stamp, blocks


@dataclass(frozen=True)
class File:
    name: str
    size: int
    digest: int
    url: str

    @property
    def chunks(self):
        return tuple((offset, min(8 * 1024**2, self.size - offset)) for offset in range(0, self.size, 8 * 1024**2))

    def read(self, directory, start, length):
        check(0 < self.size <= MAX_STREAM_FILE and 0 < length <= 64 * 1024**2 and 0 <= start <= self.size - length)
        parsed = urlsplit(self.url)
        check(parsed.scheme == 'https' and parsed.netloc in {edition['host'] for edition in EDITIONS.values()}
              and not parsed.query and not parsed.fragment)
        path = Path(directory) / 'zzz-files' / f'{self.digest:016x}-{self.size}'
        if path.is_file() and path.stat().st_size == self.size:
            try:
                stamp = _stamp(path.stat())
                blocks = _verified_file(str(path), self.size, self.digest, stamp)
                return _read_range(path, self.size, start, length, stamp, blocks)
            except ValueError:
                pass
        stamp, blocks = _download_file(path, self.url, self.size, self.digest)
        return _read_range(path, self.size, start, length, stamp, blocks)


def resource(build, row):
    root = ('design' if row['remoteName'].startswith('Blocks/Data/') else
            'silence' if row['remoteName'].startswith('Blocks/Silence/') else 'resource')
    maximum = MAX_STREAM_FILE if row['remoteName'].endswith('.pck') else MAX_FILE
    check(type(row['isPatch']) is bool and 0 < row['fileSize'] <= maximum)
    if not row['isPatch']:
        root = 'resource'
    channel = build['channel']
    suffix = 'StandaloneWindows64/' + EDITIONS[channel]['area'] + '/'
    _, url = _cdn(build['hotfix']['roots'][root].removesuffix(suffix), root, build['version'], channel)
    if not row['isPatch']:
        base = build['hotfix']['base_revision']
        check(re.fullmatch('[1-9][0-9]*_[0-9a-f]{6,64}', base))
        url = re.sub('output_[^/]+', 'output_' + base, url)
    return File((PERSISTENT if row['isPatch'] else BASE) + row['remoteName'],
                row['fileSize'], int(row['md5']), url + row['remoteName'])


def base_matches(directory, build, files):
    revision = build['hotfix']['base_revision'].split('_', 1)[0]
    for name in ('audio_revision', 'data_revision', 'res_revision', 'silence_revision'):
        asset = files[BASE + name]
        check(0 < asset.size <= 32 and asset.read(directory, 0, asset.size).decode('ascii') == revision)


@lru_cache(maxsize=4)
def _verified_base(asset, directory, digest):
    check(0 < asset.size <= MAX_FILE)
    raw = b''.join(asset.read(directory, start, min(64 * 1024**2, asset.size - start))
                   for start in range(0, asset.size, 64 * 1024**2))
    check(len(raw) == asset.size and xxhash64(raw) == digest)
    return raw


@dataclass(frozen=True)
class CheckedBase:
    asset: object
    digest: int

    @property
    def name(self):
        return self.asset.name

    @property
    def size(self):
        return self.asset.size

    @property
    def chunks(self):
        return tuple((offset, min(8 * 1024**2, self.size - offset)) for offset in range(0, self.size, 8 * 1024**2))

    def read(self, directory, start, length):
        check(0 < length <= 64 * 1024**2 and 0 <= start <= self.size - length)
        return _verified_base(self.asset, directory, self.digest)[start:start + length]


def metadata_files(directory, build, base):
    """Use only resources present in the complete selected updater inventories."""
    base_matches(directory, build, base)
    inventories = {name: rows(directory, build, name) for name in ('design', 'catalog')}
    result = {}
    for row in [*inventories['design'], *inventories['catalog']]:
        name = row['remoteName']
        if not re.fullmatch(r'Blocks/(?:Data/)?[0-9]+\.blk', name):
            continue
        key = BASE + name
        check(key not in result)
        if row['isPatch']:
            result[key] = resource(build, row)
        else:
            if key in base:
                check(base[key].size == row['fileSize'])
                result[key] = CheckedBase(base[key], int(row['md5']))
            else:
                # Optional packages can be absent from the launcher's main
                # manifest. The updater explicitly supplies their base root.
                result[key] = resource(build, row)
    return result, inventories


def silence_evidence(directory, build):
    """Check the auxiliary updater payload without assigning it dialogue meaning."""
    inventory = rows(directory, build, 'silence')
    total = 0
    for row in inventory:
        check(re.fullmatch(r'Blocks/Silence/[0-9]+\.blk', row['remoteName']) and row['fileSize'] <= 64 * 1024**2)
        asset = resource(build, row)
        asset.read(directory, 0, asset.size)
        total += asset.size
    return {'verified_payloads': len(inventory), 'bytes': total, 'interpreted_payloads': 0}


def voice_files(directory, build, locale, base):
    from . import sophon_assets as sophon
    from .zzz_assets import VOICE_FOLDERS
    game = sophon.manifest(directory, build['channel'], tuple(build['manifests']['game']), ('revision', '.pck'))
    base_matches(directory, build, game)
    inventory = rows(directory, build, 'audio')
    folder = 'Audio/Windows/Full/'
    result = {}
    for row in inventory:
        name = row['remoteName']
        if not (re.fullmatch(re.escape(folder + VOICE_FOLDERS[locale]) + r'/[A-Za-z0-9_.-]+\.pck', name)
                or re.fullmatch(re.escape(folder) + r'[A-Za-z0-9_.-]+\.pck', name)):
            continue
        if row['isPatch']:
            asset = resource(build, row)
        else:
            key = BASE + name
            asset = base.get(key) or game.get(key)
            if asset is None:
                asset = resource(build, row)
            check(asset.size == row['fileSize'])
        result[asset.name] = asset
    check(result)
    return result
