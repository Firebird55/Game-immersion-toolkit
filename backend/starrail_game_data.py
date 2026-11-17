"""Context-bound original Star Rail input stages; archives are never ready text.

The ordinary desktop catalog consumer is separate until its complete transport
and runtime closure is connected here. In particular, an Android estimate never
implies an available .NET metadata helper or original-audio decoder.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import sophon_assets as sophon, starrail_metadata as metadata
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage, MAX_HANDLE_BYTES
from .publisher_transport import PublisherTransport
from .private_data_paths import _no_links

SCHEMA = 'starrail-original-input-plan-v1'
STAGE_SCHEMA = 'starrail-original-input-stage-v1'
MAXIMUM = {'native': 1024 * 1024**2, 'metadata': 512 * 1024**2, 'startup': 64 * 1024**2}
SOURCE_LOCALES = frozenset({'en', 'ja', 'ko', 'zh-Hans', 'zh-Hant'})
TEXT_LOCALES = frozenset({'en', 'ja', 'ko', 'zh-Hans', 'zh-Hant', 'de', 'es', 'fr', 'id', 'pt', 'ru', 'th', 'vi'})
HOSTS = frozenset({'sg-hyp-api.hoyoverse.com', 'sg-public-api.hoyoverse.com', 'hyp-api.mihoyo.com',
                   'api-takumi.mihoyo.com', 'autopatchos.starrails.com', 'autopatchcn.bhsr.com'})


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _valid_request(request):
    if request.source_locale not in SOURCE_LOCALES or set(request.target_locales) - TEXT_LOCALES:
        raise GameDataError('unsupported_game_languages', 'Choose an official Star Rail text and spoken language.')


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

    def _transport(self, ctx):
        return PublisherTransport(ctx, hosts=HOSTS)

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
        build = sophon.release('starrail-' + request.region, fetch=fetch)
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
        if complete:
            return GameDataPlan(revision, None, None, handle, stage='catalog-runtime', runtime_available=False,
                message='Original metadata is verified. Study text and recordings are not available from this preparation yet.')
        return GameDataPlan(revision, download, disk, handle, stage='original-native-inputs', runtime_available=True,
            message='This downloads original metadata only. It does not prepare study text or recordings yet; their sizes are not included.')

    def download(self, plan, ctx):
        handle = plan.handle
        if (not isinstance(handle, dict) or set(handle) != {'schema', 'request', 'build', 'files'}
                or handle.get('schema') != SCHEMA or handle.get('request') != ctx.request.json()
                or plan.stage != 'original-native-inputs' or self.platform == 'android'):
            raise GameDataError('starrail_plan_changed', 'Check the Star Rail download size again.')
        _valid_request(ctx.request); ctx.check()
        directory = self._directory(ctx, ctx.request.region)
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
        receipt = {'schema': STAGE_SCHEMA, 'request': ctx.request.json(), 'build': handle['build'],
                   'files': _file_receipts(selected), 'ready': False}
        raw = json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()
        output = Path(ctx.directory) / 'original-inputs.json'
        _no_links(output); output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        return PreparationStage({'schema': STAGE_SCHEMA, 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
                                 'request': ctx.request.json(), 'build': handle['build'], 'files': handle['files']},
            'Original metadata downloaded. Study text and recordings are not available from this preparation yet.')

    def restore(self, handle, ctx):
        ctx.check()
        raise GameDataError('starrail_catalog_not_ready', 'Original input archives cannot restore a ready Star Rail library.', 409)


def create_provider(*, platform, native=None):
    if platform not in {'android', 'windows', 'linux', 'macos'}:
        return None
    return StarRailProvider(platform, native)
