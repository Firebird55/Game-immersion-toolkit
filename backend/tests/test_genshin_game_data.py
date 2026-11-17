"""Original native stages never become incomplete or community-backed libraries."""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest
import zstandard

from backend import genshin_game_data as provider, sophon_assets as sophon
from backend.game_data_protocol import GameDataError, GameDataRequest, PreparationStage
from backend.publisher_transport import source_url
from backend.tests.test_sophon_assets import field


class Context:
    game = 'genshin'
    phase = 'plan'
    consumed = 0
    stage_handle = None
    stopped = False

    def __init__(self, root, request, budget=8 * 1024**2):
        self.request, self.budget = request, budget
        self.directory, self.cache_directory = root / 'generation', root / 'cache'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.transfer_lock = threading.RLock()

    def check(self):
        if self.stopped:
            raise GameDataError('preparation_cancelled', 'Preparation stopped.', 409)

    def consume_bytes(self, count, *, kind='asset'):
        self.check()
        assert kind != 'audio'
        assert self.phase != 'plan' or kind == 'metadata'
        if self.consumed + count > self.budget:
            raise GameDataError('transfer_budget_exceeded', 'The approved size was exceeded.')
        self.consumed += count

    def remaining_bytes(self, *, kind='asset'):
        self.check()
        return self.budget - self.consumed


def fixture(tmp_path, monkeypatch, *, region='global', mode='text', wrong_whole=False):
    request = GameDataRequest(region, 'ja', ('en',), mode)
    ctx = Context(tmp_path, request)
    base = 'https://' + sophon.CHANNELS['genshin-' + region][3] + '/authored'
    encode = zstandard.ZstdCompressor().compress
    md5 = lambda b: hashlib.md5(b).hexdigest()
    objects, original, body = {}, {}, b''
    for number, name in enumerate(provider._names(region)):
        chunks = [b'S' * 512, bytes([65 + number]) * 512]
        data = b''.join(chunks); original[name] = data
        row = field(1, name.encode()) + field(4, len(data)) + field(5, ('0' * 32 if wrong_whole and number == 0 else md5(data)).encode())
        for offset, chunk in enumerate(chunks):
            identity = '0' * 16 + '_' + md5(chunk)
            objects[base + '/' + identity] = archive = encode(chunk)
            row += field(2, field(1, identity.encode()) + field(2, md5(chunk).encode()) + field(3, offset * 512)
                         + field(4, len(archive)) + field(5, len(chunk)))
        body += field(1, row)
    manifest = 'manifest_' + '0' * 16 + '_' + md5(body)
    objects[base + '/' + manifest] = encoded = encode(body)
    build = {'channel': 'genshin-' + region, 'version': '1.0.0', 'build': 'AuthoredA',
             'manifests': {'game': (base, manifest, len(encoded), len(body), md5(body), base)}}
    calls = []
    class Transport:
        def __init__(self, context, *, hosts):
            self.ctx, self.hosts = context, hosts
        def fetch_bytes(self, url, *, limit, kind):
            source_url(url, self.hosts)
            raw = objects[url]
            assert len(raw) <= limit
            self.ctx.consume_bytes(len(raw), kind=kind)
            calls.append((url, kind))
            return raw, None
    def release(channel, *, fetch):
        assert channel == build['channel']
        # Existing Sophon tests own the launcher wire schema; this test verifies
        # the provider's supplied context is used even for release metadata.
        objects[base + '/release'] = b'official metadata'
        assert fetch(base + '/release', limit=1024) == b'official metadata'
        return build
    monkeypatch.setattr(sophon, 'release', release)
    monkeypatch.setattr(sophon, 'download', lambda *a, **k: pytest.fail('Unaccounted global transport'))
    from backend import prebuilt_readers, genshin_native_x64, genshin_blb
    layout = object()
    monkeypatch.setattr(prebuilt_readers, 'prebuilt_reader', lambda kind, **kw:
        SimpleNamespace(source_identity='authored-source', manifest={'build_id': 'authored-build'}, executable=Path('frozen-reader'))
        if kind == 'genshin' and kw == {'layout': layout} else pytest.fail('Unexpected runtime resolver'))
    monkeypatch.setattr(genshin_native_x64, 'decoder', lambda: object())
    monkeypatch.setattr(genshin_blb, 'helper', lambda *a, **k: pytest.fail('Hidden helper build'))
    runtime = provider.GenshinRuntime(layout)
    result = provider.GenshinGameDataProvider(platform='windows', native=runtime, transport_factory=Transport)
    return result, ctx, calls, objects, original, build


@pytest.mark.parametrize('region', ['global', 'cn'])
@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_original_stage_counts_shared_chunks_and_never_becomes_a_snapshot(tmp_path, monkeypatch, region, mode):
    source, ctx, calls, objects, originals, build = fixture(tmp_path, monkeypatch, region=region, mode=mode)
    old = tmp_path / 'accepted-library.json'; old.write_bytes(b'previous complete library')
    plan = source.plan(ctx.request, ctx)
    assert plan.stage == 'official-native-inputs' and plan.runtime_available
    assert plan.handle['request']['content_mode'] == mode
    assert len(plan.handle['ledger']['chunks']) == 3
    assert plan.download_bytes == sum(len(objects[r['urls'][0]]) for r in plan.handle['ledger']['chunks'])
    assert plan.required_disk_bytes >= sum(map(len, originals.values())) + 3 * 512
    assert all(kind == 'metadata' for _, kind in calls)
    ctx.phase, ctx.budget, ctx.consumed = 'download', plan.download_bytes, 0
    result = source.download(plan, ctx)
    assert isinstance(result, PreparationStage) and len(result.restore_handle['sources']) == 2
    assert ctx.consumed == plan.download_bytes
    assert old.read_bytes() == b'previous complete library'
    before = len(calls)
    with pytest.raises(GameDataError, match='not a prepared dialogue library'):
        source.restore(result.restore_handle, ctx)
    assert len(calls) == before
    ctx.phase, ctx.budget, ctx.consumed = 'plan', 8 * 1024**2, 0
    ctx.stage_handle = result.restore_handle
    next_plan = source.plan(ctx.request, ctx)
    assert next_plan.stage == 'original-content-reader' and not next_plan.runtime_available
    assert next_plan.download_bytes is next_plan.required_disk_bytes is None
    assert len(calls) == before + 1  # Current launcher discovery only, no payload.


@pytest.mark.parametrize('platform', ['android', 'linux', 'macos', 'windows'])
def test_missing_runtime_gates_before_any_transfer_or_large_input(tmp_path, platform):
    request = GameDataRequest('global', 'en')
    ctx = Context(tmp_path, request)
    source = provider.create_provider(platform=platform)
    result = source.plan(request, ctx)
    assert not result.runtime_available and result.download_bytes is None and ctx.consumed == 0
    assert result.stage == 'original-runtime'


@pytest.mark.parametrize('change', ['request', 'region', 'ledger', 'size', 'missing-manifest'])
def test_changed_plan_or_cache_never_fetches_unplanned_sources(tmp_path, monkeypatch, change):
    source, ctx, calls, _, _, build = fixture(tmp_path, monkeypatch)
    plan = source.plan(ctx.request, ctx)
    before = len(calls)
    if change == 'request':
        ctx.request = GameDataRequest('global', 'en')
    elif change == 'region':
        plan.handle['build']['channel'] = 'genshin-cn'
    elif change == 'ledger':
        plan.handle['ledger']['chunks'][0]['compressed_bytes'] += 1
    elif change == 'size':
        plan = replace(plan, download_bytes=plan.download_bytes + 1)
    else:
        (ctx.cache_directory / 'genshin-original/global/manifests' / build['manifests']['game'][4]).unlink()
    ctx.phase, ctx.budget, ctx.consumed = 'download', plan.download_bytes, 0
    with pytest.raises(GameDataError):
        source.download(plan, ctx)
    assert len(calls) == before
    assert not (ctx.directory / 'original-native-inputs.json').exists()


def test_bad_whole_original_retains_previous_stage_and_retry_reuses_verified_chunks(tmp_path, monkeypatch):
    source, ctx, calls, _, _, _ = fixture(tmp_path, monkeypatch, wrong_whole=True)
    previous = ctx.directory / 'original-native-inputs.json'; previous.write_bytes(b'previous stage')
    plan = source.plan(ctx.request, ctx)
    ctx.phase, ctx.budget, ctx.consumed = 'download', plan.download_bytes, 0
    with pytest.raises(GameDataError, match='whole-file checksum'):
        source.download(plan, ctx)
    assert previous.read_bytes() == b'previous stage'
    assert not list((ctx.cache_directory / 'genshin-original/global/sources').glob('*.pending'))
    assert list((ctx.cache_directory / 'genshin-original/global/chunks').iterdir())
    before = len(calls)
    ctx.phase, ctx.budget, ctx.consumed = 'plan', 8 * 1024**2, 0
    next_plan = source.plan(ctx.request, ctx)
    assert next_plan.download_bytes < plan.download_bytes
    assert len(calls) == before + 1


def test_manifest_needs_explicit_source_consent_when_metadata_budget_is_insufficient(tmp_path, monkeypatch):
    source, ctx, calls, _, _, build = fixture(tmp_path, monkeypatch)
    ctx.budget = len(b'official metadata')
    plan = source.plan(ctx.request, ctx)
    assert plan.stage == 'official-manifest' and len(calls) == 1
    assert plan.download_bytes == build['manifests']['game'][2]
    ctx.phase, ctx.budget, ctx.consumed = 'download', plan.download_bytes, 0
    result = source.download(plan, ctx)
    assert isinstance(result, PreparationStage) and result.restore_handle['phase'] == 'official-manifest'
    assert 'manifest verified' in result.message and 'native inputs verified' not in result.message
    assert ctx.consumed == plan.download_bytes and len(calls) == 2


def test_runtime_change_or_cancellation_cannot_start_a_previously_quoted_transfer(tmp_path, monkeypatch):
    source, ctx, calls, _, _, _ = fixture(tmp_path, monkeypatch)
    plan = source.plan(ctx.request, ctx)
    before = len(calls)
    ctx.phase, ctx.budget, ctx.consumed = 'download', plan.download_bytes, 0
    ctx.stopped = True
    with pytest.raises(GameDataError, match='Preparation stopped'):
        source.download(plan, ctx)
    assert len(calls) == before
    ctx.stopped, source.runtime = False, None
    with pytest.raises(GameDataError):
        source.download(plan, ctx)
    assert len(calls) == before


def test_android_factory_and_early_gate_do_not_import_a_desktop_reader(tmp_path, monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if any(part in name for part in ('genshin_blb', 'genshin_native_x64', 'prebuilt_readers')):
            pytest.fail('Android metadata stage imported a desktop runtime')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    spec = importlib.util.spec_from_file_location('backend.authored_android_genshin', provider.__file__)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    request = GameDataRequest('global', 'en')
    ctx = Context(tmp_path, request)
    assert module.create_provider(platform='android').plan(request, ctx).stage == 'original-runtime'
