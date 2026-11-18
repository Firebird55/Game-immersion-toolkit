"""Host registry entry for the proven Reverse: 1999 discovery stage."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
from importlib import import_module
import json
import os
from urllib.error import URLError
from urllib.parse import urlsplit

from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .publisher_transport import PublisherTransport
from .reverse1999_provider import Reverse1999Provider, _selection
from . import reverse1999_release as publisher

PLATFORMS = frozenset(('android', 'windows', 'linux', 'macos'))
METADATA_HOSTS = frozenset((urlsplit(publisher.GLOBAL_SITE).hostname, *publisher.GLOBAL_UPDATE_HOSTS))
BOOTSTRAP_STAGE = 'publisher-bootstrap'
BOOTSTRAP_SCHEMA = 'reverse1999-verified-bootstrap-v1'


def _archive_reader():
    try:
        return import_module('.reverse1999_archive', __package__)
    except ImportError as error:
        if error.name in {'lzma', '_lzma'} or (
                isinstance(error, ModuleNotFoundError) and error.name == f'{__package__}.reverse1999_archive'):
            return None
        raise


def _archive(inventory):
    if (inventory['schema'] != 'reverse1999-launcher-inventory-v1'
            or inventory['region'] != 'global' or inventory['platform'] != 'Windows'):
        raise ValueError('Unrecognized Global publisher inventory.')
    archive_rows = inventory['archives']
    version = inventory['version']
    archives = publisher.package({'targetVersion': version, 'fullPackage': {
        'packageUrls': [row['url'] for row in archive_rows], 'packageSize': inventory['download_bytes'],
        'packageRealSize': inventory['expanded_bytes']}}, version)
    part = archives[0]
    if ([asdict(archive) for archive in archives] != archive_rows or part.part != 0
            or part.resource_revision != inventory['resource_revision']):
        raise ValueError('The Global bootstrap archive identity is unavailable.')
    return part


def _has_bootstrap(ctx, reader, archive):
    handle = getattr(ctx, 'stage_handle', None)
    directory = getattr(ctx, 'stage_directory', None)
    if (not isinstance(handle, dict) or handle.get('schema') != BOOTSTRAP_SCHEMA
            or handle.get('archive_md5') != archive.md5 or handle.get('resource_revision') != archive.resource_revision
            or directory is None):
        return False
    path = directory / 'resources.assets'
    try:
        _no_links(path)
        if not path.is_file() or not 48 <= path.stat().st_size <= reader.MEMBER_LIMIT:
            return False
        with path.open('rb') as source:
            raw = source.read(reader.MEMBER_LIMIT + 1)
        return len(raw) <= reader.MEMBER_LIMIT and hashlib.sha256(raw).hexdigest() == handle.get('asset_sha256')
    except (OSError, ValueError):
        return False


class Reverse1999GameDataProvider(Reverse1999Provider):
    def __init__(self, *, platform, native=None, transport_factory=PublisherTransport):
        if not isinstance(platform, str) or platform not in PLATFORMS:
            raise GameDataError('unsupported_game_data_platform', 'This game data platform is unsupported.')
        self.platform = platform
        # Native/audio services are intentionally unused by a metadata-only stage.
        # Future materialization must remain inside the selected approved plan.
        self.transport_factory = transport_factory
        super().__init__(metadata_fetch=self._fetch_metadata)

    def _fetch_metadata(self, ctx, url, *, body, limit):
        payload = None if body is None else json.dumps(body, separators=(',', ':')).encode('utf-8')
        transport = self.transport_factory(ctx, hosts=METADATA_HOSTS)
        try:
            raw, _receipt = transport.fetch_bytes(url, limit=limit, kind='metadata',
                method='GET' if payload is None else 'POST', body=payload,
                headers={'Content-Type': 'application/json', 'lang': 'en'})
        except GameDataError as error:
            # The source discovery has its own explicit publisher backup list.
            # Semantic/consent/checksum failures must not silently switch hosts.
            if error.code == 'metadata_download_interrupted':
                raise URLError('Original publisher metadata was unavailable.') from error
            raise
        return raw

    def plan(self, request, ctx):
        discovery = super().plan(request, ctx)
        inventory = discovery.handle.get('publisher_inventory')
        if inventory is None:
            return discovery
        reader = _archive_reader()
        if reader is None:
            return replace(discovery, message='Global sources found. Bootstrap verification needs an available LZMA archive reader.')
        try:
            archive = _archive(inventory)
            if _has_bootstrap(ctx, reader, archive):
                return replace(discovery, stage='publisher-bootstrap-verified',
                    message='The Global bootstrap is verified. Selected text and audio still need preparation.')
            transport = self.transport_factory(ctx, hosts=publisher.DOWNLOAD_HOSTS)

            def read_at(offset, size):
                raw, _ = transport.fetch_bytes(archive.url, limit=size, original_range=(offset, size, archive.size))
                return raw

            quote = reader.quote_bootstrap(read_at, archive.size)
        except (KeyError, TypeError, ValueError, reader.lzma.LZMAError):
            return discovery
        except GameDataError as error:
            if error.code in {'metadata_download_interrupted', 'publisher_response_invalid',
                              'publisher_size_changed', 'publisher_range_changed'}:
                return discovery
            raise
        ctx.check()
        return GameDataPlan(discovery.revision + '/bootstrap', archive.size, quote.member_size + 64 * 1024,
            handle={**discovery.handle, 'bootstrap': asdict(quote)}, runtime_available=True, stage=BOOTSTRAP_STAGE,
            message='This download verifies the Global bootstrap archive. Text and audio will still need preparation.')

    def verify_global_bootstrap(self, ctx, inventory, quote, *, retained=()):
        ctx.check()
        if _selection(ctx.request)['region'] != 'global':
            raise GameDataError('game_data_plan_changed', 'Select the Global publisher release before continuing.', 409)
        reader = _archive_reader()
        if reader is None:
            raise GameDataError('reverse1999_archive_codec_unavailable', 'The Global archive reader is unavailable on this device.', 409)
        archive = _archive(inventory)
        transport = self.transport_factory(ctx, hosts=publisher.DOWNLOAD_HOSTS)
        try:
            return reader.verify_bootstrap(archive, quote, transport, retained=retained)
        except (ValueError, reader.lzma.LZMAError) as error:
            raise GameDataError('reverse1999_bootstrap_invalid',
                'The Global bootstrap could not be verified. Existing game data was kept.', 422) from error

    def download(self, plan, ctx):
        if plan.stage != BOOTSTRAP_STAGE:
            return super().download(plan, ctx)
        selection = _selection(ctx.request)
        if plan.handle.get('request') != selection or selection['region'] != 'global':
            raise GameDataError('game_data_plan_changed', 'Check this game’s selected download again.', 409)
        reader = _archive_reader()
        if reader is None:
            raise GameDataError('reverse1999_archive_codec_unavailable', 'The Global archive reader is unavailable on this device.', 409)
        try:
            inventory = plan.handle['publisher_inventory']
            quote = reader.BootstrapQuote(**plan.handle['bootstrap'])
            archive = _archive(inventory)
            if plan.download_bytes != archive.size or plan.required_disk_bytes != quote.member_size + 64 * 1024:
                raise ValueError('The quoted Global archive changed.')
        except (KeyError, TypeError, ValueError) as error:
            raise GameDataError('game_data_plan_changed', 'Check this game’s selected download again.', 409) from error
        result = self.verify_global_bootstrap(ctx, inventory, quote)
        ctx.check()
        with (ctx.directory / 'resources.assets').open('xb') as destination:
            destination.write(result.raw_asset)
            destination.flush()
            os.fsync(destination.fileno())
        ctx.check()
        return PreparationStage({'schema': BOOTSTRAP_SCHEMA, 'archive_sha256': result.archive_sha256,
            'archive_md5': archive.md5, 'asset_sha256': result.member.asset_sha256, 'resource_revision': result.member.resource_revision,
            # A new verified copy can repair a damaged stage of the same release.
            'verification_id': ctx.directory.name, 'voice_branch': result.member.voice_branch},
            'Global bootstrap verified. Text and audio are not ready yet.')


def create_provider(*, platform, native=None):
    return Reverse1999GameDataProvider(platform=platform, native=native)
