"""Read Kuro release metadata with explicit parameters and host cryptography."""

import base64
import binascii
import gzip
import hashlib
import io
import json
import re
from urllib.parse import urlsplit

from .preparation_errors import PreparationFailure


KURO = ('https://prod-alicdn-gamestarter.kurogame.com/launcher/game/'
        '50004_P7xcUZnEr1AXIGON25E6KjpOgTlVrg6e/G153/official/index.json')

CHANNELS = {
    'global': (KURO, 'G153/50004', 'net'),
    'cn': ('https://prod-volcdn-gamestarter.kurogame.xyz/launcher/game/'
           '10003_oLNgHF1CESo51DGHN2odtp40e3oI1HfZ/G152/official/index.json', 'G152/10003', 'com'),
}

FORMAT_URL = ('https://raw.githubusercontent.com/Yumeo0/mornye-tools/4591ef24949688ec9835bf910a204d6bbc4b339c/'
              'src-tauri/crates/game-client/src/discovery.rs')
FORMAT_SHA = 'da9918d1a4ef286add40d78d40b433346e8e4790ca2bfcde6c392dd24b75c7fd'
DUBS = ('en', 'ja', 'ko', 'zh')
LIMIT = 16 * 1024**2
VERSION = r'[0-9]+\.[0-9]+\.[0-9]+'
BOOTSTRAP = 'Client/Content/Paks/pakchunk0-WindowsNoEditor.pak'


def _check(valid):
    if not valid:
        raise ValueError('Unsupported or inconsistent Kuro publisher metadata.')


def decode_manifest(raw, parameters, crypto):
    """Request ENTRY parameters only for a valid encrypted response envelope."""
    try:
        text = raw.decode('utf-8-sig')
        if text.lstrip().startswith('{'):
            return json.loads(text)
        cipher = base64.b64decode(text.strip(), validate=True)
        if not cipher or len(cipher) % 16:
            raise ValueError('Invalid encrypted ENTRY framing')
    except (UnicodeError, ValueError, binascii.Error) as error:
        raise PreparationFailure('publisher_metadata_invalid',
            'The Wuthering release-metadata response is invalid. Existing prepared text and audio are unchanged.',
            previous_snapshot_retained=True) from error

    key, iv = parameters()
    try:
        decoded = crypto.block_cipher('AES', 'CBC', key, cipher, iv=iv)
        padding = decoded[-1] if len(decoded) == len(cipher) else 0
        if not 1 <= padding <= 16 or decoded[-padding:] != bytes([padding]) * padding:
            raise ValueError('Invalid ENTRY padding')
        result = json.loads(decoded[:-padding])
        if not isinstance(result, dict):
            raise ValueError('Invalid ENTRY JSON object')
        return result
    except (UnicodeError, ValueError) as error:
        raise PreparationFailure('publisher_format_key_unresolved',
            'The verified ENTRY input cannot read the current Wuthering release metadata. The current manifest key/IV source must be verified before updating; existing text and audio are unchanged.',
            previous_snapshot_retained=True) from error


def launcher_bytes(data):
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as packed:
            data = packed.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError('Kuro launcher index exceeds its size limit.')
    return data



def launcher(region, read, read_manifest, *, excluded=()):
    url, channel_path, domain = CHANNELS[region]
    root = json.loads(read(url))
    # The live tiered launcher publishes common separately from graphics packs.
    # Pre-downloads and experiment branches can advertise an unreleased version.
    config = root['resourcePacks']['common']
    path, version = config['indexFile'], config['version']
    _check(isinstance(config['indexFileMd5'], str) and re.fullmatch('[0-9a-f]{32}', config['indexFileMd5']))
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not re.fullmatch(
            r'launcher/game/' + channel_path + '/' + re.escape(version) + r'/[A-Za-z0-9]+/common/indexFile\.json', path):
        raise ValueError('Unrecognized regional Kuro launcher index.')
    network_error = None
    for candidate in root['cdnList']:
        cdn = urlsplit(candidate['url'])
        if (cdn.netloc not in excluded and cdn.scheme == 'https' and re.fullmatch(r'[a-z0-9-]+\.aki-game\.' + domain, cdn.netloc)
                and cdn.path in ('', '/') and not cdn.query and not cdn.fragment):
            url = 'https://' + cdn.netloc + '/' + path
            try:
                data = read_manifest(url, config['indexFileMd5'])
            except OSError as error:
                network_error = error
                continue
            break
    else:
        if network_error is not None:
            raise network_error
        raise ValueError('No recognized Kuro publisher CDN.')
    files = {}
    for row in json.loads(data)['resource']:
        name = row['dest']
        if name.startswith('Client/Content/Paks/') and name.lower().endswith('.pak'):
            if (not re.fullmatch(r'Client/Content/Paks/[A-Za-z0-9_.-]+\.pak', name) or name in files or
                    not re.fullmatch('[0-9a-f]{32}', row['md5']) or type(row['size']) is not int or row['size'] <= 0):
                raise ValueError('Invalid or duplicate Kuro package.')
            files[name] = [row['size'], row['md5']]
    if not files:
        raise ValueError('The Kuro launcher has no base game PAKs.')
    folder = config['baseUrl'].rstrip('/')
    if folder != path.removesuffix('/common/indexFile.json') + '/zip':
        raise ValueError('Unexpected Kuro download directory.')
    return version, 'https://' + cdn.netloc + '/' + folder, files



def parse_entry_source(raw, digest):
    if not isinstance(raw, bytes) or len(raw) > 40 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
        raise PreparationFailure('publisher_entry_source_auth_failed',
            'The Wuthering ENTRY input did not match its required source checksum. It was rejected; existing prepared text and audio are unchanged.',
            previous_snapshot_retained=True)
    try:
        values = []
        for name in (b'KEY', b'IV'):
            matches = re.findall(b'const ENTRY_' + name + b': &str = "([^"\r\n]+)";', raw)
            if len(matches) != 1:
                raise ValueError('Expected one declaration')
            values.append(base64.b64decode(matches[0], validate=True))
        if len(values[0]) not in (16, 24, 32) or len(values[1]) != 16:
            raise ValueError('Unsupported ENTRY input size')
    except (ValueError, binascii.Error) as error:
        raise PreparationFailure('publisher_entry_source_invalid',
            'The verified Wuthering ENTRY source does not provide the required key and IV. Existing prepared text and audio are unchanged.',
            previous_snapshot_retained=True) from error
    return tuple(values)


def _size(value):
    if isinstance(value, str) and re.fullmatch(r'__kr_long__[0-9]{1,16}', value):
        value = int(value[11:])
    _check(type(value) is int and 0 < value < 2**55)
    return value


def _file(name, size, digest):
    _check(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]+\.(?:pak|sig)', name))
    _check(isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{40}', digest))
    return [_size(size), digest.lower()]


def resource_inventory(root, release, channels, read_manifest):
    products, files, versions = {}, {}, {}

    def record(channel, revision, index):
        _check(index['Version'] == revision and index['Pv'] == 1)
        versions[channel] = revision
        for layer, folder in (('BaseFiles', release), ('PatchFiles', revision)):
            for row in index['DiffPatch'][layer]:
                name = row['Name']
                info = _file(name, row['Size'], row['Hash'])
                key = '/'.join((channel, layer, name))
                _check(key not in files)
                files[key] = info
                products[key] = (root + folder + '/' + name, *info)

    names = {'resource': 'ManifestResource', **{dub: 'ManifestLang_' + dub for dub in DUBS}}
    for channel in sorted(channels):
        if channel.startswith('Option_Pack_'):
            _check(re.fullmatch(r'Option_Pack_[A-Za-z0-9_]+', channel))
            names[channel] = 'Manifest' + channel
    for channel, manifest in names.items():
        current = channels[channel]
        revision = current['Version']
        _check(re.fullmatch(VERSION, revision) and current['Name'] == channel)
        index = read_manifest(root + revision + '/' + manifest + '.txt', current['IndexSha1'][revision])
        record(channel, revision, index)
    if 'ManifestAggregated' in channels:
        current = channels['ManifestAggregated']
        rev = current['Version']
        _check(re.fullmatch(VERSION, rev) and current['Name'] == 'ManifestAggregated')
        grouped = read_manifest(root + rev + '/ManifestAggregated.txt', current['IndexSha1'][rev])
        _check(isinstance(grouped, dict) and grouped)
        for name, index in grouped.items():
            _check(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_]+', name)
                      and name not in versions and re.fullmatch(VERSION, index['Version']))
            record(name, index['Version'], index)
    return versions, files, products



def platform_config(config, launcher_version, region, read, decode):
    domain = CHANNELS[region][2]
    _check(config is not None)
    lines = config.decode('utf-8-sig').splitlines()
    routes = [line.removeprefix('UrlPath=') for line in lines if line.startswith('UrlPath=')]
    prefixes = [line.removeprefix('InternalPrefix=') for line in lines if line.startswith('InternalPrefix=')]
    _check(len(routes) == len(prefixes) == 1 and re.fullmatch(r'[A-Za-z0-9]{16,80}', routes[0]))
    network_error = None
    for prefix in prefixes[0].split(';'):
        if re.fullmatch(r'https://aki-config-[a-z0-9-]+\.aki-game2?\.' + domain, prefix):
            try:
                entry_url = f'{prefix}/{routes[0]}/index.json'
                entry_data = read(entry_url)
                source = decode(entry_data)['default']
                break
            except OSError as error:
                network_error = error
                continue
    else:
        if network_error is not None:
            raise network_error
        raise ValueError('No available regional Kuro bootstrap.')
    res = source['ResUri']
    _check(re.fullmatch(r'[A-Za-z0-9]{16,80}', res))
    network_error = None
    for cdn in source['CdnUrl']:
        url = urlsplit(cdn['url'])
        if (url.scheme == 'https' and url.path == '/prod/client/' and not url.query and not url.fragment and
                re.fullmatch(r'[a-z0-9-]+\.aki-game\.' + domain, url.netloc) and int(cdn['weight']) > 0):
            root = cdn['url'] + res + '/Windows/'
            try:
                config_data = read(root + 'config.json')
                break
            except OSError as error:
                network_error = error
                continue
    else:
        if network_error is not None:
            raise network_error
        raise ValueError('No available regional Kuro resource CDN.')
    platform = decode(config_data)
    release = platform['PackageVersion']
    _check(re.fullmatch(VERSION, release) and release.split('.')[:2] == launcher_version.split('.')[:2])
    return source, cdn, root, release, platform, {entry_url: entry_data, root + 'config.json': config_data}
