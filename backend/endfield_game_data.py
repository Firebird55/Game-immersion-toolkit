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
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


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
                                             limit=2 * 1024**2, kind='metadata')
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
        self._runtime()
        Error, Plan, _, _ = _contracts()
        transport = self._transport(request, ctx)
        identity, declaration = self._latest(request, transport)
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
                  'client': identity, 'artifacts': artifacts, 'ranges': ranges, 'receipts': receipts}
        size = sum(row['bytes'] for row in ranges)
        return Plan(revision='endfield-client-' + identity_stamp(identity), download_bytes=size,
            required_disk_bytes=2 * size + 4352, handle=handle, runtime_available=True,
            stage='client-bootstrap', message='Download original client metadata first; parameter/index verification and a separate text or audio content estimate are still required. This stage activates no game data.')

    def download(self, plan, ctx):
        self._runtime()
        Error, _, Stage, _ = _contracts()
        # Rebuild only the bounded size/source plan, before any large transfer.
        # Changed client, selection, ranges or estimate require new consent.
        current = self.plan(ctx.request, ctx)
        if (plan.handle != current.handle or plan.download_bytes != current.download_bytes or
                plan.required_disk_bytes != current.required_disk_bytes or plan.revision != current.revision or
                plan.stage != 'client-bootstrap' or plan.runtime_available is not True):
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
        from .game_tools import _atomic_file
        _atomic_file(root / 'receipt.json', _json_bytes(result))
        return Stage({'schema': 1, 'stage': result['stage'], 'client': identity,
                      'request': ctx.request.json(), 'receipt_sha256': hashlib.sha256(_json_bytes(result)).hexdigest()},
                     'Original Endfield client metadata is downloaded. Parameter/index verification and another content-size check are still required; no game text or audio is active.')

    def restore(self, handle, ctx):
        Error, _, _, _ = _contracts()
        raise Error('source_not_prepared', 'Endfield client metadata is a preparation stage, not a restorable game library.')


def create_provider(*, platform, native=None, transport_factory=None):
    return EndfieldGameDataProvider(platform, native, transport_factory=transport_factory)
