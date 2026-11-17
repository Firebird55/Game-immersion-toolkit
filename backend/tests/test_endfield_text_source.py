"""Complete original text sources use real shared budgets, never audio lanes."""
import copy
import hashlib
import io
import json
import struct
from email.message import Message
from types import SimpleNamespace as NS
import zlib

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Reviewed pure service dependency')
from backend.game_data import GameDataService, _Context
from backend.game_data_protocol import GameDataRequest, GameDataError, PreparationStage
from backend.publisher_transport import PublisherTransport
from backend import endfield_text_source as source
from backend.tests.test_endfield_release import text_table
from backend.tests.test_endfield_vfs import PARAMETERS, encrypt, CHUNK
from backend.tests.test_endfield_client_parameters import identity


def catalog(files):
    def text(value):
        raw = value.encode()
        return struct.pack('<H', len(raw)) + raw
    payload = b''.join(raw for _, raw in files)
    body = struct.pack('<ii', 5, 17) + text('authored') + struct.pack('<qiqBi', 99, 1, len(payload), 18, 1)
    body += bytes(range(16)) + bytes(16) + struct.pack('<qB', len(payload), 18) + bytes(8) + struct.pack('<i', len(files))
    offset = 0
    for name, raw in files:
        body += text('Data/TableCfg/' + name + '.bytes') + struct.pack('<q', -123)
        body += bytes(16) + hashlib.md5(raw).digest() + struct.pack('<qqBB', offset, len(raw), 18, 0) + bytes(8)
        offset += len(raw)
    body += bytes(10)
    body += struct.pack('<I', zlib.crc32(body))
    nonce = bytes(range(12))
    return nonce + encrypt(body, nonce), payload


class Fixture:
    def __init__(self, root, mode='text'):
        self.root, self.client, self.calls = root, identity(), []
        self.common = NS(key=PARAMETERS.key, directories={18: '00000018'}, protocol=3)
        self.request = GameDataRequest('global', 'en', ('ja',), mode)
        self.files = [(name, text_table(name, 1, value)) for name, value in (
            ('TextTable', 'Owned generic reference'), ('I18nTextTable_EN', 'Complete English'),
            ('I18nTextTable_JP', '完全な日本語'), ('I18nTextTable_KR', '선택하지 않음'))]
        self.index, self.payload = catalog(self.files)
        self.base = self.client['url'].split('/update/')[0] + '/resource/Windows/main/300-1_Authored/files'
        from backend.endfield_client_source import identity_stamp
        self.generation = {'client_sha256': identity_stamp(self.client), 'region': 'global',
            'layers': {role: {'url': self.base, 'version': '300-1', 'sha256': 'a' * 64, 'index_bytes': 80}
                       for role in ('initial', 'main')}}
        self.service = GameDataService(root, {})
        self.fail_at, self.corrupt, self.recheck_changed = None, False, False

    def context(self, phase='plan', budget=None):
        return _Context(self.service, self.root, 'local', 'endfield', self.request,
                        self.root / phase, phase, budget=budget)

    def transport(self, ctx):
        fixture = self
        class Response:
            def __init__(self, url, data, status, owner=None):
                self.url, self.status, self.body = url, status, io.BytesIO(data)
                self.headers = Message()
                self.headers['Content-Length'] = str(len(data))
                if owner:
                    self.headers['Content-Range'] = owner
            def geturl(self): return self.url
            def read(self, size): return self.body.read(size)
            def __enter__(self): return self
            def __exit__(self, *_): pass
        def server(request, **_):
            url = request.full_url
            fixture.calls.append(url)
            if url.endswith('.blc'):
                return Response(url, fixture.index, 200)
            assert url.endswith('/' + CHUNK), 'No audio/native/other-table route'
            start, end = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            if fixture.fail_at is not None and start >= fixture.fail_at:
                raise OSError('Authored interruption')
            raw = fixture.payload[start:end + 1]
            if fixture.corrupt:
                raw = raw[:-1] + bytes([raw[-1] ^ 1])
            return Response(url, raw, 206, f'bytes {start}-{end}/{len(fixture.payload)}')
        return PublisherTransport(ctx, hosts={'beyond.hg-cdn.com'}, opener=server)

    def plan(self):
        ctx = self.context()
        return source.plan(ctx, self.client, self.common, self.generation, self.transport(ctx))

    def download(self, approved, index, *, changed=False, budget=None):
        ctx = self.context('download', approved['download_bytes'] if budget is None else budget)
        return source.download(ctx, self.client, self.common, approved, index, self.transport(ctx),
            recheck=lambda: (self.client, {} if changed else self.generation))


@pytest.fixture
def original(tmp_path):
    fixture = Fixture(tmp_path)
    try: yield fixture
    finally: fixture.service.close()


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_complete_selected_original_tables_quote_cold_warm_and_reopen_offline(original, mode):
    original.request = GameDataRequest('global', 'en', ('ja',), mode)
    plan, index = original.plan()
    assert plan['catalog_entries'] == 4 and plan['selected_entries'] == 3
    assert all('KR.bytes' not in row['file']['name'] for row in plan['files'])
    assert all(url.endswith('.blc') for url in original.calls)
    assert plan['payload_bytes'] == sum(len(raw) for name, raw in original.files if name != 'I18nTextTable_KR')
    assert plan['download_bytes'] > plan['payload_bytes'] and plan['required_disk_bytes'] > plan['payload_bytes']
    reference = original.download(plan, index)
    assert reference['stage'] == 'original-text-tables-downloaded'
    calls = list(original.calls)
    ctx = original.context()
    offline = source.Catalog(ctx, original.client, original.common, reference)
    assert offline.file('TableCfg/I18nTextTable_EN.json') == {'1': 'Complete English'}
    assert offline.file('TableCfg/I18nTextTable_JP.json') == {'1': '完全な日本語'}
    assert offline.file('TableCfg/Missing.json', optional=True) == {}
    assert original.calls == calls
    warm, _ = original.plan()
    assert warm['payload_bytes'] == 0 and warm['retained_verified_bytes'] == plan['payload_bytes']
    assert warm['download_bytes'] < plan['download_bytes'] and warm['required_disk_bytes'] < plan['required_disk_bytes']
    before = len([url for url in original.calls if url.endswith('.chk')])
    original.download(warm, index)
    assert len([url for url in original.calls if url.endswith('.chk')]) == before
    assert not any('Audio' in url or url.endswith('.dll') for url in original.calls)


@pytest.mark.parametrize('change', ['crc', 'root', 'missing-language', 'duplicate', 'path', 'missing-digest'])
def test_bad_original_index_or_authored_table_never_publishes_source(original, change):
    if change == 'crc':
        original.index = original.index[:-1] + bytes([original.index[-1] ^ 1])
    else:
        files = list(original.files)
        if change == 'root':
            files[0] = (files[0][0], text_table('WrongAuthoredRoot', 1, 'Wrong root'))
        elif change == 'missing-language': files = files[:-2] + files[-1:]
        elif change == 'duplicate': files.append(files[0])
        elif change == 'path': files[0] = ('../TextTable', files[0][1])
        original.index, original.payload = catalog(files)
        if change == 'missing-digest':
            plain = bytearray(encrypt(original.index[12:], original.index[:12]))
            digest = hashlib.md5(files[0][1]).digest()
            at = plain.index(digest)
            plain[at:at + 16] = bytes(16)  # Valid CRC, wrong complete source hash.
            plain[-4:] = struct.pack('<I', zlib.crc32(plain[:-4]))
            original.index = original.index[:12] + encrypt(bytes(plain), original.index[:12])
    with pytest.raises(GameDataError):
        plan, index = original.plan()
        original.download(plan, index)
    assert not list(original.root.rglob('receipt.json'))


@pytest.mark.parametrize('change', ['payload', 'generation', 'cancel', 'budget', 'plan', 'selection'])
def test_failed_update_preserves_previous_complete_source(original, change):
    plan, index = original.plan()
    old = original.download(plan, index)
    old_path = source._root(original.context()) / 'sources' / old['receipt_sha256'] / 'receipt.json'
    before = old_path.read_bytes()
    # A complete different original source body, with its own correct MD5.
    original.files[1] = ('I18nTextTable_EN', text_table('I18nTextTable_EN', 1, 'Changed original English'))
    original.index, original.payload = catalog(original.files)
    plan, index = original.plan()
    if change == 'payload': original.corrupt = True
    elif change == 'cancel': original.fail_at = 0
    elif change == 'plan': plan['payload_bytes'] += 1
    elif change == 'selection': original.request = GameDataRequest('global', 'en', ('ko',), 'text')
    with pytest.raises((GameDataError, OSError)):
        original.download(plan, index, changed=change == 'generation', budget=0 if change == 'budget' else None)
    assert old_path.read_bytes() == before
    old_ctx = original.context()
    old_ctx.request = GameDataRequest('global', 'en', ('ja',), 'text')
    assert source.Catalog(old_ctx, original.client, original.common, old).file('TableCfg/I18nTextTable_EN.json') == {'1': 'Complete English'}


def test_tampered_offline_reference_or_table_fails_without_network(original):
    plan, index = original.plan()
    reference = original.download(plan, index)
    ctx = original.context()
    bad = copy.deepcopy(reference)
    bad['client_sha256'] = '0' * 64
    with pytest.raises(GameDataError): source.Catalog(ctx, original.client, original.common, bad)
    catalog_ = source.Catalog(ctx, original.client, original.common, reference)
    row = catalog_.files['Data/TableCfg/I18nTextTable_EN.bytes']
    path = source._root(ctx) / 'assets' / row.content_hashes[1]
    path.write_bytes(bytes(row.size))
    with pytest.raises(GameDataError): catalog_.file('TableCfg/I18nTextTable_EN.json')
    # Warm estimates never subtract corrupted local data.
    warm, _ = original.plan()
    assert warm['payload_bytes'] == row.size


def test_planning_context_cannot_download_table_bodies(original):
    plan, index = original.plan()
    ctx = original.context()
    with pytest.raises(GameDataError, match='Approve'):
        source.download(ctx, original.client, original.common, plan, index, original.transport(ctx), recheck=lambda: None)
    assert all(url.endswith('.blc') for url in original.calls)


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_provider_uses_same_original_text_stage_with_separate_audio_witness(original, monkeypatch, mode):
    from backend import endfield_game_data as provider_module, endfield_resource_source
    original.request = GameDataRequest('global', 'en', ('ja',), mode)
    bootstrap = {'schema': 1, 'stage': 'client-bootstrap-downloaded', 'client': original.client,
                 'request': original.request.json(), 'receipt_sha256': 'b' * 64}
    continuation = (bootstrap if mode == 'text' else {'schema': 1, 'stage': 'original-audio-master-verified',
        'client': original.client, 'request': original.request.json(), 'generation': original.generation,
        'witness': {'explicit_original_source': 'fixture'}, 'native': {'bootstrap': bootstrap}})
    provider = provider_module.create_provider(platform='windows')
    monkeypatch.setattr(provider, '_runtime', lambda: None)  # Native ownership has independent original controls.
    monkeypatch.setattr(provider, '_latest', lambda *_: (original.client, None))
    monkeypatch.setattr(provider, '_transport', lambda request, ctx: original.transport(ctx))
    monkeypatch.setattr(provider, '_text_bootstrap', lambda *_: NS())
    monkeypatch.setattr(provider, '_common', lambda *_: original.common)
    monkeypatch.setattr(endfield_resource_source, 'discover', lambda *_: original.generation)
    ctx = original.context()
    ctx.stage_handle = continuation
    plan = provider.plan(original.request, ctx)
    assert plan.stage == 'original-text-tables' and plan.handle['source'] == continuation
    assert all(url.endswith('.blc') for url in original.calls)
    downloading = original.context('download', plan.download_bytes)
    result = provider.download(plan, downloading)  # No download-context stage_handle.
    assert isinstance(result, PreparationStage)
    assert result.restore_handle['text']['stage'] == 'original-text-tables-downloaded'
    assert result.restore_handle['source'] == continuation
    if mode == 'text-audio':
        assert result.restore_handle['source']['witness'] == continuation['witness']
    assert not any('Audio' in url or url.endswith('.dll') for url in original.calls)


def test_cold_text_reader_import_does_not_require_audio_parameter_or_signature_software():
    import subprocess
    import sys
    script = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('backend.endfield_akpk_') or fullname in {
            'backend.endfield_native_source', 'backend.endfield_native_import',
            'backend.endfield_publisher_signature', 'backend.genshin_native_x64',
            'backend.game_tools', 'backend.voice_assets', 'backend.prepared_library'}:
            raise AssertionError('Text source attempted unused audio/desktop software: ' + fullname)
sys.meta_path.insert(0, Guard())
from backend.endfield_text_source import Catalog, plan, download
from backend.endfield_resource_source import discover
from backend.endfield_navigation_source import plan as navigation_plan
from backend.endfield_presentation_bundles import plan as bundle_plan
assert callable(plan) and callable(download) and callable(discover)
assert callable(navigation_plan)
assert callable(bundle_plan)
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
