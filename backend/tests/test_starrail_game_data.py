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


def fixture(tmp_path, monkeypatch, *, platform='windows', generation=1):
    from types import SimpleNamespace
    provider = game.create_provider(platform=platform)
    # These tests isolate original format/service I/O. Resolver behavior has
    # separate tests below; no installed SDK or private cache supplies it.
    monkeypatch.setattr(provider, '_reader', lambda directory: SimpleNamespace(identity='b' * 64))
    base = 'https://autopatchos.starrails.com/test/1.2.3/' + str(generation)
    original, objects, raw = {}, {}, b''
    chunk_urls = []
    md5 = lambda value: hashlib.md5(value).hexdigest()
    for role, name in game.metadata.CANONICAL.items():
        data = ('Inert original fixture ' + role + '/' + str(generation)).encode(); original[role] = data
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
        'retcode': 0, 'data': {'tag': '1.2.3', 'build_id': 'Fixture' + str(generation), 'manifests': manifests}}).encode()
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
        assert next_plan['download_bytes'] == 0 and next_plan['state'] != 'ready'
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
    monkeypatch.setattr(provider, '_reader', lambda *a: pytest.fail('Android must not select a desktop runtime'))
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        row = service.plan('starrail', REQUEST)['game']
        assert row['download_bytes'] > 0 and not row['can_download']
        with pytest.raises(GameDataError):
            service.download('starrail', {'plan_id': row['plan_id'], 'revision': row['revision']})
        assert not set(chunks) & set(calls)
    finally:
        service.close()


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_missing_default_reader_gates_original_inputs_before_any_large_asset(tmp_path, monkeypatch, mode):
    provider, _, _, chunks, calls, _ = fixture(tmp_path, monkeypatch)
    def missing(directory):
        raise GameDataError('starrail_reader_unavailable', 'The verified reader is unavailable.')
    monkeypatch.setattr(provider, '_reader', missing)
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        row = service.plan('starrail', REQUEST | {'content_mode': mode})['game']
        assert row['download_bytes'] > 0 and not row['can_download']
        assert 'Repair or re-extract' in row['message']
        with pytest.raises(GameDataError):
            service.download('starrail', {'plan_id': row['plan_id'], 'revision': row['revision']})
        assert not set(chunks) & set(calls)
    finally:
        service.close()


def test_reader_removed_after_quote_fails_before_unquoted_rechecks_or_assets(tmp_path, monkeypatch):
    provider, _, _, _, calls, _ = fixture(tmp_path, monkeypatch)
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        row = service.plan('starrail', REQUEST)['game']
        def missing(directory):
            raise GameDataError('starrail_reader_unavailable', 'The verified reader is unavailable.')
        monkeypatch.setattr(provider, '_reader', missing); before = len(calls)
        service.download('starrail', {'plan_id': row['plan_id'], 'revision': row['revision']})
        assert finish(service)['job']['status'] == 'failed' and len(calls) == before
    finally:
        service.close()


def test_default_runtime_uses_verified_prebuilt_closure_without_sdk_or_cache_fallback(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend import prebuilt_readers
    native = object(); provider = game.create_provider(platform='windows', native=native)
    assert provider.native is native
    executable = tmp_path / 'delivered' / 'StarRailMetadata.exe'
    calls = []
    def resolve(kind):
        calls.append(kind)
        return SimpleNamespace(executable=executable, source_identity='a' * 64, manifest={'build_id': 'b' * 64})
    monkeypatch.setattr(prebuilt_readers, 'prebuilt_reader', resolve)
    monkeypatch.setattr(game.metadata, 'helper', lambda *a, **k: pytest.fail('No SDK or mutable-cache helper fallback'))
    helper = provider._reader(tmp_path / 'untrusted-cache')
    assert calls == ['starrail'] and helper.command == (str(executable),)
    assert helper.identity == game.metadata._identity({'source': 'a' * 64, 'build': 'b' * 64})
    def missing(kind):
        raise ValueError('private-resource-location')
    monkeypatch.setattr(prebuilt_readers, 'prebuilt_reader', missing)
    with pytest.raises(GameDataError) as error:
        provider._reader(tmp_path)
    assert error.value.code == 'starrail_reader_unavailable' and 'private-resource-location' not in str(error.value)


def test_finite_text_stages_activate_real_shared_matcher_and_restore_without_network(tmp_path, monkeypatch):
    """Only native/catalog format boundaries are authored fixture substitutes."""
    from types import SimpleNamespace
    from backend import starrail_native_preparation, starrail_original_provider
    from backend.starrail_original_catalog import OriginalCatalog
    from backend.starrail_original_tables import OriginalTables
    from backend.tests.test_starrail_text_only import Catalog
    from backend.xxhash64 import xxhash64
    provider, _, objects, _, calls, _ = fixture(tmp_path, monkeypatch)
    state = {'metadata_ready': False}
    reader = SimpleNamespace(identity='b' * 64)
    monkeypatch.setattr(provider, '_reader', lambda directory: reader)
    def probe(*args, **kwargs):
        assert kwargs.get('allow_generate') is False
        if not state['metadata_ready']:
            raise ValueError('Not prepared')
        return object()
    monkeypatch.setattr(game.metadata, 'prepare', probe)
    def derive(*args, **kwargs):
        assert kwargs['reader'] is reader and callable(kwargs['fetch'])
        state['metadata_ready'] = True
        return SimpleNamespace(identity='a' * 64)
    monkeypatch.setattr(starrail_native_preparation, 'prepare', derive)
    assets = {}
    for name in ('core', 'mission', 'caption'):
        body = ('authored complete ' + name + ' package').encode()
        from backend.starrail_hotfix import AudioFile
        asset = AudioFile(name + '.bytes', len(body), hashlib.md5(body).hexdigest(), 'https://autopatchos.starrails.com/test/' + name)
        assets[name] = asset; objects[asset.url] = body
    class TextCatalog(Catalog):
        _mission_paths = OriginalCatalog._mission_paths
        _overrides = OriginalCatalog._overrides
        def __init__(self, ctx, build):
            super().__init__(); self.data = self.tables
            self.build = build | {'content_mode': 'text', 'hotfix': {'authored_fixture': 'pinned-original-generation'}}
            self.data['VideoConfig'] = [{'VideoID': 1, 'CaptionPath': 'Config/CutSceneCaption/OwnedFilm_Caption.json', 'VideoPath': 'Owned.usm'}]
            self.data['PerformanceVideo'] = [{'PerformanceID': 1, 'PerformancePath': 'Config/Level/Mission/1/Act/Act1.json'}]
            self.movie_files = {'owned.usm': SimpleNamespace(task_ids=(1,), name='Owned.usm', size=12, digest='c' * 32)}
            self.configs = SimpleNamespace(descriptions=SimpleNamespace(binary_path=lambda path: 'BakedConfig/' + path[:-5] + '.bytes'))
            self.tables = OriginalTables.__new__(OriginalTables)
            self.tables.directory = provider._directory(ctx, 'global') / 'sophon'
            transport = provider._transport(ctx)
            self.tables.package_fetch = lambda url, *, limit: transport.fetch_bytes(url, limit=limit, kind='asset', expected_size=limit)[0]
            self.tables.resources = {}
            paths = {'BakedConfig/ExcelOutput/' + name + '.bytes' for name in starrail_original_provider.TABLES}
            paths.update('BakedConfig/ExcelOutput/' + name + '.bytes' for name in ('TextmapMain_en', 'Textmap_en', 'TextmapMain_cn', 'Textmap_cn'))
            for path in paths:
                self.tables.resources[xxhash64(path.encode())] = assets['core'], 0, assets['core'].size
            for name, path in [('mission', 'Config/Level/Mission/1/Act/Act1.json'),
                               ('caption', 'Config/CutSceneCaption/OwnedFilm_Caption.json'),
                               ('caption', 'Config/CutSceneCaption/Alternate_Caption.json')]:
                self.tables.resources[xxhash64(self.configs.descriptions.binary_path(path).encode())] = assets[name], 0, assets[name].size
        def file(self, path, **kwargs):
            if path.startswith('TextMap/'):
                return {str(key): ('原始测试台词' if 'CHS' in path else 'Original fixture sentence number ') + str(key) for key in range(101, 106)}
            if path.startswith('Config/'):
                return {'OnStartSequece': [{'TaskList': [{'$type': 'RPG.GameCore.PlayVideo', 'VideoID': 1,
                    'OverrideCaptionPath': 'Config/CutSceneCaption/Alternate_Caption.json'}]}]}
            return self.data.get(path.removeprefix('ExcelOutput/').removesuffix('.json'), [])
    monkeypatch.setattr(provider, '_text_context', lambda ctx, build, reader, discover: (
        'sophon-' + 'f' * 64, TextCatalog(ctx, build), SimpleNamespace(identity='a' * 64)))
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        phases = []
        for number in range(6):
            row = start(service); result = finish(service)
            phases.append(result['job']['status'])
            assert result['job']['status'] in {'needs_plan', 'complete'}
            if number == 2:
                # A discovered pending generation continues from its exact
                # same-request stage; the mutable launcher is unnecessary.
                for url in list(objects):
                    if '/getGameBranches?' in url or '/getBuild?' in url:
                        del objects[url]
            if result['job']['status'] == 'complete':
                break
        assert result['job']['status'] == 'complete'
        assert len(phases) == 6
        assert all(asset.url in calls for asset in assets.values())
        before = len(calls)
        source = service.restore('starrail')
        assert len(calls) == before and source.voice_source is None
        payload = json.loads(source.snapshot_path.read_bytes())
        assert payload['content_mode'] == 'text' and all(not row['audio'] for row in payload['records'])
        assert source.source_proof.origin == 'official'
        # A real subsequent input stage must keep this verified Ready A;
        # stage archives must not occupy its current/restore slot.
        previous_sha = hashlib.sha256(source.snapshot_path.read_bytes()).hexdigest()
        next_provider, *_ = fixture(tmp_path, monkeypatch, generation=2)
        service.providers['starrail'] = next_provider
        start(service)
        assert finish(service)['job']['status'] == 'needs_plan'
        retained = service.restore('starrail')
        assert retained.snapshot_path == source.snapshot_path
        assert hashlib.sha256(retained.snapshot_path.read_bytes()).hexdigest() == previous_sha
        source.snapshot_path.write_bytes(b'corrupt')
        with pytest.raises(GameDataError, match='integrity'):
            service.restore('starrail')
    finally:
        service.close()


def test_pending_source_is_hash_bound_and_never_crosses_request_or_edition():
    from types import SimpleNamespace
    from backend.game_data_protocol import GameDataRequest
    request = GameDataRequest.parse(REQUEST)
    raw = {'schema': game.STAGE_SCHEMA, 'request': request.json(), 'build': {'channel': 'starrail-global',
           'version': '1.2.3', 'hotfix': {'owned': 'generation'}}, 'files': {}, 'ready': False}
    handle = raw | {'receipt_sha256': game._identity(raw)}
    assert game._staged_build(SimpleNamespace(stage_handle=handle), request) == raw['build']
    changed_request = GameDataRequest('global', 'ja', (), 'text')
    assert game._staged_build(SimpleNamespace(stage_handle=handle), changed_request) is None
    changed = handle | {'files': {'foreign': 'owner'}}
    with pytest.raises(GameDataError, match='receipt changed'):
        game._staged_build(SimpleNamespace(stage_handle=changed), request)
    with pytest.raises(GameDataError, match='malformed'):
        game._staged_build(SimpleNamespace(stage_handle=handle | {'unknown': 7}), request)
    foreign = raw | {'build': raw['build'] | {'channel': 'starrail-cn'}}
    with pytest.raises(GameDataError, match='another publisher edition'):
        game._staged_build(SimpleNamespace(stage_handle=foreign | {'receipt_sha256': game._identity(foreign)}), request)


def audio_fixture(tmp_path, monkeypatch):
    """Actual shared service + HTTPS range/cache parsers after native boundary."""
    from types import SimpleNamespace
    from backend import starrail_hotfix
    from backend.tests.test_starrail_game_audio import package
    provider, _, objects, _, calls, _ = fixture(tmp_path, monkeypatch)
    request = REQUEST | {'content_mode': 'text-audio'}
    reader = SimpleNamespace(identity='b' * 64)
    monkeypatch.setattr(provider, '_reader', lambda directory: reader)
    monkeypatch.setattr(game.metadata, 'prepare', lambda *a, **k: object())
    monkeypatch.setattr(game, '_required_text', lambda catalog, request: ('text-snapshot', {}, {}))
    body = package(); digest = hashlib.md5(body).hexdigest()
    raw = json.dumps({'Path': 'English/External.pck', 'Md5': digest, 'Size': len(body), 'Patch': True}).encode()
    routes = {key: folder + '/V1.2Live/output_123_ab_cd' for key, folder in
              [('design', 'design_data'), ('asb', 'asb'), ('base', 'asb'), ('lua', 'lua')]}
    hotfix = {'routes': routes, 'indexes': {'audio': [123, hashlib.md5(raw).hexdigest(), len(raw)]}}
    captured = {}
    def context(ctx, build, reader, *, discover, offline=False):
        catalog = SimpleNamespace(build=build | {'content_mode': 'text', 'hotfix': hotfix},
            tables=SimpleNamespace(directory=provider._directory(ctx, 'global') / 'sophon'))
        root = starrail_hotfix.roots(catalog.build)['asb']
        objects[root + 'AudioBlock/AudioV_' + hashlib.md5(raw).hexdigest() + '.bytes'] = raw
        captured['catalog'] = catalog
        return 'sophon-' + 'f' * 64, catalog, SimpleNamespace(identity='a' * 64)
    monkeypatch.setattr(provider, '_text_context', context)
    monkeypatch.setattr(starrail_hotfix, 'download', lambda *a, **k: pytest.fail('Hidden global audio index transport'))
    tags = {'value': '"opaque-audio-generation"'}
    def open_(req, **kwargs):
        calls.append(req.full_url)
        if req.get_header('Range'):
            assert req.get_method() == 'GET' and req.full_url.endswith('/AudioBlock/English/External.pck')
            start, end = map(int, req.get_header('Range')[6:].split('-'))
            return Response(body[start:end+1], status=206, url=req.full_url, headers={
                'Content-Length': str(end-start+1), 'Content-Range': f'bytes {start}-{end}/{len(body)}', 'ETag': tags['value']})
        return Response(objects[req.full_url], url=req.full_url)
    monkeypatch.setattr(provider, '_transport', lambda ctx: PublisherTransport(ctx, hosts=game.HOSTS, opener=open_))
    return provider, request, calls, captured, tags


def test_text_audio_inventory_is_explicitly_quoted_and_never_activates_partial_audio(tmp_path, monkeypatch):
    provider, request, calls, _, _ = audio_fixture(tmp_path, monkeypatch)
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        for expected, transfer in [('original-native-inputs', None), ('audio-inventory-prefixes', 28), ('audio-inventory-headers', 40)]:
            row = service.plan('starrail', request)['game']
            if transfer is not None:
                assert row['download_bytes'] == transfer
            before = len(calls)
            service.download('starrail', {'plan_id': row['plan_id'], 'revision': row['revision']})
            result = finish(service)
            assert result['job']['status'] == 'needs_plan' and result['state'] != 'ready'
            if transfer is not None:
                assert len(calls) == before + 1
        final = service.plan('starrail', request)['game']
        assert not final['can_download'] and final['download_bytes'] is None
        assert not list(tmp_path.rglob('textmap.json'))
    finally:
        service.close()


def test_lost_audio_index_between_quote_and_download_fails_without_unquoted_request(tmp_path, monkeypatch):
    provider, request, calls, captured, _ = audio_fixture(tmp_path, monkeypatch)
    service = GameDataService(tmp_path, {'starrail': provider})
    try:
        first = service.plan('starrail', request)['game']
        service.download('starrail', {'plan_id': first['plan_id'], 'revision': first['revision']})
        assert finish(service)['job']['status'] == 'needs_plan'
        row = service.plan('starrail', request)['game']; assert row['download_bytes'] == 28
        catalog = captured['catalog']
        (catalog.tables.directory / 'starrail-indexes' / catalog.build['hotfix']['indexes']['audio'][1]).unlink()
        before = len(calls)
        service.download('starrail', {'plan_id': row['plan_id'], 'revision': row['revision']})
        assert finish(service)['job']['status'] == 'failed'
        assert len(calls) == before and not list(tmp_path.rglob('textmap.json'))
        # A new explicit plan repairs metadata under the planning budget.
        retry = service.plan('starrail', request)['game']; assert retry['download_bytes'] == 28
        assert len(calls) > before
    finally:
        service.close()
