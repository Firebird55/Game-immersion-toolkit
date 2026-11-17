"""Real shared transport/service fences around inert original-input fixtures."""
import hashlib
import json
import time
from urllib.parse import urlencode

import pytest
import zstandard

from backend import starrail_game_data as game, sophon_assets as sophon
from backend.game_data import GameDataService
from backend.game_data_protocol import GameDataError
from backend.publisher_transport import PublisherTransport
from backend.tests.test_sophon_assets import field
from backend.tests.test_publisher_transport import Response

REQUEST = {'region': 'global', 'source_locale': 'en', 'target_locales': ['zh-Hans'], 'content_mode': 'text'}


def fixture(tmp_path, monkeypatch, *, platform='windows'):
    provider = game.create_provider(platform=platform)
    base = 'https://autopatchos.starrails.com/test/1.2.3'
    original, objects, raw = {}, {}, b''
    chunk_urls = []
    md5 = lambda value: hashlib.md5(value).hexdigest()
    for role, name in game.metadata.CANONICAL.items():
        data = ('Inert original fixture ' + role).encode(); original[role] = data
        encoded = zstandard.ZstdCompressor().compress(data)
        object_name = '0' * 16 + '_' + md5(data)
        url = base + '/' + object_name; objects[url] = encoded; chunk_urls.append(url)
        chunk = field(1, object_name.encode()) + field(2, md5(data).encode()) + field(3, 0) + field(4, len(encoded)) + field(5, len(data))
        raw += field(1, field(1, name.encode()) + field(2, chunk) + field(4, len(data)) + field(5, md5(data).encode()))
    encoded = zstandard.ZstdCompressor().compress(raw)
    manifest = 'manifest_' + '0' * 16 + '_' + md5(raw); objects[base + '/' + manifest] = encoded
    channel = 'starrail-global'; (launcher, launcher_id, downloader), app, platform_id, _ = sophon.CHANNELS[channel]
    main = {'branch': 'main', 'tag': '1.2.3', 'password': 'inert-fixture', 'package_id': 'fixture'}
    objects[f'https://{launcher}/hyp/hyp-connect/api/getGameBranches?launcher_id={launcher_id}'] = json.dumps({
        'retcode': 0, 'data': {'game_branches': [{'game': {'id': app}, 'main': main}]}}).encode()
    # The real reader builds its query in tag/branch/password/package order.
    query = urlencode({key: main[key] for key in ('tag', 'branch', 'password', 'package_id')} | {'plat_app': platform_id})
    delivery = {'encryption': 0, 'compression': 1, 'url_suffix': '', 'url_prefix': base}
    manifests = [{'matching_field': key, 'manifest': {'id': manifest, 'checksum': md5(raw),
                  'compressed_size': len(encoded), 'uncompressed_size': len(raw)},
                  'manifest_download': delivery, 'chunk_download': delivery}
                 for key in ('game', 'en-us', 'zh-cn', 'ja-jp', 'ko-kr')]
    objects[f'https://{downloader}/downloader/sophon_chunk/api/getBuild?{query}'] = json.dumps({
        'retcode': 0, 'data': {'tag': '1.2.3', 'build_id': 'FixtureA', 'manifests': manifests}}).encode()
    calls, failures = [], set()
    def open_(request, **kwargs):
        assert request.get_method() == 'GET' and request.data is None
        calls.append(request.full_url)
        data = objects[request.full_url]
        if request.full_url in failures:
            return Response(data[:-1], url=request.full_url, headers={'Content-Length': str(len(data))})
        return Response(data, url=request.full_url)
    monkeypatch.setattr(provider, '_transport', lambda ctx: PublisherTransport(ctx, hosts=game.HOSTS, opener=open_))
    monkeypatch.setattr(sophon, 'download', lambda *args, **kwargs: pytest.fail('Hidden global publisher transport'))
    return provider, original, objects, chunk_urls, calls, failures


def finish(service):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        row = next(row for row in service.snapshot()['games'] if row['id'] == 'starrail')
        if row['job'] and row['job']['status'] not in {'queued', 'running'}:
            return row
        time.sleep(.01)
    raise AssertionError('Stage did not finish')


def start(service):
    row = service.plan('starrail', REQUEST)['game']
    service.download('starrail', {'plan_id': row['plan_id'], 'revision': row['revision']})
    return row


def test_exact_original_chunk_estimate_and_whole_inputs_never_become_ready_text(tmp_path, monkeypatch):
    provider, original, objects, chunks, calls, _ = fixture(tmp_path, monkeypatch)
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        row = start(service)
        assert row['download_bytes'] == sum(len(objects[url]) for url in chunks)
        result = finish(service)
        assert result['job']['status'] == 'needs_plan'
        assert result['state'] != 'ready'
        for data in original.values():
            path = tmp_path / 'starrail/cache/original-native/global/native-files' / hashlib.md5(data).hexdigest()
            assert path.read_bytes() == data
        assert not list(tmp_path.rglob('textmap.json'))
        next_plan = service.plan('starrail', REQUEST)['game']
        assert not next_plan['can_download'] and next_plan['download_bytes'] is None
        with pytest.raises(GameDataError, match='archives'):
            provider.restore({}, type('Context', (), {'check': lambda self: None})())
    finally:
        service.close()


def test_interrupted_chunk_retry_reuses_complete_sources_and_refuses_partial_cache(tmp_path, monkeypatch):
    provider, original, objects, chunks, calls, failures = fixture(tmp_path, monkeypatch)
    failures.add(chunks[-1]); service = GameDataService(tmp_path, {'starrail': provider})
    try:
        first = start(service); assert finish(service)['job']['status'] == 'failed'
        assert not list(tmp_path.rglob('textmap.json'))
        failures.clear(); before = len(calls)
        second = start(service); assert second['download_bytes'] < first['download_bytes']
        assert finish(service)['job']['status'] == 'needs_plan'
        assert chunks[0] not in calls[before:] and chunks[1] not in calls[before:]
        assert calls.count(chunks[-1]) == 2
    finally:
        service.close()


def test_cached_chunks_reconstruct_corrupt_whole_input_without_network_asset_transfer(tmp_path, monkeypatch):
    provider, original, _, chunks, calls, _ = fixture(tmp_path, monkeypatch)
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        start(service); assert finish(service)['job']['status'] == 'needs_plan'
        data = original['native']; path = tmp_path / 'starrail/cache/original-native/global/native-files' / hashlib.md5(data).hexdigest()
        path.write_bytes(b'x' * len(data)); before = len(calls)
        row = start(service); assert row['download_bytes'] == 0
        assert finish(service)['job']['status'] == 'needs_plan' and path.read_bytes() == data
        assert not set(chunks) & set(calls[before:])
    finally:
        service.close()


def test_android_metadata_estimate_does_not_authorize_unavailable_runtime_or_audio(tmp_path, monkeypatch):
    provider, _, _, chunks, calls, _ = fixture(tmp_path, monkeypatch, platform='android')
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        row = service.plan('starrail', REQUEST)['game']
        assert row['download_bytes'] > 0 and not row['can_download']
        with pytest.raises(GameDataError):
            service.download('starrail', {'plan_id': row['plan_id'], 'revision': row['revision']})
        assert not set(chunks) & set(calls)
    finally:
        service.close()
