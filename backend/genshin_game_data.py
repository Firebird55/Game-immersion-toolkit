"""Accounted original Genshin native-input stage, never a partial dialogue index.

The launcher manifest and complete selected source files come from the publisher.
Original dispatch, remaining bindings and Subtitle acquisition still gate the
next content stage. Missing host readers cannot trigger large source transfers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import sophon_assets as sophon
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .publisher_transport import PublisherTransport

SCHEMA = 'genshin-original-native-input-stage-v1'
PLATFORMS = {'android', 'windows', 'linux', 'macos'}
TEXT_LOCALES = {'en', 'zh-Hans', 'zh-Hant', 'ja', 'ko', 'de', 'fr', 'es-ES',
                'pt-BR', 'th', 'ru', 'vi', 'id', 'it', 'tr'}
VOICE_LOCALES = {'en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'}


class GenshinRuntime:
    """Explicit installed Windows BLB closure; never builds or downloads helpers."""
    def __init__(self, layout):
        self.layout = layout
        self.helper = self.validate()

    def validate(self):
        # Lazy desktop imports keep the metadata-stage module Android-safe.
        from .prebuilt_readers import prebuilt_reader
        from .genshin_blb import Helper
        from .genshin_native_x64 import decoder
        reader = prebuilt_reader('genshin', layout=self.layout)
        decoder()
        identity = hashlib.sha256((reader.source_identity + reader.manifest['build_id']).encode()).hexdigest()
        return Helper((str(reader.executable),), identity)


class _UnplannedTransfer(Exception):
    pass


def _offline(*args, **kwargs):
    raise _UnplannedTransfer()


def _safe(path):
    path = Path(path).absolute()
    _no_links(path)
    return path


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _revision(build):
    return 'genshin-native-' + hashlib.sha256(_canonical(build)).hexdigest()


def _selection(request):
    if (request.source_locale not in TEXT_LOCALES or set(request.target_locales) - TEXT_LOCALES
            or request.content_mode == 'text-audio' and request.source_locale not in VOICE_LOCALES):
        raise GameDataError('genshin_languages', 'Choose official Genshin text languages and, when requested, an official dub.')
    return request.json()


def _names(region):
    stem = 'GenshinImpact' if region == 'global' else 'YuanShen'
    return (stem + '.exe', stem + '_Data/Native/Data/Metadata/global-metadata.dat')


def _valid(path, digest, size):
    path = _safe(path)
    try:
        if not path.is_file() or path.stat().st_size != size:
            return False
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'md5').hexdigest() == digest
    except OSError:
        return False


def _source(cache, asset):
    return _safe(cache / 'sources' / asset.digest)


def _files(cache, build, region, fetch):
    spec = tuple(build['manifests']['game'])
    _safe(cache / 'manifests' / spec[4])
    wanted = _names(region)
    files = sophon.manifest(cache, build['channel'], spec, wanted, fetch=fetch)
    if set(files) != set(wanted):
        raise GameDataError('genshin_original_source_missing', 'The complete original Genshin native inputs are unavailable.')
    for asset in files.values():
        maximum = 768 * 1024**2 if asset.name.endswith('.exe') else 256 * 1024**2
        if not 512 <= asset.size <= maximum:
            raise GameDataError('genshin_original_source_bounds', 'The original Genshin native inputs exceed their supported bounds.')
        for _, _, _, _, digest in asset.chunks:
            _safe(cache / 'chunks' / digest)
    return files


def _quote(cache, files):
    chunks, originals, pending = {}, [], 0
    for name, asset in sorted(files.items()):
        cached = _valid(_source(cache, asset), asset.digest, asset.size)
        originals.append({'name': name, 'md5': asset.digest, 'bytes': asset.size, 'cached': cached})
        if cached:
            continue
        pending += asset.size
        for _, size, compressed, identity, digest in asset.chunks:
            row = {'md5': digest, 'bytes': size, 'compressed_bytes': compressed,
                   'urls': [asset.prefix + '/' + identity],
                   'cached': _valid(cache / 'chunks' / digest, digest, size)}
            previous = chunks.get(digest)
            if previous:
                if (previous['bytes'], previous['compressed_bytes']) != (size, compressed):
                    raise GameDataError('genshin_source_identity_changed', 'The original Genshin source sizes disagree.')
                row['urls'] = sorted(set(previous['urls'] + row['urls']))
            chunks[digest] = row
    rows = [row for _, row in sorted(chunks.items())]
    missing = [row for row in rows if not row['cached']]
    transfer = sum(row['compressed_bytes'] for row in missing)
    # Includes complete materialized files, verified expanded cache, one chunk's
    # atomic staging, and a bounded receipt; it is not a complete game quote.
    disk = pending + sum(row['bytes'] for row in missing) + max((row['bytes'] for row in missing), default=0) + 1024**2
    return {'files': originals, 'chunks': rows}, transfer, disk


def _record(ctx, handle):
    target = _safe(ctx.directory / 'original-native-inputs.json')
    pending = _safe(ctx.directory / 'original-native-inputs.pending')
    ctx.check()
    pending.write_bytes(_canonical(handle))
    ctx.check()
    pending.replace(target)
    message = ('Official Genshin manifest verified. Check the native source download size next.'
        if handle['phase'] == 'official-manifest' else
        'Original Genshin native inputs verified. Dialogue and audio still need the next supported source stage.')
    return PreparationStage(handle, message)


class GenshinGameDataProvider:
    title = 'Genshin Impact'

    def __init__(self, *, platform, native=None, transport_factory=PublisherTransport):
        if platform not in PLATFORMS:
            raise GameDataError('unsupported_game_data_platform', 'This game data platform is unsupported.')
        self.platform, self.runtime, self.transport_factory = platform, native, transport_factory

    def _reader(self):
        if self.platform != 'windows' or not isinstance(self.runtime, GenshinRuntime):
            return None
        try:
            return self.runtime.validate()
        except (ImportError, OSError, ValueError):
            return None

    def _fetch(self, ctx, *, kind, allowed=None):
        (launcher, _, downloader), _, _, publisher = sophon.CHANNELS['genshin-' + ctx.request.region]
        transport = self.transport_factory(ctx, hosts={launcher, downloader, publisher})
        def fetch(url, *, limit):
            ctx.check()
            if allowed is not None and url not in allowed:
                raise GameDataError('game_data_plan_changed', 'Check the Genshin source download size again.', 409)
            raw, _ = transport.fetch_bytes(url, limit=limit, kind=kind)
            return raw
        return fetch

    def plan(self, request, ctx):
        selection = _selection(request)
        if ctx.game != 'genshin' or ctx.request != request:
            raise GameDataError('game_data_plan_changed', 'Check the selected Genshin languages again.', 409)
        ctx.check()
        reader = self._reader()
        if reader is None:
            return GameDataPlan('genshin-reader-unavailable', None, None, stage='original-runtime',
                message='The verified Genshin original-container reader is unavailable on this device.')
        with ctx.transfer_lock:
            cache = _safe(ctx.cache_directory / 'genshin-original' / request.region)
            build = sophon.release('genshin-' + request.region, fetch=self._fetch(ctx, kind='metadata'))
            revision = _revision(build)
            handle = {'schema': SCHEMA, 'game': 'genshin', 'request': selection, 'build': build,
                      'revision': revision, 'runtime_identity': reader.identity}
            spec = tuple(build['manifests']['game'])
            if not (0 < spec[2] <= sophon.MAX_MANIFEST and 0 < spec[3] <= sophon.MAX_MANIFEST):
                raise GameDataError('genshin_manifest_bounds', 'The official Genshin manifest exceeds its supported bounds.')
            if not _valid(cache / 'manifests' / spec[4], spec[4], spec[3]) and spec[2] > ctx.remaining_bytes(kind='metadata'):
                return GameDataPlan(revision, spec[2], spec[3] * 2 + 1024**2, handle=handle,
                    runtime_available=True, download_is_upper_bound=True, stage='official-manifest',
                    message='Download the official Genshin manifest first, then check the native source size.')
            files = _files(cache, build, request.region, self._fetch(ctx, kind='metadata'))
            ledger, transfer, disk = _quote(cache, files)
            if all(row['cached'] for row in ledger['files']):
                return GameDataPlan(revision, None, None, handle=handle, stage='original-content-reader',
                    message='Original Genshin native inputs are verified. Official bootstrap, remaining dialogue bindings and film subtitles still need a supported source stage.')
            handle['ledger'] = ledger
            return GameDataPlan(revision, transfer, disk, handle=handle, download_is_upper_bound=True,
                runtime_available=True, stage='official-native-inputs',
                message='Download the complete official Genshin native reader inputs. This stage does not prepare dialogue or audio.')

    def download(self, plan, ctx):
        selection = _selection(ctx.request)
        handle, build = plan.handle, plan.handle.get('build', {})
        reader = self._reader()
        if (ctx.game != 'genshin' or handle.get('schema') != SCHEMA or handle.get('game') != 'genshin'
                or handle.get('request') != selection or build.get('channel') != 'genshin-' + ctx.request.region
                or plan.revision != handle.get('revision') or plan.revision != _revision(build)
                or plan.stage not in {'official-manifest', 'official-native-inputs'} or not plan.runtime_available
                or reader is None or handle.get('runtime_identity') != reader.identity):
            raise GameDataError('game_data_plan_changed', 'Check the Genshin source download again.', 409)
        with ctx.transfer_lock:
            cache = _safe(ctx.cache_directory / 'genshin-original' / ctx.request.region)
            ctx.check()
            if plan.stage == 'official-manifest':
                spec = tuple(build['manifests']['game'])
                if (plan.download_bytes, plan.required_disk_bytes) != (spec[2], spec[3] * 2 + 1024**2):
                    raise GameDataError('game_data_plan_changed', 'Check the Genshin manifest size again.', 409)
                _files(cache, build, ctx.request.region,
                       self._fetch(ctx, kind='asset', allowed={spec[0] + '/' + spec[1]}))
                return _record(ctx, {**handle, 'phase': 'official-manifest'})
            try:
                files = _files(cache, build, ctx.request.region, _offline)
            except _UnplannedTransfer as error:
                raise GameDataError('game_data_plan_changed', 'The cached Genshin manifest changed. Check its size again.', 409) from error
            ledger, transfer, disk = _quote(cache, files)
            if handle.get('ledger') != ledger or (plan.download_bytes, plan.required_disk_bytes) != (transfer, disk):
                raise GameDataError('game_data_plan_changed', 'The cached Genshin sources changed. Check their size again.', 409)
            fetch = self._fetch(ctx, kind='asset', allowed={url for row in ledger['chunks'] if not row['cached'] for url in row['urls']})
            receipts = []
            for asset in files.values():
                destination = _source(cache, asset)
                if not _valid(destination, asset.digest, asset.size):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    pending = _safe(destination.with_suffix('.pending'))
                    try:
                        with pending.open('wb') as stream:
                            for offset in range(0, asset.size, 8 * 1024**2):
                                ctx.check()
                                stream.write(asset.read(cache, offset, min(8 * 1024**2, asset.size - offset), fetch=fetch))
                        if not _valid(pending, asset.digest, asset.size):
                            raise GameDataError('genshin_original_source_invalid', 'An original Genshin native input failed its whole-file checksum.')
                        ctx.check()
                        pending.replace(destination)
                    except ValueError as error:
                        raise GameDataError('genshin_original_source_invalid',
                            'An original Genshin native input failed its whole-file checksum.') from error
                    finally:
                        pending.unlink(missing_ok=True)
                with destination.open('rb') as stream:
                    content_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
                receipts.append({'name': asset.name, 'publisher_md5': asset.digest, 'bytes': asset.size, 'sha256': content_sha})
            return _record(ctx, {**{k: v for k, v in handle.items() if k != 'ledger'},
                                 'phase': 'official-native-inputs', 'sources': receipts})

    def restore(self, handle, ctx):
        ctx.check()
        raise GameDataError('genshin_native_inputs_only', 'Original Genshin source files are not a prepared dialogue library.', 409)


def create_provider(*, platform, native=None):
    return GenshinGameDataProvider(platform=platform, native=native)
