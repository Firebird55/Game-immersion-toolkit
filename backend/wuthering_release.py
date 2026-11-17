"""Resolve the active regional Wuthering Waves story, movie and dub manifests."""
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
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from . import wuthering_release_pak as pak
from .game_tools import _atomic_file, download as download_bytes
from .wuthering_assets import PUBLIC_METADATA_URL

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
TIERS = ('sd', 'hd', 'uhd')
LIMIT = 16 * 1024**2
VERSION = r'[0-9]+\.[0-9]+\.[0-9]+'


def download(url, *, limit):
    return download_bytes(url, limit=limit, opener=pak.open_publisher_url)


class _NoKeyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('The original publisher key endpoint redirected. Retry discovery.')


def _native_key_download(url, *, limit):
    """Keep original key-update requests on their discovered publisher host."""
    def read(context):
        handler = urllib.request.HTTPSHandler(context=context)
        opener = urllib.request.build_opener(_NoKeyRedirect, handler)
        request = urllib.request.Request(url, headers={'User-Agent': 'GameImmersionToolkit/1'})
        with opener.open(request, timeout=90) as response:
            pak.check(response.status == 200 and response.geturl() == url)
            data = response.read(limit + 1)
        pak.check(len(data) <= limit)
        return data
    try:
        return read(pak._publisher_tls())
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        return read(None)  # Separate verified system trust; never disable TLS.


def kuro_bytes(url):
    data = download(url, limit=LIMIT)
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as packed:
            data = packed.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError('Kuro launcher index exceeds its size limit.')
    return data


@lru_cache(maxsize=3)
def _launcher_manifest(url, digest):
    data = kuro_bytes(url)
    if hashlib.md5(data).hexdigest() != digest:
        raise ValueError('Kuro launcher manifest checksum mismatch.')
    return data


def launcher(region='global', *, excluded=()):
    url, channel_path, domain = CHANNELS[region]
    root = json.loads(kuro_bytes(url))
    # The live tiered launcher publishes common separately from graphics packs.
    # Pre-downloads and experiment branches can advertise an unreleased version.
    config = root['resourcePacks']['common']
    path, version = config['indexFile'], config['version']
    pak.check(isinstance(config['indexFileMd5'], str) and re.fullmatch('[0-9a-f]{32}', config['indexFileMd5']))
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
                data = _launcher_manifest(url, config['indexFileMd5'])
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


@lru_cache(maxsize=1)
def _format(tools=None):
    from . import wuthering_metadata as metadata
    raw = metadata.format_source(tools, FORMAT_SHA) if tools is not None else None
    if raw is None:
        raw = download(FORMAT_URL, limit=40 * 1024)
        pak.check(hashlib.sha256(raw).hexdigest() == FORMAT_SHA)
        if tools is not None:
            metadata.remember_format(tools, raw, FORMAT_SHA)
    return tuple(base64.b64decode(re.search(b'const ENTRY_' + name + b': &str = "([^"]+)";', raw)[1], validate=True)
                 for name in (b'KEY', b'IV'))


def _archive_parameters(tools=None, historical=False):
    from . import wuthering_metadata as metadata
    from .preparation_errors import PreparationFailure
    record = metadata._parameter_record(tools) if tools is not None else None
    retained, owners, defaults = record if record is not None else ((), (), ())
    native = {value for _, value in owners}
    # Historical descriptors preserve independently verified legacy origins.
    # Current native descriptors permit only a separately proven default owner.
    excluded = native - set(retained if historical else defaults)
    retained = tuple(value for value in retained if value not in excluded)
    if tools is not None and record is None and not metadata.empty_parameter_cache(tools):
        raise PreparationFailure('game_metadata_unavailable',
            'The protected Wuthering archive parameter cache is invalid. Restore the cache or retry '
            'preparation with valid original inputs; the previous index and recordings are retained.')
    try:
        from . import wuthering_initial_seed
        values = wuthering_initial_seed.parameters(tools, download)
        return tuple(dict.fromkeys((*retained, *(value for value in values if value not in excluded))))
    except (OSError, ValueError, TypeError) as error:
        if retained:
            return retained
        raise PreparationFailure('game_metadata_unavailable',
            'The fixed Wuthering initial seed is unavailable and no package-verified local parameters remain. '
            'Retry when the immutable source is reachable; the previous index and recordings are retained. '
            'Unknown bootstrap/default-key rotations require an original-source resolver, not newer community keys.') from error


def _package(tools, info, params):
    from . import wuthering_metadata as metadata
    native = getattr(params, 'native', None)
    bootstrap = getattr(params, 'bootstrap', None)
    if bootstrap is not None:
        # This independent original producer never borrows a legacy/default
        # envelope, and its output cannot authorize an unrelated nonzero FGuid.
        options = {'verified_default_parameters': (bootstrap.parameter,) if bootstrap.verified else (),
                   'native_parameters': native if native is not None else {},
                   'verified_native_parameters': metadata.native_parameters(tools) if native else ()}
    else:
        options = {'verified_default_parameters': metadata.default_parameters(tools)}
    if native is not None and bootstrap is None:
        options.update(native_parameters=native, verified_native_parameters=metadata.native_parameters(tools))
    package = pak.Package(*info, tools, params, **options)
    parameter = getattr(package, 'verified_parameter', None)
    if parameter is not None:
        native_guid = getattr(package, 'verified_native_guid', None)
        if bootstrap is not None and native_guid is None:
            pak.check(getattr(package, 'verified_default_parameter', False) and parameter == bootstrap.parameter)
            from . import wuthering_native_bootstrap
            # A source's actual bootstrap owner proves its default role. Other
            # packages still validate their original indices, but do not race
            # to publish redundant per-resource bootstrap-owner records.
            if not bootstrap.verified or bootstrap.owner_id is None or wuthering_native_bootstrap._owner(info, bootstrap.region) == bootstrap.owner_id:
                wuthering_native_bootstrap.remember_owner(tools, bootstrap, info)
            remembered = True
        else:
            remembered = metadata.remember_parameter(tools, parameter, native_guid=native_guid,
                                                    default_verified=getattr(package, 'verified_default_parameter', False))
        if native_guid is not None and not remembered:
            from .preparation_errors import PreparationFailure
            raise PreparationFailure('publisher_key_cache_failed',
                'The verified Wuthering publisher-key ownership could not be retained safely. '
                'Check protected toolkit storage, then retry; the previous index and recordings are kept.')
    return package


def _bootstrap_package(tools, info, region):
    from . import wuthering_native_bootstrap as original
    from .preparation_errors import PreparationFailure
    params = original.parameters(tools, info, region)
    try:
        return _package(tools, info, params), params
    except PreparationFailure as error:
        if error.code != 'archive_parameters_missing':
            raise
        # A known original source may serve ordinary new content unchanged.
        # Only a key mismatch asks the current official catalogue for a new
        # producer. Neither path falls back to a community parameter list.
        refreshed = original.parameters(tools, info, region, refresh=True)
        if original.identity(refreshed.bootstrap.source) == original.identity(params.bootstrap.source):
            raise error
        return _package(tools, info, refreshed), refreshed


def _json(raw, tools=None):
    text = raw.decode('utf-8-sig')
    if text.lstrip().startswith('{'):
        return json.loads(text)
    key, iv = _format(tools)
    cipher = base64.b64decode(text.strip(), validate=True)
    return json.loads(unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(cipher), 16))


def _manifest(url, sha, cache=None):
    pak.check(isinstance(sha, str) and re.fullmatch('[0-9a-fA-F]{40}', sha))
    digest = sha.lower()
    path = Path(cache) / 'kuro-manifests' / digest if cache is not None else None
    if path is not None and path.is_file() and path.stat().st_size <= LIMIT:
        raw = path.read_bytes()
        if hashlib.sha1(raw).hexdigest() == digest:
            return _json(raw, cache)
    raw = download(url, limit=LIMIT)
    pak.check(hashlib.sha1(raw).hexdigest() == digest)
    index = _json(raw, cache)
    if path is not None:
        _atomic_file(path, raw)
    return index


def _size(value):
    if isinstance(value, str) and re.fullmatch(r'__kr_long__[0-9]{1,16}', value):
        value = int(value[11:])
    pak.check(type(value) is int and 0 < value < 2**55)
    return value


def _file(name, size, digest):
    pak.check(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]+\.(?:pak|sig)', name))
    pak.check(isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{40}', digest))
    return [_size(size), digest.lower()]


def _resource_inventory(root, release, channels, cache):
    products, files, versions = {}, {}, {}

    def record(channel, revision, index):
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

    names = {'resource': 'ManifestResource', **{dub: 'ManifestLang_' + dub for dub in DUBS}}
    for channel in sorted(channels):
        if channel.startswith('Option_Pack_'):
            pak.check(re.fullmatch(r'Option_Pack_[A-Za-z0-9_]+', channel))
            names[channel] = 'Manifest' + channel
    for channel, manifest in names.items():
        current = channels[channel]
        revision = current['Version']
        pak.check(re.fullmatch(VERSION, revision) and current['Name'] == channel)
        index = _manifest(root + revision + '/' + manifest + '.txt', current['IndexSha1'][revision], cache)
        record(channel, revision, index)
    if 'ManifestAggregated' in channels:
        current = channels['ManifestAggregated']
        rev = current['Version']
        pak.check(re.fullmatch(VERSION, rev) and current['Name'] == 'ManifestAggregated')
        grouped = _manifest(root + rev + '/ManifestAggregated.txt', current['IndexSha1'][rev], cache)
        pak.check(isinstance(grouped, dict) and grouped)
        for name, index in grouped.items():
            pak.check(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_]+', name)
                      and name not in versions and re.fullmatch(VERSION, index['Version']))
            record(name, index['Version'], index)
    return versions, files, products


def discover(cache, launcher_version, launcher_root, launcher_files, *, videos=True, region='global'):
    from . import wuthering_metadata as metadata
    domain = CHANNELS[region][2]
    bootstrap = 'Client/Content/Paks/pakchunk0-WindowsNoEditor.pak'
    size, digest = launcher_files[bootstrap]
    base, params = _bootstrap_package(cache, (launcher_root + '/' + bootstrap, size, digest), region)
    config = base.member('Client/Config/Kuro/KuroPublicConfig.ini')
    pak.check(config is not None)
    lines = config.decode('utf-8-sig').splitlines()
    routes = [line.removeprefix('UrlPath=') for line in lines if line.startswith('UrlPath=')]
    prefixes = [line.removeprefix('InternalPrefix=') for line in lines if line.startswith('InternalPrefix=')]
    pak.check(len(routes) == len(prefixes) == 1 and re.fullmatch(r'[A-Za-z0-9]{16,80}', routes[0]))
    network_error = None
    for prefix in prefixes[0].split(';'):
        if re.fullmatch(r'https://aki-config-[a-z0-9-]+\.aki-game2?\.' + domain, prefix):
            try:
                source = _json(download(f'{prefix}/{routes[0]}/index.json', limit=LIMIT), cache)['default']
                break
            except OSError as error:
                network_error = error
                continue
    else:
        if network_error is not None:
            raise network_error
        raise ValueError('No available regional Kuro bootstrap.')
    res = source['ResUri']
    pak.check(re.fullmatch(r'[A-Za-z0-9]{16,80}', res))
    network_error = None
    for cdn in source['CdnUrl']:
        url = urlsplit(cdn['url'])
        if (url.scheme == 'https' and url.path == '/prod/client/' and not url.query and not url.fragment and
                re.fullmatch(r'[a-z0-9-]+\.aki-game\.' + domain, url.netloc) and int(cdn['weight']) > 0):
            root = cdn['url'] + res + '/Windows/'
            try:
                config_data = download(root + 'config.json', limit=LIMIT)
                break
            except OSError as error:
                network_error = error
                continue
    else:
        if network_error is not None:
            raise network_error
        raise ValueError('No available regional Kuro resource CDN.')
    platform = _json(config_data, cache)
    release = platform['PackageVersion']
    pak.check(re.fullmatch(VERSION, release) and release.split('.')[:2] == launcher_version.split('.')[:2])
    versions, files, products = _resource_inventory(root, release, platform['ResVersions'], cache)
    video_pointers = {}
    if videos:
        for tier in TIERS:
            video_url = root + 'VideoConfig_' + tier + '.json'
            pointer = download(video_url, limit=LIMIT)
            video_pointers[video_url] = pointer
            cfg = _json(pointer, cache)
            index = _manifest(root + release + '/Video/VideoManifest_' + tier + '.json', cfg['IndexSha1'], cache)
            for scene, row in index['VideoInfos']['PakMap'].items():
                if scene == '__kr_map__' and row is None:
                    continue
                pak.check(re.fullmatch(r'[0-9]+_[0-9]+', scene))
                for prefix in ('Pak', 'Sig'):
                    name = row[prefix + 'Name']
                    pak.check(name == f'Video_{scene}-{tier.upper()}-WindowsNoEditor.' + prefix.lower())
                    files['Video/' + tier + '/' + name] = _file(name, row[prefix + 'Size'], row[prefix + 'Hash'])
    pointers = {root + 'config.json': config_data, **video_pointers}
    from . import wuthering_publisher_keys as publisher_keys
    mix = source.get('MixUri')
    pak.check(isinstance(mix, str) and re.fullmatch(r'[A-Za-z0-9]{16,80}', mix))
    params = publisher_keys.current(cache, cdn['url'] + mix + '/Windows/', release, region,
                                    params, _native_key_download, lambda raw: _json(raw, cache), pointers,
                                    verified_defaults=params if getattr(params, 'bootstrap', None) is not None
                                    else metadata.default_parameters(cache))
    verify_pointers(pointers)
    return versions, files, products, params, pointers


def verify_pointers(pointers):
    def current(url):
        if re.search(r'/KeyList(?:_[0-9]+\.[0-9]+\.[0-9]+)?\.json$', url):
            from .wuthering_publisher_keys import KEYLIST_LIMIT
            return _native_key_download(url, limit=KEYLIST_LIMIT)
        return download(url, limit=LIMIT)
    if any(current(url) != previous for url, previous in pointers.items()):
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
def _current(tools, period, region='global'):
    version, root, base = launcher(region)
    excluded = set()
    while True:
        try:
            versions, _, products, params, pointers = discover(tools, version, root, base, videos=False, region=region)
            break
        except OSError as network_error:
            # A mirror may serve its small JSON but time out on the game PAK.
            # Retry only released mirrors independently listed by the same launcher.
            host = urlsplit(root).netloc
            if host in excluded:
                raise
            excluded.add(host)
            if len(excluded) >= 8:
                raise
            try:
                version, root, base = launcher(region, excluded=excluded)
            except (OSError, ValueError):
                raise network_error
    descriptor = {'schema': 1, 'base': base, 'root': root, 'products': products,
                  'launcher': version, 'versions': versions}
    native_sources = getattr(params, 'sources', ())
    bootstrap = getattr(params, 'bootstrap', None)
    if native_sources or bootstrap is not None:
        descriptor['native_key_sources'] = list(native_sources)
    if bootstrap is not None:
        from . import wuthering_native_bootstrap
        descriptor['native_bootstrap'] = wuthering_native_bootstrap.reference(bootstrap.source)
    if region != 'global':
        descriptor['region'] = region
    raw = json.dumps(descriptor, sort_keys=True, separators=(',', ':')).encode()
    stamp = 'wuwa-' + hashlib.sha256(raw).hexdigest()
    path = _descriptor_path(tools, stamp)
    if not snapshot_available(tools, stamp):
        _atomic_file(path, raw)
    return stamp, descriptor, params, pointers


def fingerprint(tools):
    from .publisher_regions import selected_region
    return _current(Path(tools), int(time.monotonic() // 60), selected_region(Path(tools), 'wuwa'))[0]


def _packages(snapshot, channel, layer):
    if layer == 'launcher':
        return [(snapshot['root'] + '/' + name, *info) for name, info in snapshot['base'].items()]
    return [tuple(info) for name, info in snapshot['products'].items()
            if name.startswith(f'{channel}/{layer}/') and name.endswith('.pak')]


def _locations(tools, packages, params, *, wanted=(), prefix=None):
    def scan(info):
        package = _package(tools, info, params)
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
    params = _voice_parameters(stamp, tools)
    result = {}
    for layer in ('BaseFiles', 'PatchFiles'):
        result.update(_locations(tools, _packages(snapshot, code, layer), params, prefix=EXTERNAL_ROOT + code + '_'))
    return {name: value for name, value in result.items() if value[1] >= 0 and name.endswith('.wem')}


@lru_cache(maxsize=3)
def _voice_parameters(stamp, tools=None):
    if tools is None:
        return _archive_parameters()
    return _parameters_for_snapshot(tools, _snapshot(tools, stamp))


def _parameters_for_snapshot(tools, snapshot):
    from . import wuthering_metadata as metadata
    from .preparation_errors import PreparationFailure
    if 'native_bootstrap' in snapshot:
        from . import wuthering_native_bootstrap as original
        bootstrap = 'Client/Content/Paks/pakchunk0-WindowsNoEditor.pak'
        size, digest = snapshot['base'][bootstrap]
        info = snapshot['root'] + '/' + bootstrap, size, digest
        baseline = original.parameters(tools, info, snapshot.get('region', 'global'), retained=snapshot['native_bootstrap'])
        pak.check('native_key_sources' in snapshot)
        if not baseline.bootstrap.verified:
            _package(tools, info, baseline)
        from . import wuthering_publisher_keys as publisher_keys
        return publisher_keys.restore(tools, snapshot['native_key_sources'], snapshot.get('region', 'global'),
                                      baseline, lambda raw: _json(raw, tools), verified_defaults=baseline)
    if 'native_key_sources' not in snapshot:
        return _archive_parameters(tools, True)
    try:
        baseline = _archive_parameters(tools)
    except PreparationFailure as error:
        if (error.code != 'game_metadata_unavailable' or 'native_key_sources' not in snapshot
                or not metadata.empty_parameter_cache(tools)):
            raise
        baseline = ()
    from . import wuthering_publisher_keys as publisher_keys
    return publisher_keys.restore(tools, snapshot['native_key_sources'], snapshot.get('region', 'global'),
                                  baseline, lambda raw: _json(raw, tools),
                                  verified_defaults=metadata.default_parameters(tools))


@lru_cache(maxsize=4)
def _voice_package(tools, stamp, info):
    return _package(tools, info, _voice_parameters(stamp, tools))


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
    data = _package(tools, info, params).extract(position)
    pak.check(data.startswith(b'SQLite format 3\0'))
    _atomic_file(path, hashlib.sha256(entry + data).digest() + data)
    return data


def _read_tables(tools, snapshot, params, locales, destination):
    """Read complete original members and attest exact PlotAudio bytes for lookups."""
    from . import wuthering_tables as tables
    root = 'Client/Content/Aki/ConfigDB/'
    names = tables.required_tables(locales)
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
        if name == root + 'db_plot_audio.db':
            return hashlib.sha256(data).hexdigest()
    with ThreadPoolExecutor(max_workers=3) as pool:
        plot_audio_proofs = [digest for digest in pool.map(read, selected.items()) if digest]
    pak.check(all((destination / name).is_file() for name in
                  ('db_plot_audio.db', *(table for table in tables.NARRATIVE_TABLES if table != tables.FLOATING_SUBTITLES))))
    pak.check(len(plot_audio_proofs) == 1)
    return plot_audio_proofs[0]


def _movie_locations(tools, snapshot, params, code, names):
    if not names:
        return {}
    current = {}
    for layer in ('BaseFiles', 'PatchFiles'):
        current.update(_locations(tools, _packages(snapshot, code, layer), params, wanted=names))
    return {name: ref for name, ref in current.items() if ref[1] >= 0}


def _movie_records(tools, snapshot, stamp, params, db_root, records, voices, locale, decoder):
    from . import wuthering_assets as assets, wuthering_cinematics as films
    from .languages import audio_locale
    if decoder is None:
        return
    candidates = films.candidates(db_root, records, voices, locale)
    if not candidates:
        return
    code = assets.VOICE_LOCALES[locale][0]
    events = {event for _, event, _, _ in candidates}
    banks = {films.EVENT_ROOT + code + '/' + event + '.bnk': event for event in events}
    bank_refs = _movie_locations(tools, snapshot, params, code, set(banks))
    event_tracks = {}
    for name, (info, pos) in bank_refs.items():
        event = banks[name]
        media = films.media_id(_voice_package(tools, stamp, info).extract(pos), event)
        if media:
            event_tracks[event] = f'{films.MEDIA_ROOT}{code}/{media}.wem'
    mapped = _movie_locations(tools, snapshot, params, code, set(event_tracks.values()))
    current_depot = None
    decoded = None
    with tempfile.TemporaryDirectory(dir=db_root) as temporary:
        directory = Path(temporary)
        for row, event, references, anchor in sorted(candidates, key=lambda item: item[1]):
            depot = event_tracks.get(event)
            if depot not in mapped:
                continue
            if depot != current_depot:
                current_depot = depot
                info, pos = mapped[depot]
                data = _source_bytes(tools, stamp, depot, (info, pos))
                _validate_wem(data)
                decoded = films.samples(data, decoder, directory)
            if decoded is None:
                continue
            performances = []
            for source in references:
                info, pos = voices[source]
                data = _source_bytes(tools, stamp, source, (info, pos))
                _validate_wem(data)
                performances.append(films.samples(data, decoder, directory))
            span = films.interval(decoded, performances, anchor)
            if span:
                row['audio'] = {'depot': depot, 'locale': audio_locale(locale),
                                'start_ms': span[0], 'end_ms': span[1]}
                row['voice_status'] = 'voiced'


def _movie_context_records(tools, snapshot, stamp, params, db_root, records, locale, decoder, *, plot_audio_sha256=None):
    from . import wuthering_assets as assets, wuthering_bank as bank
    from . import wuthering_cinematics as films, wuthering_context as context
    if decoder is None or not any(row.get('dialogue_kind') == 'cinematic'
                                  and row.get('voice_status') == 'unavailable'
                                  and row.get('audio') is None for row in records):
        return
    code = assets.VOICE_LOCALES[locale][0]
    needed = set(context.context_candidates(db_root, records, locale, plot_audio_sha256=plot_audio_sha256).values())
    events = {event for scene, choices in context.full_scene_events(db_root).items() if scene in needed for event in choices}
    names = {films.EVENT_ROOT + code + '/' + event + '.bnk': event for event in events}
    references = _movie_locations(tools, snapshot, params, code, set(names))
    banks = {names[name]: _voice_package(tools, stamp, info).extract(position)
             for name, (info, position) in references.items()}
    candidates = {media for data in banks.values() for media in bank.media_candidates(data)}
    names = {f'{films.MEDIA_ROOT}{code}/{media}.wem': media for media in candidates}
    references = _movie_locations(tools, snapshot, params, code, set(names))
    members = {names[name] for name in references}
    bindings = {event: bank.scene_sources(data, event, members) for event, data in banks.items()}
    wanted = {source.media_id for sources in bindings.values() for source in sources}
    shapes = {}
    with tempfile.TemporaryDirectory(dir=db_root) as temporary:
        for name, (info, position) in references.items():
            media = names[name]
            if media not in wanted:
                continue
            data = _source_bytes(tools, stamp, name, (info, position))
            _validate_wem(data)
            shape = films.source_info(data, decoder, Path(temporary), film_context=True)
            if shape:
                shapes[media] = shape
    context.assign_contexts(db_root, records, locale, bindings, shapes, plot_audio_sha256=plot_audio_sha256)


def _same_launcher(snapshot, current):
    version, root, base = current
    # Each call has already verified the selected regional publisher, checksummed
    # package list, hashes and release directory. CDNs can rotate mid-Setup.
    return (snapshot['launcher'] == version and snapshot['base'] == base
            and urlsplit(snapshot['root']).path == urlsplit(root).path)


def _shared_locations(tools, snapshot, params, names):
    remaining, result = set(names), {}
    for layer in ('PatchFiles', 'BaseFiles', 'launcher'):
        if not remaining:
            break
        matches = _locations(tools, _packages(snapshot, 'resource', layer), params, wanted=remaining)
        result.update(matches)
        remaining.difference_update(matches)  # Tombstones must mask older sources.
    return {name: reference for name, reference in result.items() if reference[1] >= 0}


def _music_records(tools, snapshot, stamp, params, db_root, locale, targets, decoder):
    from . import wuthering_music as music, wuthering_bank as bank, wuthering_cinematics as films
    events = {event for values in music.callers(db_root).values() for event in values} if (db_root / music.TABLE).is_file() else set()
    names = {films.EVENT_ROOT + event + '.bnk': event for event in events}
    references = _shared_locations(tools, snapshot, params, names) if decoder else {}
    banks = {names[name]: _voice_package(tools, stamp, info).extract(position)
             for name, (info, position) in references.items()}
    candidates = {media for data in banks.values() for media in bank.media_candidates(data)}
    names = {f'{films.MEDIA_ROOT}{media}.wem': media for media in candidates}
    references = _shared_locations(tools, snapshot, params, names) if names else {}
    members = {names[name] for name in references}
    sources = {event: bank.song_sources(data, event, members) for event, data in banks.items()}
    wanted = {source.media_id for values in sources.values() for source in values if not source.authored_mute}
    shapes = {}
    with tempfile.TemporaryDirectory(dir=db_root) as temporary:
        for name, (info, position) in references.items():
            media = names[name]
            if media in wanted:
                data = _source_bytes(tools, stamp, name, (info, position))
                _validate_wem(data)
                shape = films.source_info(data, decoder, Path(temporary))
                if shape:
                    shapes[media] = shape
    return music.records(db_root, locale, targets, sources, shapes)


def build_language(tools, source_locale, targets, progress=lambda _message: None, *, decoder=None):
    from . import wuthering_assets as assets
    # Native decoders still observe Windows path limits. Resolve a cache alias
    # before adding the release and nested private work directories.
    tools = Path(tools).resolve()
    if source_locale not in assets.SUPPORTED_LOCALES:
        raise ValueError('Unsupported Wuthering study/audio locale.')
    from .publisher_regions import selected_region
    region = selected_region(tools, 'wuwa')
    stamp, snapshot, params, pointers = _current(tools, int(time.monotonic() // 60), region)
    payload = _build_snapshot_language(tools, stamp, snapshot, params, source_locale, targets, progress,
                                       decoder=decoder, region=region)
    verify_pointers(pointers)
    if selected_region(tools, 'wuwa') != region or not _same_launcher(snapshot, launcher(region)):
        raise ValueError('Kuro updated the launcher during preparation. Retry.')
    return payload


def build_retained_language(tools, stamp, source_locale, targets, progress=lambda _message: None, *, decoder=None):
    """Explicitly replay one retained catalogue, never substitute it for discovery.

    This supports repeatable original-source verification and an already retained
    library. It makes no assertion that this catalogue's former live discovery
    roots still advertise it. Ordinary Setup continues to use build_language.
    """
    from . import wuthering_assets as assets
    from .publisher_regions import selected_region
    tools = Path(tools).resolve()
    if source_locale not in assets.SUPPORTED_LOCALES:
        raise ValueError('Unsupported Wuthering study/audio locale.')
    snapshot = _snapshot(tools, stamp)
    region = snapshot.get('region', 'global')
    if region not in CHANNELS or selected_region(tools, 'wuwa') != region:
        raise ValueError('The retained Wuthering catalogue belongs to another publisher region.')
    payload = _build_snapshot_language(tools, stamp, snapshot, _parameters_for_snapshot(tools, snapshot),
                                       source_locale, targets, progress, decoder=decoder, region=region)
    if _snapshot(tools, stamp) != snapshot or selected_region(tools, 'wuwa') != region:
        raise ValueError('The retained Wuthering catalogue or selected region changed during preparation.')
    return {**payload, 'source_replay': 'retained_original_catalogue'}


def _build_snapshot_language(tools, stamp, snapshot, params, source_locale, targets, progress, *, decoder, region):
    """The same original table/voice/movie/song joins for current and retained input."""
    from . import wuthering_assets as assets
    from .languages import resolve_locale
    resolved = {target: resolve_locale(target, assets.TEXT_LOCALES) for target in targets}
    selected = {locale for locale in resolved.values() if locale}
    progress('Reading the publisher’s original Wuthering story and translation tables')
    with tempfile.TemporaryDirectory(dir=_descriptor_path(tools, stamp).parent) as folder:
        path = Path(folder)
        # Song vocal language is independent of the selected UI/voice pack.
        # Read the actual KeepOrigin/original relation across the voiced locales.
        plot_audio_sha256 = _read_tables(tools, snapshot, params, {*assets.SUPPORTED_LOCALES, *selected}, path)
        pak.check((path / assets.TEXT_LOCALES[source_locale] / 'lang_multi_text.db').is_file())
        selected = {locale for locale in selected if (path / assets.TEXT_LOCALES[locale] / 'lang_multi_text.db').is_file()}
        progress('Matching authored voice paths against the selected publisher dub')
        files = _voice_locations(tools, stamp, assets.VOICE_LOCALES[source_locale][0])
        records = assets.build_language_records(path, files, source_locale, selected)
        _movie_records(tools, snapshot, stamp, params, path, records, files, source_locale, decoder)
        _movie_context_records(tools, snapshot, stamp, params, path, records, source_locale, decoder,
                               plot_audio_sha256=plot_audio_sha256)
        records.extend(_music_records(tools, snapshot, stamp, params, path, source_locale, selected, decoder))
    pak.check(records)
    for record in records:
        if record['audio']:
            record['audio']['publisher'] = stamp
    mapped = sum(bool(row['audio']) for row in records)
    available = {locale for row in records for locale in row['texts']}
    missing = [target for target, locale in resolved.items() if locale not in available]
    return {'format': 2, 'game': 'wuwa', 'install': None, 'source_mode': 'publisher', 'source_region': region, 'fingerprint': stamp,
            'source_locale': source_locale, 'records': records, 'missing_translation_locales': missing,
            'publisher_song_cues': sum(row.get('dialogue_kind') == 'music_subtitle' and bool(row.get('text_capture_verified')) for row in records),
            'publisher_song_voices': sum(row.get('dialogue_kind') == 'music_subtitle' and bool(row.get('audio')) for row in records),
            'coverage_warnings': assets.COVERAGE_WARNINGS,
            'message': f'{len(records):,} official {source_locale} lines; {mapped:,} original voices'}


def _cached_source(tools, stamp, depot):
    directory = _descriptor_path(tools, stamp).parent / 'clips'
    key = hashlib.sha256(depot.encode()).hexdigest()
    binding = hashlib.sha256((stamp + '/' + depot).encode()).digest()
    path = directory / key
    if path.is_file() and path.stat().st_size <= pak.MEMBER_LIMIT + 32:
        cached = path.read_bytes()
        if len(cached) > 32 and hashlib.sha256(binding + cached[32:]).digest() == cached[:32]:
            try:
                _validate_wem(cached[32:])
                return cached[32:]
            except ValueError:
                pass
    return None


def _same_catalogue_source(tools, stamp, depot):
    """A key-input-only descriptor change does not change original media.

    Both immutable descriptor hashes and every remaining field must agree.
    This deliberately does not infer cross-version member equivalence.
    """
    try:
        current = dict(_snapshot(tools, stamp))
    except FileNotFoundError:
        # The lower-level explicit-reference cache primitive also serves owned
        # callers before descriptor publication. Missing metadata permits no
        # migration; the original reference still authenticates a new transfer.
        return None
    current.pop('native_key_sources', None)
    current.pop('native_bootstrap', None)
    for path in (Path(tools) / 'wuwa-publisher').glob('wuwa-*/release.json'):
        previous = path.parent.name
        if previous == stamp or not re.fullmatch('wuwa-[0-9a-f]{64}', previous):
            continue
        try:
            old = dict(_snapshot(tools, previous))
        except (OSError, ValueError, TypeError, KeyError):
            continue  # Invalid older cache metadata establishes no equivalence.
        old.pop('native_key_sources', None)
        old.pop('native_bootstrap', None)
        if old == current:
            data = _cached_source(tools, previous, depot)
            if data is not None:
                return data
    return None


def _source_bytes(tools, stamp, depot, reference=None):
    """Reuse an exact original source during preparation and later playback.

    A manifest-owned reference authenticates every new transfer. Snapshot and
    full depot path bind cached bytes, keeping retained older recordings usable
    without consulting the newest publisher inventory. Native key-input-only
    changes can reuse a validated identical catalogue without a media download.
    """
    tools = Path(tools)
    cached = _cached_source(tools, stamp, depot)
    if cached is not None:
        return cached
    data = _same_catalogue_source(tools, stamp, depot)
    if data is not None:
        binding = hashlib.sha256((stamp + '/' + depot).encode()).digest()
        path = _descriptor_path(tools, stamp).parent / 'clips' / hashlib.sha256(depot.encode()).hexdigest()
        _atomic_file(path, hashlib.sha256(binding + data).digest() + data)
        return data
    if reference is None:
        return None
    from . import wuthering_source_cache
    data = wuthering_source_cache.cached(tools, depot, reference)
    if data is not None:
        binding = hashlib.sha256((stamp + '/' + depot).encode()).digest()
        path = _descriptor_path(tools, stamp).parent / 'clips' / hashlib.sha256(depot.encode()).hexdigest()
        _atomic_file(path, hashlib.sha256(binding + data).digest() + data)
        return data
    info, position = reference
    data = _voice_package(tools, stamp, info).extract(position)
    _validate_wem(data)
    wuthering_source_cache.remember(tools, depot, reference, data)
    binding = hashlib.sha256((stamp + '/' + depot).encode()).digest()
    path = _descriptor_path(tools, stamp).parent / 'clips' / hashlib.sha256(depot.encode()).hexdigest()
    _atomic_file(path, hashlib.sha256(binding + data).digest() + data)
    return data


def extract(tools, audio, locale=None):
    from . import wuthering_assets as assets
    from .languages import audio_locale
    depot = assets._validate_voice(audio)
    pak.check(locale is None or audio_locale(locale) == audio.get('locale'))
    code = assets.VOICE_LOCALES[audio['locale']][0]
    stamp, tools = audio['publisher'], Path(tools)
    _snapshot(tools, stamp)
    cached = _source_bytes(tools, stamp, depot)
    if cached is not None:
        return cached
    if depot.startswith(assets.EXTERNAL_ROOT):
        reference = _voice_locations(tools, stamp, code).get(depot)
    elif audio.get('music_context') is True:
        reference = _shared_locations(tools, _snapshot(tools, stamp), _voice_parameters(stamp, tools), {depot}).get(depot)
    else:
        reference = _movie_locations(tools, _snapshot(tools, stamp), _voice_parameters(stamp, tools), code, {depot}).get(depot)
    if reference is None:
        raise ValueError('The released dub does not contain this exact original voice.')
    return _source_bytes(tools, stamp, depot, reference)


def _validate_wem(data):
    pak.check(data[:4] == b'RIFF' and data[8:12] == b'WAVE' and int.from_bytes(data[4:8], 'little') + 8 == len(data))


def voice(cache, products, locale, stem, params):
    pak.check(locale in DUBS and re.fullmatch(r'[a-zA-Z0-9_]{1,240}', stem))
    target = f'Client/Content/Aki/WwiseAudio_Generated/WwiseExternalSource/{locale}_{stem}.wem'
    for layer in ('PatchFiles', 'BaseFiles'):
        matches = []
        for key, (url, size, digest) in products.items():
            if key.startswith(f'{locale}/{layer}/') and key.endswith('.pak'):
                data = _package(cache, (url, size, digest), params).member(target)
                if data is not None:
                    matches.append(data)
        if matches:
            pak.check(len(matches) == 1)
            data = matches[0]
            _validate_wem(data)
            return data
    raise ValueError('The released dub does not contain this exact external voice path.')
