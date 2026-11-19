"""Consented Wuthering bootstrap and release manifest verification.

This provider does not activate a matcher or claim a prepared language library.
Downloaded publisher code is read as bounded data and is never executed.
"""
import base64
import hashlib
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit

from .game_data_protocol import GameDataError, GameDataPlan, MAX_METADATA_BYTES, PreparationStage
from .publisher_transport import PublisherTransport
from .private_data_paths import _no_links

POLICY = 'wuwa-official-bootstrap-stage/1'
FORMAT_MESSAGE = ('The original bootstrap module is verified. Check the official Global release and '
    'its resource and dub manifests. Encrypted metadata uses verified community compatibility parameters.')
CONTENT_MESSAGE = ('The official Global release and its resource and dub manifests are verified. '
    'Preparing dialogue tables and audio still requires the portable content reader.')
METADATA_MAX = 2 * 1024**2


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _source():
    from . import wuthering_bootstrap_source
    return wuthering_bootstrap_source


def _file(ctx, name):
    root = Path(ctx.cache_directory).absolute()
    _no_links(root)
    path = root / 'wuwa-bootstrap-stage' / name
    _no_links(path)
    return path


def _save(path, raw):
    from .atomic_files import write_bytes
    _no_links(path)
    write_bytes(path, raw)


def _request(request):
    from .wuthering_locales import SUPPORTED_LOCALES, TEXT_LOCALES
    if request.source_locale not in SUPPORTED_LOCALES or any(x not in TEXT_LOCALES for x in request.target_locales):
        raise GameDataError('unsupported_game_language', 'Choose an official Wuthering language.')


def _archive(transport, url, total, etag, crypto):
    from .publisher_apk_zip import ApkMetadata
    def read_range(start, count):
        raw, receipt = transport.fetch_bytes(url, limit=count, expected_size=count,
            original_range=(start, count, total), headers={'If-Match': etag})
        _source()._check(receipt.response_etag == etag)
        return raw
    return ApkMetadata(read_range, total, allow_signed_zero_tail=True,
        maximum_metadata=METADATA_MAX, crypto=crypto)


def _handle(value, request):
    if (not isinstance(value, dict) or value.get('policy') != POLICY or
            value.get('request') != request.json() or value.get('stage') not in ('bootstrap', 'manifest-format', 'manifest-verified')):
        raise GameDataError('invalid_source_handle', 'Check the Wuthering download size again.')
    return value


def _retained(ctx, value):
    ctx.check()
    source_reader = _source()
    source = source_reader.reference(value['source'])
    module = source_reader._module(Path(ctx.cache_directory), source)
    _no_links(module)
    try:
        valid = module.stat().st_size == source['module']['plain_bytes'] and source_reader._file_hash(module, check=ctx.check) == source['module']['sha256']
    except OSError:
        valid = False
    if not valid:
        raise GameDataError('publisher_bootstrap_cache_invalid', 'The original bootstrap module needs repair.')
    # Derive only in memory; the archive reader has not yet authorized a key.
    result = source_reader.default_output(module, source['module']['sha256'], check=ctx.check)
    return source, result.parameter


class WutheringGameDataProvider:
    title = 'Wuthering Waves'

    def __init__(self, platform, native=None, *, transport_factory=None):
        if platform not in ('windows', 'linux', 'macos', 'android', 'desktop'):
            raise ValueError('Unsupported Wuthering preparation platform')
        self.platform, self.native = platform, native
        self._transport_factory = transport_factory
        self._accepted_entry = None

    def _transport(self, ctx, *, hosts):
        if self._transport_factory is not None:
            return self._transport_factory(ctx, hosts=hosts)
        if self.platform in ('desktop', 'windows') and sys.platform == 'win32' and any(
                re.fullmatch(r'[a-z0-9-]+\.aki-game\.(?:com|net)', host) for host in hosts):
            # Match the existing verified Windows Kuro trust route when a
            # conflicting intermediate is present in the Windows system store.
            from urllib.request import HTTPSHandler, build_opener
            from .publisher_transport import _PublisherRedirect
            from .wuthering_release_pak import _publisher_tls
            opener = build_opener(_PublisherRedirect(hosts), HTTPSHandler(context=_publisher_tls()))
            return PublisherTransport(ctx, hosts=hosts, opener=opener.open)
        return PublisherTransport(ctx, hosts=hosts)

    def _crypto(self):
        try:
            from .publisher_crypto import create_publisher_crypto
            if self.platform == 'android':
                return create_publisher_crypto(platform='android', native=self.native.publisherCrypto())
            platform = self.platform
            if platform == 'desktop':
                platform = {'win32': 'windows', 'linux': 'linux', 'darwin': 'macos'}.get(sys.platform)
            return create_publisher_crypto(platform=platform)
        except Exception as error:
            # This boundary only creates the maintained host capability. It
            # does not catch or reinterpret publisher parsing/hash failures.
            raise GameDataError('game_runtime_unavailable',
                'The verified publisher cryptography runtime is unavailable on this device.', 409) from error

    def _verify_manifest(self, handle, ctx):
        from . import wuthering_manifest as manifest, wuthering_publisher_keys as publisher_keys
        from .preparation_errors import PreparationFailure
        from .wuthering_portable_pak import PortablePackage

        source, parameter = _retained(ctx, handle)
        crypto = self._crypto()

        def fetch(url, **options):
            transport = self._transport(ctx, hosts={urlsplit(url).hostname})
            return transport.fetch_bytes(url, **options)

        def read(url):
            raw, _ = fetch(url, limit=manifest.LIMIT)
            return raw

        def launcher_read(url):
            raw, _ = fetch(url, limit=manifest.LIMIT, allow_gzip=True)
            return manifest.launcher_bytes(raw)

        def launcher_index(url, sha):
            raw = launcher_read(url)
            manifest._check(hashlib.md5(raw).hexdigest() == sha)
            return raw

        used_compatibility = False

        @lru_cache(maxsize=1)
        def parameters():
            nonlocal used_compatibility
            try:
                raw, _ = fetch(manifest.FORMAT_URL, limit=40 * 1024, digests={'sha256': manifest.FORMAT_SHA})
            except GameDataError as error:
                if isinstance(error.__cause__, HTTPError) and error.__cause__.code in {404, 410}:
                    raise PreparationFailure('publisher_entry_source_unavailable',
                        'The pinned Wuthering manifest source is unavailable.', previous_snapshot_retained=True) from error
                raise
            value = manifest.parse_entry_source(raw, manifest.FORMAT_SHA)
            used_compatibility = True
            return value

        def fetch_source(url, *, limit):
            try:
                return fetch(url, limit=limit)[0]
            except GameDataError as error:
                ctx.check()
                raise OSError('The public Wuthering compatibility source could not be read.') from error

        decode = manifest.EntryDecoder(parameters, crypto, fetch_source, self._accepted_entry)

        def inventory_read(url, digest):
            manifest._check(isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{40}', digest))
            digest = digest.lower()
            path = _file(ctx, 'manifest-' + digest + '.json')
            ctx.check()
            if path.is_file() and path.stat().st_size <= manifest.LIMIT:
                raw = path.read_bytes()
                if hashlib.sha1(raw).hexdigest() == digest:
                    return decode(raw)
            raw, _ = fetch(url, limit=manifest.LIMIT, digests={'sha1': digest})
            decoded = decode(raw)
            _save(path, raw)
            return decoded

        try:
            version, launcher_root, files = manifest.launcher('global', launcher_read, launcher_index)
            url = launcher_root + '/' + manifest.BOOTSTRAP
            size, digest = files[manifest.BOOTSTRAP]
            _, witness = fetch(url, limit=1, expected_size=1, original_range=(0, 1, size))
            etag = witness.response_etag
            manifest._check(etag)

            def read_range(owner, total, offset, count):
                raw, receipt = fetch(owner, limit=count, expected_size=count,
                    original_range=(offset, count, total), headers={'If-Match': etag})
                manifest._check(receipt.response_etag == etag)
                return raw

            package = PortablePackage(url, size, digest, _file(ctx, 'manifest-index'), (parameter,),
                range_reader=read_range, crypto=crypto, native_parameters={}, verified_default_parameters=())
            manifest._check(package.verified_default_parameter)
            config = package.member('Client/Config/Kuro/KuroPublicConfig.ini')
            entry, cdn, root, release, platform, pointers = manifest.platform_config(config, version, 'global', read, decode)
            versions, _, products = manifest.resource_inventory(root, release, platform['ResVersions'], inventory_read)
            manifest._check(products)
            mix = entry.get('MixUri')
            manifest._check(isinstance(mix, str) and re.fullmatch(r'[A-Za-z0-9]{16,80}', mix))
            native = publisher_keys.current(_file(ctx, 'manifest-index'), cdn['url'] + mix + '/Windows/',
                release, 'global', (parameter,), lambda url, *, limit: fetch(url, limit=limit)[0],
                decode, pointers, verified_defaults=(parameter,))
            if (any(read(url) != raw for url, raw in pointers.items()) or
                    manifest.launcher('global', launcher_read, launcher_index) != (version, launcher_root, files)):
                raise GameDataError('publisher_object_changed', 'Kuro changed the release during verification. Retry.', 409)
        except PreparationFailure as error:
            raise GameDataError(error.code, str(error), 409) from error
        except (ValueError, KeyError, TypeError) as error:
            raise GameDataError('publisher_metadata_invalid',
                'The official Wuthering release could not be verified. Your previous data is retained.', 409) from error
        receipt = {'version': version, 'versions': versions, 'packages': products, 'root': root,
            'launcher_root': launcher_root, 'launcher_packages': files,
            'bootstrap': digest, 'native_key_sources': native.sources,
            'entry_source_sha256': (decode.candidate[1]['sha256'] if decode.used_fallback else
                                    manifest.FORMAT_SHA if used_compatibility else None),
            'entry_source_release': decode.candidate[1] if decode.used_fallback else None,
            'pointers_sha256': {url: _digest(raw) for url, raw in pointers.items()}}
        raw = _json(receipt)
        if len(raw) > METADATA_MAX:
            raise GameDataError('publisher_metadata_limit', 'The Wuthering release inventory exceeds its size limit.')
        key = _digest(raw)
        ctx.check()
        _save(_file(ctx, key + '.json'), raw)
        if decode.used_fallback:
            self._accepted_entry = decode.candidate
        getattr(ctx, 'preparation_memo', {})['wuwa-manifest-verified'] = True
        return PreparationStage({'policy': POLICY, 'stage': 'manifest-verified',
            'request': ctx.request.json(), 'source': source, 'inventory_sha256': key,
            'revision': versions['resource']}, CONTENT_MESSAGE)

    def _verified_inventory(self, handle, ctx):
        key = handle.get('inventory_sha256', '')
        if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
            raise GameDataError('invalid_source_handle', 'Check the Wuthering release again.')
        path = _file(ctx, key + '.json')
        if not path.is_file() or path.stat().st_size > METADATA_MAX or _digest(path.read_bytes()) != key:
            raise GameDataError('publisher_manifest_cache_invalid', 'The verified Wuthering release inventory needs repair.')

    def plan(self, request, ctx):
        _request(request)
        ctx.check()
        if ctx.stage_handle is not None:
            previous = _handle(ctx.stage_handle, request)
            if previous['stage'] == 'manifest-verified':
                self._verified_inventory(previous, ctx)
                memo = getattr(ctx, 'preparation_memo', {})
                if not ((getattr(ctx, 'job', None) or {}).get('automatic')) or memo.get('wuwa-manifest-verified'):
                    return GameDataPlan(previous['revision'], None, None, previous,
                        stage='manifest-verified', message=CONTENT_MESSAGE)
                previous = {**previous, 'stage': 'manifest-format'}
            if previous['stage'] == 'manifest-format':
                source, _ = _retained(ctx, previous)
                if request.region == 'global':
                    try:
                        self._crypto()
                    except GameDataError as error:
                        return GameDataPlan(source['version'], None, None, previous,
                            stage='manifest-format', message=error.message)
                    return GameDataPlan(source['version'], MAX_METADATA_BYTES, MAX_METADATA_BYTES + 3 * METADATA_MAX, previous,
                        download_is_upper_bound=True, runtime_available=True,
                        stage='manifest-format', message=FORMAT_MESSAGE)
                return GameDataPlan(source['version'], None, None, previous, stage='manifest-format',
                    message='This manifest reader currently supports the Global edition.')
        crypto = self._crypto()
        source_reader = _source()
        metadata = self._transport(ctx, hosts={urlsplit(source_reader.CATALOGUE).hostname})
        raw, _receipt = metadata.fetch_bytes(source_reader.CATALOGUE + '?_t=' + str(int(time.time() // 60)), limit=64 * 1024)
        catalogue = json.loads(raw)
        if not isinstance(catalogue, dict) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', catalogue.get('version', '')):
            raise GameDataError('publisher_source_invalid', 'The original Wuthering catalogue changed.')
        url = source_reader._url(catalogue['primary'])
        transport = self._transport(ctx, hosts={urlsplit(url).hostname})
        _first, identity = transport.fetch_bytes(url, limit=1, expected_size=1, original_range=(0, 1, None))
        total, etag = identity.original_range[2], identity.response_etag
        if not etag or not 0 < total <= 4 * 1024**3:
            raise GameDataError('publisher_source_invalid', 'The original APK needs a stable size and ETag.')
        archive = _archive(transport, url, total, etag, crypto)
        manifest = archive.member('AndroidManifest.xml', read=True, maximum=METADATA_MAX)
        name = source_reader._library(manifest)
        offset, packed = archive.member(name, maximum=source_reader.MAX_MODULE)
        entry = archive.entries[name]
        source_reader._check(entry['method'] == 8)
        encoded = lambda value: base64.b64encode(value).decode('ascii')
        artifact = {'catalogue_sha256': _digest(raw), 'version': catalogue['version'], 'url': url,
            'total': total, 'etag': etag, 'name': name, 'offset': offset, 'packed': packed, 'entry': entry,
            'layout': {'signing_offset': archive.layout.signing_offset,
                'signing_block': encoded(archive.layout.signing_block), 'central_directory': encoded(archive.layout.central_directory),
                'eocd': encoded(archive.layout.eocd)},
            'witnesses': [[start, encoded(data)] for start, data in archive.witnesses]}
        serialized = _json(artifact)
        if len(serialized) > METADATA_MAX:
            raise GameDataError('publisher_metadata_limit', 'The original APK metadata exceeds this reader’s limit.')
        key = _digest(serialized)
        ctx.check()
        _save(_file(ctx, key + '.json'), serialized)
        handle = {'policy': POLICY, 'stage': 'bootstrap', 'request': request.json(), 'artifact_sha256': key}
        # The full carrier must pass APK-v2 integrity even though only its native
        # member is retained. It may contain unused packaged audio; disclose it.
        disk = packed + entry['plain'] + len(serialized) + 64 * 1024
        return GameDataPlan(catalogue['version'], total, disk, handle, runtime_available=True,
            stage='bootstrap', message='Verify the complete original installer carrier and retain only its native module. '
                'The carrier includes unused packaged media. No optional voice pack or language library is downloaded in this stage.')

    def download(self, plan, ctx):
        handle = _handle(plan.handle, ctx.request)
        if handle['stage'] == plan.stage == 'manifest-format' and ctx.request.region == 'global':
            if plan.download_bytes != MAX_METADATA_BYTES:
                raise GameDataError('invalid_download_plan', 'Check the Wuthering manifest download again.')
            return self._verify_manifest(handle, ctx)
        if handle['stage'] != 'bootstrap' or plan.stage != 'bootstrap':
            raise GameDataError('invalid_download_plan', 'Check the Wuthering download again.')
        key = handle.get('artifact_sha256', '')
        if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
            raise GameDataError('invalid_source_handle', 'Check the original download again.')
        path = _file(ctx, key + '.json')
        if not path.is_file() or path.stat().st_size > METADATA_MAX:
            raise GameDataError('publisher_bootstrap_cache_invalid', 'Check the original download again.')
        serialized = path.read_bytes()
        if _digest(serialized) != key:
            raise GameDataError('publisher_bootstrap_cache_invalid', 'Check the original download again.')
        artifact = json.loads(serialized)
        crypto = self._crypto()
        from .publisher_apk import ApkLayout, verify_stream
        source_reader = _source()
        url = source_reader._url(artifact['url'])
        if plan.download_bytes != artifact['total']:
            raise GameDataError('invalid_download_plan', 'Check the original download size again.')
        decoded_bytes = lambda value: base64.b64decode(value, validate=True)
        layout = ApkLayout(artifact['total'], artifact['layout']['signing_offset'],
            decoded_bytes(artifact['layout']['signing_block']), decoded_bytes(artifact['layout']['central_directory']),
            decoded_bytes(artifact['layout']['eocd']), allow_signed_zero_tail=True)
        layout.validate(crypto=crypto)
        witnesses = [(start, decoded_bytes(data)) for start, data in artifact['witnesses']]
        transport = self._transport(ctx, hosts={urlsplit(url).hostname})
        root = _file(ctx, 'pending').parent
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root, prefix='pending-') as directory:
            directory = Path(directory)
            compressed, decoded = directory / 'selected.deflate', directory / 'module.so'
            with compressed.open('xb') as sink:
                def consume(stream):
                    class WitnessStream:
                        at = 0
                        def read(self, count):
                            raw = stream.read(count)
                            for start, expected in witnesses:
                                left, right = max(self.at, start), min(self.at + len(raw), start + len(expected))
                                if left < right:
                                    source_reader._check(raw[left - self.at:right - self.at] == expected[left - start:right - start])
                            self.at += len(raw)
                            return raw
                    return verify_stream(WitnessStream(), layout, crypto=crypto,
                        member=(artifact['offset'], artifact['packed']), member_sink=sink)
                verified, _receipt = transport.consume_stream(url, consume, limit=artifact['total'],
                    expected_size=artifact['total'], headers={'If-Match': artifact['etag']})
            size, crc, plain_sha, packed_sha = source_reader._decode_module(compressed, decoded, artifact['entry'], check=ctx.check)
            source = source_reader.reference({'policy': source_reader.POLICY, 'catalogue': source_reader.CATALOGUE,
                'catalogue_sha256': artifact['catalogue_sha256'], 'version': artifact['version'],
                'url': url, 'bytes': artifact['total'], 'etag': artifact['etag'],
                'apk_sha256': verified['apk_sha256'], 'v2_digest': verified['v2_content_digest'],
                'signers': verified['certificate_sha256'], 'module': {'name': artifact['name'],
                    'sha256': plain_sha, 'compressed_sha256': packed_sha, 'compressed_bytes': artifact['packed'],
                    'plain_bytes': size, 'crc32': f'{crc:08x}'}})
            source_reader.default_output(decoded, plain_sha, check=ctx.check)
            target = source_reader._module(Path(ctx.cache_directory), source)
            _no_links(target)
            ctx.check()
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                source_reader._check(source_reader._file_hash(target, check=ctx.check) == plain_sha)
            else:
                decoded.replace(target)
        return PreparationStage({'policy': POLICY, 'stage': 'manifest-format',
            'request': ctx.request.json(), 'source': source}, FORMAT_MESSAGE)

    def restore(self, handle, ctx):
        ctx.check()
        _handle(handle, ctx.request)
        if handle['stage'] == 'bootstrap':
            raise GameDataError('publisher_bootstrap_incomplete',
                'The original bootstrap download has not been verified. Complete its download stage before preparing language data; existing data is unchanged.', 409)
        if handle['stage'] == 'manifest-verified':
            self._verified_inventory(handle, ctx)
            raise GameDataError('publisher_content_reader_unavailable', CONTENT_MESSAGE, 409)
        _retained(ctx, handle)
        raise GameDataError('publisher_manifest_incomplete', FORMAT_MESSAGE, 409)


def create_provider(platform, native=None, *, transport_factory=None):
    return WutheringGameDataProvider(platform, native, transport_factory=transport_factory)
