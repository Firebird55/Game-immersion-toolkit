"""Resolve the active Global Wuthering Waves story, movie and dub manifests."""
import base64
from functools import lru_cache
import hashlib
import json
import re
from urllib.parse import urlsplit

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from . import wuthering_release_pak as pak
from .game_tools import download
from .wuthering_assets import PUBLIC_METADATA_URL

FORMAT_URL = ('https://raw.githubusercontent.com/Yumeo0/mornye-tools/4591ef24949688ec9835bf910a204d6bbc4b339c/'
              'src-tauri/crates/game-client/src/discovery.rs')
FORMAT_SHA = 'da9918d1a4ef286add40d78d40b433346e8e4790ca2bfcde6c392dd24b75c7fd'
DUBS = ('en', 'ja', 'ko', 'zh')
TIERS = ('sd', 'hd', 'uhd')
LIMIT = 16 * 1024**2
VERSION = r'[0-9]+\.[0-9]+\.[0-9]+'


@lru_cache(maxsize=1)
def _format():
    raw = download(FORMAT_URL, limit=40 * 1024)
    pak.check(hashlib.sha256(raw).hexdigest() == FORMAT_SHA)
    return tuple(base64.b64decode(re.search(b'const ENTRY_' + name + b': &str = "([^"]+)";', raw)[1], validate=True)
                 for name in (b'KEY', b'IV'))


def _archive_parameters():
    data = json.loads(download(PUBLIC_METADATA_URL, limit=512 * 1024))
    return tuple(bytes.fromhex(value) for value in dict.fromkeys(re.findall(r'0x([0-9a-fA-F]{64})', json.dumps(data))))


def _json(raw):
    text = raw.decode('utf-8-sig')
    if text.lstrip().startswith('{'):
        return json.loads(text)
    key, iv = _format()
    cipher = base64.b64decode(text.strip(), validate=True)
    return json.loads(unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(cipher), 16))


def _manifest(url, sha):
    pak.check(isinstance(sha, str) and re.fullmatch('[0-9a-fA-F]{40}', sha))
    raw = download(url, limit=LIMIT)
    pak.check(hashlib.sha1(raw).hexdigest() == sha.lower())
    return _json(raw)


def _size(value):
    if isinstance(value, str) and re.fullmatch(r'__kr_long__[0-9]{1,16}', value):
        value = int(value[11:])
    pak.check(type(value) is int and 0 < value < 2**55)
    return value


def _file(name, size, digest):
    pak.check(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]+\.(?:pak|sig)', name))
    pak.check(isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{40}', digest))
    return [_size(size), digest.lower()]


def discover(cache, launcher_version, launcher_root, launcher_files, *, videos=True):
    bootstrap = 'Client/Content/Paks/pakchunk0-WindowsNoEditor.pak'
    size, digest = launcher_files[bootstrap]
    params = _archive_parameters()
    base = pak.Package(launcher_root + '/' + bootstrap, size, digest, cache, params)
    config = base.member('Client/Config/Kuro/KuroPublicConfig.ini')
    pak.check(config is not None)
    lines = config.decode('utf-8-sig').splitlines()
    routes = [line.removeprefix('UrlPath=') for line in lines if line.startswith('UrlPath=')]
    prefixes = [line.removeprefix('InternalPrefix=') for line in lines if line.startswith('InternalPrefix=')]
    pak.check(len(routes) == len(prefixes) == 1 and re.fullmatch(r'[A-Za-z0-9]{16,80}', routes[0]))
    for prefix in prefixes[0].split(';'):
        if re.fullmatch(r'https://aki-config-[a-z0-9-]+\.aki-game2?\.net', prefix):
            try:
                source = _json(download(f'{prefix}/{routes[0]}/index.json', limit=LIMIT))['default']
                break
            except OSError:
                continue
    else:
        raise ValueError('No available Global Kuro bootstrap.')
    res = source['ResUri']
    pak.check(re.fullmatch(r'[A-Za-z0-9]{16,80}', res))
    for cdn in source['CdnUrl']:
        url = urlsplit(cdn['url'])
        if (url.scheme == 'https' and url.path == '/prod/client/' and not url.query and not url.fragment and
                re.fullmatch(r'[a-z0-9-]+\.aki-game\.net', url.netloc) and int(cdn['weight']) > 0):
            root = cdn['url'] + res + '/Windows/'
            try:
                config_data = download(root + 'config.json', limit=LIMIT)
                break
            except OSError:
                continue
    else:
        raise ValueError('No available Global Kuro resource CDN.')
    platform = _json(config_data)
    release = platform['PackageVersion']
    pak.check(re.fullmatch(VERSION, release) and release.split('.')[:2] == launcher_version.split('.')[:2])
    products, files, versions = {}, {}, {}
    for channel in ('resource', *DUBS):
        current = platform['ResVersions'][channel]
        revision = current['Version']
        pak.check(re.fullmatch(VERSION, revision) and current['Name'] == channel)
        name = 'ManifestResource' if channel == 'resource' else 'ManifestLang_' + channel
        index = _manifest(root + revision + '/' + name + '.txt', current['IndexSha1'][revision])
        pak.check(index['Version'] == revision and index['Pv'] == 1)
        versions[channel] = revision
        for layer, folder in (('BaseFiles', release), ('PatchFiles', revision)):
            for row in index['DiffPatch'][layer]:
                name = row['Name']
                info = _file(name, row['Size'], row['Hash'])
                key = '/'.join((channel, layer, name))
                pak.check(key not in files)
                files[key] = info
                products[key] = (root + folder + '/' + name, *info)
    video_pointers = {}
    if videos:
        for tier in TIERS:
            video_url = root + 'VideoConfig_' + tier + '.json'
            pointer = download(video_url, limit=LIMIT)
            video_pointers[video_url] = pointer
            cfg = _json(pointer)
            index = _manifest(root + release + '/Video/VideoManifest_' + tier + '.json', cfg['IndexSha1'])
            for scene, row in index['VideoInfos']['PakMap'].items():
                if scene == '__kr_map__' and row is None:
                    continue
                pak.check(re.fullmatch(r'[0-9]+_[0-9]+', scene))
                for prefix in ('Pak', 'Sig'):
                    name = row[prefix + 'Name']
                    pak.check(name == f'Video_{scene}-{tier.upper()}-WindowsNoEditor.' + prefix.lower())
                    files['Video/' + tier + '/' + name] = _file(name, row[prefix + 'Size'], row[prefix + 'Hash'])
    pointers = {root + 'config.json': config_data, **video_pointers}
    verify_pointers(pointers)
    return versions, files, products, params, pointers


def verify_pointers(pointers):
    if any(download(url, limit=LIMIT) != previous for url, previous in pointers.items()):
        raise ValueError('Kuro updated the active resource manifests. Retry.')



def voice(cache, products, locale, stem, params):
    pak.check(locale in DUBS and re.fullmatch(r'[a-zA-Z0-9_]{1,240}', stem))
    target = f'Client/Content/Aki/WwiseAudio_Generated/WwiseExternalSource/{locale}_{stem}.wem'
    for layer in ('PatchFiles', 'BaseFiles'):
        matches = []
        for key, (url, size, digest) in products.items():
            if key.startswith(f'{locale}/{layer}/') and key.endswith('.pak'):
                data = pak.Package(url, size, digest, cache, params).member(target)
                if data is not None:
                    matches.append(data)
        if matches:
            pak.check(len(matches) == 1)
            data = matches[0]
            pak.check(data[:4] == b'RIFF' and data[8:12] == b'WAVE' and int.from_bytes(data[4:8], 'little') + 8 == len(data))
            return data
    raise ValueError('The released dub does not contain this exact external voice path.')
