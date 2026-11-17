"""Context-budgeted Endfield client-metadata bootstrap, never a ready library.

The original parameter recognizers and resource producers remain separate.
This first provider stage establishes a bounded source cache for their future
context-owned execution; downloading it does not activate text or voice data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from .endfield_client_source import Image, client_identity, identity_stamp, metadata_sections

TITLE = 'Arknights: Endfield'
METADATA = 'Endfield_Data/il2cpp_data/Metadata/global-metadata.dat'
CHANNELS = {
    'global': ('launcher.gryphline.com', 'YDUTE5gscDZ229CW', 'TiaytKBUIEdoEwRT', 6, 'beyond.hg-cdn.com'),
    'cn': ('launcher.hypergryph.com', '6LL0KJuqHBVz33WK', 'abYeZZ16BPluCFyT', 1, 'beyond.hycdn.cn'),
}
PLATFORMS = {'android', 'windows', 'linux', 'macos'}
LAUNCHER_LIMIT = 2 * 1024**2
RECHECK_METADATA_UPPER = 2 * LAUNCHER_LIMIT + 4352


def _contracts():
    # The reviewed shared service/transport wave owns these modules on every
    # host. Do not substitute desktop urllib or a second Android implementation.
    from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
    from .publisher_transport import PublisherTransport
    return GameDataError, GameDataPlan, PreparationStage, PublisherTransport


class _Header:
    def __init__(self, data):
        self.data = data

    def read(self, offset, size):
        if offset != 0 or size != len(self.data):
            raise ValueError('Endfield size preflight requested more than its original header.')
        return self.data


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _source_plan(handle):
    # Raw launcher JSON can renew temporary tokens or unrelated fields without
    # changing the canonical original artifact declaration. Keep that receipt
    # as evidence, not as generation identity. The actual original headers are
    # still byte-bound: a changed header must not reuse an old size approval.
    receipts = handle.get('receipts')
    if not isinstance(receipts, dict) or any(not isinstance(receipts.get(name), dict)
                                            for name in (METADATA, 'GameAssembly.dll')):
        return None
    return ({key: value for key, value in handle.items() if key != 'receipts'},
            {name: receipts[name].get('sha256') for name in (METADATA, 'GameAssembly.dll')})


class EndfieldGameDataProvider:
    title = TITLE

    def __init__(self, platform, native=None, *, transport_factory=None):
        if platform not in PLATFORMS:
            raise ValueError('Choose an explicit reviewed preparation platform.')
        self.platform, self.native = platform, native
        self.transport_factory = transport_factory

    def _transport(self, request, ctx):
        Error, _, _, Transport = _contracts()
        if ctx.game != 'endfield' or request.region not in CHANNELS or request.content_mode not in {'text', 'text-audio'}:
            raise Error('invalid_game_languages', 'Choose the Endfield region, languages and download mode.')
        launcher, _app, _launcher_app, _channel, cdn = CHANNELS[request.region]
        return (self.transport_factory or Transport)(ctx, hosts={launcher, cdn})

    def _latest(self, request, transport):
        Error, _, _, _ = _contracts()
        launcher, app, launcher_app, channel, cdn = CHANNELS[request.region]
        query = urlencode(dict(appcode=app, launcher_appcode=launcher_app, channel=channel,
                               sub_channel=channel, launcher_sub_channel=channel, disk_type=0, patch_encrypt=1))
        raw, receipt = transport.fetch_bytes('https://' + launcher + '/api/game/get_latest?' + query,
                                             limit=LAUNCHER_LIMIT, kind='metadata')
        try:
            latest = json.loads(raw)
            identity = client_identity(latest, region=request.region, cdn='https://' + cdn + '/' + app)
        except (ValueError, KeyError, TypeError) as error:
            raise Error('publisher_response_invalid', 'The Endfield launcher returned an incomplete client declaration.') from error
        return identity, receipt

    def _runtime(self):
        Error, _, _, _ = _contracts()
        if self.platform != 'windows':
            raise Error('missing_toolkit_runtime',
                        'Endfield independent preparation needs the reviewed native decoder and hash runtime for this host. Existing prepared data is retained.')
        from .endfield_parameters import source_runtime
        from .preparation_errors import PreparationFailure
        try:
            source_runtime()
        except PreparationFailure as error:
            raise Error(error.code, str(error)) from error

    def plan(self, request, ctx):
        return self._plan(request, ctx, getattr(ctx, 'stage_handle', None))

    def _original_import(self, bootstrap):
        from .endfield_client_source import Metadata
        from .endfield_native_import import managed_import
        return managed_import(Metadata(bootstrap.artifact(METADATA)),
                              Image(bootstrap.artifact('GameAssembly.dll')))

    def _common(self, bootstrap):
        from .endfield_client_source import Metadata
        from .endfield_client_contract import derive
        return derive(Metadata(bootstrap.artifact(METADATA)), Image(bootstrap.artifact('GameAssembly.dll')))

    def _plan(self, request, ctx, continuation):
        self._runtime()
        Error, Plan, _, _ = _contracts()
        transport = self._transport(request, ctx)
        identity, declaration = self._latest(request, transport)
        if (isinstance(continuation, dict) and continuation.get('client') == identity and
                continuation.get('request') == request.json()):
            if continuation.get('stage') == 'original-audio-native-source-downloaded':
                return self._plan_control(request, ctx, identity, transport, continuation)
            if continuation.get('stage') == 'original-audio-master-verified':
                return self._plan_text(request, ctx, identity, transport, continuation)
            if continuation.get('stage') == 'original-text-tables-downloaded':
                return self._plan_navigation(request, ctx, identity, transport, continuation)
            if continuation.get('stage') == 'original-text-navigation-pending':
                return self._plan_navigation(request, ctx, identity, transport, continuation)
            if continuation.get('stage') == 'original-text-navigation-verified':
                raise Error('source_not_prepared',
                    'Endfield original text and presentation navigation are verified. Selected graph/UI bundles and their AES/header provenance still need preparation before a complete capture-ready library; existing data is retained.')
            if continuation.get('stage') == 'client-bootstrap-downloaded':
                if request.content_mode == 'text':
                    return self._plan_text(request, ctx, identity, transport, continuation)
                from .endfield_bootstrap_source import Bootstrap
                bootstrap = Bootstrap(ctx, identity, transport, continuation)
                try:
                    original_import = self._original_import(bootstrap)
                except (ValueError, KeyError, TypeError) as error:
                    raise Error('unsupported_original_metadata',
                        'Endfield original client import ownership could not be established. Existing data is retained.') from error
                from .endfield_native_source import OriginalNativeSource
                original = OriginalNativeSource(ctx, identity, transport).plan(original_import)
                handle = {'schema': 1, 'stage': 'original-audio-native-member', 'client': identity,
                          'request': request.json(), 'bootstrap': continuation, 'source_plan': original}
                return Plan(revision='endfield-client-' + identity_stamp(identity),
                    download_bytes=original['download_bytes'] + LAUNCHER_LIMIT,
                    required_disk_bytes=original['required_disk_bytes'], handle=handle,
                    download_is_upper_bound=True, runtime_available=True, stage=handle['stage'],
                    message='Original audio native member plus bounded source rechecks; package controls and text preparation still follow. This stage activates no game data.')
        headers, artifacts, receipts = {}, {}, {'declaration': declaration.json()}
        for artifact, size in ((METADATA, 256), ('GameAssembly.dll', 4096)):
            data, receipt = transport.fetch_bytes(identity['url'] + '/' + artifact, limit=size,
                kind='metadata', expected_size=size, original_range=(0, size, None))
            owner = receipt.original_range
            if not owner or owner[:2] != (0, size) or type(owner[2]) is not int or owner[2] < size:
                raise Error('publisher_range_changed', 'The Endfield original file owner could not be established.')
            headers[artifact], artifacts[artifact], receipts[artifact] = data, owner[2], receipt.json()
        try:
            sections = metadata_sections(_Header(headers[METADATA]))
            image = Image(_Header(headers['GameAssembly.dll']), read_tables=False)
            ranges = [{'artifact': METADATA, 'offset': offset, 'bytes': size}
                      for name, (offset, size) in sections.items()
                      if name in {'strings', 'methods', 'types', 'images', 'literals', 'literal_data'}]
            ranges += [{'artifact': 'GameAssembly.dll', 'offset': image.sections[name][2],
                        'bytes': image.sections[name][3]} for name in ('.rdata', '.data')]
            if any(row['offset'] < 0 or row['bytes'] <= 0 or
                   row['offset'] + row['bytes'] > artifacts[row['artifact']] for row in ranges):
                raise ValueError('Original table range leaves its declared artifact.')
        except (ValueError, KeyError, TypeError) as error:
            raise Error('unsupported_game_format', 'Endfield original client metadata has an unsupported structure. Previous data is retained.') from error
        handle = {'schema': 1, 'stage': 'client-bootstrap', 'request': request.json(),
                  'client': identity, 'artifacts': artifacts, 'ranges': ranges, 'receipts': receipts,
                  'transfer_bytes': {'client_tables': sum(row['bytes'] for row in ranges),
                                     'verification_metadata_upper_bound': RECHECK_METADATA_UPPER}}
        size = sum(row['bytes'] for row in ranges)
        return Plan(revision='endfield-client-' + identity_stamp(identity), download_bytes=size + RECHECK_METADATA_UPPER,
            required_disk_bytes=2 * size + 4352, handle=handle, runtime_available=True,
            download_is_upper_bound=True, stage='client-bootstrap',
            message='Original client tables plus a bounded metadata recheck allowance; parameter/index verification and a separate text or audio content estimate follow. This stage activates no game data.')

    def download(self, plan, ctx):
        self._runtime()
        Error, _, Stage, _ = _contracts()
        if plan.stage == 'original-audio-native-member':
            return self._download_native(plan, ctx)
        if plan.stage == 'original-audio-package-control':
            return self._download_control(plan, ctx)
        if plan.stage == 'original-text-tables':
            return self._download_text(plan, ctx)
        if plan.stage in {'original-text-manifest', 'original-text-navigation-indices'}:
            return self._download_navigation(plan, ctx)
        # Rebuild only the bounded size/source plan, before any large transfer.
        # Changed client, selection, ranges or estimate require new consent.
        current = self.plan(ctx.request, ctx)
        if (_source_plan(plan.handle) != _source_plan(current.handle) or plan.download_bytes != current.download_bytes or
                plan.required_disk_bytes != current.required_disk_bytes or plan.revision != current.revision or
                plan.stage != 'client-bootstrap' or plan.runtime_available is not True or
                plan.download_is_upper_bound is not True):
            raise Error('publisher_size_changed', 'The Endfield client or selected download changed. Check its size again.')
        transport = self._transport(ctx.request, ctx)
        handle = plan.handle
        selection = hashlib.sha256(_json_bytes({'client': handle['client'], 'request': ctx.request.json()})).hexdigest()
        root = Path(ctx.cache_directory) / 'endfield-client-bootstrap' / selection
        completed = []
        for number, row in enumerate(handle['ranges']):
            ctx.check()
            target = root / (str(number) + '.bin')
            receipt = transport.download_to(handle['client']['url'] + '/' + row['artifact'], target,
                limit=row['bytes'], expected_size=row['bytes'], kind='asset',
                original_range=(row['offset'], row['bytes'], handle['artifacts'][row['artifact']]))
            completed.append({'range': row, 'receipt': receipt.json(), 'file': target.name})
        identity, _ = self._latest(ctx.request, transport)
        if identity != handle['client']:
            raise Error('publisher_size_changed', 'Endfield changed during metadata preparation. Existing game data is retained.')
        # Receipt metadata is inert and local. It is neither a source key nor a
        # publisher-content proof: full VFS/file/schema validation comes next.
        result = {'schema': 1, 'stage': 'client-bootstrap-downloaded', 'request': ctx.request.json(),
                  'client': identity, 'ranges': completed,
                  'authentication': 'official HTTPS range receipts; not complete native artifact hashes'}
        from .game_data import _write
        _write(root / 'receipt.json', result)
        return Stage({'schema': 1, 'stage': result['stage'], 'client': identity,
                      'request': ctx.request.json(), 'receipt_sha256': hashlib.sha256(_json_bytes(result)).hexdigest()},
                     'Original Endfield client metadata is downloaded. Parameter/index verification and another content-size check are still required; no game text or audio is active.')

    def _download_native(self, plan, ctx):
        Error, _, Stage, _ = _contracts()
        # The service exposes stage_handle during planning only. Reopen solely
        # the exact private continuation bound into this approved plan.
        continuation = plan.handle.get('bootstrap')
        current = self._plan(ctx.request, ctx, continuation)
        if (current.handle != plan.handle or current.revision != plan.revision or
                current.download_bytes != plan.download_bytes or current.required_disk_bytes != plan.required_disk_bytes or
                current.stage != plan.stage or plan.download_is_upper_bound is not True or plan.runtime_available is not True):
            raise Error('publisher_size_changed', 'Endfield original source or download approval changed. Check its size again.')
        from .endfield_bootstrap_source import Bootstrap
        from .endfield_native_source import OriginalNativeSource
        from .endfield_native_import import Import
        transport = self._transport(ctx.request, ctx)
        identity = current.handle['client']
        # Revalidate the bootstrap receipt and large source bytes through the
        # same owner recognizer, instead of trusting an entrypoint from a handle.
        bootstrap = Bootstrap(ctx, identity, transport, continuation)
        original_import = self._original_import(bootstrap)
        if original_import != Import(**current.handle['source_plan']['import']):
            raise Error('unverified_original_import', 'Endfield original import changed during native source preparation.')
        _, source = OriginalNativeSource(ctx, identity, transport).acquire(current.handle['source_plan'], original_import,
            recheck=lambda: self._latest(ctx.request, transport)[0])
        return Stage({'schema': 1, 'stage': 'original-audio-native-source-downloaded',
            'request': ctx.request.json(), 'client': identity, 'bootstrap': continuation,
            'source_receipt_sha256': hashlib.sha256(_json_bytes(source)).hexdigest()},
            'Endfield original audio native source is verified. Original package controls and text preparation are still required; no dialogue or voice library is active.')

    def _plan_control(self, request, ctx, identity, transport, continuation, *, generation=None):
        Error, Plan, _, _ = _contracts()
        if request.content_mode != 'text-audio':
            raise Error('audio_not_requested', 'Endfield original audio controls require the audio selection.')
        from .endfield_bootstrap_source import Bootstrap, SMALL_TOTAL
        from .endfield_native_source import OriginalNativeSource
        from .endfield_resource_source import discover, control_plan
        bootstrap = Bootstrap(ctx, identity, transport, continuation.get('bootstrap'))
        imported = self._original_import(bootstrap)
        OriginalNativeSource(ctx, identity, transport).verified(imported, continuation.get('source_receipt_sha256'))
        try:
            common = self._common(bootstrap)
        except (ValueError, KeyError, TypeError) as error:
            raise Error('unsupported_original_metadata', 'Endfield original common parameters could not be derived. Existing data is retained.') from error
        generation = generation if generation is not None else discover(ctx, identity, transport)
        control, _ = control_plan(ctx, identity, common, generation, transport)
        handle = {'schema': 1, 'stage': control['stage'], 'client': identity, 'request': request.json(),
                  'native': continuation, 'control': control}
        return Plan(revision='endfield-resources-' + hashlib.sha256(_json_bytes(generation)).hexdigest(),
            download_bytes=control['download_bytes'] + 2 * LAUNCHER_LIMIT + 2 * SMALL_TOTAL,
            required_disk_bytes=control['required_disk_bytes'], handle=handle, download_is_upper_bound=True,
            runtime_available=True, stage=handle['stage'],
            message='One selected original voice-bank control plus bounded source rechecks. Text/playback preparation still follows; no game library is active.')

    def _download_control(self, plan, ctx):
        Error, _, Stage, _ = _contracts()
        native = plan.handle.get('native')
        current = self._plan(ctx.request, ctx, native)
        if (current.handle != plan.handle or current.revision != plan.revision or
                current.download_bytes != plan.download_bytes or current.required_disk_bytes != plan.required_disk_bytes or
                current.stage != plan.stage or plan.download_is_upper_bound is not True or plan.runtime_available is not True):
            raise Error('publisher_size_changed', 'Endfield original package source or quoted transfer changed.')
        from .endfield_bootstrap_source import Bootstrap
        from .endfield_resource_source import discover, control_plan, download_control
        from .endfield_akpk_witness import activate
        transport = self._transport(ctx.request, ctx)
        identity = current.handle['client']
        bootstrap = Bootstrap(ctx, identity, transport, native['bootstrap'])
        common = self._common(bootstrap)
        control = current.handle['control']
        # Re-read the small original index through the same typed plan instead
        # of accepting byte data or package parameters from a client handle.
        second, index = control_plan(ctx, identity, common, control['generation'], transport)
        if second != control:
            raise Error('publisher_size_changed', 'Endfield original bank control changed before its download.')
        file, payload = download_control(ctx, identity, common, control, index, transport)
        reference = activate(ctx, bootstrap, native, control['generation'], index, control['block'], file.name, payload,
            recheck=lambda: (self._latest(ctx.request, transport)[0], discover(ctx, identity, transport)))
        return Stage({'schema': 1, 'stage': 'original-audio-master-verified', 'client': identity,
            'request': ctx.request.json(), 'generation': control['generation'], 'witness': reference,
            'native': native},
            'Endfield original audio parameters passed their original package controls. Text-resource and playback preparation are still required; no dialogue library is active.')

    def restore(self, handle, ctx):
        Error, _, _, _ = _contracts()
        raise Error('source_not_prepared', 'Endfield client metadata is a preparation stage, not a restorable game library.')

    def _text_bootstrap(self, ctx, identity, transport, continuation):
        from .endfield_bootstrap_source import Bootstrap
        if ctx.request.content_mode == 'text':
            stage = continuation
        elif ctx.request.content_mode == 'text-audio' and continuation.get('stage') == 'original-audio-master-verified':
            stage = continuation['native']['bootstrap']
        else:
            Error, _, _, _ = _contracts()
            raise Error('invalid_local_state', 'Endfield text/audio preparation needs its explicit original source stage.')
        return Bootstrap(ctx, identity, transport, stage)

    def _plan_text(self, request, ctx, identity, transport, continuation, *, generation=None):
        from .endfield_bootstrap_source import SMALL_TOTAL
        from .endfield_resource_source import discover
        from .endfield_text_source import plan as text_plan
        Error, Plan, _, _ = _contracts()
        bootstrap = self._text_bootstrap(ctx, identity, transport, continuation)
        try:
            common = self._common(bootstrap)
        except (ValueError, KeyError, TypeError) as error:
            raise Error('unsupported_original_metadata', 'Endfield original text common parameters could not be derived. Existing data is retained.') from error
        generation = generation if generation is not None else discover(ctx, identity, transport)
        if request.content_mode == 'text-audio' and continuation.get('generation') != generation:
            return self._restart_resources(request, ctx, identity, transport, continuation, generation)
        content, _ = text_plan(ctx, identity, common, generation, transport)
        handle = {'schema': 1, 'stage': content['stage'], 'client': identity,
                  'request': request.json(), 'source': continuation, 'text': content}
        return Plan(revision='endfield-resources-' + hashlib.sha256(_json_bytes(generation)).hexdigest(),
            download_bytes=content['download_bytes'] + 2 * LAUNCHER_LIMIT + 2 * SMALL_TOTAL,
            required_disk_bytes=content['required_disk_bytes'], handle=handle, download_is_upper_bound=True,
            runtime_available=True, stage=handle['stage'],
            message='Selected original translation tables and the complete shared TableCfg catalog, including non-narrative overhead, plus bounded source rechecks. This stage activates no dialogue library.')

    def _download_text(self, plan, ctx):
        Error, _, Stage, _ = _contracts()
        continuation = plan.handle.get('source')
        current = self._plan(ctx.request, ctx, continuation)
        if (current.handle != plan.handle or current.revision != plan.revision or
                current.download_bytes != plan.download_bytes or current.required_disk_bytes != plan.required_disk_bytes or
                current.stage != plan.stage or plan.download_is_upper_bound is not True or plan.runtime_available is not True):
            raise Error('publisher_size_changed', 'Endfield original text source or quoted transfer changed. Check its size again.')
        from .endfield_resource_source import discover
        from .endfield_text_source import plan as text_plan, download
        transport = self._transport(ctx.request, ctx)
        identity = current.handle['client']
        common = self._common(self._text_bootstrap(ctx, identity, transport, continuation))
        quoted, index = text_plan(ctx, identity, common, current.handle['text']['generation'], transport)
        if quoted != current.handle['text']:
            raise Error('publisher_size_changed', 'Endfield original text index or verified cache changed before download.')
        reference = download(ctx, identity, common, quoted, index, transport,
            recheck=lambda: (self._latest(ctx.request, transport)[0], discover(ctx, identity, transport)))
        return Stage({'schema': 1, 'stage': reference['stage'], 'client': identity,
            'request': ctx.request.json(), 'source': continuation, 'text': reference},
            'Endfield complete selected original text tables are verified. Canonical dialogue snapshot and selected-audio materialization still follow; no library is active.')

    def _plan_navigation(self, request, ctx, identity, transport, continuation):
        from .endfield_bootstrap_source import SMALL_TOTAL
        from .endfield_resource_source import discover
        from .endfield_text_source import Catalog
        from .endfield_navigation_source import plan as navigation_plan
        Error, Plan, _, _ = _contracts()
        tables_stage = continuation if continuation['stage'] == 'original-text-tables-downloaded' else continuation['tables']
        try:
            common = self._common(self._text_bootstrap(ctx, identity, transport, tables_stage['source']))
        except (ValueError, KeyError, TypeError) as error:
            raise Error('unsupported_original_metadata', 'Endfield original navigation parameters could not be derived. Existing data is retained.') from error
        catalog = Catalog(ctx, identity, common, tables_stage['text'])
        generation = discover(ctx, identity, transport)
        if generation != catalog.generation:
            return self._restart_resources(request, ctx, identity, transport, tables_stage['source'], generation)
        content, _ = navigation_plan(ctx, identity, common, generation, transport)
        handle = {'schema': 1, 'stage': content['stage'], 'client': identity, 'request': request.json(),
                  'tables': tables_stage, 'navigation': content}
        return Plan(revision='endfield-resources-' + hashlib.sha256(_json_bytes(generation)).hexdigest(),
            download_bytes=content['download_bytes'] + 2 * LAUNCHER_LIMIT + 4 * SMALL_TOTAL,
            required_disk_bytes=content['required_disk_bytes'], handle=handle, download_is_upper_bound=True,
            runtime_available=True, stage=handle['stage'],
            message='Separately quoted complete original registry or required bundle indexes, plus bounded source rechecks. Exact graph/UI owners follow the verified registry; no dialogue library is active.')

    def _download_navigation(self, plan, ctx):
        Error, _, Stage, _ = _contracts()
        continuation = {'schema': 1, 'stage': 'original-text-navigation-pending',
                        'client': plan.handle.get('client'), 'request': ctx.request.json(), 'tables': plan.handle.get('tables')}
        current = self._plan(ctx.request, ctx, continuation)
        if (current.handle != plan.handle or current.revision != plan.revision or
                current.download_bytes != plan.download_bytes or current.required_disk_bytes != plan.required_disk_bytes or
                current.stage != plan.stage or plan.download_is_upper_bound is not True or plan.runtime_available is not True):
            raise Error('publisher_size_changed', 'Endfield original navigation, verified cache or quoted transfer changed. Check its size again.')
        from .endfield_resource_source import discover
        from .endfield_navigation_source import plan as navigation_plan, download
        transport = self._transport(ctx.request, ctx)
        identity = current.handle['client']
        tables_stage = current.handle['tables']
        try:
            common = self._common(self._text_bootstrap(ctx, identity, transport, tables_stage['source']))
        except (ValueError, KeyError, TypeError) as error:
            raise Error('unsupported_original_metadata', 'Endfield original navigation parameters changed before download. Existing data is retained.') from error
        quoted, index = navigation_plan(ctx, identity, common, current.handle['navigation']['generation'], transport)
        if quoted != current.handle['navigation']:
            raise Error('publisher_size_changed', 'Endfield original navigation changed before its approved download.')
        result = download(ctx, identity, common, quoted, index, transport,
            recheck=lambda: (self._latest(ctx.request, transport)[0], discover(ctx, identity, transport)))
        return Stage({'schema': 1, 'stage': result['stage'], 'client': identity,
            'request': ctx.request.json(), 'tables': tables_stage, 'navigation': result},
            'Endfield original navigation source stage is complete. Remaining selected bundle acquisition and verified presentation decoding still precede a complete capture-ready library.')

    def _restart_resources(self, request, ctx, identity, transport, source, generation):
        # A normal resource hotfix need not change the client. Reuse only this
        # exact client's checked upstream source; never reset/delete old data or
        # loop forever on the superseded downstream stage handle.
        if request.content_mode == 'text':
            return self._plan_text(request, ctx, identity, transport, source, generation=generation)
        Error, _, _, _ = _contracts()
        if not isinstance(source, dict) or source.get('stage') != 'original-audio-master-verified':
            raise Error('invalid_local_state', 'Endfield changed and needs its exact original audio source before replanning.')
        return self._plan_control(request, ctx, identity, transport, source.get('native'), generation=generation)


def create_provider(*, platform, native=None, transport_factory=None):
    return EndfieldGameDataProvider(platform, native, transport_factory=transport_factory)
