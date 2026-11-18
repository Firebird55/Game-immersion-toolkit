"""Context-owned original NTE downloads and verified offline text sources.

Bootstrap, archive and native processing are explicit preparation stages.
Text + audio and non-Windows native reading retain their separate gates.
No downloaded game/SDK code is executed by this provider.
"""
from pathlib import Path

from . import nte_updater_source as source
from . import nte_updater_baseline as baseline
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .publisher_transport import PublisherTransport


STUDY = frozenset(('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'))
TARGETS = STUDY | {'fr', 'de', 'es-ES', 'ru'}
STAGE = 'nte-original-updater-stage-v1'


def _artifacts(inputs):
    # The frozen historical pair is often identical to the current pair. A
    # shared artifact is planned/acquired once, including after a launcher update.
    return {item.identity: item for plan in (inputs, baseline.inputs()) for item in plan.artifacts}.values()


def _costs(inputs, cache):
    missing = _missing(inputs, cache)
    return {'compressed_bytes': sum(item.packed_size for item in missing),
            'decoded_bytes': sum(item.size for item in missing)}


def _missing(inputs, cache):
    missing = [item for item in _artifacts(inputs) if source.retained(cache, item) is None]
    if len({item.url for item in missing}) != len(missing):
        raise GameDataError('historical_source_changed',
            'A required older NTE compatibility download changed. Your previous library is retained.')
    return missing


class NteGameDataProvider:
    title = 'Neverness to Everness'

    def __init__(self, *, platform, native=None, opener=None):
        if platform not in {'windows', 'android', 'linux', 'macos'}:
            raise ValueError('Unsupported NTE host platform')
        self.platform, self.native, self.opener = platform, native, opener

    def _cache(self, ctx):
        cache = Path(ctx.cache_directory)/'tools/nte-publisher/format'
        try:
            _no_links(cache)
        except ValueError as error:
            raise GameDataError('unsafe_game_cache', 'Game downloads need an ordinary private cache directory.') from error
        return cache

    def _reader(self, ctx):
        if self.platform != 'windows':
            raise GameDataError('nte_reader_unavailable',
                'A compatible NTE data reader is not available on this device. Your previous library is retained.', 409)
        from .nte_game_data_runtime import WindowsNteRuntime, resolve
        if self.platform == 'windows' and isinstance(self.native, WindowsNteRuntime):
            return self.native.reader(ctx)
        return resolve(self.platform, ctx)

    def plan(self, request, ctx):
        ctx.check()
        if request.source_locale not in STUDY or set(request.target_locales) - TARGETS:
            raise GameDataError('unsupported_game_languages', 'Choose a supported NTE study language and translation languages.')
        if request.region != 'global':
            return GameDataPlan('nte-mainland-source-pending', None, None, stage='compatibility',
                message='Mainland NTE compatibility preparation still needs its original source integration.')
        cache = self._cache(ctx)
        transport = PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener)
        metadata = {}
        def fetch(url, *, limit):
            body, _ = transport.fetch_bytes(url, limit=limit, kind='metadata')
            metadata[url] = len(body)
            return body
        inputs = source.plan(fetch=fetch)
        ctx.check()
        costs = _costs(inputs, cache)
        if costs['compressed_bytes'] == 0:
            source.resolve_retained(inputs, cache)
            baseline.parameters(cache)
            try:
                reader = self._reader(ctx)
            except GameDataError as error:
                if error.code != 'nte_reader_unavailable':
                    raise
                return GameDataPlan('nte-content-'+inputs.identity, None, None, stage='content',
                    message='Official NTE compatibility information is verified. A compatible game-content reader is still required on this device.')
            from . import nte_game_data_content as content
            return content.plan(request, ctx, inputs, reader, transport)
        handle = {'schema': STAGE, 'inputs': inputs.description(), 'inputs_sha256': inputs.identity,
                  'baseline_inputs_sha256': baseline.inputs().identity,
                  'verification_bytes': metadata, 'request': request.json()}
        return GameDataPlan('nte-bootstrap-'+inputs.identity,
            costs['compressed_bytes'] + sum(metadata.values()), costs['decoded_bytes'] + 64 * 1024,
            handle=handle, download_is_upper_bound=True, runtime_available=True, stage='compatibility',
            message='Download official NTE compatibility information, then check the game-content download size.')

    def download(self, plan, ctx):
        ctx.check()
        if plan.stage in {'audio-member-ranges', 'process-audio-bindings', 'materialize-audio', 'finalize-audio'}:
            reader = self._reader(ctx)
            from . import nte_game_data_audio as audio
            from .preparation_errors import PreparationFailure
            try:
                if plan.stage == 'process-audio-bindings': return audio.download_bindings(plan, ctx, reader)
                if plan.stage == 'materialize-audio': return audio.download_materialize(plan, ctx, reader)
                transport = PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener)
                if plan.stage == 'audio-member-ranges': return audio.download_ranges(plan, ctx, reader, transport)
                return audio.download_finalize(plan, ctx, reader, transport)
            except PreparationFailure as error:
                raise GameDataError(error.code, str(error), 409) from error
        if plan.stage in {'authored-subtitle-ranges', 'normalize-text'}:
            reader = self._reader(ctx)
            from . import nte_game_data_text as text
            transport = PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener)
            if plan.stage == 'authored-subtitle-ranges':
                return text.download_subtitles(plan, ctx, reader, transport)
            from .preparation_errors import PreparationFailure
            try:
                return text.download_text(plan, ctx, reader, transport)
            except PreparationFailure as error:
                raise GameDataError(error.code, str(error), 409) from error
        if plan.stage == 'authoring-import-ranges':
            reader = self._reader(ctx)
            from . import nte_game_data_imports as dependencies
            return dependencies.download(plan, ctx, reader,
                PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener))
        if plan.stage == 'process-authoring':
            reader = self._reader(ctx)
            from . import nte_game_data_authoring as authoring
            from .preparation_errors import PreparationFailure
            try:
                return authoring.download(plan, ctx, reader)
            except PreparationFailure as error:
                raise GameDataError(error.code, str(error), 409) from error
        if plan.stage == 'initial-descriptions':
            reader = self._reader(ctx)
            from . import nte_game_data_initial as initial
            return initial.download(plan, ctx, reader,
                PublisherTransport(ctx, hosts=source.HOSTS | initial.HOSTS, opener=self.opener))
        if plan.stage == 'dialogue-package-ranges':
            reader = self._reader(ctx)
            from . import nte_game_data_packages as packages
            return packages.download(plan, ctx, reader,
                PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener))
        if plan.stage == 'process-metadata':
            reader = self._reader(ctx)
            from . import nte_game_data_prepare as processing
            # Local processing has a true zero-byte allowance. No publisher
            # transport is constructed, and no current metadata is requested.
            return processing.download(plan, ctx, reader)
        if plan.stage == 'global-import-metadata':
            reader = self._reader(ctx)
            from . import nte_game_data_iostore as imports
            return imports.download(plan, ctx, reader,
                PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener))
        if plan.stage == 'archive-index-ranges':
            reader = self._reader(ctx)
            from . import nte_game_data_ranges as ranges
            return ranges.download(plan, ctx, reader,
                PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener))
        if plan.stage == 'original-indices':
            reader = self._reader(ctx)
            from . import nte_game_data_content as content
            return content.download(plan, ctx, reader,
                PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener))
        handle = plan.handle
        if (plan.stage != 'compatibility' or not isinstance(handle, dict)
                or set(handle) != {'schema', 'inputs', 'inputs_sha256', 'baseline_inputs_sha256', 'verification_bytes', 'request'}
                or handle['schema'] != STAGE or handle['request'] != ctx.request.json()):
            raise GameDataError('download_plan_changed', 'Check the NTE download size again.', 409)
        inputs = source._inputs(handle['inputs'])
        if (inputs.identity != handle['inputs_sha256'] or plan.revision != 'nte-bootstrap-'+inputs.identity
                or handle['baseline_inputs_sha256'] != baseline.inputs().identity):
            raise GameDataError('download_plan_changed', 'Check the NTE download size again.', 409)
        metadata = handle['verification_bytes']
        if (not isinstance(metadata, dict) or set(metadata) != {source.VERSION_URL, inputs.manifest_url}
                or any(type(count) is not int or not 0 < count <= source.MAX_MANIFEST for count in metadata.values())):
            raise GameDataError('download_plan_changed', 'Check the NTE download size again.', 409)
        cache = self._cache(ctx)
        transport = PublisherTransport(ctx, hosts=source.HOSTS, opener=self.opener)
        artifacts = {item.url: item for item in _missing(inputs, cache)}
        if sum(item.packed_size for item in artifacts.values()) + sum(metadata.values()) != plan.download_bytes:
            raise GameDataError('download_plan_changed', 'Check the NTE download size again.', 409)
        transferred = 0
        def fetch(url, *, limit):
            nonlocal transferred
            ctx.check()
            if url in artifacts:
                item = artifacts[url]
                body, receipt = transport.fetch_bytes(url, limit=item.packed_size, kind='asset',
                    expected_size=item.packed_size, digests={'md5': item.packed_md5})
            elif url in metadata:
                body, receipt = transport.fetch_bytes(url, limit=metadata[url], kind='metadata', expected_size=metadata[url])
            else:
                raise GameDataError('game_source_changed', 'NTE update information changed. Check the download size again.', 409)
            ctx.check()
            transferred += receipt.bytes
            return body
        # Serialize publication with the same account/delete/cancellation guard
        # used for transfers. Artifacts stay immutable and do not activate an index.
        with ctx.transfer_lock:
            ctx.check()
            source.resolve(inputs, cache, fetch=fetch)
            baseline.acquire(cache, fetch=fetch)
            ctx.check()
            source.recheck(inputs, fetch=fetch)
            ctx.check()
        ctx.progress('verifying', transferred, plan.download_bytes, 'Official NTE compatibility information verified.')
        return PreparationStage({'schema': STAGE, 'inputs_sha256': inputs.identity},
            'Official NTE compatibility information is downloaded. Check the remaining game-content preparation.')

    def restore(self, handle, ctx):
        ctx.check()
        if isinstance(handle, dict) and handle.get('schema') == 'nte-original-audio-snapshot-v1':
            if self.platform != 'windows':
                raise GameDataError('nte_audio_runtime_unavailable', 'A compatible original-voice runtime is required on this device.', 409)
            from .nte_game_data_audio_snapshot import restore
            from .runtime_bundle import discover_layout
            from .nte_game_data_runtime import WindowsNteRuntime
            layout = ((self.native.layout if self.native.audio_layout is None else self.native.audio_layout)
                if isinstance(self.native, WindowsNteRuntime) else discover_layout())
            return restore(handle, ctx, layout)
        if isinstance(handle, dict) and handle.get('schema') == 'nte-original-text-snapshot-v1':
            from .nte_game_data_snapshot import restore
            return restore(handle, ctx)
        raise GameDataError('incomplete_game_source', 'NTE compatibility information alone is not a prepared game library.')


def create_provider(*, platform, native=None):
    return NteGameDataProvider(platform=platform, native=native)
