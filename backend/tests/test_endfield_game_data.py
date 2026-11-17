"""Actual shared contracts with owned small publisher-client range fixtures."""
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

# The shared service/transport is an independently reviewed integration wave.
# A game-only checkout must not replace that dependency with a second schema.
protocol = pytest.importorskip('backend.game_data_protocol', reason='Reviewed shared provider contract is a separate dependency')
transport = pytest.importorskip('backend.publisher_transport', reason='Reviewed context transport is a separate dependency')

from backend import endfield_game_data as source, endfield_parameters
from backend.tests.endfield_parameter_fixture import toy_metadata, toy_pe
from backend.tests.test_endfield_client_parameters import identity


class Fixture:
    def __init__(self, tmp_path, mode='text'):
        self.client = identity()
        self.latest = {'version': self.client['version'], 'pkg': {'file_path': self.client['url'],
            'game_files_md5': self.client['game_files_md5'], 'packs': [
                {'url': row['url'], 'md5': row['md5'], 'package_size': str(row['bytes'])}
                for row in self.client['artifacts']]}}
        self.data = {source.METADATA: toy_metadata(), 'GameAssembly.dll': toy_pe()}
        self.calls, self.fail_download, self.owner_delta = [], False, 0
        self.request = protocol.GameDataRequest('global', 'en', ('ja',), mode)
        self.ctx = SimpleNamespace(game='endfield', request=self.request, cache_directory=tmp_path / 'cache',
                                   check=lambda: None)

    def factory(self, ctx, *, hosts):
        fixture = self
        assert ctx is self.ctx
        assert hosts == {'launcher.gryphline.com', 'beyond.hg-cdn.com'}
        class Transport:
            def fetch_bytes(self, url, *, limit, kind, expected_size=None, original_range=None):
                fixture.calls.append(('fetch', kind, url, original_range))
                assert kind == 'metadata'
                if '/get_latest?' in url:
                    data = json.dumps(fixture.latest).encode()
                    owner = None
                else:
                    artifact = next(name for name in fixture.data if url == fixture.client['url'] + '/' + name)
                    raw = fixture.data[artifact]
                    assert original_range == (0, expected_size, None)
                    data, owner = raw[:expected_size], (0, expected_size, len(raw) + fixture.owner_delta)
                assert len(data) <= limit
                return data, transport.TransferReceipt(hashlib.sha256(url.encode()).hexdigest(), len(data),
                    hashlib.sha256(data).hexdigest(), {}, owner)

            def download_to(self, url, destination, *, limit, expected_size, kind, original_range):
                fixture.calls.append(('download', kind, url, original_range))
                assert kind == 'asset'
                if fixture.fail_download:
                    raise protocol.GameDataError('metadata_download_interrupted', 'Authored interrupted range')
                artifact = next(name for name in fixture.data if url == fixture.client['url'] + '/' + name)
                offset, size, total = original_range
                assert total == len(fixture.data[artifact]) and size == expected_size == limit
                data = fixture.data[artifact][offset:offset + size]
                assert len(data) == size
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                return transport.TransferReceipt(hashlib.sha256(url.encode()).hexdigest(), len(data),
                    hashlib.sha256(data).hexdigest(), {}, original_range)
        return Transport()


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_original_size_plan_and_download_are_only_a_non_audio_bootstrap(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path, mode)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    plan = provider.plan(fixture.request, fixture.ctx)
    assert plan.stage == 'client-bootstrap' and plan.runtime_available is True
    tables = sum(row['bytes'] for row in plan.handle['ranges'])
    assert plan.source_proof is None and plan.download_bytes == tables + source.RECHECK_METADATA_UPPER
    assert plan.download_is_upper_bound is True
    assert plan.handle['transfer_bytes'] == {'client_tables': tables,
        'verification_metadata_upper_bound': source.RECHECK_METADATA_UPPER}
    assert plan.required_disk_bytes == 2 * tables + 4352
    assert not any(row[0] == 'download' for row in fixture.calls)
    result = provider.download(plan, fixture.ctx)
    assert isinstance(result, protocol.PreparationStage)
    assert not isinstance(result, protocol.SnapshotSource)
    assert result.restore_handle['stage'] == 'client-bootstrap-downloaded'
    assert result.restore_handle['request']['content_mode'] == mode
    assert all(call[1] != 'audio' for call in fixture.calls)
    assert 'not complete native artifact hashes' in next(fixture.ctx.cache_directory.rglob('receipt.json')).read_text()
    with pytest.raises(protocol.GameDataError, match='not a restorable game library'):
        provider.restore(result.restore_handle, fixture.ctx)


@pytest.mark.parametrize('change', ['client', 'mode', 'range', 'estimate', 'revision', 'stage', 'header-bytes', 'receipt-shape', 'bound-kind'])
def test_changed_source_selection_or_estimate_stops_before_large_transfer(tmp_path, monkeypatch, change):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    plan = provider.plan(fixture.request, fixture.ctx)
    if change == 'client':
        fixture.latest['pkg']['game_files_md5'] = 'f' * 32
    elif change == 'mode':
        fixture.ctx.request = protocol.GameDataRequest('global', 'en', ('ja',), 'text-audio')
    elif change == 'range':
        plan.handle['ranges'][0]['offset'] += 1
    elif change == 'header-bytes':
        changed = bytearray(fixture.data['GameAssembly.dll'])
        changed[0x50] ^= 1  # Valid PE with unchanged table ranges but different original header bytes.
        fixture.data['GameAssembly.dll'] = bytes(changed)
    elif change == 'receipt-shape':
        plan.handle['receipts'] = 'malformed authored input'
    else:
        from dataclasses import replace
        plan = replace(plan, **{'estimate': {'download_bytes': plan.download_bytes + 1},
                                'revision': {'revision': 'changed'}, 'stage': {'stage': 'content'},
                                'bound-kind': {'download_is_upper_bound': False}}[change])
    with pytest.raises(protocol.GameDataError) as caught:
        provider.download(plan, fixture.ctx)
    assert caught.value.code == 'publisher_size_changed'
    assert not any(call[0] == 'download' for call in fixture.calls)


@pytest.mark.parametrize('platform', ['android', 'linux', 'macos'])
def test_unreviewed_host_runtime_never_fetches_native_source(tmp_path, platform):
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform=platform, transport_factory=lambda *_a, **_kw: pytest.fail('No unsupported-host transfer'))
    with pytest.raises(protocol.GameDataError) as caught:
        provider.plan(fixture.request, fixture.ctx)
    assert caught.value.code == 'missing_toolkit_runtime'


def test_incomplete_owner_bounds_and_interruption_preserve_existing_data(tmp_path, monkeypatch):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    fixture.owner_delta = -4000
    with pytest.raises(protocol.GameDataError):
        provider.plan(fixture.request, fixture.ctx)
    fixture.owner_delta = 0
    plan = provider.plan(fixture.request, fixture.ctx)
    retained = tmp_path / 'previous-language.json'
    retained.write_bytes(b'authored previous active data')
    fixture.fail_download = True
    with pytest.raises(protocol.GameDataError):
        provider.download(plan, fixture.ctx)
    assert retained.read_bytes() == b'authored previous active data'
    assert not list(fixture.ctx.cache_directory.rglob('receipt.json'))


def test_mode_and_language_selections_keep_distinct_source_stage_identities(tmp_path, monkeypatch):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    plans = []
    for request in (fixture.request, protocol.GameDataRequest('global', 'en', ('ja',), 'text-audio'),
                    protocol.GameDataRequest('global', 'ja', ('en',), 'text')):
        fixture.ctx.request = request
        plan = provider.plan(request, fixture.ctx)
        plans.append(plan)
        provider.download(plan, fixture.ctx)
    assert plans[0].revision == plans[1].revision == plans[2].revision
    assert plans[0].handle != plans[1].handle != plans[2].handle
    receipts = list(fixture.ctx.cache_directory.rglob('receipt.json'))
    assert len(receipts) == 3
    assert {json.loads(path.read_bytes())['request']['content_mode'] for path in receipts} == {'text', 'text-audio'}
    assert all(call[1] != 'audio' for call in fixture.calls)


def test_original_artifact_hash_changes_generation_even_with_same_marketing_version(tmp_path, monkeypatch):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    first = provider.plan(fixture.request, fixture.ctx)
    fixture.latest['pkg']['game_files_md5'] = 'e' * 32
    second = provider.plan(fixture.request, fixture.ctx)
    assert first.revision != second.revision
    assert first.handle['client']['version'] == second.handle['client']['version']
    assert first.handle['request'] == second.handle['request']


def test_launcher_token_refresh_does_not_change_original_generation_or_size_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path)
    provider = source.create_provider(platform='windows', transport_factory=fixture.factory)
    first = provider.plan(fixture.request, fixture.ctx)
    fixture.latest['action'] = 12
    fixture.latest['pkg']['packs'][0]['url'] += '?auth_key=refreshed-authored-token'
    second = provider.plan(fixture.request, fixture.ctx)
    assert first.revision == second.revision
    assert first.handle['receipts']['declaration']['sha256'] != second.handle['receipts']['declaration']['sha256']
    assert first.handle['client'] == second.handle['client']
    result = provider.download(first, fixture.ctx)
    assert isinstance(result, protocol.PreparationStage)
    assert all(call[1] != 'audio' for call in fixture.calls)


def test_cold_factory_and_parameter_imports_do_not_load_desktop_tools_or_native_libraries():
    import subprocess
    import sys
    program = r'''
import importlib.abc, sys
class NoDesktop(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = ('backend.game_tools', 'backend.runtime_paths', 'backend.runtime_bundle',
                     'backend.steam_games', 'backend.prepared_library', 'capstone', 'xxhash', 'numpy', 'Crypto')
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise AssertionError('Forbidden cold import: ' + fullname)
sys.meta_path.insert(0, NoDesktop())
from backend import endfield_game_data, endfield_parameters, endfield_lua_parameters
provider = endfield_game_data.create_provider(platform='android')
assert provider.platform == 'android'
assert 'backend.game_data' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', program], cwd=Path(__file__).parents[2],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_real_shared_context_and_transport_pay_for_all_revalidation_bytes(tmp_path, monkeypatch, mode):
    import io
    from email.message import Message
    from backend.game_data import GameDataService, _Context
    monkeypatch.setattr(endfield_parameters, 'source_runtime', lambda: None)
    fixture = Fixture(tmp_path, mode)
    calls, launcher_count = [], [0]

    class Response:
        def __init__(self, url, data, status, range_=None):
            self.url, self.status, self.body = url, status, io.BytesIO(data)
            self.headers = Message()
            self.headers['Content-Length'] = str(len(data))
            if range_:
                self.headers['Content-Range'] = range_
        def geturl(self): return self.url
        def read(self, size): return self.body.read(size)
        def __enter__(self): return self
        def __exit__(self, *_): pass

    def server(request, **_):
        if '/get_latest?' in request.full_url:
            launcher_count[0] += 1
            # Variable non-generation metadata may grow after the quote. The
            # two explicit bounded launcher rechecks must still fit the budget.
            fixture.latest['unrelated'] = 'x' * (10000 * launcher_count[0])
            raw = json.dumps(fixture.latest).encode()
            calls.append(('metadata', len(raw)))
            return Response(request.full_url, raw, 200)
        artifact = next(name for name in fixture.data if request.full_url == fixture.client['url'] + '/' + name)
        bounds = request.get_header('Range').removeprefix('bytes=').split('-')
        low, high = map(int, bounds)
        raw = fixture.data[artifact]
        calls.append(('range', high - low + 1))
        return Response(request.full_url, raw[low:high + 1], 206, f'bytes {low}-{high}/{len(raw)}')

    provider = source.create_provider(platform='windows', transport_factory=lambda ctx, **kw:
        transport.PublisherTransport(ctx, opener=server, **kw))
    service = GameDataService(tmp_path, {'endfield': provider})
    try:
        planning = _Context(service, tmp_path, 'local', 'endfield', fixture.request, tmp_path / 'plan', 'plan')
        plan = provider.plan(fixture.request, planning)
        calls.clear()
        downloading = _Context(service, tmp_path, 'local', 'endfield', fixture.request,
                               tmp_path / 'download', 'download', budget=plan.download_bytes)
        result = provider.download(plan, downloading)
        tables = plan.handle['transfer_bytes']['client_tables']
        assert tables < downloading.consumed == sum(size for _, size in calls) <= plan.download_bytes
        assert isinstance(result, protocol.PreparationStage) and not isinstance(result, protocol.SnapshotSource)
        assert launcher_count[0] == 3
        # The old tables-only approval genuinely cannot pay for the same strict
        # context/transport lane; no mock counters or global budget relaxation.
        too_small = _Context(service, tmp_path, 'local', 'endfield', fixture.request,
                            tmp_path / 'short', 'download', budget=tables)
        with pytest.raises(protocol.GameDataError) as error:
            provider.download(plan, too_small)
        assert error.value.code == 'publisher_size_changed'
        assert too_small.consumed <= tables
    finally:
        service.close()
