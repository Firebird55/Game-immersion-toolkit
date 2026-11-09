"""Read coherent NTE Windows updater inventories and their content-addressed file locations."""
import base64
import hashlib
import json
import tempfile
import urllib.request
import io
import re
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile

from .game_tools import download

LIMIT = 16 * 1024**2
HOSTS = {'nte-global': 'ntecdn1.perfectworld.com', 'nte-cn': 'yhcdn1.wmupd.com'}
GLOBAL_FORMAT = ('https://raw.githubusercontent.com/Tobiichi-Origuchi/nte_patcher/'
                 '1135247b3a21ac72304b8bd9f5aa548994f7a8ef/tests/test_integration.rs',
                 '995f3bb64304c468c025b71bdaf5f463b324261450f0e07b5bd51b0349b5cfd8')
CN_FORMAT = ('https://raw.githubusercontent.com/kuaichu/game-cdn-archive/'
             '58fb1715ce2f891e9873741c66700817d9552cda/scripts/nte_downloader.py',
             '012e6728bbfc3f11c4ab4f9ec0ffd3504ac194d16b6e684acf9ab25810dcb9ef')


def _reference(source):
    raw = download(source[0], limit=64 * 1024)
    if hashlib.sha256(raw).hexdigest() != source[1]:
        raise ValueError('Changed NTE updater format reference.')
    return raw


@lru_cache(maxsize=2)
def _parameters(region):
    reference = _reference(GLOBAL_FORMAT)
    key = re.search(rb'let key = b"([^"]{16})";', reference)[1]
    iv = re.search(rb'let iv = b"([^"]{16})";', reference)[1]
    if region == 'nte-cn':
        reference = _reference(CN_FORMAT)
        key = re.search(rb'decode_patcherxml0\(raw, "([^"]{1,16})"\)', reference)[1].ljust(16, b'0')
    return key, iv


def _xml(raw, region, digest):
    if raw.startswith(b'PatcherXML0\0'):
        from Crypto.Cipher import AES
        if len(raw) < 32 or len(raw) % 16:
            raise ValueError('Invalid NTE resource-list envelope.')
        size = struct.unpack_from('<I', raw, 12)[0]
        if not 0 < size <= LIMIT:
            raise ValueError('Invalid NTE resource-list size.')
        key, iv = _parameters(region)
        payload = AES.new(key, AES.MODE_CBC, iv).decrypt(raw[16:])
        inflater = zlib.decompressobj()
        raw = inflater.decompress(payload, size + 1)
        if not inflater.eof or len(raw) != size:
            raise ValueError('Incomplete NTE resource list.')
    if hashlib.md5(raw).hexdigest() != digest:
        raise ValueError('NTE publisher resource-list checksum mismatch.')
    return ElementTree.fromstring(raw)


@dataclass(frozen=True)
class File:
    size: int
    digest: str
    object_size: int
    object_digest: str
    offset: int


def _length(value):
    if not value or not re.fullmatch(r'[0-9]{1,16}', value):
        raise ValueError('Invalid NTE resource size or offset.')
    return int(value)


def _digest(value):
    if not value or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('Invalid NTE file identity.')
    return value


def files(archive, region, version, sections, checksum):
    """Include both independent CDN files and files embedded in patcher packages."""
    with ZipFile(io.BytesIO(archive)) as packed:
        entries = [entry for entry in packed.infolist() if entry.filename == 'ResList.bin']
        if len(entries) != 1 or not 0 < entries[0].file_size <= LIMIT:
            raise ValueError('Invalid NTE resource list.')
        raw = packed.read(entries[0])
    root = _xml(raw, region, checksum)
    if root.tag != 'ResList' or root.get('version') != version or root.get('tag') != 'baseTag':
        raise ValueError('NTE manifest and launcher versions differ.')
    nodes = [root]
    seen = set()
    for section in root.findall('BaseVersion'):
        tag = section.get('tag')
        nested = section.findall('ResList')
        if (tag in seen or not tag or tag not in sections or section.get('version') != sections[tag]
                or len(nested) != 1):
            raise ValueError('NTE optional resource section mismatch.')
        seen.add(tag)
        nodes.extend(nested)
    if seen != sections.keys() - {'baseTag'}:
        raise ValueError('Missing NTE optional resource section.')

    result = {}

    def add(name, file):
        if (not name or '\\' in name or not name.startswith('Client/') or name != str(PurePosixPath(name))
                or '..' in PurePosixPath(name).parts or name in result or file.offset + file.size > file.object_size):
            raise ValueError('Invalid or duplicate NTE resource path or range.')
        result[name] = file

    for listing in nodes:
        for row in listing.findall('Res'):
            size, digest = _length(row.get('filesize')), _digest(row.get('md5'))
            add(row.get('filename'), File(size, digest, size, digest, 0))
        for package in listing.findall('Package/Pak'):
            size, digest = _length(package.get('filesize')), _digest(package.get('md5'))
            for row in package.findall('Entry'):
                add(row.get('name'), File(_length(row.get('size')), _digest(row.get('md5')),
                                          size, digest, _length(row.get('offset'))))
    if not result:
        raise ValueError('Empty NTE resource inventory.')
    return result, [len(raw), hashlib.sha256(raw).hexdigest()]


def discover(region):
    host = HOSTS[region]
    branch = 'publish_PC'
    visited = set()
    while branch not in visited and len(visited) < 12:
        visited.add(branch)
        root = 'https://' + host + '/clientRes/' + branch + '/Version/Windows'
        cfg = ElementTree.fromstring(download(root + '/config.xml', limit=256 * 1024))
        next_branch = cfg.findtext('ResConfig')
        if next_branch:
            next_branch = json.loads(base64.b64decode(next_branch, validate=True)).get('branchName')
        if not next_branch or next_branch == branch:
            version = cfg.findtext('ResVersion', '')
            if not re.fullmatch(r'\d+\.\d+\.\d+', version):
                raise ValueError('Invalid NTE release version.')
            raw = download(root + '/version/' + version + '/ResList.bin.zip', limit=LIMIT)
            sections = {}
            previous = {}
            for item in cfg.findall('BaseVerson/Res'):
                tag, revision, size = item.get('Tag', ''), item.get('version', ''), item.get('ResSize', '')
                if (not re.fullmatch(r'[a-zA-Z0-9_]+', tag) or not re.fullmatch(r'\d+\.\d+\.\d+', revision)
                        or not size.isdecimal() or tag in sections):
                    raise ValueError('Invalid or duplicate NTE resource section.')
                sections[tag] = revision
                previous[tag] = [int(size), revision]
            items, previous['ResList.bin'] = files(raw, region, version, sections, cfg.findtext('Extra/listHash'))
            return branch, version, items, previous
        if not re.fullmatch(r'PC_[0-9]+', next_branch):
            raise ValueError('Unsupported NTE release branch.')
        branch = next_branch
    raise ValueError('NTE region returned an incomplete release chain.')


def save_file(region, branch, item, destination, *, verify=None):
    """Read only the manifest-declared byte range and publish the verified file atomically."""
    name = f'{item.object_digest}.{item.object_size}'
    url = f'https://{HOSTS[region]}/clientRes/{branch}/Res/{name[0]}/{name}'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        staged = Path(tmp) / 'download'
        checksum = hashlib.md5()
        with staged.open('wb') as out:
            position = 0
            while position < item.size:
                length = min(4 * 1024**2, item.size - position)
                start = item.offset + position
                end = start + length - 1
                request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}',
                                                               'Accept-Encoding': 'identity'})
                with urllib.request.urlopen(request, timeout=60) as response:
                    if (response.status != 206 or response.geturl() != url or
                            response.headers.get('Content-Range') != f'bytes {start}-{end}/{item.object_size}'):
                        raise ValueError('NTE CDN returned an unexpected file range.')
                    data = response.read(length + 1)
                if len(data) != length:
                    raise ValueError('Incomplete NTE resource.')
                out.write(data)
                checksum.update(data)
                position += length
        if checksum.hexdigest() != item.digest:
            raise ValueError('NTE resource checksum mismatch.')
        if verify is not None:
            verify()
        staged.replace(destination)
