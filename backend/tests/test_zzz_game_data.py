"""The portable bootstrap stage must obey real transport and readiness fences."""
from dataclasses import replace
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlencode

from Crypto.PublicKey import RSA
import pytest
import zstandard

from backend import hoyo_dispatch_metadata as metadata, sophon_assets as sophon, zzz_game_data as game
from backend.game_data_protocol import GameDataError, GameDataRequest, PreparationStage, MAX_METADATA_BYTES
from backend.game_data import GameDataService
from backend.publisher_transport import PublisherTransport
from backend.tests.test_sophon_assets import field
from backend.tests.test_hoyo_bootstrap_assets import asset_file
from backend.tests.test_hoyo_zzz_bootstrap import document
from backend.tests.test_zzz_native_key_data import image, initializer


class Context:
    game = 'zzz'
    def __init__(self, root, request, phase='plan', budget=MAX_METADATA_BYTES):
        self.request, self.phase, self.budget, self.consumed = request, phase, budget, 0
        self.cache_directory, self.directory = root / 'cache', root / phase
        self.directory.mkdir(parents=True, exist_ok=True)
        self.transfer_lock = threading.RLock()
        self.stopped = False
    def check(self):
        if self.stopped: raise GameDataError('preparation_cancelled', 'Preparation stopped.', 409)
    def cancelled(self): return self.stopped
    def consume_bytes(self, count, *, kind='asset'):
        self.check()
        if self.phase == 'plan' and kind != 'metadata' or kind == 'audio' and self.request.content_mode == 'text':
            raise GameDataError('unapproved_asset_transfer', 'Download consent is required.')
        if self.consumed + count > self.budget:
            raise GameDataError('transfer_budget_exceeded', 'The source exceeded its approved size.')
        self.consumed += count
    def remaining_bytes(self, *, kind='asset'):
        self.consume_bytes(0, kind=kind)
        return self.budget - self.consumed
    def progress(self, *args): self.check()


class Response:
    status = 200
    def __init__(self, url, data):
        self.url, self.stream = url, io.BytesIO(data)
        self.headers = Message(); self.headers['Content-Length'] = str(len(data))
    def __enter__(self): return self
    def __exit__(self, *args): self.stream.close()
    def geturl(self): return self.url
    def read(self, count): return self.stream.read(count)


def publisher(region, version='3.3.0', key=None):
    key = key or RSA.generate(1024)
    channel = 'zzz-' + region
    (launcher, launcher_id, downloader), identity, platform, host = sophon.CHANNELS[channel]
    prefix = 'https://' + host + '/synthetic/' + version
    bodies = {game.bootstrap.RESOURCE: asset_file(document(region, version, 'a' * 16)),
              game.bootstrap.NATIVE_RESOURCE: image(initializer(key))}
    objects, names, chunks = {}, {}, {}
    for name, raw in bodies.items():
        row = field(1, name.encode()) + field(4, len(raw)) + field(5, hashlib.md5(raw).hexdigest().encode())
        ranges = [(0, raw)] if name == game.bootstrap.RESOURCE else [(0, raw[:0x800]), (0x800, raw[0x800:])]
        chunks[name] = []
        for offset, data in ranges:
            digest = hashlib.md5(data).hexdigest()
            object_id = '0' * 16 + '_' + digest
            encoded = zstandard.ZstdCompressor().compress(data)
            objects[prefix + '/' + object_id] = encoded
            chunks[name].append((offset, len(data), len(encoded), object_id, digest))
            row += field(2, field(1, object_id.encode()) + field(2, digest.encode()) + field(3, offset)
                         + field(4, len(encoded)) + field(5, len(data)))
        names[name] = field(1, row)
    manifest = b''.join(names.values())
    md5 = hashlib.md5(manifest).hexdigest()
    manifest_id = 'manifest_' + '0' * 16 + '_' + md5
    packed = zstandard.ZstdCompressor().compress(manifest)
    objects[prefix + '/' + manifest_id] = packed
    main = {'tag': version, 'branch': 'main', 'password': 'transient', 'package_id': 'package'}
    objects[f'https://{launcher}/hyp/hyp-connect/api/getGameBranches?launcher_id={launcher_id}'] = json.dumps(
        {'retcode': 0, 'data': {'game_branches': [{'game': {'id': identity}, 'main': main}]}}).encode()
    query = urlencode({key: main[key] for key in ('tag', 'branch', 'password', 'package_id')} | {'plat_app': platform})
    rows = [{'matching_field': locale,
        'manifest': {'id': manifest_id, 'compressed_size': len(packed), 'uncompressed_size': len(manifest), 'checksum': md5},
        'manifest_download': {'encryption': 0, 'compression': 1, 'url_suffix': '', 'url_prefix': prefix},
        'chunk_download': {'encryption': 0, 'compression': 1, 'url_suffix': '', 'url_prefix': prefix}}
        for locale in ['game', *sorted(set(sophon.VOICE_FIELDS.values()))]]
    objects[f'https://{downloader}/downloader/sophon_chunk/api/getBuild?{query}'] = json.dumps(
        {'retcode': 0, 'data': {'tag': version, 'build_id': 'Generation' + version.replace('.', ''), 'manifests': rows}}).encode()
    return objects, bodies, chunks, key


def provider(objects, calls, platform='android'):
    def factory(ctx, *, hosts):
        def open(request, **kwargs):
            calls.append((ctx.phase, request.full_url))
            return Response(request.full_url, objects[request.full_url])
        return PublisherTransport(ctx, hosts=hosts, opener=open)
    return game.ZzzGameDataProvider(platform=platform, native=object(), transport_factory=factory)


@pytest.mark.parametrize('region', ['global', 'cn'])
def test_original_bootstrap_is_a_bounded_download_stage_and_never_ready(tmp_path, monkeypatch, region):
    objects, bodies, chunks, key = publisher(region)
    calls = []
    reader = provider(objects, calls)
    request = GameDataRequest(region, 'ja', ('en',))
    def forbidden(*args, **kwargs): raise AssertionError('Provider escaped to a global/community downloader')
    monkeypatch.setattr(sophon, 'download', forbidden)
    monkeypatch.setattr(metadata, 'initial_seed', forbidden)
    monkeypatch.setattr(metadata, 'fetch', forbidden)
    planning = Context(tmp_path, request)
    plan = reader.plan(request, planning)
    assert plan.runtime_available and plan.stage == 'official-bootstrap' and plan.download_is_upper_bound
    assert plan.source_proof is None
    missing = [row for row in plan.handle['containers'] if not row['cached']]
    assert plan.download_bytes == sum(row['compressed_bytes'] for row in missing)
    assert planning.consumed <= MAX_METADATA_BYTES
    body_urls = {url for row in missing for url in row['urls']}
    assert not body_urls.intersection(url for _, url in calls)
    assert all('.pck' not in url for _, url in calls)
    download = Context(tmp_path, request, 'download', plan.download_bytes)
    result = reader.download(plan, download)
    assert isinstance(result, PreparationStage) and download.consumed == plan.download_bytes
    assert (download.directory / 'bootstrap-source.json').is_file()
    raw = json.dumps(result.restore_handle)
    assert 'RSAKeyValue' not in raw and str(key.d) not in raw and 'transient' not in raw
    assert result.restore_handle['bootstrap_proof']['policy'] == 'official-current-client-data'
    with pytest.raises(GameDataError, match='not a prepared dialogue library'):
        reader.restore(result.restore_handle, Context(tmp_path, request, 'restore', 0))
    before = len(calls)
    following = reader.plan(request, Context(tmp_path, request))
    assert following.stage == 'catalogue-runtime' and not following.runtime_available
    assert following.download_bytes is None and following.required_disk_bytes is None
    assert all('/hyp/' in url or '/getBuild?' in url for _, url in calls[before:])
    audio = reader.plan(replace(request, content_mode='text-audio'), Context(tmp_path, replace(request, content_mode='text-audio')))
    assert audio.revision == following.revision and audio.handle['request'] != following.handle['request']


def test_missing_native_runtime_invalid_mode_and_cancel_do_not_open_body_connections(tmp_path, monkeypatch):
    objects, _, _, _ = publisher('global')
    calls = []; reader = provider(objects, calls)
    request = GameDataRequest('global', 'en')
    monkeypatch.setattr(game, '_runtime', lambda: False)
    plan = reader.plan(request, Context(tmp_path, request))
    assert not plan.runtime_available and plan.download_bytes > 0
    before = len(calls)
    with pytest.raises(GameDataError): reader.download(plan, Context(tmp_path, request, 'download', plan.download_bytes))
    assert len(calls) == before
    cancelled = Context(tmp_path, request); cancelled.stopped = True
    with pytest.raises(GameDataError): reader.plan(request, cancelled)
    with pytest.raises(GameDataError):
        reader.plan(GameDataRequest('global', 'fr', content_mode='text-audio'), Context(tmp_path, request))
    assert len(calls) == before


def test_same_format_new_source_replans_and_failed_checksum_keeps_old_bootstrap(tmp_path):
    objects, _, _, _ = publisher('global')
    calls = []; reader = provider(objects, calls)
    request = GameDataRequest('global', 'en')
    first = reader.plan(request, Context(tmp_path, request))
    stage = reader.download(first, Context(tmp_path, request, 'download', first.download_bytes))
    cache = tmp_path / 'cache' / 'zzz-original' / 'global'
    before = {str(path.relative_to(cache)): hashlib.sha256(path.read_bytes()).hexdigest() for path in cache.rglob('*') if path.is_file()}
    newer, _, _, _ = publisher('global', '3.4.0')
    objects.clear(); objects.update(newer)
    changed = reader.plan(request, Context(tmp_path, request))
    assert changed.revision != first.revision
    body = next(url for row in changed.handle['containers'] if not row['cached'] for url in row['urls'])
    objects[body] = b'x' * len(objects[body])
    with pytest.raises((ValueError, zstandard.ZstdError)):
        reader.download(changed, Context(tmp_path, request, 'download', changed.download_bytes))
    assert all((cache / name).is_file() and hashlib.sha256((cache / name).read_bytes()).hexdigest() == sha for name, sha in before.items())
    assert stage.restore_handle['revision'] == first.revision


def test_changed_request_or_cache_rejects_before_approved_transfer(tmp_path):
    objects, _, _, _ = publisher('global')
    calls = []; reader = provider(objects, calls)
    request = GameDataRequest('global', 'en')
    plan = reader.plan(request, Context(tmp_path, request))
    before = len(calls)
    with pytest.raises(GameDataError):
        reader.download(plan, Context(tmp_path, replace(request, content_mode='text-audio'), 'download', plan.download_bytes))
    digest = plan.handle['build']['manifests']['game'][4]
    (tmp_path / 'cache/zzz-original/global/manifests' / digest).write_bytes(b'corrupt')
    with pytest.raises(GameDataError):
        reader.download(plan, Context(tmp_path, request, 'download', plan.download_bytes))
    assert len(calls) == before


def test_real_service_exposes_bootstrap_needs_plan_then_reader_unavailable(tmp_path):
    objects, _, _, _ = publisher('global')
    calls = []; reader = provider(objects, calls)
    request = GameDataRequest('global', 'en')
    service = GameDataService(tmp_path / 'host', {'zzz': reader})
    def status():return next(row for row in service.snapshot()['games'] if row['id'] == 'zzz')
    try:
        planned = service.plan('zzz', request.json())['game']
        assert planned['can_download'] and planned['download_bytes'] > 0 and planned['content_mode'] == 'text'
        service.download('zzz', {'plan_id': planned['plan_id'], 'revision': planned['revision']})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = status()
            if row['job'] and row['job']['status'] not in {'running', 'queued'}:break
            time.sleep(.01)
        assert row['job']['status'] == 'needs_plan' and row['state'] != 'ready'
        assert row['installed_bytes'] > 0 and row['can_delete']
        following = service.plan('zzz', request.json())['game']
        assert not following['can_download'] and following['download_bytes'] is None
        assert following['state'] != 'ready' and 'Dialogue preparation' in following['message']
    finally:
        service.close()
