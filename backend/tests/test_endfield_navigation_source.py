"""Large original navigation bytes require separately quoted download stages."""
import hashlib
import io
import json
import struct
from email.message import Message
from types import SimpleNamespace as NS
import zlib

import brotli
import pytest

pytest.importorskip('backend.game_data_protocol', reason='Reviewed pure service dependency')
from backend.game_data import GameDataService, _Context
from backend.game_data_protocol import GameDataRequest, GameDataError
from backend.publisher_transport import PublisherTransport
from backend import endfield_navigation_source as source
from backend.tests.test_endfield_client_parameters import identity
from backend.tests.test_endfield_vfs import PARAMETERS, encrypt, CHUNK


def index(files, block):
    def text(value):
        raw = value.encode()
        return struct.pack('<H', len(raw)) + raw
    payload = b''.join(raw for _, raw in files)
    body = struct.pack('<ii', 5, 17) + text('owned fixture') + struct.pack('<qiqBi', 99, 1, len(payload), block, 1)
    body += bytes(range(16)) + bytes(16) + struct.pack('<qB', len(payload), block) + bytes(8) + struct.pack('<i', len(files))
    offset = 0
    for name, raw in files:
        body += text(name) + struct.pack('<q', -123) + bytes(16) + hashlib.md5(raw).digest()
        body += struct.pack('<qqBB', offset, len(raw), block, 0) + bytes(8)
        offset += len(raw)
    body += bytes(10)
    body += struct.pack('<I', zlib.crc32(body))
    nonce = bytes(range(12))
    return nonce + encrypt(body, nonce), payload


def registry(owners):
    def field(raw): return struct.pack('<i', len(raw)) + raw
    strings, assets, bundles = bytearray(), bytearray(4), bytearray(struct.pack('<i', len(owners)))
    for number, (path, bundle) in enumerate(sorted(owners.items()), 1):
        start = len(strings)
        strings.extend(field(brotli.compress(path.encode('utf-16le'))))
        bundle_at = len(strings)
        strings.extend(field(bundle.encode('utf-16le')))
        assets.extend(struct.pack('<qii8x', number, start, number))
        bundles.extend(struct.pack('<ii40x', number, bundle_at))
    raw = bytes.fromhex('11ff11ff00000000f4f3f2f1') + bytes(8)
    raw += field(assets) + field(b'') + field(bundles) + field(strings)
    return brotli.compress(raw)


class Fixture:
    def __init__(self, root, mode='text', initial_ui=False):
        self.root, self.client = root, identity()
        self.common = NS(key=PARAMETERS.key, directories={4: '00000004', 2: '00000002', 11: '00000011'}, protocol=3)
        self.request = GameDataRequest('global', 'en', ('ja',), mode)
        self.service = GameDataService(root, {})
        from backend.endfield_client_source import identity_stamp
        base = self.client['url'].split('/update/')[0] + '/resource/Windows/'
        self.generation = {'client_sha256': identity_stamp(self.client), 'region': 'global',
            'layers': {role: {'url': base + role + '/300-1_Authored/files', 'version': '300-1',
                             'sha256': 'a' * 64, 'index_bytes': 80} for role in ('initial', 'main')}}
        self.owners = {path: ('initial' if initial_ui and number == 0 else 'main') + f'/{number+1:x}.ab'
                       for number, path in enumerate(sorted(source.UI))}
        self.owners[source.DIALOG_GRAPHS + 'owned.json'] = 'main/abc123.ab'
        self.manifest = registry(self.owners)
        self.index4, _ = index([(source.MANIFEST, self.manifest)], 4)
        self.indices = {}
        for block, role in ((2, 'initial'), (11, 'main')):
            files = [('Data/Bundles/Windows/' + name, b'owned fixture bundle')
                     for name in sorted(set(self.owners.values())) if name.startswith(role + '/')]
            if files:
                self.indices[block], _ = index(files, block)
        self.calls, self.reads = [], []
        self.corrupt_manifest = self.corrupt_index = False
        self.declared_size, self.changed_etag = None, False
        self.no_etag = self.weak_etag = self.changed_header = False

    def context(self, phase='plan', budget=None):
        return _Context(self.service, self.root, 'local', 'endfield', self.request,
                        self.root / phase, phase, budget=budget)

    def transport(self, ctx):
        fixture = self
        class Response:
            def __init__(self, url, raw, status, range_=None, etag=None):
                self.url, self.status, self.body = url, status, io.BytesIO(raw)
                self.headers = Message()
                self.headers['Content-Length'] = str(len(raw))
                if range_: self.headers['Content-Range'] = range_
                if etag: self.headers['ETag'] = etag
            def geturl(self): return self.url
            def read(self, size):
                raw = self.body.read(size)
                fixture.reads.append((self.url, len(raw)))
                return raw
            def __enter__(self): return self
            def __exit__(self, *_): pass
        def server(request, **_):
            url = request.full_url
            range_ = request.get_header('Range')
            fixture.calls.append((url, range_))
            if url.endswith('/00000004.blc'):
                assert range_ is None
                return Response(url, fixture.index4, 200)
            if url.endswith('.chk'):
                assert '/00000004/' in url and url.endswith('/' + CHUNK)
                raw = fixture.manifest
                if fixture.corrupt_manifest: raw = raw[:-1] + bytes([raw[-1] ^ 1])
            else:
                block = next(block for block in fixture.indices if url.endswith('/' + fixture.common.directories[block] + '.blc'))
                raw = fixture.indices[block]
                if fixture.corrupt_index and range_ != 'bytes=0-15': raw = raw[:-1] + bytes([raw[-1] ^ 1])
                if fixture.changed_header and range_ != 'bytes=0-15': raw = bytes([raw[0] ^ 1]) + raw[1:]
            low, high = map(int, range_.removeprefix('bytes=').split('-'))
            total = fixture.declared_size if fixture.declared_size and url.endswith('.blc') else len(raw)
            tag = '"changed-original"' if fixture.changed_etag and high != 15 else '"actual-original"'
            if fixture.no_etag: tag = None
            if fixture.weak_etag: tag = 'W/"weak-original"'
            return Response(url, raw[low:high + 1], 206, f'bytes {low}-{high}/{total}', tag)
        return PublisherTransport(ctx, hosts={'beyond.hg-cdn.com'}, opener=server)

    def plan(self):
        ctx = self.context()
        return source.plan(ctx, self.client, self.common, self.generation, self.transport(ctx))

    def download(self, plan, index4, *, changed=False, budget=None):
        ctx = self.context('download', plan['download_bytes'] if budget is None else budget)
        return source.download(ctx, self.client, self.common, plan, index4, self.transport(ctx),
            recheck=lambda: (self.client, {} if changed else self.generation))


@pytest.fixture
def original(tmp_path):
    fixture = Fixture(tmp_path)
    try: yield fixture
    finally: fixture.service.close()


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
@pytest.mark.parametrize('initial_ui', [False, True])
def test_complete_manifest_then_exact_required_index_owners_use_separate_quotes(tmp_path, mode, initial_ui):
    original = Fixture(tmp_path, mode, initial_ui)
    try:
        first, index4 = original.plan()
        assert first['stage'] == 'original-text-manifest' and first['payload_bytes'] == len(original.manifest)
        assert first['owned_ui_paths'] is None and first['selected_bundle_count'] is None
        assert not any(url.endswith('.chk') for url, _ in original.calls)
        result = original.download(first, index4)
        assert result['stage'] == 'original-text-navigation-pending'
        plan, index4 = original.plan()
        assert plan['stage'] == 'original-text-navigation-indices'
        assert plan['owned_ui_paths'] == 11 and plan['owned_dialog_graph_paths'] == 1
        assert {entry['block'] for entry in plan['indices']} == ({2, 11} if initial_ui else {11})
        assert plan['payload_bytes'] == sum(map(len, original.indices.values()))
        assert all(range_ == 'bytes=0-15' for url, range_ in original.calls if url.endswith('.blc') and '/00000004.blc' not in url)
        result = original.download(plan, index4)
        assert result['stage'] == 'original-text-navigation-verified'
        assert result['selected_bundle_count'] == 12
        path = source._root(original.context()) / 'sources' / (result['receipt_sha256'] + '.json')
        body = json.loads(path.read_bytes())
        assert body['aes_header_parameters_verified'] is False and body['bundle_payloads_downloaded'] is False
        warm, index4 = original.plan()
        assert warm['payload_bytes'] == 0 and all(row['cached'] for row in warm['indices'])
        assert warm['required_disk_bytes'] < plan['required_disk_bytes']
        reads = sum(n for _, n in original.reads)
        index_files = {p: p.stat().st_mtime_ns for p in source._root(original.context()).glob('indices/*.blc')}
        assert original.download(warm, index4) == result
        assert sum(n for _, n in original.reads) == reads  # No hidden warm re-download.
        assert {p: p.stat().st_mtime_ns for p in index_files} == index_files  # No large warm disk rewrite.
        assert all('/00000004/' in url or not url.endswith('.chk') for url, _ in original.calls)
    finally:
        original.service.close()


def test_large_index_preflight_stays_inside_real_plan_metadata_budget(original):
    plan, index4 = original.plan()
    original.download(plan, index4)
    original.declared_size = 33_483_621
    original.reads.clear()
    plan, _ = original.plan()
    assert plan['payload_bytes'] == 33_483_621
    assert sum(n for _, n in original.reads) == len(original.index4) + source.HEADER
    assert plan['download_is_upper_bound'] and plan['download_bytes'] > plan['payload_bytes']
    assert plan['required_disk_bytes'] > plan['payload_bytes']


@pytest.mark.parametrize('change', ['crc', 'etag', 'header', 'generation', 'budget', 'cancel', 'plan'])
def test_failed_navigation_refresh_keeps_previous_complete_receipt(original, change):
    first, index4 = original.plan()
    original.download(first, index4)
    plan, index4 = original.plan()
    old = original.download(plan, index4)
    path = source._root(original.context()) / 'sources' / (old['receipt_sha256'] + '.json')
    before = path.read_bytes()
    original.generation['layers']['main']['sha256'] = 'f' * 64
    plan, index4 = original.plan()
    if change == 'crc': original.corrupt_index = True
    elif change == 'etag': original.changed_etag = True
    elif change == 'header': original.changed_header = True
    elif change == 'plan': plan['manifest_index_sha256'] = '0' * 64
    with pytest.raises(GameDataError):
        if change == 'cancel':
            ctx = original.context('download', plan['download_bytes'])
            ctx.cancel.set()
            source.download(ctx, original.client, original.common, plan, index4, original.transport(ctx), recheck=lambda: None)
        else:
            original.download(plan, index4, changed=change == 'generation', budget=0 if change == 'budget' else None)
    assert path.read_bytes() == before


@pytest.mark.parametrize('validator', ['absent', 'weak'])
def test_no_strong_validator_quotes_full_current_index_and_retains_exact_offline_source(original, validator):
    original.no_etag = validator == 'absent'
    original.weak_etag = validator == 'weak'
    first, index4 = original.plan()
    original.download(first, index4)
    plan, index4 = original.plan()
    old = original.download(plan, index4)
    calls = len(original.calls)
    old_body, old_owners, old_files = source.restore(original.context(), original.client, original.common, original.generation, old)
    assert len(original.calls) == calls
    assert old_body['indices'][0]['freshness']['kind'] == 'complete-current-response'
    assert old_body['indices'][0]['freshness']['transfer']['bytes'] == len(original.indices[11])
    quote, index4 = original.plan()
    assert not quote['indices'][0]['cached'] and quote['payload_bytes'] == len(original.indices[11])
    # Manifest reuse really is content-addressed: the freshly fetched complete
    # block4 index publishes its current MD5, and the whole cache matches it.
    assert quote['manifest_cached'] and quote['stage'] == 'original-text-navigation-indices'
    before = original.indices[11]
    files = [('Data/Bundles/Windows/' + name, b'X' * len(b'owned fixture bundle')) for name in sorted(set(original.owners.values()))]
    original.indices[11], _ = index(files, 11)
    assert len(original.indices[11]) == len(before) and original.indices[11][:16] == before[:16]
    # Same generation, URL and short header; a changed valid body is still read.
    current = original.download(quote, index4)
    assert current['receipt_sha256'] != old['receipt_sha256']
    _, _, current_files = source.restore(original.context(), original.client, original.common, original.generation, current)
    assert [row.content_hashes for row in current_files.values()] != [row.content_hashes for row in old_files.values()]
    calls = len(original.calls)
    assert source.restore(original.context(), original.client, original.common, original.generation, old)[1] == old_owners
    assert len(original.calls) == calls  # Offline exact-source restore is not an online freshness claim.


def test_changed_current_publisher_manifest_digest_requires_new_payload_quote(original):
    original.no_etag = True
    first, index4 = original.plan()
    original.download(first, index4)
    assert original.plan()[0]['manifest_cached']
    original.owners[source.DIALOG_GRAPHS + 'future.json'] = 'main/ddd.ab'
    original.manifest = registry(original.owners)
    original.index4, _ = index([(source.MANIFEST, original.manifest)], 4)
    quote, _ = original.plan()
    assert quote['stage'] == 'original-text-manifest' and not quote['manifest_cached']
    assert quote['manifest']['content_hashes'][1] == hashlib.md5(original.manifest).hexdigest()
    assert quote['payload_bytes'] == len(original.manifest)


@pytest.mark.parametrize('change', ['MD5', 'missing-ui', 'too-large-index'])
def test_bad_manifest_or_index_owner_never_publishes_complete_navigation(original, change):
    if change == 'missing-ui':
        original.owners.pop(next(iter(source.UI)))
        original.manifest = registry(original.owners)
        original.index4, _ = index([(source.MANIFEST, original.manifest)], 4)
    first, index4 = original.plan()
    if change == 'MD5': original.corrupt_manifest = True
    with pytest.raises(GameDataError):
        original.download(first, index4)
        original.declared_size = source.MAX_BUNDLE_INDEX + 1
        original.plan()
    assert not list(source._root(original.context()).glob('sources/*.json'))


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_ordinary_provider_continues_actual_text_receipt_through_navigation_stages(tmp_path, monkeypatch, mode):
    from backend import endfield_game_data as game, endfield_resource_source
    from backend.tests.test_endfield_text_source import Fixture as TextFixture
    from backend.game_data_protocol import PreparationStage, SnapshotSource
    original, text = Fixture(tmp_path, mode), TextFixture(tmp_path, mode)
    original.common.directories[18] = text.common.directories[18]
    text.generation = original.generation
    try:
        text_plan, text_index = text.plan()
        reference = text.download(text_plan, text_index)
        bootstrap = {'schema': 1, 'stage': 'client-bootstrap-downloaded', 'client': original.client,
                     'request': original.request.json(), 'receipt_sha256': 'b' * 64}
        source_stage = bootstrap if mode == 'text' else {
            'schema': 1, 'stage': 'original-audio-master-verified', 'client': original.client,
            'request': original.request.json(), 'native': {'bootstrap': bootstrap},
            'generation': original.generation, 'witness': {'explicit_source': 'fixture'}}
        tables_stage = {'schema': 1, 'stage': 'original-text-tables-downloaded', 'client': original.client,
                        'request': original.request.json(), 'source': source_stage, 'text': reference}
        provider = game.create_provider(platform='windows')
        # Only native/bootstrap ownership is simulated; real text receipts,
        # original MD5/typed readers, transport, budgets and all stages remain.
        monkeypatch.setattr(provider, '_runtime', lambda: None)
        monkeypatch.setattr(provider, '_latest', lambda *_: (original.client, None))
        monkeypatch.setattr(provider, '_transport', lambda request, ctx: original.transport(ctx))
        monkeypatch.setattr(provider, '_text_bootstrap', lambda *_: NS())
        monkeypatch.setattr(provider, '_common', lambda *_: original.common)
        monkeypatch.setattr(endfield_resource_source, 'discover', lambda *_: original.generation)
        continuation = tables_stage
        for expected in ('original-text-manifest', 'original-text-navigation-indices'):
            ctx = original.context()
            ctx.stage_handle = continuation
            quoted = provider.plan(original.request, ctx)
            assert quoted.stage == expected
            downloading = original.context('download', quoted.download_bytes)
            assert downloading.stage_handle is None
            result = provider.download(quoted, downloading)
            assert isinstance(result, PreparationStage) and not isinstance(result, SnapshotSource)
            assert 0 < downloading.consumed <= quoted.download_bytes
            assert result.restore_handle['tables'] == tables_stage
            continuation = result.restore_handle
        assert continuation['stage'] == 'original-text-navigation-verified'
        ctx = original.context()
        ctx.stage_handle = continuation
        with pytest.raises(GameDataError, match='AES/header'):
            provider.plan(original.request, ctx)
        assert not any('/Audio' in url or url.endswith('.dll') for url, _ in original.calls)
        ctx.stage_handle = tables_stage
        calls = len(original.calls)
        def missing_owner(_): raise ValueError('Authored missing original owner')
        monkeypatch.setattr(provider, '_common', missing_owner)
        with pytest.raises(GameDataError) as error:
            provider.plan(original.request, ctx)
        assert error.value.code == 'unsupported_original_metadata' and len(original.calls) == calls
    finally:
        original.service.close()
        text.service.close()
