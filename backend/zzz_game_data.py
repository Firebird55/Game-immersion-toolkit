"""Accounted official ZZZ bootstrap and PC text preparation stages.

The original publisher sources are data. Source stages never pretend that
archives are a prepared dialogue library. PC text uses a verified frozen
reader; Android and complete selected-dub materialization remain explicit gates.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

from . import hoyo_dispatch_metadata, hoyo_zzz_bootstrap as bootstrap, sophon_assets as sophon
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .publisher_transport import PublisherTransport

SCHEMA = 'zzz-official-bootstrap-stage-v1'
PLATFORMS = frozenset(('android', 'windows', 'linux', 'macos'))
TEXT_LOCALES = frozenset(('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko', 'de', 'fr', 'es-ES',
                         'pt-BR', 'th', 'ru', 'vi', 'id'))
VOICE_LOCALES = frozenset(('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'))


class _MissingBootstrap(Exception):
    pass


def _no_transfer(*args, **kwargs):
    raise _MissingBootstrap()


def _safe(path):
    path = Path(path).absolute()
    for item in reversed((path, *path.parents)):
        if item.is_symlink() or item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise GameDataError('unsafe_game_cache', 'The game source cache must use ordinary private files.')
    return path


def _selection(request):
    if (request.region not in ('global', 'cn') or request.content_mode not in ('text', 'text-audio')
            or request.source_locale not in TEXT_LOCALES
            or request.content_mode == 'text-audio' and request.source_locale not in VOICE_LOCALES):
        raise GameDataError('zzz_languages', 'Choose official ZZZ text languages and, when requested, an official dub.')
    return request.json()


def _revision(build):
    # Original launcher generation, independent of content mode/locales. The
    # later content generation must additionally pin actual hotfix identities.
    return 'zzz-bootstrap-' + hashlib.sha256(json.dumps(build, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _cache(ctx):
    return _safe(Path(ctx.cache_directory) / 'zzz-original' / ctx.request.region)


def _files(build, cache, fetch):
    spec = tuple(build['manifests']['game'])
    _safe(cache / 'manifests' / spec[4])
    files = sophon.manifest(cache, build['channel'], spec,
                           (bootstrap.RESOURCE, bootstrap.NATIVE_RESOURCE), fetch=fetch)
    if set(files) != {bootstrap.RESOURCE, bootstrap.NATIVE_RESOURCE}:
        raise GameDataError('zzz_bootstrap_source_missing', 'The official ZZZ bootstrap files are unavailable.')
    for asset in files.values():
        for chunk in asset.chunks:
            _safe(cache / 'chunks' / chunk[4])
    return files


def _valid_file(path, digest, size):
    path = _safe(path)
    try:
        if not path.is_file() or path.stat().st_size != size:
            return False
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'md5').hexdigest() == digest
    except OSError:
        return False


def _cached(cache, digest, size):
    return _valid_file(cache / 'chunks' / digest, digest, size)


def _record_stage(ctx, result, message):
    raw = json.dumps(result, sort_keys=True, separators=(',', ':')).encode()
    ctx.check()
    pending = _safe(ctx.directory / 'bootstrap-source.pending')
    destination = _safe(ctx.directory / 'bootstrap-source.json')
    pending.write_bytes(raw)
    ctx.check()
    pending.replace(destination)
    return PreparationStage(result, message)


def _quote(files, native, cache):
    # Resource object/name metadata can require additional original chunks. A
    # complete-container bound is explicit; download still reads only the exact
    # original app_version/login_setting objects, not unrelated resource bodies.
    rows = {}
    sections = {item['md5'] for item in native['chunks']}
    for name, asset in files.items():
        for _, expanded, compressed, identity, digest in asset.chunks:
            if name == bootstrap.NATIVE_RESOURCE and digest not in sections:
                continue
            url = asset.prefix + '/' + identity
            if digest in rows:
                if rows[digest]['expanded_bytes'] != expanded:
                    raise GameDataError('zzz_source_identity_changed', 'The official ZZZ source sizes disagree.')
                rows[digest]['compressed_bytes'] = max(rows[digest]['compressed_bytes'], compressed)
                rows[digest]['urls'].add(url)
            else:
                rows[digest] = {'md5': digest, 'expanded_bytes': expanded, 'compressed_bytes': compressed,
                                'urls': {url}, 'cached': _cached(cache, digest, expanded)}
    result = [{**row, 'urls': sorted(row['urls'])} for _, row in sorted(rows.items())]
    missing = [row for row in result if not row['cached']]
    network = sum(row['compressed_bytes'] for row in missing)
    disk = sum(row['expanded_bytes'] for row in missing)
    # Include an atomic-write staging file and bounded source receipt overhead.
    disk += max((row['expanded_bytes'] for row in missing), default=0) + 1024**2
    return result, network, disk


class ZzzGameDataProvider:
    title = 'Zenless Zone Zero'

    def __init__(self, *, platform, native=None, transport_factory=PublisherTransport, reader_resolver=None, codec_layout=None):
        if platform not in PLATFORMS:
            raise GameDataError('unsupported_game_data_platform', 'This game data platform is unsupported.')
        self.platform, self.transport_factory = platform, transport_factory
        self.reader_resolver = reader_resolver
        self.codec_layout = codec_layout
        self._audio_verification = {}
        # No desktop helper or speculative native method is a portable reader.

    def _reader(self):
        if self.platform == 'android':return None
        from .prebuilt_node_reader import production_zzz_reader
        from .preparation_errors import PreparationFailure
        try:return (self.reader_resolver or production_zzz_reader)()
        except PreparationFailure:return None

    def _codecs(self):
        if self.platform == 'android':return None
        from .zzz_owned_audio import available_codecs
        return available_codecs(layout=self.codec_layout)

    def _verification(self, ctx):
        key = str(Path(ctx.cache_directory).absolute()), ctx.request.region
        if key not in self._audio_verification:
            if len(self._audio_verification) >= 16:self._audio_verification.pop(next(iter(self._audio_verification)))
            self._audio_verification[key] = {}
        return self._audio_verification[key]

    def _fetch(self, ctx, *, kind, allowed=None):
        channel = 'zzz-' + ctx.request.region
        (launcher, _, downloader), _, _, publisher = sophon.CHANNELS[channel]
        transport = self.transport_factory(ctx, hosts={launcher, downloader, publisher})
        def fetch(url, *, limit):
            ctx.check()
            if allowed is not None and url not in allowed:
                raise GameDataError('game_data_plan_changed', 'The required source changed. Check the download size again.', 409)
            raw, _receipt = transport.fetch_bytes(url, limit=limit, kind=kind)
            return raw
        return fetch

    def plan(self, request, ctx):
        selection = _selection(request)
        if ctx.request != request or ctx.game != 'zzz':
            raise GameDataError('game_data_plan_changed', 'Check the selected ZZZ download again.', 409)
        ctx.check()
        with ctx.transfer_lock:
            cache = _cache(ctx)
            fetch = self._fetch(ctx, kind='metadata')
            build = sophon.release('zzz-' + request.region, fetch=fetch)
            revision = _revision(build)
            handle = {'schema': SCHEMA, 'game': 'zzz', 'request': selection, 'build': build, 'revision': revision}
            spec = tuple(build['manifests']['game'])
            if not (0 < spec[2] <= sophon.MAX_MANIFEST and 0 < spec[3] <= sophon.MAX_MANIFEST):
                raise GameDataError('zzz_manifest_bounds', 'The original ZZZ manifest exceeds the supported source bounds.')
            if (not _valid_file(cache / 'manifests' / spec[4], spec[4], spec[3])
                    and spec[2] > ctx.remaining_bytes(kind='metadata')):
                return GameDataPlan(revision, spec[2], spec[3] * 2 + 1024**2,
                    handle=handle, runtime_available=True, stage='official-manifest',
                    message='Download the original ZZZ manifest first, then check the remaining source size.')
            files = _files(build, cache, fetch)
            try:
                config = bootstrap.official(build, request.region, cache, fetch=_no_transfer)
            except _MissingBootstrap:
                pass
            else:
                handle['bootstrap_proof'] = hoyo_dispatch_metadata.provenance(config)
                reader = self._reader()
                if reader is not None:
                    from . import zzz_pc_stages
                    options = {'codecs': self._codecs()} if request.content_mode == 'text-audio' else {}
                    return zzz_pc_stages.plan(ctx, build, cache, reader, transport_factory=self.transport_factory, **options)
                ctx.check()
                return GameDataPlan(revision, None, None, handle=handle, runtime_available=False,
                    stage='catalogue-runtime', message='Official ZZZ bootstrap verified. Dialogue preparation is not available on this device yet.')
            _, _, native = bootstrap.native_source_plan(build, cache, fetch=fetch)
            containers, network, disk = _quote(files, native, cache)
            handle['containers'], handle['native_source'] = containers, native
            ctx.check()
            return GameDataPlan(revision, network, disk, handle=handle, download_is_upper_bound=True,
                runtime_available=True, stage='official-bootstrap',
                message='Download original ZZZ bootstrap sources first. This stage does not prepare dialogue or audio.')

    def download(self, plan, ctx):
        if plan.handle.get('schema') == 'zzz-pc-official-text-v1':
            reader = self._reader()
            if reader is None:raise GameDataError('zzz_reader_unavailable', 'The verified ZZZ reader is unavailable on this device.')
            from . import zzz_pc_stages
            with ctx.transfer_lock:
                options = {'codecs': self._codecs(), 'verification': self._verification(ctx)} if ctx.request.content_mode == 'text-audio' else {}
                return zzz_pc_stages.download(ctx, plan, reader, transport_factory=self.transport_factory, **options)
        selection = _selection(ctx.request)
        handle = plan.handle
        if (handle.get('schema') != SCHEMA or handle.get('game') != 'zzz' or handle.get('request') != selection
                or plan.stage not in ('official-manifest', 'official-bootstrap') or not plan.runtime_available
                or handle.get('build', {}).get('channel') != 'zzz-' + ctx.request.region
                or plan.revision != handle.get('revision') or plan.revision != _revision(handle['build'])):
            raise GameDataError('game_data_plan_changed', 'Check the selected ZZZ download again.', 409)
        with ctx.transfer_lock:
            ctx.check()
            cache, build = _cache(ctx), handle['build']
            if plan.stage == 'official-manifest':
                spec = tuple(build['manifests']['game'])
                if plan.download_bytes != spec[2] or plan.required_disk_bytes != spec[3] * 2 + 1024**2:
                    raise GameDataError('game_data_plan_changed', 'Check the ZZZ manifest download size again.', 409)
                _files(build, cache, self._fetch(ctx, kind='asset', allowed={spec[0] + '/' + spec[1]}))
                return _record_stage(ctx, {'schema': SCHEMA, 'game': 'zzz', 'request': selection,
                    'revision': plan.revision, 'build': build, 'phase': 'official-manifest',
                    'manifest_md5': spec[4], 'manifest_bytes': spec[3]},
                    'Original ZZZ manifest verified. Check the next download size to continue.')
            # Existing metadata must still be authentic. Its repair is another
            # estimate, not an unplanned connection charged to source payloads.
            try:
                files = _files(build, cache, _no_transfer)
                _, _, native = bootstrap.native_source_plan(build, cache, fetch=_no_transfer)
            except _MissingBootstrap as error:
                raise GameDataError('game_data_plan_changed', 'The cached ZZZ metadata changed. Check its size again.', 409) from error
            current, network, disk = _quote(files, native, cache)
            if current != handle.get('containers') or native != handle.get('native_source') or network != plan.download_bytes or disk != plan.required_disk_bytes:
                raise GameDataError('game_data_plan_changed', 'The cached ZZZ source changed. Check its size again.', 409)
            allowed = {url for row in current if not row['cached'] for url in row['urls']}
            config = bootstrap.official(build, ctx.request.region, cache,
                                        fetch=self._fetch(ctx, kind='asset', allowed=allowed))
            proof = hoyo_dispatch_metadata.provenance(config)
            result = {'schema': SCHEMA, 'game': 'zzz', 'request': selection, 'revision': plan.revision,
                      'build': build, 'bootstrap_proof': proof}
            # Only inert source identity/provenance is persisted; no RSA object,
            # plaintext XML, decoded seed/config, callable or host path escapes.
            return _record_stage(ctx, result,
                'Original ZZZ bootstrap verified. Dialogue preparation still needs a supported reader.')

    def restore(self, handle, ctx):
        ctx.check()
        if self.platform == 'android' and isinstance(handle, dict) and handle.get('schema') in (
                'zzz-pc-official-audio-v1', 'zzz-pc-official-text-v1'):
            raise GameDataError('zzz_reader_unavailable', 'The verified ZZZ reader is unavailable on this device.')
        if isinstance(handle, dict) and handle.get('schema') == 'zzz-pc-official-audio-v1':
            from . import zzz_pc_audio
            return zzz_pc_audio.restore(ctx, handle, self._codecs(), transport_factory=self.transport_factory,
                                       verification=self._verification(ctx))
        if isinstance(handle, dict) and handle.get('schema') == 'zzz-pc-official-text-v1':
            from . import zzz_pc_stages
            return zzz_pc_stages.restore(ctx, handle)
        raise GameDataError('zzz_bootstrap_only', 'Original ZZZ bootstrap sources are not a prepared dialogue library.', 409)


def create_provider(*, platform, native=None):
    return ZzzGameDataProvider(platform=platform, native=native)
