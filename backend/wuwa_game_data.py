"""Consented official bootstrap stage, with an explicit unresolved format gate.

This provider does not activate a matcher or claim a prepared language library.
Downloaded publisher code is read as bounded data and is never executed.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .publisher_transport import PublisherTransport
from .private_data_paths import _no_links

POLICY = 'wuwa-official-bootstrap-stage/1'
FORMAT_MESSAGE = ('The original bootstrap module is verified. Independent release-manifest '
    'key/IV discovery is still unavailable; no language library has been activated.')
METADATA_MAX = 2 * 1024**2


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _native():
    try:
        from . import wuthering_native_bootstrap
        return wuthering_native_bootstrap
    except ImportError as error:
        raise GameDataError('game_runtime_unavailable',
            'The device needs the original APK cryptography reader before this download.', 409) from error


def _file(ctx, name):
    root = Path(ctx.cache_directory).absolute()
    _no_links(root)
    path = root / 'wuwa-bootstrap-stage' / name
    _no_links(path)
    return path


def _save(path, raw):
    from .game_tools import _atomic_file
    _no_links(path)
    _atomic_file(path, raw)


def _request(request):
    from .wuthering_assets import SUPPORTED_LOCALES, TEXT_LOCALES
    if request.source_locale not in SUPPORTED_LOCALES or any(x not in TEXT_LOCALES for x in request.target_locales):
        raise GameDataError('unsupported_game_language', 'Choose an official Wuthering language.')


class _TransportZip:
    """Bind the existing ZIP parser to the shared consent/budget transport."""
    @staticmethod
    def create(native, transport, url, total, etag):
        class Archive(native._Zip):
            def range(self, start, count):
                native._check(0 < count <= METADATA_MAX and 0 <= start <= self.total - count and
                              self.metadata_bytes + count <= METADATA_MAX)
                raw, _receipt = transport.fetch_bytes(url, limit=count, expected_size=count,
                    original_range=(start, count, total), headers={'If-Match': etag})
                self.metadata_bytes += len(raw)
                return raw
        return Archive(url, total, etag)


def _handle(value, request):
    if (not isinstance(value, dict) or value.get('policy') != POLICY or
            value.get('request') != request.json() or value.get('stage') not in ('bootstrap', 'manifest-format')):
        raise GameDataError('invalid_source_handle', 'Check the Wuthering download size again.')
    return value


def _retained(ctx, value):
    native = _native()
    source = native.reference(value['source'])
    module = native._module(Path(ctx.cache_directory), source)
    _no_links(module)
    try:
        valid = module.stat().st_size == source['module']['plain_bytes'] and native._file_hash(module) == source['module']['sha256']
    except OSError:
        valid = False
    if not valid:
        raise GameDataError('publisher_bootstrap_cache_invalid', 'The original bootstrap module needs repair.')
    # Derive only in memory; the archive reader has not yet authorized a key.
    native.default_output(module, source['module']['sha256'])
    return source


class WutheringGameDataProvider:
    title = 'Wuthering Waves'

    def __init__(self, platform, native=None):
        if platform not in ('desktop', 'android'):
            raise ValueError('Unsupported Wuthering preparation platform')
        self.platform = platform

    def plan(self, request, ctx):
        _request(request)
        ctx.check()
        if ctx.stage_handle is not None:
            previous = _handle(ctx.stage_handle, request)
            if previous['stage'] == 'manifest-format':
                source = _retained(ctx, previous)
                return GameDataPlan(source['version'], 0, 0, previous, runtime_available=False,
                    stage='manifest-format', message=FORMAT_MESSAGE)
        native = _native()
        metadata = PublisherTransport(ctx, hosts={urlsplit(native.CATALOGUE).hostname})
        raw, _receipt = metadata.fetch_bytes(native.CATALOGUE + '?_t=' + str(int(time.time() // 60)), limit=64 * 1024)
        catalogue = json.loads(raw)
        if not isinstance(catalogue, dict) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', catalogue.get('version', '')):
            raise GameDataError('publisher_source_invalid', 'The original Wuthering catalogue changed.')
        url = native._url(catalogue['primary'])
        transport = PublisherTransport(ctx, hosts={urlsplit(url).hostname})
        _first, identity = transport.fetch_bytes(url, limit=1, expected_size=1, original_range=(0, 1, None))
        total, etag = identity.original_range[2], identity.response_etag
        if not etag or not 0 < total <= 4 * 1024**3:
            raise GameDataError('publisher_source_invalid', 'The original APK needs a stable size and ETag.')
        archive = _TransportZip.create(native, transport, url, total, etag)
        manifest = archive.member('AndroidManifest.xml', read=True, maximum=METADATA_MAX)
        name = native._library(manifest)
        offset, packed = archive.member(name)
        entry = archive.entries[name]
        native._check(entry['method'] == 8)
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
            stage='bootstrap', message='Language preparation remains blocked by release-manifest key/IV discovery after this step. '
                'Verify the complete original installer carrier and retain only its native module. '
                'The carrier includes unused packaged media. No optional voice pack or language library is downloaded in this stage.')

    def download(self, plan, ctx):
        handle = _handle(plan.handle, ctx.request)
        if handle['stage'] != 'bootstrap' or plan.stage != 'bootstrap':
            raise GameDataError('publisher_format_key_unresolved', FORMAT_MESSAGE, 409)
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
        native = _native()
        url = native._url(artifact['url'])
        if plan.download_bytes != artifact['total']:
            raise GameDataError('invalid_download_plan', 'Check the original download size again.')
        decoded_bytes = lambda value: base64.b64decode(value, validate=True)
        layout = native.ApkLayout(artifact['total'], artifact['layout']['signing_offset'],
            decoded_bytes(artifact['layout']['signing_block']), decoded_bytes(artifact['layout']['central_directory']),
            decoded_bytes(artifact['layout']['eocd']), allow_signed_zero_tail=True)
        layout.validate()
        witnesses = [(start, decoded_bytes(data)) for start, data in artifact['witnesses']]
        transport = PublisherTransport(ctx, hosts={urlsplit(url).hostname})
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
                                    native._check(raw[left - self.at:right - self.at] == expected[left - start:right - start])
                            self.at += len(raw)
                            return raw
                    return native.verify_stream(WitnessStream(), layout,
                        member=(artifact['offset'], artifact['packed']), member_sink=sink)
                verified, _receipt = transport.consume_stream(url, consume, limit=artifact['total'],
                    expected_size=artifact['total'], headers={'If-Match': artifact['etag']})
            size, crc, plain_sha, packed_sha = native._decode_module(compressed, decoded, artifact['entry'], check=ctx.check)
            source = native.reference({'policy': native.POLICY, 'catalogue': native.CATALOGUE,
                'catalogue_sha256': artifact['catalogue_sha256'], 'version': artifact['version'],
                'url': url, 'bytes': artifact['total'], 'etag': artifact['etag'],
                'apk_sha256': verified['apk_sha256'], 'v2_digest': verified['v2_content_digest'],
                'signers': verified['certificate_sha256'], 'module': {'name': artifact['name'],
                    'sha256': plain_sha, 'compressed_sha256': packed_sha, 'compressed_bytes': artifact['packed'],
                    'plain_bytes': size, 'crc32': f'{crc:08x}'}})
            native.default_output(decoded, plain_sha)
            target = native._module(Path(ctx.cache_directory), source)
            _no_links(target)
            ctx.check()
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                native._check(native._file_hash(target) == plain_sha)
            else:
                decoded.replace(target)
        return PreparationStage({'policy': POLICY, 'stage': 'manifest-format',
            'request': ctx.request.json(), 'source': source}, FORMAT_MESSAGE)

    def restore(self, handle, ctx):
        _handle(handle, ctx.request)
        if handle['stage'] == 'manifest-format':
            _retained(ctx, handle)
        raise GameDataError('publisher_format_key_unresolved', FORMAT_MESSAGE, 409)


def create_provider(platform, native=None):
    return WutheringGameDataProvider(platform, native)
