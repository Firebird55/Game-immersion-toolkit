"""The portable bootstrap stage must obey real transport and readiness fences."""
import base64
import builtins
from dataclasses import replace
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
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
    stage_handle = None
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


def provider(objects, calls, platform='android', provider_type=game.ZzzGameDataProvider):
    def factory(ctx, *, hosts):
        def open(request, **kwargs):
            calls.append((ctx.phase, request.full_url))
            return Response(request.full_url, objects[request.full_url])
        return PublisherTransport(ctx, hosts=hosts, opener=open)
    return provider_type(platform=platform, native=object(), transport_factory=factory)


@pytest.mark.parametrize('region', ['global', 'cn'])
def test_original_bootstrap_is_a_bounded_download_stage_and_never_ready(tmp_path, monkeypatch, region):
    objects, bodies, chunks, key = publisher(region)
    original_import = builtins.__import__

    def portable_import(name, *args, **kwargs):
        if name.split('.')[0] in {'Crypto', 'brotli'}:
            raise AssertionError('Original ZZZ bootstrap imported a desktop dependency')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', portable_import)
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


def test_invalid_mode_and_cancel_do_not_open_body_connections(tmp_path):
    objects, _, _, _ = publisher('global')
    calls = []; reader = provider(objects, calls)
    request = GameDataRequest('global', 'en')
    cancelled = Context(tmp_path, request); cancelled.stopped = True
    with pytest.raises(GameDataError): reader.plan(request, cancelled)
    with pytest.raises(GameDataError):
        reader.plan(GameDataRequest('global', 'fr', content_mode='text-audio'), Context(tmp_path, request))
    assert not calls


def test_android_current_update_metadata_uses_the_attested_gateway_without_desktop_crypto(tmp_path, monkeypatch):
    from Crypto.Cipher import PKCS1_v1_5
    from backend.publisher_crypto import SOURCE_SHA256, MAX_BYTES
    from backend.xxhash64 import xxhash64

    objects, _, _, key = publisher('global')
    calls = []
    reader = provider(objects, calls)
    request = GameDataRequest('global', 'ja', ('en',))
    initial = reader.plan(request, Context(tmp_path, request))
    stage = reader.download(initial, Context(tmp_path, request, 'download', initial.download_bytes))
    retained = (tmp_path / 'download' / 'bootstrap-source.json').read_bytes()

    dispatch = 'https://globaldp-prod-os01.zenlesszonezero.com/query_dispatch?version=OSPRODWin3.3.0&channel_id=1'
    gateway = 'https://prod-gf-eu.zenlesszonezero.com/query_gateway'
    objects[dispatch] = json.dumps({'retcode': 0, 'region_list': [
        {'retcode': 0, 'name': 'prod_gf_eu', 'is_recommend': True, 'dispatch_url': gateway}
    ]}).encode()
    gateway += '?version=OSPRODWin3.3.0&seed=' + 'a' * 16 + '&channel_id=1&rsa_ver=1'
    base = b'933_abcdef'
    index_names = {'design_data': ('data_version',), 'game_res': ('res_version', 'audio_version', 'base_revision'),
                   'silence_data': ('silence_version',)}
    updates = {}
    for name, revision in [('design_data', 'data_revision'), ('game_res', 'res_revision'), ('silence_data', 'silence_revision')]:
        path = 'game_res' if name == 'game_res' else 'design_data'
        client = 'client_silence' if name == 'silence_data' else 'client'
        prefix = f'https://autopatchos.zenlesszonezero.com/{path}/3.3_live/output_2000_abcdef/{client}/'
        replies = [{'fileName': entry, 'fileSize': len(base), 'fileMD5': str(xxhash64(base))}
                   for entry in index_names[name]]
        updates[name] = {'base_url': prefix, revision: '2000', 'md5_files': json.dumps(replies)}
        if name == 'game_res':
            base_url = prefix + 'StandaloneWindows64/oversea/base_revision'
    updates['game_res']['audio_revision'] = '2001'
    payload = json.dumps({'retcode': 0, 'cdn_conf_ext': updates}).encode()
    encrypt = PKCS1_v1_5.new(key.public_key())
    decrypt = PKCS1_v1_5.new(key)
    encrypted = b''.join(encrypt.encrypt(payload[i:i + 117]) for i in range(0, len(payload), 117))
    objects[gateway] = json.dumps({'content': base64.b64encode(encrypted).decode('ascii'), 'sign': 'authored'}).encode()
    objects[base_url] = base
    blocks = []

    class AndroidCrypto:
        def proof(self):
            return json.dumps({'schema': 'toolkit-publisher-crypto-v1', 'abi': 'arm64-v8a',
                'source_sha256': SOURCE_SHA256, 'platform_primitives': 'JCA',
                'apk_entry_verified': True, 'licenses_verified': True, 'system_fallback': False,
                'original_client_execution': False, 'account_keys_reused': False, 'pointer_bits': 64,
                'library_sha256': 'a'*64, 'manifest_sha256': 'b'*64, 'key_bytes': 32,
                'nonce_bytes': 12, 'max_bytes': MAX_BYTES})

        def rsaDecryptPkcs1(self, n, e, d, p, q, body):
            assert tuple(int.from_bytes(value, 'big') for value in (n, e, d, p, q)) == (
                key.n, key.e, key.d, *sorted((key.p, key.q)))
            blocks.append(body)
            return decrypt.decrypt(body, b'') or None

    original_import = builtins.__import__
    def portable_import(name, *args, **kwargs):
        assert name.split('.')[0] not in {'Crypto', 'brotli'}
        return original_import(name, *args, **kwargs)

    monkeypatch.setitem(sys.modules, 'java', SimpleNamespace(jclass=lambda _: AndroidCrypto))
    monkeypatch.setattr(builtins, '__import__', portable_import)
    reader.native = SimpleNamespace(publisherCrypto=AndroidCrypto)
    current = reader.plan(request, Context(tmp_path, request))
    assert current.stage == 'catalogue-runtime' and not current.runtime_available
    assert current.download_bytes is None and current.revision != initial.revision
    assert current.handle['hotfix']['base_revision'] == base.decode()
    assert current.handle['hotfix']['audio_revision'] == '2001'
    assert b''.join(blocks) == encrypted
    assert calls[-3:] == [('plan', url) for url in (dispatch, gateway, base_url)]
    objects[base_url] = b'0' * len(base)
    cached = tmp_path / 'cache' / 'zzz-content' / 'global' / 'files' / f'{xxhash64(base):016x}-{len(base)}'
    cached.write_bytes(b'1' * len(base))
    with pytest.raises(ValueError):
        reader.plan(request, Context(tmp_path, request))
    assert (tmp_path / 'download' / 'bootstrap-source.json').read_bytes() == retained
    assert stage.restore_handle['revision'] == initial.revision


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


def test_cache_ancestor_refuses_before_any_descendant_metadata_access(tmp_path, monkeypatch):
    ancestor = tmp_path / 'linked-cache'
    child = ancestor / 'private-source' / 'chunk'
    actual_link, actual_exists = Path.is_symlink, Path.exists
    def is_link(path):
        if path == ancestor:return True
        if ancestor in path.parents:raise AssertionError('Descendant link metadata was inspected first')
        return actual_link(path)
    def exists(path):
        if ancestor in path.parents:raise AssertionError('Descendant existence was inspected first')
        return actual_exists(path)
    monkeypatch.setattr(Path, 'is_symlink', is_link)
    monkeypatch.setattr(Path, 'exists', exists)
    with pytest.raises(GameDataError, match='ordinary private files'):
        game._safe(child)


def test_manifest_growth_has_an_explicit_consented_stage_before_detailed_plan(tmp_path):
    objects, _, _, _ = publisher('global')
    api_bytes = sum(len(body) for url, body in objects.items() if '/hyp/' in url or '/getBuild?' in url)
    manifest_url = next(url for url in objects if '/manifest_' in url)
    declared = len(objects[manifest_url])
    calls = []; reader = provider(objects, calls)
    request = GameDataRequest('global', 'en')
    initial = Context(tmp_path, request, budget=api_bytes + declared - 1)
    plan = reader.plan(request, initial)
    assert plan.stage == 'official-manifest' and plan.runtime_available
    assert plan.download_bytes == declared and all(url != manifest_url for _, url in calls)
    result = reader.download(plan, Context(tmp_path, request, 'download', declared))
    assert isinstance(result, PreparationStage) and result.restore_handle['phase'] == 'official-manifest'
    assert [url for phase, url in calls if phase == 'download'] == [manifest_url]
    following = Context(tmp_path, request)
    following.stage_handle = result.restore_handle
    assert reader.plan(request, following).stage == 'official-bootstrap'


def test_greater_than_eight_mib_manifest_size_is_quoted_without_body_io(tmp_path):
    objects, _, _, _ = publisher('cn')
    url = next(url for url in objects if '/getBuild?' in url)
    response = json.loads(objects[url])
    for row in response['data']['manifests']:
        row['manifest']['compressed_size'] = MAX_METADATA_BYTES + 4096
    objects[url] = json.dumps(response).encode()
    calls = []; request = GameDataRequest('cn', 'ja')
    plan = provider(objects, calls).plan(request, Context(tmp_path, request))
    assert plan.stage == 'official-manifest' and plan.download_bytes == MAX_METADATA_BYTES + 4096
    assert len(calls) == 2 and all('/hyp/' in address or '/getBuild?' in address for _, address in calls)


def test_real_service_old_ready_survives_actual_zzz_manifest_and_bootstrap_stages(tmp_path, monkeypatch):
    from backend import game_data as service_module
    from backend.tests.test_game_data import Provider as Baseline, REQUEST, finish
    baseline = Baseline()
    objects, _, _, _ = publisher('global', '3.4.0')
    calls = []
    class Transition(game.ZzzGameDataProvider):
        def restore(self, handle, ctx):
            if handle.get('revision') == baseline.revision:return baseline.restore(handle, ctx)
            return super().restore(handle, ctx)
    actual = provider(objects, calls, provider_type=Transition)
    service = GameDataService(tmp_path / 'host', {'zzz': baseline})
    try:
        first = service.plan('zzz', REQUEST)['game']
        service.download('zzz', {'plan_id': first['plan_id'], 'revision': first['revision']})
        assert finish(service)['state'] == 'ready'
        original = tmp_path / 'host/zzz/current.json'
        original_bytes = original.read_bytes()
        service.providers['zzz'] = actual
        api_bytes = sum(len(body) for url, body in objects.items() if '/hyp/' in url or '/getBuild?' in url)
        manifest_size = len(objects[next(url for url in objects if '/manifest_' in url)])
        monkeypatch.setattr(service_module, 'MAX_METADATA_BYTES', api_bytes + manifest_size - 1)
        planned = service.plan('zzz', REQUEST)['game']
        service.download('zzz', {'plan_id': planned['plan_id'], 'revision': planned['revision']})
        assert finish(service)['job']['status'] == 'needs_plan'
        assert original.read_bytes() == original_bytes and service.restore('zzz') is not None
        monkeypatch.setattr(service_module, 'MAX_METADATA_BYTES', MAX_METADATA_BYTES)
        following = service.plan('zzz', REQUEST)['game']
        service.download('zzz', {'plan_id': following['plan_id'], 'revision': following['revision']})
        assert finish(service)['job']['status'] == 'needs_plan'
        assert original.read_bytes() == original_bytes and service.restore('zzz') is not None
        service.close()
        offline = GameDataService(tmp_path / 'host', {'zzz': actual})
        try:
            assert offline.restore('zzz') is not None
        finally:offline.close()
    finally:service.close()
