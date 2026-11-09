"""Resolve the active Global Wuthering Waves story, movie and dub manifests."""
import base64
from functools import lru_cache
import gzip
import io
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from . import wuthering_release_pak as pak
from .game_tools import _atomic_file, download
from .wuthering_assets import PUBLIC_METADATA_URL

KURO = 'https://prod-alicdn-gamestarter.kurogame.com/launcher/game/G153/50004_obOHXFrFanqsaIEOmuKroCcbZkQRBC7c/index.json'

FORMAT_URL = ('https://raw.githubusercontent.com/Yumeo0/mornye-tools/4591ef24949688ec9835bf910a204d6bbc4b339c/'
              'src-tauri/crates/game-client/src/discovery.rs')
FORMAT_SHA = 'da9918d1a4ef286add40d78d40b433346e8e4790ca2bfcde6c392dd24b75c7fd'
DUBS = ('en', 'ja', 'ko', 'zh')
TIERS = ('sd', 'hd', 'uhd')
LIMIT = 16 * 1024**2
VERSION = r'[0-9]+\.[0-9]+\.[0-9]+'


def kuro_bytes(url):
    data = download(url, limit=LIMIT)
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as packed:
            data = packed.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError('Kuro launcher index exceeds its size limit.')
    return data


def launcher():
    root = json.loads(kuro_bytes(KURO))['default']
    config = root['config']
    path, version = config['indexFile'], config['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not re.fullmatch(
            r'launcher/game/G153/50004/' + re.escape(version) + r'/[A-Za-z0-9]+/resource/50004/'
            + re.escape(version) + r'/indexFile\.json', path):
        raise ValueError('Unrecognized Global Kuro launcher index.')
    for candidate in root['cdnList']:
        cdn = urlsplit(candidate['url'])
        if (cdn.scheme == 'https' and re.fullmatch(r'[a-z0-9-]+\.aki-game\.net', cdn.netloc)
                and cdn.path in ('', '/') and not cdn.query and not cdn.fragment):
            url = 'https://' + cdn.netloc + '/' + path
            data = kuro_bytes(url)
            if hashlib.md5(data).hexdigest() != config['indexFileMd5']:
                raise ValueError('Kuro launcher manifest checksum mismatch.')
            break
    else:
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
    folder = root['resourcesBasePath'].rstrip('/')
    if folder != path.split('/resource/')[0] + '/zip':
        raise ValueError('Unexpected Kuro download directory.')
    return version, 'https://' + cdn.netloc + '/' + folder, files


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


def _descriptor_path(tools, stamp):
    pak.check(isinstance(stamp, str) and re.fullmatch(r'wuwa-[0-9a-f]{64}', stamp))
    return Path(tools) / 'wuwa-publisher' / stamp / 'release.json'


def _snapshot(tools, stamp):
    raw = _descriptor_path(tools, stamp).read_bytes()
    pak.check('wuwa-' + hashlib.sha256(raw).hexdigest() == stamp)
    snapshot = json.loads(raw)
    pak.check(snapshot['schema'] == 1)
    return snapshot


def snapshot_available(tools, stamp):
    try:
        _snapshot(tools, stamp)
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


@lru_cache(maxsize=2)
def _current(tools, period):
    version, root, base = launcher()
    versions, _, products, params, pointers = discover(tools, version, root, base, videos=False)
    descriptor = {'schema': 1, 'base': base, 'root': root, 'products': products,
                  'launcher': version, 'versions': versions}
    raw = json.dumps(descriptor, sort_keys=True, separators=(',', ':')).encode()
    stamp = 'wuwa-' + hashlib.sha256(raw).hexdigest()
    path = _descriptor_path(tools, stamp)
    if not snapshot_available(tools, stamp):
        _atomic_file(path, raw)
    return stamp, descriptor, params, pointers


def fingerprint(tools):
    return _current(Path(tools), int(time.monotonic() // 60))[0]


def _packages(snapshot, channel, layer):
    if layer == 'launcher':
        return [(snapshot['root'] + '/' + name, *info) for name, info in snapshot['base'].items()]
    return [tuple(info) for name, info in snapshot['products'].items()
            if name.startswith(f'{channel}/{layer}/') and name.endswith('.pak')]


def _locations(tools, packages, params, *, wanted=(), prefix=None):
    def scan(info):
        package = pak.Package(*info, tools, params)
        return info, package.locations(wanted=wanted, prefix=prefix)

    found = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for info, locations in pool.map(scan, packages):
            for name, position in locations.items():
                if name in found:
                    raise ValueError('Multiple Kuro packages in the same layer claim the same path.')
                # A tombstone in an overlay masks an older original.
                pak.check(position >= 0 or position == -2147483648)
                found[name] = (info, position)
    return found


@lru_cache(maxsize=3)
def _voice_locations(tools, stamp, code):
    from .wuthering_assets import EXTERNAL_ROOT
    snapshot = _snapshot(tools, stamp)
    params = _voice_parameters(stamp)
    result = {}
    for layer in ('BaseFiles', 'PatchFiles'):
        result.update(_locations(tools, _packages(snapshot, code, layer), params, prefix=EXTERNAL_ROOT + code + '_'))
    return {name: value for name, value in result.items() if value[1] >= 0 and name.endswith('.wem')}


@lru_cache(maxsize=3)
def _voice_parameters(stamp):
    return _archive_parameters()


@lru_cache(maxsize=4)
def _voice_package(tools, stamp, info):
    return pak.Package(*info, tools, _voice_parameters(stamp))


def _table(tools, info, position, name, params):
    # Reuse a table across independent game/dub revisions only when its
    # containing package, encoded entry and full path still agree.
    entry = hashlib.sha256(f'{info[2]}/{position}/{name}'.encode()).digest()
    path = tools / 'wuwa-publisher' / 'tables' / entry.hex()
    if path.is_file() and path.stat().st_size <= pak.MEMBER_LIMIT + 32:
        cached = path.read_bytes()
        data = cached[32:]
        if data.startswith(b'SQLite format 3\0') and hashlib.sha256(entry + data).digest() == cached[:32]:
            return data
    data = pak.Package(*info, tools, params).extract(position)
    pak.check(data.startswith(b'SQLite format 3\0'))
    _atomic_file(path, hashlib.sha256(entry + data).digest() + data)
    return data


def _read_tables(tools, snapshot, params, locales, destination):
    from . import wuthering_assets as assets
    root = 'Client/Content/Aki/ConfigDB/'
    names = {'db_plot_audio.db', *assets.NARRATIVE_TABLES}
    for locale in locales:
        code = assets.TEXT_LOCALES[locale]
        names.update((code + '/lang_multi_text.db', code + '/lang_multi_text_1sthalf.db'))
    remaining = {root + name for name in names}
    selected = {}
    for layer in ('PatchFiles', 'BaseFiles', 'launcher'):
        if not remaining:
            break
        matches = _locations(tools, _packages(snapshot, 'resource', layer), params, wanted=remaining)
        selected.update(matches)
        remaining.difference_update(matches)
    def read(item):
        name, (info, position) = item
        if position < 0:
            return
        data = _table(tools, info, position, name, params)
        _atomic_file(destination / name[len(root):], data)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(read, selected.items()))
    pak.check(all((destination / name).is_file() for name in
                  ('db_plot_audio.db', *(table for table in assets.NARRATIVE_TABLES if table != assets.FLOATING_SUBTITLES))))


def build_language(tools, source_locale, targets, progress=lambda _message: None):
    from . import wuthering_assets as assets
    from .languages import resolve_locale
    tools = Path(tools)
    if source_locale not in assets.SUPPORTED_LOCALES:
        raise ValueError('Unsupported Wuthering study/audio locale.')
    stamp, snapshot, params, pointers = _current(tools, int(time.monotonic() // 60))
    resolved = {target: resolve_locale(target, assets.TEXT_LOCALES) for target in targets}
    selected = {locale for locale in resolved.values() if locale}
    progress('Reading the publisher’s current Wuthering story and translation tables')
    with tempfile.TemporaryDirectory(dir=_descriptor_path(tools, stamp).parent) as folder:
        path = Path(folder)
        _read_tables(tools, snapshot, params, {source_locale, *selected}, path)
        pak.check((path / assets.TEXT_LOCALES[source_locale] / 'lang_multi_text.db').is_file())
        selected = {locale for locale in selected if (path / assets.TEXT_LOCALES[locale] / 'lang_multi_text.db').is_file()}
        progress('Matching authored voice paths against the selected publisher dub')
        files = _voice_locations(tools, stamp, assets.VOICE_LOCALES[source_locale][0])
        records = assets.build_language_records(path, files, source_locale, selected)
    pak.check(records)
    for record in records:
        if record['audio']:
            record['audio']['publisher'] = stamp
    verify_pointers(pointers)
    if launcher() != (snapshot['launcher'], snapshot['root'], snapshot['base']):
        raise ValueError('Kuro updated the launcher during preparation. Retry.')
    mapped = sum(bool(row['audio']) for row in records)
    available = {locale for row in records for locale in row['texts']}
    missing = [target for target, locale in resolved.items() if locale not in available]
    return {'format': 2, 'game': 'wuwa', 'install': None, 'source_mode': 'publisher', 'fingerprint': stamp,
            'source_locale': source_locale, 'records': records, 'missing_translation_locales': missing,
            'coverage_warnings': assets.COVERAGE_WARNINGS,
            'message': f'{len(records):,} official {source_locale} lines; {mapped:,} original voices'}


def extract(tools, audio, locale=None):
    from . import wuthering_assets as assets
    from .languages import audio_locale
    depot = assets._validate_voice(audio)
    pak.check(locale is None or audio_locale(locale) == audio.get('locale'))
    code = assets.VOICE_LOCALES[audio['locale']][0]
    stamp, tools = audio['publisher'], Path(tools)
    directory = _descriptor_path(tools, stamp).parent / 'clips'
    _snapshot(tools, stamp)
    key = hashlib.sha256(depot.encode()).hexdigest()
    binding = hashlib.sha256((stamp + '/' + depot).encode()).digest()
    path = directory / key
    if path.is_file() and path.stat().st_size <= pak.MEMBER_LIMIT + 32:
        cached = path.read_bytes()
        if len(cached) > 32 and hashlib.sha256(binding + cached[32:]).digest() == cached[:32]:
            return cached[32:]
    reference = _voice_locations(tools, stamp, code).get(depot)
    if reference is None:
        raise ValueError('The released dub does not contain this exact original voice.')
    info, position = reference
    data = _voice_package(tools, stamp, info).extract(position)
    _validate_wem(data)
    _atomic_file(path, hashlib.sha256(binding + data).digest() + data)
    return data


def _validate_wem(data):
    pak.check(data[:4] == b'RIFF' and data[8:12] == b'WAVE' and int.from_bytes(data[4:8], 'little') + 8 == len(data))


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
            _validate_wem(data)
            return data
    raise ValueError('The released dub does not contain this exact external voice path.')
