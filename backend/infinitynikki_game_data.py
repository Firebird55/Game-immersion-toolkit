"""Consent-bound original native bootstrap, never a prepared dialogue snapshot.

The original mainland APK owns the evidenced wrapper/default PAK consumers.
Its use as bootstrap data does not establish Global Android client acceptance;
every downstream Global archive still needs its own compatibility verification.
No downloaded module, client or script is executed. Derived material stays in
memory and is not serialized as a key cache or exposed by this stage.
"""
import base64
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import zlib

from .atomic_files import replace as atomic_replace
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .publisher_transport import PublisherTransport, STRONG_ETAG


POLICY = 'infinitynikki-original-native-bootstrap/1'
HOMEPAGE = 'https://infinitynikki.nuanpaper.com/home'
APK_HOST = 'x6cn-game-apk.papegames.com'
NATIVE_MEMBER = 'lib/arm64-v8a/libUnreal.so'
METADATA_MAX = 2 * 1024**2
ARTIFACT_MAX = 3 * 1024**2
NATIVE_MAX = 256 * 1024**2
OWNER_MAX = 4 * 1024**3
TEXT_LOCALES = {'de', 'en', 'es', 'es-419', 'fr', 'id', 'it', 'ja', 'ja-JP', 'ko', 'pt', 'pt-BR',
                'th', 'zh', 'zh-CN', 'zh-TW', 'zh-Hans', 'zh-Hant'}
GATE = ('The original native bootstrap is verified. Current regional SDK/resource selection, '
        'patch precedence, caption/voice bindings and the selected host codecs still need '
        'verification. No language library has been activated.')
QUOTE = ('This step verifies the complete official mainland Android installer and retains only '
         'its native bootstrap module. The carrier includes unused packaged media, even in '
         'text-only mode; no optional voice pack is selected. This source also supplies native '
         'bootstrap data for Global, with separate Global archive compatibility checks required. '
         'Current resource selection, captions, voice bindings and host codecs remain unresolved '
         'after this step; this download does not prepare a playable language library.')


def _check(value):
    if not value:
        raise GameDataError('publisher_source_unverified', 'Could not verify the original Infinity Nikki bootstrap source.')


def _guard(method):
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError, OSError, struct.error, zlib.error) as error:
            raise GameDataError('publisher_source_unverified',
                'Could not verify the original Infinity Nikki bootstrap. Check the source and download size again.') from error
    return guarded


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _path(ctx, name):
    _check(isinstance(name, str) and re.fullmatch(r'[0-9a-f]{64}\.(?:json|so)', name))
    path = Path(ctx.cache_directory).absolute() / 'infinitynikki-native-bootstrap' / name
    _no_links(path)
    return path


def _save(path, value):
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, pending = tempfile.mkstemp(prefix='pending-', dir=path.parent)
    pending = Path(pending)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        _no_links(path)
        atomic_replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def _read(ctx, digest):
    _check(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest))
    path = _path(ctx, digest + '.json')
    _check(path.is_file() and path.stat().st_size <= ARTIFACT_MAX)
    raw = path.read_bytes()
    _check(_sha(raw) == digest)
    return json.loads(raw)


def _crypto(platform, native):
    # Desktop remains compatible with the canonical verifier's lazy default.
    # Android requires the actual manifest-bound Java service, never a shim.
    if platform != 'android':
        return None
    try:
        from .publisher_crypto import create_publisher_crypto
        _check(native is not None and callable(getattr(native, 'publisherCrypto', None)))
        return create_publisher_crypto(platform='android', native=native.publisherCrypto())
    except (ImportError, AttributeError, TypeError, ValueError, GameDataError) as error:
        raise GameDataError('game_runtime_unavailable',
            'The Android original-source cryptography runtime is unavailable on this device.', 409) from error


def _formats():
    try:
        from .publisher_apk_zip import ApkMetadata
        from .publisher_apk import verify_stream
        return ApkMetadata, verify_stream
    except ImportError as error:
        raise GameDataError('game_runtime_unavailable',
            'The original APK integrity reader is unavailable on this host.', 409) from error


def _request(request):
    if request.source_locale not in TEXT_LOCALES or any(value not in TEXT_LOCALES for value in request.target_locales):
        raise GameDataError('unsupported_game_language', 'Choose an official Infinity Nikki subtitle language.')


def _handle(handle, request):
    _check(isinstance(handle, dict) and handle.get('policy') == POLICY and handle.get('request') == request.json() and
           handle.get('stage') in ('native-bootstrap', 'content-reader', 'global-launcher-bootstrap', 'global-sdk-source',
                                   'global-build-manifests', 'global-build-source',
                                   'global-configuration-packages', 'global-configuration-source') and
           set(handle) == {'policy', 'request', 'stage', 'receipt_sha256'})
    _check(isinstance(handle['receipt_sha256'], str) and re.fullmatch('[0-9a-f]{64}', handle['receipt_sha256']))
    return handle


def _selection(artifact, crypto):
    from .infinity_nikki_release import android_source_url
    ApkMetadata, _ = _formats()
    _check(isinstance(artifact, dict) and set(artifact) == {'policy', 'request', 'website_sha256', 'url', 'total', 'etag', 'ranges'} and
           artifact['policy'] == POLICY and isinstance(artifact['website_sha256'], str) and
           re.fullmatch('[0-9a-f]{64}', artifact['website_sha256']))
    android_source_url(artifact['url'])
    _check(type(artifact['total']) is int and 22 <= artifact['total'] <= OWNER_MAX and
           isinstance(artifact['etag'], str) and STRONG_ETAG.fullmatch(artifact['etag']) and
           isinstance(artifact['ranges'], list) and 0 < len(artifact['ranges']) <= 64)
    ranges, size = [], 0
    for item in artifact['ranges']:
        _check(isinstance(item, list) and len(item) == 2 and type(item[0]) is int and isinstance(item[1], str))
        raw = base64.b64decode(item[1], validate=True)
        size += len(raw)
        _check(0 < len(raw) and size <= METADATA_MAX and 0 <= item[0] <= artifact['total'] - len(raw))
        for at, previous in ranges:
            left, right = max(item[0], at), min(item[0] + len(raw), at + len(previous))
            if left < right:
                _check(raw[left - item[0]:right - item[0]] == previous[left - at:right - at])
        ranges.append((item[0], raw))
    def read(start, count):
        for at, raw in ranges:
            if at <= start and start + count <= at + len(raw):
                return raw[start - at:start - at + count]
        raise GameDataError('publisher_metadata_incomplete', 'Check the original installer size again.')
    options = {'maximum_metadata': METADATA_MAX}
    if crypto is not None:
        options['crypto'] = crypto
    archive = ApkMetadata(read, artifact['total'], **options)
    selected = archive.member(NATIVE_MEMBER, maximum=NATIVE_MAX)
    entry = archive.entries[NATIVE_MEMBER]
    _check(entry['method'] in (0, 8) and 0 < entry['packed'] <= NATIVE_MAX)
    return archive, selected, entry


def _revision(artifact):
    return 'native-' + _sha(_json({key: artifact[key] for key in ('url', 'total', 'etag')}))[:24]


def _plan(artifact, handle, archive, entry):
    message = QUOTE
    if artifact['request']['region'] == 'global':
        message += (' The following Global metadata step currently requires Windows publisher-signature '
                    'verification; that continuation is not yet available on Android.')
    return GameDataPlan(_revision(artifact), artifact['total'],
        entry['packed'] + entry['plain'] + len(_json(artifact)) + 64 * 1024,
        handle, runtime_available=True, stage='native-bootstrap', message=message)


def _decode(source, target, entry, check):
    digest, crc, count = hashlib.sha256(), 0, 0
    decoder = zlib.decompressobj(-15) if entry['method'] == 8 else None
    with source.open('rb') as packed, target.open('xb') as output:
        while raw := packed.read(64 * 1024):
            check()
            if decoder:
                while raw:
                    value = decoder.decompress(raw, min(1024**2, entry['plain'] - count + 1))
                    raw = decoder.unconsumed_tail
                    _check(not decoder.unused_data)
                    count += len(value)
                    _check(count <= entry['plain'])
                    output.write(value)
                    digest.update(value)
                    crc = zlib.crc32(value, crc)
            else:
                count += len(raw)
                _check(count <= entry['plain'])
                output.write(raw)
                digest.update(raw)
                crc = zlib.crc32(raw, crc)
        _check(count == entry['plain'] and crc & 0xffffffff == entry['crc'] and
               (decoder is None or decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail))
        output.flush()
        os.fsync(output.fileno())
    return digest.hexdigest()


def _native_owner(path, digest, check):
    from .infinity_nikki_pak_material import extract_default_pak_material
    _no_links(path)
    _check(path.is_file() and 64 <= path.stat().st_size <= NATIVE_MAX)
    check()
    raw = path.read_bytes()
    _check(_sha(raw) == digest)
    # This follows the actual wrapper/index consumers to the registered static
    # producer. It neither executes instructions nor authorizes any ciphertext.
    material = extract_default_pak_material(raw, expected_native_sha256=digest)
    _check(material.source_sha256 == digest)
    check()


def _retained(handle, ctx):
    receipt = _read(ctx, handle['receipt_sha256'])
    _check(receipt.get('policy') == POLICY and receipt.get('request') == ctx.request.json() and
           receipt.get('native_consumer_checked') is True and isinstance(receipt.get('module_sha256'), str) and
           re.fullmatch('[0-9a-f]{64}', receipt['module_sha256']) and
           receipt.get('verified', {}).get('whole_apk_v2_integrity_verified') is True)
    path = _path(ctx, receipt['module_sha256'] + '.so')
    _check(path.is_file() and 64 <= path.stat().st_size == receipt['module_plain_bytes'] <= NATIVE_MAX)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    _check(digest == receipt['module_sha256'])
    return receipt


class InfinityNikkiGameDataProvider:
    title = 'Infinity Nikki'

    def __init__(self, platform, native=None, transport_factory=PublisherTransport):
        if platform not in {'windows', 'linux', 'macos', 'desktop', 'android'}:
            raise ValueError('Unsupported Infinity Nikki preparation host')
        self.platform, self.native, self.transport_factory = platform, native, transport_factory

    @_guard
    def plan(self, request, ctx):
        _request(request)
        ctx.check()
        if getattr(ctx, 'stage_handle', None) is not None:
            previous = _handle(ctx.stage_handle, request)
            if previous['stage'] in ('global-configuration-packages', 'global-configuration-source'):
                from . import infinity_nikki_configuration_stage
                return infinity_nikki_configuration_stage.plan(self, previous, ctx)
            if previous['stage'] in ('global-build-manifests', 'global-build-source'):
                from . import infinity_nikki_build_stage
                return infinity_nikki_build_stage.plan(self, previous, ctx)
            if previous['stage'] in ('content-reader', 'global-launcher-bootstrap', 'global-sdk-source'):
                from . import infinity_nikki_sdk_stage
                return infinity_nikki_sdk_stage.plan(self, previous, ctx)
        crypto = _crypto(self.platform, self.native)
        from .infinity_nikki_release import parse_android_link, MAX_PAGE
        ApkMetadata, _ = _formats()
        transport = self.transport_factory(ctx, hosts={'infinitynikki.nuanpaper.com', APK_HOST})
        raw, _receipt = transport.fetch_bytes(HOMEPAGE, limit=MAX_PAGE, kind='metadata')
        url = parse_android_link(raw)
        first, identity = transport.fetch_bytes(url, limit=4, expected_size=4, kind='metadata', original_range=(0, 4, None))
        _check(first == b'PK\x03\x04' and identity.original_range is not None and
               identity.original_range[:2] == (0, 4) and identity.response_etag is not None)
        total, etag = identity.original_range[2], identity.response_etag
        _check(type(total) is int and 22 <= total <= OWNER_MAX and STRONG_ETAG.fullmatch(etag))
        ranges = []
        def read(start, count):
            value, _receipt = transport.fetch_bytes(url, limit=count, expected_size=count, kind='metadata',
                original_range=(start, count, total), headers={'If-Match': etag})
            ranges.append([start, base64.b64encode(value).decode('ascii')])
            return value
        options = {'maximum_metadata': METADATA_MAX}
        if crypto is not None:
            options['crypto'] = crypto
        archive = ApkMetadata(read, total, **options)
        archive.member(NATIVE_MEMBER, maximum=NATIVE_MAX)
        entry = archive.entries[NATIVE_MEMBER]
        _check(0 < entry['packed'] <= NATIVE_MAX)
        artifact = {'policy': POLICY, 'request': request.json(), 'website_sha256': _sha(raw),
                    'url': url, 'total': total, 'etag': etag, 'ranges': ranges}
        serialized = _json(artifact)
        _check(len(serialized) <= ARTIFACT_MAX)
        digest = _sha(serialized)
        ctx.check()
        _save(_path(ctx, digest + '.json'), serialized)
        handle = {'policy': POLICY, 'request': request.json(), 'stage': 'native-bootstrap', 'receipt_sha256': digest}
        return _plan(artifact, handle, archive, entry)

    @_guard
    def download(self, plan, ctx):
        handle = _handle(plan.handle, ctx.request)
        if handle['stage'] in ('global-configuration-packages', 'global-configuration-source'):
            from . import infinity_nikki_configuration_stage
            return infinity_nikki_configuration_stage.download(self, plan, ctx)
        if handle['stage'] in ('global-build-manifests', 'global-build-source'):
            from . import infinity_nikki_build_stage
            return infinity_nikki_build_stage.download(self, plan, ctx)
        if handle['stage'] in ('global-launcher-bootstrap', 'global-sdk-source'):
            from . import infinity_nikki_sdk_stage
            return infinity_nikki_sdk_stage.download(self, plan, ctx)
        _check(handle['stage'] == plan.stage == 'native-bootstrap')
        crypto = _crypto(self.platform, self.native)
        artifact = _read(ctx, handle['receipt_sha256'])
        _check(artifact.get('request') == ctx.request.json())
        archive, selected, entry = _selection(artifact, crypto)
        _check(plan == _plan(artifact, handle, archive, entry))
        _, verify_stream = _formats()
        transport = self.transport_factory(ctx, hosts={APK_HOST})
        root = _path(ctx, handle['receipt_sha256'] + '.json').parent
        with tempfile.TemporaryDirectory(dir=root, prefix='pending-') as pending:
            pending = Path(pending)
            compressed, decoded = pending / 'native.packed', pending / 'native.so'
            with compressed.open('xb') as output:
                def consume(stream):
                    class WitnessStream:
                        at = 0
                        def read(self, count):
                            raw = stream.read(count)
                            for start, expected in archive.witnesses:
                                left, right = max(self.at, start), min(self.at + len(raw), start + len(expected))
                                if left < right:
                                    _check(raw[left - self.at:right - self.at] == expected[left - start:right - start])
                            self.at += len(raw)
                            return raw
                    options = {'crypto': crypto} if crypto is not None else {}
                    return verify_stream(WitnessStream(), archive.layout, member=selected, member_sink=output, **options)
                verified, transfer = transport.consume_stream(artifact['url'], consume, limit=artifact['total'],
                    expected_size=artifact['total'], kind='asset', headers={'If-Match': artifact['etag']})
            _check(compressed.stat().st_size == entry['packed'])
            digest = _decode(compressed, decoded, entry, ctx.check)
            _native_owner(decoded, digest, ctx.check)
            receipt = {'policy': POLICY, 'request': ctx.request.json(), 'revision': plan.revision,
                'artifact_sha256': handle['receipt_sha256'], 'module_name': NATIVE_MEMBER,
                'module_sha256': digest, 'module_plain_bytes': entry['plain'],
                'module_crc32': f"{entry['crc']:08x}", 'native_consumer_checked': True,
                'verified': verified, 'transfer': transfer.json(), 'bootstrap_region': 'cn',
                'global_android_client_accepted': False, 'publisher_certificate_independently_pinned': False}
            serialized = _json(receipt)
            receipt_digest = _sha(serialized)
            target = _path(ctx, digest + '.so')
            ctx.check()
            if target.exists():
                with target.open('rb') as stream:
                    _check(hashlib.file_digest(stream, 'sha256').hexdigest() == digest)
            else:
                atomic_replace(decoded, target)
            _save(_path(ctx, receipt_digest + '.json'), serialized)
            ctx.check()
        return PreparationStage({'policy': POLICY, 'request': ctx.request.json(), 'stage': 'content-reader',
                                 'receipt_sha256': receipt_digest}, GATE)

    @_guard
    def restore(self, handle, ctx):
        _handle(handle, ctx.request)
        if handle['stage'] in ('global-configuration-packages', 'global-configuration-source'):
            from . import infinity_nikki_configuration_stage
            return infinity_nikki_configuration_stage.restore(self, handle, ctx)
        if handle['stage'] in ('global-build-manifests', 'global-build-source'):
            from . import infinity_nikki_build_stage
            return infinity_nikki_build_stage.restore(self, handle, ctx)
        if handle['stage'] in ('global-launcher-bootstrap', 'global-sdk-source'):
            from . import infinity_nikki_sdk_stage
            return infinity_nikki_sdk_stage.restore(handle, ctx)
        if handle['stage'] == 'content-reader':
            _retained(handle, ctx)
        raise GameDataError('publisher_content_reader_unresolved', GATE, 409)


def create_provider(platform, native=None, *, transport_factory=PublisherTransport):
    return InfinityNikkiGameDataProvider(platform, native, transport_factory)
