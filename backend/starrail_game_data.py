"""Context-bound original Star Rail text, staged estimates and offline restore.

Only complete native/package verification can produce a ready text snapshot.
Android metadata and independent original-audio preparation remain unavailable;
input archives alone cannot masquerade as a usable library.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading

from . import sophon_assets as sophon, starrail_metadata as metadata
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage, SnapshotSource, SourceProof, MAX_HANDLE_BYTES
from .private_data_paths import MAX_TEXT
from .publisher_transport import PublisherTransport
from .private_data_paths import _no_links

SCHEMA = 'starrail-original-input-plan-v1'
STAGE_SCHEMA = 'starrail-original-input-stage-v1'
MAXIMUM = {'native': 1024 * 1024**2, 'metadata': 512 * 1024**2, 'startup': 64 * 1024**2}
SOURCE_LOCALES = frozenset({'en', 'ja', 'ko', 'zh-Hans', 'zh-Hant'})
TEXT_LOCALES = frozenset({'en', 'ja', 'ko', 'zh-Hans', 'zh-Hant', 'de', 'es', 'fr', 'id', 'pt', 'ru', 'th', 'vi'})
HOSTS = frozenset({'sg-hyp-api.hoyoverse.com', 'sg-public-api.hoyoverse.com', 'hyp-api.mihoyo.com',
                   'api-takumi.mihoyo.com', 'autopatchos.starrails.com', 'autopatchcn.bhsr.com'})
TEXT_SCHEMA = 'starrail-original-text-source-v1'
TEXT_PLAN = 'starrail-original-text-plan-v1'
AUDIO_PLAN = 'starrail-original-audio-plan-v1'
AUDIO_SOURCE = 'starrail-original-audio-source-v1'


def _packages_for(catalog, paths):
    from .xxhash64 import xxhash64
    result = {}
    for path in paths:
        value = catalog.tables.resources.get(xxhash64(path.encode('utf-8')))
        if value is None:
            raise GameDataError('unsupported_starrail_resource', 'A required original Star Rail text resource is unavailable.')
        asset = value[0]
        if asset.digest in result and result[asset.digest].size != asset.size:
            raise GameDataError('conflicting_starrail_packages', 'The original text package identities disagree.')
        result[asset.digest] = asset
    return result


def _missing_packages(catalog, packages):
    result = {}
    for digest, asset in packages.items():
        path = catalog.tables.directory / 'starrail-design-packages' / (digest + '.bytes')
        _no_links(path)
        if not path.is_file() or path.stat().st_size != asset.size or metadata._hash(path, 'md5') != digest:
            result[digest] = asset
    return result


def _package_receipts(packages):
    return {digest: {'name': asset.name, 'bytes': asset.size} for digest, asset in packages.items()}


def _description_disk(selected):
    # Same-filesystem hardlinks normally share the immutable input bodies, but
    # exFAT and some providers require the reader's documented copy fallback.
    return sum(asset.size for asset in selected.values()) + sum(metadata.OUTPUTS.values()) + 132 * 1024**2 + MAX_HANDLE_BYTES


def _required_text(catalog, request):
    """Locate only required core/config packages from actual authored owners."""
    from .starrail_original_provider import TABLES
    from .starrail_original_tables import TEXT_CODES
    paths = {'BakedConfig/ExcelOutput/' + name + '.bytes' for name in TABLES}
    for locale in {request.source_locale, *request.target_locales}:
        for code in catalog.text_locales[locale]:
            main = code.startswith('Main'); code = code[4:] if main else code
            paths.add('BakedConfig/ExcelOutput/' + ('TextmapMain_' if main else 'Textmap_') + TEXT_CODES[code] + '.bytes')
    packages = _packages_for(catalog, paths)
    if missing := _missing_packages(catalog, packages):
        return 'text-core', packages, missing
    videos = catalog.file('ExcelOutput/VideoConfig.json')
    captions = {row['CaptionPath'] for rows in (videos, catalog.file('ExcelOutput/CutSceneConfig.json'),
                 catalog.file('ExcelOutput/LoopCGConfig.json')) for row in rows if row.get('CaptionPath')}
    missions = catalog._mission_paths(videos)
    packages.update(_packages_for(catalog, {catalog.configs.descriptions.binary_path(path) for path in missions}))
    if missing := _missing_packages(catalog, packages):
        return 'text-missions', packages, missing
    available = {row['VideoID'] for row in videos if row.get('CaptionPath')}
    for path in sorted(missions):
        catalog._overrides(catalog.file(path), available, captions)
    packages.update(_packages_for(catalog, {catalog.configs.descriptions.binary_path(path) for path in captions}))
    missing = _missing_packages(catalog, packages)
    return ('text-captions' if missing else 'text-snapshot'), packages, missing


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _text_revision(handle):
    # One publisher/schema generation spans several package estimates. A phase
    # transition is not a new source revision, and Ready must retire its stage.
    identity = {name: handle[name] for name in ('request', 'build', 'helper', 'native')}
    mode = 'text-audio' if handle['request']['content_mode'] == 'text-audio' else 'text'
    return handle['build']['version'] + '/' + mode + '-' + _identity(identity)[:24]


def _valid_request(request):
    if request.source_locale not in SOURCE_LOCALES or set(request.target_locales) - TEXT_LOCALES:
        raise GameDataError('unsupported_game_languages', 'Choose an official Star Rail text and spoken language.')


def _staged_build(ctx, request):
    stage = getattr(ctx, 'stage_handle', None)
    if stage is None:
        return None
    if (not isinstance(stage, dict) or stage.get('schema') != STAGE_SCHEMA
            or stage.get('request') != request.json()):
        return None
    required = {'schema', 'request', 'build', 'files', 'ready', 'receipt_sha256'}
    allowed = required | {'native', 'packages', 'audio'}
    # Older input-only receipts did not carry their complete hashable value.
    # Their immutable body cache remains useful through the fresh manifest.
    if set(stage) == {'schema', 'request', 'build', 'files', 'receipt_sha256'}:
        return None
    if not required <= set(stage) or set(stage) - allowed or stage['ready'] is not False:
        raise GameDataError('starrail_stage_changed', 'The pending original source receipt is malformed. Your active library is retained.')
    raw = {key: value for key, value in stage.items() if key != 'receipt_sha256'}
    if _identity(raw) != stage['receipt_sha256']:
        raise GameDataError('starrail_stage_changed', 'The pending original source receipt changed. Your active library is retained.')
    build = stage['build']
    if not isinstance(build, dict) or build.get('channel') != 'starrail-' + request.region:
        raise GameDataError('starrail_stage_changed', 'The pending original source belongs to another publisher edition.')
    # Once native discovery pins the actual hotfix indexes, subsequent package
    # stages finish that exact generation even if a newer launcher appears.
    # An early native-only stage still needs fresh current resource discovery.
    return build if 'hotfix' in build else None


def _inputs(directory, build, fetch):
    channel = build.get('channel')
    if channel not in {'starrail-global', 'starrail-cn'}:
        raise GameDataError('invalid_starrail_generation', 'The Star Rail publisher generation changed.')
    assets = sophon.manifest(directory / 'sophon', channel, tuple(build['manifests']['game']),
                             tuple(metadata.NAMES.values()), fetch=fetch)
    selected = {}
    for role, basename in metadata.NAMES.items():
        matches = [asset for asset in assets.values() if asset.name.rsplit('/', 1)[-1] == basename]
        if len(matches) != 1 or not 0 < matches[0].size <= MAXIMUM[role]:
            raise GameDataError('unsupported_starrail_inputs', 'The publisher metadata inputs need a supported reader.')
        selected[role] = matches[0]
    return selected


def _file_receipts(selected):
    return {role: {'name': asset.name, 'md5': asset.digest, 'bytes': asset.size}
            for role, asset in selected.items()}


def _budget(directory, selected):
    """Count authenticated missing chunks once, excluding complete whole inputs."""
    missing, whole, complete = {}, 0, True
    for asset in selected.values():
        target = directory / 'native-files' / asset.digest
        _no_links(target)
        if target.is_file() and target.stat().st_size == asset.size and metadata._hash(target, 'md5') == asset.digest:
            continue
        complete = False
        whole += asset.size
        for _, expanded, compressed, _, digest in asset.chunks:
            entry = expanded, compressed
            if digest in missing and missing[digest][0] != expanded:
                raise GameDataError('conflicting_starrail_chunks', 'The publisher chunk identities disagree.')
            path = directory / 'sophon/chunks' / digest
            _no_links(path)
            if path.is_file() and path.stat().st_size == expanded and metadata._hash(path, 'md5') == digest:
                continue
            missing.setdefault(digest, entry)
    return (sum(pair[1] for pair in missing.values()),
            whole + sum(pair[0] for pair in missing.values()) + MAX_HANDLE_BYTES, complete)


class StarRailProvider:
    title = 'Honkai: Star Rail'

    def __init__(self, platform, native=None):
        self.platform = platform
        # No undocumented native method names or caller-injected schemas.
        # A future host bridge must have a separately verified contract.
        self.native = native
        self._descriptions = None
        self._description_lock = threading.RLock()

    def _transport(self, ctx, *, additional_hosts=()):
        return PublisherTransport(ctx, hosts=HOSTS | frozenset(additional_hosts))

    def _metadata_fetch(self, ctx, transport):
        def fetch(url, *, limit):
            from urllib.parse import urlsplit
            parsed = urlsplit(url)
            chosen = transport
            if parsed.hostname not in HOSTS:
                domain = '.starrails.com' if ctx.request.region == 'global' else '.bhsr.com'
                if not parsed.hostname or not parsed.hostname.endswith(domain) or parsed.path not in {'/query_dispatch', '/query_gateway'}:
                    raise GameDataError('invalid_starrail_dispatch', 'The original Star Rail dispatch address changed.')
                chosen = self._transport(ctx, additional_hosts=(parsed.hostname,))
            return chosen.fetch_bytes(url, limit=limit, kind='metadata')[0]
        return fetch

    @staticmethod
    def _reader(directory):
        # The canonical application resolves only its immutable delivered
        # closure. Source-SDK preparation remains an explicit maintainer tool;
        # neither a mutable helper cache nor PATH can select this runtime.
        from .prebuilt_readers import prebuilt_reader
        from .runtime_bundle import RuntimeBundleError
        try:
            reader = prebuilt_reader('starrail')
        except (OSError, ValueError, RuntimeBundleError) as error:
            raise GameDataError('starrail_reader_unavailable',
                'The verified Star Rail reader is unavailable. Repair or re-extract this toolkit build, then check the download size again. Your existing library is retained.', 409) from error
        return metadata.Helper((str(reader.executable),),
            metadata._identity({'source': reader.source_identity, 'build': reader.manifest['build_id']}))

    def _text_context(self, ctx, build, reader, *, discover, offline=False):
        from . import starrail_native_preparation as native, starrail_original_discovery as discovery
        from . import starrail_original_provider as original
        directory = self._directory(ctx, ctx.request.region)
        transport = self._transport(ctx)
        def missing(url, *, limit):
            raise GameDataError('starrail_audio_inputs_changed', 'The verified original cache changed. Check the download size again.')
        fetch = missing if offline else self._metadata_fetch(ctx, transport)
        generation = native.prepare(directory, build, original.TABLES, reader=reader, fetch=fetch, allow_generate=False)
        if discover:
            build = discovery.prepare(directory / 'sophon', build, generation.routes, fetch=fetch)
        def package_fetch(url, *, limit):
            if offline:
                return missing(url, limit=limit)
            return transport.fetch_bytes(url, limit=limit, kind='asset', expected_size=limit)[0]
        key = directory.absolute(), generation.identity
        with self._description_lock:
            ctx.check()
            if self._descriptions is None or self._descriptions[0] != key:
                descriptions = original.Descriptions(original.NativeIndex(generation.native))
                self._descriptions = key, descriptions
            descriptions = self._descriptions[1]
            ctx.check()
        stamp, catalog = original.catalog_source(directory, build, generation, content_mode='text',
            fetch=fetch, package_fetch=package_fetch, config_descriptions=descriptions)
        return stamp, catalog, generation

    @staticmethod
    def _stage(ctx, handle, message):
        raw = json.dumps(handle, sort_keys=True, separators=(',', ':')).encode()
        if len(raw) > MAX_HANDLE_BYTES:
            raise GameDataError('starrail_stage_too_large', 'The original Star Rail source receipt exceeds its limit.')
        path = Path(ctx.directory) / 'original-inputs.json'
        _no_links(path); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        return PreparationStage(handle | {'receipt_sha256': hashlib.sha256(raw).hexdigest()}, message)

    def _text_plan(self, request, ctx, build, selected):
        directory = self._directory(ctx, request.region)
        try:
            reader = self._reader(directory)
        except (OSError, ValueError, GameDataError):
            return GameDataPlan(build['version'], None, None, stage='metadata-runtime', runtime_available=False,
                message='The delivered Star Rail metadata reader is unavailable on this device. Your previous library is retained.')
        transport = self._transport(ctx); fetch = self._metadata_fetch(ctx, transport)
        try:
            metadata.prepare(directory, build, reader=reader, fetch=fetch, allow_generate=False)
        except ValueError:
            handle = {'schema': TEXT_PLAN, 'request': request.json(), 'build': build,
                      'files': _file_receipts(selected), 'phase': 'native-descriptions', 'packages': {},
                      'helper': reader.identity, 'native': None}
            return GameDataPlan(_text_revision(handle), 0,
                _description_disk(selected),
                handle, stage='native-descriptions', runtime_available=True,
                message='Prepare the verified original metadata locally before estimating text packages. No further download is included in this step.')
        stamp, catalog, generation = self._text_context(ctx, build, reader, discover='hotfix' not in build)
        phase, packages, missing = _required_text(catalog, request)
        if phase == 'text-snapshot' and request.content_mode == 'text-audio':
            return self._audio_plan(ctx, catalog, generation, reader, selected, packages)
        handle = {'schema': TEXT_PLAN, 'request': request.json(), 'build': catalog.build,
                  'files': _file_receipts(selected), 'phase': phase, 'packages': _package_receipts(packages),
                  'helper': reader.identity, 'native': generation.identity}
        disk = sum(asset.size for asset in missing.values()) + (MAX_TEXT if phase == 'text-snapshot' else 0) + MAX_HANDLE_BYTES
        audio_note = (' Audio is omitted by request.' if request.content_mode == 'text' else
                      ' Recordings require a separate download estimate before this library can become ready.')
        return GameDataPlan(_text_revision(handle),
            sum(asset.size for asset in missing.values()), disk, handle, stage=phase, runtime_available=True,
                message=('Prepare the verified original text library.' if phase == 'text-snapshot'
                     else 'Download the required original text packages. Additional authored scene packages may need a separate estimate.') + audio_note)

    def _audio_inventory(self, ctx, catalog, *, offline=False):
        from . import starrail_game_audio as audio, starrail_hotfix as hotfix
        def missing(url, *, limit):
            raise GameDataError('starrail_audio_inputs_changed', 'The verified audio index changed. Check the download size again.')
        fetch = missing if offline else self._metadata_fetch(ctx, self._transport(ctx))
        raw = hotfix.index(catalog.tables.directory, catalog.build, 'audio', fetch=fetch)
        selected = audio.inventory_owners(catalog.build, raw, ctx.request.source_locale)
        store = audio.RangeStore(self._directory(ctx, ctx.request.region) / 'original-audio')
        quote = audio.header_quote(selected, store)
        receipt = {'audio_index_md5': catalog.build['hotfix']['indexes']['audio'][1],
            'selection_sha256': audio.identity([owner.json() for owner in selected]),
            'quote_sha256': quote.digest, 'owner_count': len(selected)}
        members = ()
        if not quote.spans:
            from . import starrail_events as events
            from . import starrail_game_bindings as bindings
            from .starrail_assets import authored_links
            inventory = audio.directories(selected, store, ctx.request.source_locale)
            assets = sophon.manifest(catalog.tables.directory, catalog.build['channel'],
                tuple(catalog.build['manifests']['game']), (events.LOOKUP,), fetch=fetch)
            if set(assets) != {events.LOOKUP}:
                raise GameDataError('starrail_audio_lookup_missing', 'The official audio event lookup is unavailable. Your existing library is retained.')
            lookup = audio.OriginalLookup(catalog.tables.directory, assets[events.LOOKUP])
            quote = lookup.quote()
            receipt['lookup'] = audio.lookup_identity(lookup.asset)
            if quote.spans:
                receipt['quote_sha256'] = quote.digest
                return quote, lookup, receipt, members
            links = authored_links(catalog, ctx.request.source_locale)
            names = {link['audio_event'] for link in links if link.get('audio_event')}
            lookup_raw = lookup.read(); banks = events.bank_lookup(lookup_raw)
            receipt['authored_events_sha256'] = audio.identity(sorted(names))
            quote, _ = audio.neutral_bank_quote(inventory, banks, names, store)
            if not quote.spans:
                quote, _ = audio.localized_bank_quote(inventory, banks, names, store, ctx.request.source_locale)
            if not quote.spans:
                event = bindings.event_inventory(inventory, lookup_raw, names, store, ctx.request.source_locale)
                quote = event.quote
                receipt['event_unresolved'] = len(event.unresolved)
                receipt['event_unresolved_sha256'] = audio.identity(event.unresolved)
                receipt['event_choices_sha256'] = audio.identity(event.choices)
                receipt['event_bindings_sha256'] = audio.identity({name:
                    [[variant, mid, span.json()] for variant, (mid, span) in sorted(options.items(), key=lambda item: item[0] or '')]
                    for name, options in event.bindings.items()})
                if not quote.spans:
                    members = {span for options in event.bindings.values() for _, span in options.values()}
                    quote = bindings.recording_quote(event.bindings, store)
                if not quote.spans:
                    sources = {link['source'] for link in links if link.get('source')}
                    quote, external, unbound = bindings.external_quote(inventory, sources, store, ctx.request.source_locale)
                    members = tuple(external.values())
                    receipt['external_sources'] = len(sources)
                    receipt['external_unbound'] = len(unbound)
                    receipt['external_unbound_sha256'] = audio.identity(unbound)
                    receipt['external_bindings_sha256'] = audio.identity({source: span.json() for source, span in external.items()})
                    if not quote.spans and not event.unresolved and not unbound:
                        receipt['movie_audio_required'] = self._required_movie_audio(catalog, ctx.request.source_locale)
                        if not receipt['movie_audio_required']:
                            quote = audio.Quote('audio-snapshot', ())
            receipt['quote_sha256'] = quote.digest
        return quote, store, receipt, members

    @staticmethod
    def _required_movie_audio(catalog, locale):
        from .starrail_films import _movie_sources
        from .starrail_assets import selected_tables, TEXT_LOCALES
        from .hoyo_dialogue import display_text
        import re
        scripts = list(catalog.caption_scripts())
        movies, _ = _movie_sources(catalog, scripts, locale)
        # Config-only captions with no original movie owner remain unresolved
        # inventory; they do not invent a movie requirement or certify silence.
        tables = selected_tables(catalog, getattr(catalog, 'text_locales', TEXT_LOCALES), locale, ())
        for filename, script in scripts:
            match = re.fullmatch(r'([A-Za-z0-9_-]+)_Caption\.json', filename)
            if match and movies.get(match[1]) and any(
                    display_text(tables[locale].get(str(cue['CaptionTextID']['Hash']), ''))
                    for cue in script['CaptionList']):
                return True
        return False

    def _audio_plan(self, ctx, catalog, generation, reader, selected, packages):
        quote, _, audio, _ = self._audio_inventory(ctx, catalog)
        handle = {'schema': AUDIO_PLAN, 'request': ctx.request.json(), 'build': catalog.build,
            'files': _file_receipts(selected), 'helper': reader.identity, 'native': generation.identity,
            'packages': _package_receipts(packages), 'phase': quote.phase, 'audio': audio}
        if quote.phase == 'audio-snapshot' and self._audio_runtime_available():
            return GameDataPlan(_text_revision(handle), 0, 2 * MAX_TEXT + MAX_HANDLE_BYTES,
                handle, stage=quote.phase, runtime_available=True,
                message='Prepare the verified text and locally available original recordings. No further download is included.')
        if not quote.spans and quote.phase != 'audio-snapshot':
            return GameDataPlan(_text_revision(handle), None, None, stage='original-audio-bindings', runtime_available=False,
                message='The downloaded audio metadata is verified. More recording branches and movie audio need support before this library can be used. Your existing library is retained.')
        if quote.phase not in {'audio-inventory-prefixes', 'audio-inventory-headers', 'audio-event-lookup'} and not self._audio_runtime_available():
            return GameDataPlan(_text_revision(handle), None, None, stage='audio-runtime', runtime_available=False,
                message='The verified audio reader is unavailable on this device. Repair or re-extract this toolkit build before downloading recordings. Your existing library is retained.')
        return GameDataPlan(_text_revision(handle), quote.download_bytes, quote.disk_bytes + MAX_HANDLE_BYTES,
            handle, stage=quote.phase, runtime_available=True,
            message='Download the next part of the selected official audio pack. Further recording preparation needs a separate estimate; this library will not become ready yet.')

    @staticmethod
    def _audio_runtime_available():
        from .native_codecs import packaged_codec_executable
        return all(packaged_codec_executable(tool) is not None for tool in ('vgmstream', 'ffmpeg'))

    @staticmethod
    def _directory(ctx, region):
        directory = Path(ctx.cache_directory) / 'original-native' / region
        _no_links(directory)
        return directory

    def plan(self, request, ctx):
        _valid_request(request); ctx.check()
        transport = self._transport(ctx)
        def fetch(url, *, limit):
            return transport.fetch_bytes(url, limit=limit, kind='metadata')[0]
        build = _staged_build(ctx, request) or sophon.release('starrail-' + request.region, fetch=fetch)
        directory = self._directory(ctx, request.region)
        selected = _inputs(directory, build, fetch)
        download, disk, complete = _budget(directory, selected)
        handle = {'schema': SCHEMA, 'request': request.json(), 'build': build, 'files': _file_receipts(selected)}
        revision = build['version'] + '/native-' + _identity(handle)[:24]
        # Keep the metadata estimate visible without soliciting large native
        # inputs on a device whose required managed reader is not delivered.
        if self.platform == 'android':
            return GameDataPlan(revision, download, disk, handle, stage='metadata-runtime', runtime_available=False,
                message='Star Rail preparation is not available on Android yet. The shown size is an original metadata estimate.')
        try:
            self._reader(directory)
        except (OSError, ValueError, GameDataError):
            return GameDataPlan(revision, download, disk, handle, stage='metadata-runtime', runtime_available=False,
                message='The verified Star Rail reader is unavailable. Repair or re-extract this toolkit build, then check the download size again. Your existing library is retained.')
        if complete:
            return self._text_plan(request, ctx, build, selected)
        return GameDataPlan(revision, download, disk, handle, stage='original-native-inputs', runtime_available=True,
            message='This downloads original metadata only. It does not prepare study text or recordings yet; their sizes are not included.')

    def download(self, plan, ctx):
        handle = plan.handle
        if isinstance(handle, dict) and handle.get('schema') == AUDIO_PLAN:
            return self._download_audio(plan, ctx)
        if isinstance(handle, dict) and handle.get('schema') == TEXT_PLAN:
            return self._download_text(plan, ctx)
        if (not isinstance(handle, dict) or set(handle) != {'schema', 'request', 'build', 'files'}
                or handle.get('schema') != SCHEMA or handle.get('request') != ctx.request.json()
                or plan.stage != 'original-native-inputs' or self.platform == 'android'):
            raise GameDataError('starrail_plan_changed', 'Check the Star Rail download size again.')
        _valid_request(ctx.request); ctx.check()
        directory = self._directory(ctx, ctx.request.region)
        # A reader removed after the quote cannot strand a new large native
        # download. Revalidate it before even the manifest recheck can fetch.
        self._reader(directory)
        transport = self._transport(ctx)
        def fetch_metadata(url, *, limit):
            return transport.fetch_bytes(url, limit=limit, kind='metadata')[0]
        selected = _inputs(directory, handle['build'], fetch_metadata)
        if handle['files'] != _file_receipts(selected) or handle['build']['channel'] != 'starrail-' + ctx.request.region:
            raise GameDataError('starrail_plan_changed', 'The Star Rail original inputs changed. Check the size again.')
        expected_revision = handle['build']['version'] + '/native-' + _identity(handle)[:24]
        if plan.revision != expected_revision:
            raise GameDataError('starrail_plan_changed', 'The Star Rail plan identity changed. Check the size again.')
        download, disk, _ = _budget(directory, selected)
        if plan.download_bytes is None or download > plan.download_bytes or plan.required_disk_bytes is None or disk > plan.required_disk_bytes:
            raise GameDataError('starrail_plan_changed', 'The verified cache changed. Check the Star Rail download size again.')
        def fetch_asset(url, *, limit):
            return transport.fetch_bytes(url, limit=limit, kind='asset', expected_size=limit)[0]
        directory.mkdir(parents=True, exist_ok=True)
        for asset in selected.values():
            ctx.check(); metadata._input(directory, asset, fetch=fetch_asset)
        ctx.check()
        return self._stage(ctx, {'schema': STAGE_SCHEMA, 'request': ctx.request.json(), 'build': handle['build'],
                                'files': _file_receipts(selected), 'ready': False},
            'Original metadata downloaded. Study text and recordings are not available from this preparation yet.')

    def _download_text(self, plan, ctx):
        handle = plan.handle
        phases = {'native-descriptions', 'text-core', 'text-missions', 'text-captions', 'text-snapshot'}
        if (set(handle) != {'schema', 'request', 'build', 'files', 'phase', 'packages', 'helper', 'native'}
                or handle['request'] != ctx.request.json()
                or handle['phase'] not in phases or plan.stage != handle['phase'] or self.platform == 'android'
                or handle['build']['channel'] != 'starrail-' + ctx.request.region
                or plan.revision != _text_revision(handle)):
            raise GameDataError('starrail_plan_changed', 'Check the original text download size again.')
        ctx.check(); directory = self._directory(ctx, ctx.request.region)
        transport = self._transport(ctx); fetch = self._metadata_fetch(ctx, transport)
        selected = _inputs(directory, handle['build'], fetch)
        if _file_receipts(selected) != handle['files'] or not _budget(directory, selected)[2]:
            raise GameDataError('starrail_inputs_changed', 'The original metadata cache changed. Check the download size again.')
        reader = self._reader(directory)
        if reader.identity != handle['helper']:
            raise GameDataError('starrail_reader_changed', 'The original metadata reader changed. Check the size again.')
        if plan.stage == 'native-descriptions':
            from . import starrail_native_preparation as native, starrail_original_provider as original
            if handle['packages'] or handle['native'] is not None or plan.download_bytes != 0:
                raise GameDataError('starrail_plan_changed', 'Check the original metadata preparation again.')
            if plan.required_disk_bytes is None or plan.required_disk_bytes < _description_disk(selected):
                raise GameDataError('starrail_plan_changed', 'Check the original metadata storage estimate again.')
            generation = native.prepare(directory, handle['build'], original.TABLES, reader=reader, fetch=fetch)
            ctx.check()
            return self._stage(ctx, {'schema': STAGE_SCHEMA, 'request': ctx.request.json(), 'build': handle['build'],
                'files': handle['files'], 'native': generation.identity, 'ready': False},
                'Original metadata is prepared. Check the separate original text package estimate next.')
        stamp, catalog, generation = self._text_context(ctx, handle['build'], reader, discover=False)
        if generation.identity != handle['native']:
            raise GameDataError('starrail_schema_changed', 'The original text schema changed. Check the download size again.')
        phase, packages, missing = _required_text(catalog, ctx.request)
        actual = _package_receipts(packages)
        if (not isinstance(handle['packages'], dict) or not handle['packages']
                or any(actual.get(digest) != value for digest, value in handle['packages'].items())):
            raise GameDataError('starrail_packages_changed', 'The required original text packages changed. Check their size again.')
        planned = {digest: packages[digest] for digest in handle['packages']}
        remaining = _missing_packages(catalog, planned)
        if plan.download_bytes is None or sum(asset.size for asset in remaining.values()) > plan.download_bytes:
            raise GameDataError('starrail_package_cache_changed', 'The original text cache changed. Check its size again.')
        needed_disk = sum(asset.size for asset in remaining.values()) + (MAX_TEXT if plan.stage == 'text-snapshot' else 0) + MAX_HANDLE_BYTES
        if plan.required_disk_bytes is None or plan.required_disk_bytes < needed_disk:
            raise GameDataError('starrail_plan_changed', 'Check the original text storage estimate again.')
        if plan.stage == 'text-snapshot':
            if (ctx.request.content_mode != 'text' or phase != 'text-snapshot' or missing
                    or plan.download_bytes != 0 or set(actual) != set(handle['packages'])):
                raise GameDataError('starrail_text_incomplete', 'The original text packages are incomplete. Check their size again.')
            return self._snapshot(ctx, handle, stamp, catalog, generation, packages)
        for asset in planned.values():
            ctx.check(); catalog.tables._package(asset)
        ctx.check()
        return self._stage(ctx, {'schema': STAGE_SCHEMA, 'request': ctx.request.json(), 'build': handle['build'],
            'files': handle['files'], 'packages': handle['packages'], 'native': generation.identity, 'ready': False},
            'Original text packages verified. Check the remaining preparation estimate; recordings are not downloaded by this step.')

    def _download_audio(self, plan, ctx):
        handle = plan.handle
        if (set(handle) != {'schema', 'request', 'build', 'files', 'helper', 'native', 'packages', 'phase', 'audio'}
                or handle['request'] != ctx.request.json() or ctx.request.content_mode != 'text-audio'
                or handle['phase'] not in {'audio-inventory-prefixes', 'audio-inventory-headers',
                    'audio-event-lookup', 'audio-neutral-banks', 'audio-localized-banks',
                    'audio-state-banks', 'audio-streamed-members', 'audio-external-members', 'audio-snapshot'}
                or plan.stage != handle['phase'] or plan.revision != _text_revision(handle)
                or self.platform == 'android' or handle['build']['channel'] != 'starrail-' + ctx.request.region):
            raise GameDataError('starrail_plan_changed', 'Check the original audio inventory size again.')
        ctx.check(); directory = self._directory(ctx, ctx.request.region)
        def missing(url, *, limit):
            raise GameDataError('starrail_audio_inputs_changed', 'The verified original cache changed. Check the audio download size again.')
        # Every recheck is cache-only. Lost metadata must trigger a new quote;
        # it cannot consume a small inventory consent with unquoted downloads.
        selected = _inputs(directory, handle['build'], missing)
        if _file_receipts(selected) != handle['files'] or not _budget(directory, selected)[2]:
            raise GameDataError('starrail_inputs_changed', 'The original metadata cache changed. Check the audio size again.')
        reader = self._reader(directory)
        if reader.identity != handle['helper']:
            raise GameDataError('starrail_reader_changed', 'The delivered reader changed. Check the audio size again.')
        stamp, catalog, generation = self._text_context(ctx, handle['build'], reader, discover=False, offline=True)
        phase, packages, absent = _required_text(catalog, ctx.request)
        if (generation.identity != handle['native'] or phase != 'text-snapshot' or absent
                or _package_receipts(packages) != handle['packages']):
            raise GameDataError('starrail_audio_inputs_changed', 'The original text generation changed. Check the audio size again.')
        quote, store, receipt, members = self._audio_inventory(ctx, catalog, offline=True)
        if (quote.phase != plan.stage or receipt != handle['audio'] or plan.download_bytes != quote.download_bytes
                or plan.required_disk_bytes is None or plan.required_disk_bytes < quote.disk_bytes + MAX_HANDLE_BYTES):
            raise GameDataError('starrail_audio_plan_changed', 'The original audio inventory or cache changed. Check its size again.')
        if plan.stage not in {'audio-inventory-prefixes', 'audio-inventory-headers', 'audio-event-lookup'} and not self._audio_runtime_available():
            raise GameDataError('starrail_audio_runtime_unavailable',
                'The verified audio reader changed. Repair or re-extract this toolkit build, then check the size again. Your existing library is retained.')
        if plan.stage == 'audio-snapshot':
            if quote.spans or plan.required_disk_bytes < 2 * MAX_TEXT + MAX_HANDLE_BYTES:
                raise GameDataError('starrail_audio_plan_changed', 'Check the original recording storage estimate again.')
            return self._snapshot_audio(ctx, handle, stamp, catalog, generation, packages, store)
        transport = self._transport(ctx)
        for span in quote.spans:
            ctx.check(); store.acquire(span, transport)
        # Validate this stage without fetching a later stage's manifest or
        # metadata. Inventory consent cannot authorize a lookup acquisition.
        from . import starrail_game_audio as audio, starrail_hotfix as hotfix
        if plan.stage in {'audio-inventory-prefixes', 'audio-inventory-headers'}:
            raw = hotfix.index(catalog.tables.directory, catalog.build, 'audio', fetch=missing)
            owners = audio.inventory_owners(catalog.build, raw, ctx.request.source_locale)
            if not audio.header_quote(owners, store).spans:
                audio.directories(owners, store, ctx.request.source_locale)
        elif plan.stage == 'audio-event-lookup':
            store.read()
        elif plan.stage in {'audio-streamed-members', 'audio-external-members'}:
            audio.validate_recordings(quote.spans, members, store)
        else:
            # Complete bank identities/sections, not just their range hashes,
            # are required before this event-bank stage can be retained.
            raw = hotfix.index(catalog.tables.directory, catalog.build, 'audio', fetch=missing)
            owners = audio.inventory_owners(catalog.build, raw, ctx.request.source_locale)
            inventory = audio.directories(owners, store, ctx.request.source_locale)
            audio.validate_banks(inventory, quote.spans, store, ctx.request.source_locale)
        ctx.check()
        return self._stage(ctx, {'schema': STAGE_SCHEMA, 'request': ctx.request.json(), 'build': handle['build'],
            'files': handle['files'], 'packages': handle['packages'], 'native': generation.identity,
            'audio': receipt, 'ready': False},
            'Original audio inventory verified. Recordings are not downloaded yet; check the next preparation estimate.')

    @staticmethod
    def _snapshot(ctx, handle, stamp, catalog, generation, packages):
        from .starrail_assets import index_text_catalog
        from .language_worker import write_payload
        ctx.check()
        payload = index_text_catalog(stamp, catalog, ctx.request.source_locale, ctx.request.target_locales, catalog.tables.directory.parent)
        payload['publisher_region'] = ctx.request.region
        path = Path(ctx.directory) / 'textmap.json'; _no_links(path)
        write_payload('starrail', payload, ctx.request.source_locale, ctx.request.target_locales, path)
        if not 0 < path.stat().st_size <= MAX_TEXT:
            raise GameDataError('starrail_text_too_large', 'The prepared original text exceeds its storage limit.')
        receipt = {'schema': TEXT_SCHEMA, 'request': ctx.request.json(), 'build': handle['build'],
            'native': generation.identity, 'helper': handle['helper'], 'native_files': handle['files'],
            'whole_original_packages': _package_receipts(packages), 'snapshot_sha256': metadata._hash(path)}
        raw = json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()
        if len(raw) > MAX_HANDLE_BYTES:
            raise GameDataError('starrail_receipt_too_large', 'The original source receipt exceeds its limit.')
        proofpath = Path(ctx.directory) / 'source-proof.json'; _no_links(proofpath); proofpath.write_bytes(raw)
        ctx.check()
        digest = hashlib.sha256(raw).hexdigest()
        restored = {'schema': TEXT_SCHEMA, 'request': ctx.request.json(), 'receipt_sha256': digest,
                    'snapshot_sha256': receipt['snapshot_sha256']}
        return SnapshotSource(path, restored, SourceProof('official', digest, True))

    def restore(self, handle, ctx):
        ctx.check()
        if isinstance(handle, dict) and handle.get('schema') == AUDIO_SOURCE:
            return self._restore_audio(handle, ctx)
        if not isinstance(handle, dict) or handle.get('schema') != TEXT_SCHEMA:
            raise GameDataError('starrail_catalog_not_ready', 'Original input archives cannot restore a ready Star Rail library.', 409)
        if (set(handle) != {'schema', 'request', 'receipt_sha256', 'snapshot_sha256'}
                or handle['request'] != ctx.request.json() or ctx.request.content_mode != 'text'):
            raise GameDataError('starrail_restore_changed', 'The original text library does not match this request.')
        path, proofpath = Path(ctx.directory) / 'textmap.json', Path(ctx.directory) / 'source-proof.json'
        _no_links(path); _no_links(proofpath)
        if (not proofpath.is_file() or not 0 < proofpath.stat().st_size <= MAX_HANDLE_BYTES
                or metadata._hash(proofpath) != handle['receipt_sha256'] or not path.is_file()
                or not 0 < path.stat().st_size <= MAX_TEXT or metadata._hash(path) != handle['snapshot_sha256']):
            raise GameDataError('starrail_restore_corrupt', 'The original text library failed its integrity check.')
        value = json.loads(proofpath.read_bytes())
        if (not isinstance(value, dict) or set(value) != {'schema', 'request', 'build', 'native', 'helper',
                'native_files', 'whole_original_packages', 'snapshot_sha256'} or value.get('schema') != TEXT_SCHEMA
                or value.get('request') != ctx.request.json() or value.get('snapshot_sha256') != handle['snapshot_sha256']):
            raise GameDataError('starrail_restore_corrupt', 'The original text source receipt changed.')
        return SnapshotSource(path, handle, SourceProof('official', handle['receipt_sha256'], True))

    def _snapshot_audio(self, ctx, handle, stamp, catalog, generation, packages, store):
        from . import starrail_game_snapshot as snapshot, starrail_game_bindings as bindings
        from . import starrail_game_audio as audio, starrail_events as events
        from .starrail_assets import index_text_catalog
        from .language_worker import write_payload
        ctx.check()
        payload = index_text_catalog(stamp, catalog, ctx.request.source_locale, ctx.request.target_locales, catalog.tables.directory.parent)
        sources = [row.get('source_voice_binding') or {} for row in payload['records']]
        # Every source owner is reconstructed from the same whole AudioV.
        # No network, mutable schema or installed audio path participates here.
        from . import starrail_hotfix as hotfix
        def missing(*a, **k):
            raise GameDataError('starrail_audio_inputs_changed', 'The verified original audio cache changed. Check its size again.')
        raw = hotfix.index(catalog.tables.directory, catalog.build, 'audio', fetch=missing)
        owners = audio.inventory_owners(catalog.build, raw, ctx.request.source_locale)
        inventory = audio.directories(owners, store, ctx.request.source_locale)
        assets = sophon.manifest(catalog.tables.directory, catalog.build['channel'],
            tuple(catalog.build['manifests']['game']), (events.LOOKUP,), fetch=missing)
        lookup = audio.OriginalLookup(catalog.tables.directory, assets[events.LOOKUP]).read()
        event = bindings.event_inventory(inventory, lookup,
            {source['audio_event'] for source in sources if source.get('audio_event')}, store, ctx.request.source_locale)
        _, external, unbound = bindings.external_quote(inventory,
            {source['source'] for source in sources if source.get('source')}, store, ctx.request.source_locale)
        if event.quote.spans or event.unresolved or unbound:
            raise GameDataError('starrail_audio_incomplete', 'The authored original recordings are incomplete. Your existing library is retained.')
        from .starrail_assets import authored_links, selected_tables
        sequence_texts = {}
        if event.bindings:
            tables = selected_tables(catalog, catalog.text_locales, ctx.request.source_locale, ctx.request.target_locales)
            sequence_texts = {'starrail:' + str(link['id']): {locale: table[str(link['hash'])]
                for locale, table in tables.items() if str(link['hash']) in table}
                for link in authored_links(catalog, ctx.request.source_locale) if link.get('audio_event')}
        payload, members = snapshot.render(payload, external, event.bindings, sequence_texts=sequence_texts)
        voices = audio.OriginalVoices(store, members, cancelled=ctx.cancelled)
        if any(row.get('audio') and not voices.has(row) for row in payload['records']):
            raise GameDataError('starrail_audio_incomplete', 'The original recordings could not be verified locally.')
        payload['publisher_region'] = ctx.request.region
        path = Path(ctx.directory) / 'textmap.json'; _no_links(path)
        write_payload('starrail', payload, ctx.request.source_locale, ctx.request.target_locales, path)
        memberspath = Path(ctx.directory) / 'original-members.json'; _no_links(memberspath)
        member_raw = json.dumps(snapshot.pack(members), sort_keys=True, separators=(',', ':')).encode()
        if not 0 < len(member_raw) <= MAX_TEXT or not 0 < path.stat().st_size <= MAX_TEXT:
            raise GameDataError('starrail_audio_too_large', 'The original recording snapshot exceeds its storage limit.')
        memberspath.write_bytes(member_raw); ctx.check()
        receipt = {'schema': AUDIO_SOURCE, 'request': ctx.request.json(), 'build': handle['build'],
            'native': generation.identity, 'helper': handle['helper'], 'native_files': handle['files'],
            'whole_original_packages': _package_receipts(packages), 'audio': handle['audio'],
            'snapshot_sha256': metadata._hash(path), 'members_sha256': metadata._hash(memberspath)}
        raw = json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()
        if len(raw) > MAX_HANDLE_BYTES:
            raise GameDataError('starrail_receipt_too_large', 'The original recording receipt exceeds its limit.')
        proofpath = Path(ctx.directory) / 'source-proof.json'; _no_links(proofpath); proofpath.write_bytes(raw)
        ctx.check(); digest = hashlib.sha256(raw).hexdigest()
        handle = {'schema': AUDIO_SOURCE, 'request': ctx.request.json(), 'receipt_sha256': digest,
            'snapshot_sha256': receipt['snapshot_sha256'], 'members_sha256': receipt['members_sha256']}
        return SnapshotSource(path, handle, SourceProof('official', digest, True), voices)

    def _restore_audio(self, handle, ctx):
        from . import starrail_game_audio as audio, starrail_game_snapshot as snapshot
        if (set(handle) != {'schema', 'request', 'receipt_sha256', 'snapshot_sha256', 'members_sha256'}
                or handle['request'] != ctx.request.json() or ctx.request.content_mode != 'text-audio'):
            raise GameDataError('starrail_restore_changed', 'The original recordings do not match this request.')
        if self.platform == 'android' or not self._audio_runtime_available():
            raise GameDataError('starrail_audio_runtime_unavailable', 'The verified original audio reader is unavailable on this device.')
        paths = {'source-proof.json': (MAX_HANDLE_BYTES, handle['receipt_sha256']),
            'textmap.json': (MAX_TEXT, handle['snapshot_sha256']),
            'original-members.json': (MAX_TEXT, handle['members_sha256'])}
        for name, (limit, digest) in paths.items():
            path = Path(ctx.directory) / name; _no_links(path)
            if not path.is_file() or not 0 < path.stat().st_size <= limit or metadata._hash(path) != digest:
                raise GameDataError('starrail_restore_corrupt', 'The original recording library failed its integrity check.')
        value = json.loads((Path(ctx.directory) / 'source-proof.json').read_bytes())
        if (not isinstance(value, dict) or set(value) != {'schema', 'request', 'build', 'native', 'helper',
                'native_files', 'whole_original_packages', 'snapshot_sha256', 'members_sha256', 'audio'}
                or value.get('schema') != AUDIO_SOURCE or value.get('request') != ctx.request.json()
                or value.get('snapshot_sha256') != handle['snapshot_sha256'] or value.get('members_sha256') != handle['members_sha256']):
            raise GameDataError('starrail_restore_corrupt', 'The original recording source receipt changed.')
        path = Path(ctx.directory) / 'textmap.json'; payload = json.loads(path.read_bytes())
        if payload.get('content_mode') != 'text-audio' or payload.get('source_locale') != ctx.request.source_locale:
            raise GameDataError('starrail_restore_changed', 'The recording snapshot belongs to another request.')
        members = snapshot.unpack(json.loads((Path(ctx.directory) / 'original-members.json').read_bytes()), payload)
        store = audio.RangeStore(self._directory(ctx, ctx.request.region) / 'original-audio')
        voices = audio.OriginalVoices(store, members, cancelled=ctx.cancelled)
        ctx.check()
        return SnapshotSource(path, handle, SourceProof('official', handle['receipt_sha256'], True), voices)


def create_provider(*, platform, native=None):
    if platform not in {'android', 'windows', 'linux', 'macos'}:
        return None
    return StarRailProvider(platform, native)
