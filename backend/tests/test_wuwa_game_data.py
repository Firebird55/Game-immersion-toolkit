"""Shared-budget bootstrap staging never pretends to be a prepared library."""
from email.message import Message
import io
import json
from pathlib import Path
import threading
import time

import pytest

from backend import wuwa_game_data as provider
from backend.game_data_protocol import GameDataError, GameDataRequest, PreparationStage
from backend.publisher_transport import PublisherTransport
from backend.tests.test_wuthering_native_bootstrap import source, signed_game, signing_key, URL


contexts = []


def Context(root, mode='text'):
    from backend.game_data import GameDataService, _Context
    service = GameDataService(root, {})
    contexts.append(service)
    return _Context(service, root, 'local', 'wuwa',
        GameDataRequest('global', 'ja', ('en', 'zh-Hans'), mode), root / 'generation', 'plan')


@pytest.fixture(autouse=True)
def close_contexts():
    yield
    while contexts:
        contexts.pop().close()


class Response(io.BytesIO):
    def __init__(self, data, url, status=200, headers=None, *, on_read=lambda: None):
        super().__init__(data)
        self.url, self.status, self.headers, self.on_read = url, status, Message(), on_read
        for key, value in (headers or {}).items(): self.headers[key] = value
    def geturl(self): return self.url
    def read(self, count):
        value = super().read(min(count, 173))
        self.on_read()
        return value


@pytest.fixture
def original(tmp_path, monkeypatch, signing_key):
    _ref, module = source(tmp_path)
    apk = signed_game(module, signing_key)
    calls, controls = [], {'corrupt': False, 'cancel': None, 'offline': False}
    def open_(request, **kwargs):
        if controls['offline']: pytest.fail('This operation must remain offline')
        url = request.full_url
        calls.append(request)
        if url.startswith(provider._native().CATALOGUE + '?_t='):
            raw = json.dumps({'primary': URL, 'version': '1.0.0'}).encode()
            return Response(raw, url, headers={'Content-Length': str(len(raw))})
        assert url == URL
        headers = {'ETag': '"original"'}
        if request.get_header('Range'):
            start, end = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            headers.update({'Content-Range': f'bytes {start}-{end}/{len(apk)}', 'Content-Length': str(end-start+1)})
            return Response(apk[start:end+1], url, 206, headers)
        raw = bytearray(apk)
        if controls['corrupt']: raw[-23] ^= 1
        headers['Content-Length'] = str(len(raw))
        def on_read():
            if controls['cancel'] is not None: controls['cancel'].cancel.set()
        return Response(bytes(raw), url, headers=headers, on_read=on_read)
    monkeypatch.setattr(provider, 'PublisherTransport', lambda ctx, **kwargs:
        PublisherTransport(ctx, opener=open_, **kwargs))
    # This lane must not touch legacy seeds, protected ownership, or processes.
    monkeypatch.setattr(provider._native().metadata, '_read', lambda *a: pytest.fail('No protected bootstrap input'))
    return module, apk, calls, controls


@pytest.mark.parametrize('platform', ['desktop', 'android'])
@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_real_shared_transport_full_integrity_stage_then_honest_format_gate(tmp_path, original, platform, mode):
    module, apk, calls, controls = original
    ctx = Context(tmp_path, mode)
    adapter = provider.create_provider(platform, object())
    plan = adapter.plan(ctx.request, ctx)
    assert plan.download_bytes == len(apk) and plan.required_disk_bytes >= len(module)
    assert plan.stage == 'bootstrap' and plan.runtime_available and plan.source_proof is None
    assert all(request.get_header('Range') or request.full_url.startswith(provider._native().CATALOGUE) for request in calls)
    assert 'packaged media' in plan.message and 'optional voice pack' in plan.message
    ctx.phase, ctx.consumed, ctx.budget = 'download', 0, plan.download_bytes
    stage = adapter.download(plan, ctx)
    assert isinstance(stage, PreparationStage) and ctx.consumed == len(apk)
    path = provider._native()._module(ctx.cache_directory, stage.restore_handle['source'])
    assert path.read_bytes() == module
    assert not list(ctx.cache_directory.rglob('*.deflate')) and not list(ctx.cache_directory.rglob('*.apk'))
    controls['offline'] = True
    ctx.phase, ctx.stage_handle = 'plan', stage.restore_handle
    gate = adapter.plan(ctx.request, ctx)
    assert gate.stage == 'manifest-format' and not gate.runtime_available and gate.source_proof is None
    with pytest.raises(GameDataError) as failure: adapter.restore(stage.restore_handle, ctx)
    assert failure.value.code == 'publisher_format_key_unresolved'


@pytest.mark.parametrize('fault', ['corrupt', 'cancel', 'budget'])
def test_full_carrier_failure_keeps_old_data_and_cleans_provisional_member(tmp_path, original, fault):
    _module, _apk, _calls, controls = original
    ctx = Context(tmp_path)
    adapter = provider.create_provider('android')
    plan = adapter.plan(ctx.request, ctx)
    marker = ctx.cache_directory / 'retained-index-and-audio'
    marker.write_bytes(b'complete old library')
    ctx.phase, ctx.consumed, ctx.budget = 'download', 0, plan.download_bytes
    if fault == 'corrupt': controls['corrupt'] = True
    elif fault == 'cancel': controls['cancel'] = ctx
    else: ctx.budget -= 1
    with pytest.raises((ValueError, GameDataError)): adapter.download(plan, ctx)
    assert marker.read_bytes() == b'complete old library'
    assert not list(ctx.cache_directory.rglob('module.so'))
    assert not list(ctx.cache_directory.rglob('pending-*'))
    if fault == 'cancel': assert ctx.consumed > 0


def test_corrupt_retained_native_stage_is_not_ready_or_an_automatic_redownload(tmp_path, original):
    _module, _apk, _calls, controls = original
    ctx = Context(tmp_path)
    adapter = provider.create_provider('desktop')
    plan = adapter.plan(ctx.request, ctx)
    ctx.phase, ctx.consumed, ctx.budget = 'download', 0, plan.download_bytes
    stage = adapter.download(plan, ctx)
    path = provider._native()._module(ctx.cache_directory, stage.restore_handle['source'])
    path.write_bytes(b'corrupt')
    ctx.phase, ctx.stage_handle = 'plan', stage.restore_handle
    controls['offline'] = True
    with pytest.raises(GameDataError) as failure: adapter.plan(ctx.request, ctx)
    assert failure.value.code == 'publisher_bootstrap_cache_invalid'


def test_cross_request_stage_cannot_authorize_another_dub_or_region(tmp_path, original):
    ctx = Context(tmp_path)
    adapter = provider.create_provider('android')
    plan = adapter.plan(ctx.request, ctx)
    ctx.request = GameDataRequest('cn', 'en')
    with pytest.raises(GameDataError) as failure: adapter.download(plan, ctx)
    assert failure.value.code == 'invalid_source_handle'


def test_actual_settings_service_stage_restart_gate_and_scoped_delete(tmp_path, original):
    from backend.game_data import GameDataService
    _module, _apk, _calls, controls = original
    adapter = provider.create_provider('android')
    history = tmp_path / 'saved-history.db'
    history.write_bytes(b'user history')
    other = tmp_path / 'nte/cache/other-original'
    other.parent.mkdir(parents=True)
    other.write_bytes(b'other game')
    service = GameDataService(tmp_path, {'wuwa': adapter})
    request = GameDataRequest('global', 'ja', ('en', 'zh-Hans')).json()
    try:
        row = service.plan('wuwa', request)['game']
        assert row['can_download'] and not row['can_activate']
        service.download('wuwa', {'plan_id': row['plan_id'], 'revision': row['revision']})
        deadline = time.monotonic() + 5
        while True:
            row = next(x for x in service.snapshot()['games'] if x['id'] == 'wuwa')
            if row['job'] and row['job']['status'] not in ('queued', 'running'): break
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert row['job']['status'] == 'needs_plan' and not row['can_activate']
        assert not (tmp_path / 'wuwa/current.json').exists()
        assert (tmp_path / 'wuwa/stage.json').is_file()
    finally:
        service.close()
    controls['offline'] = True
    restarted = GameDataService(tmp_path, {'wuwa': adapter})
    try:
        row = restarted.plan('wuwa', request)['game']
        assert not row['can_download'] and not row['can_activate'] and row['installed_bytes'] > 0
        assert provider.FORMAT_MESSAGE in row['message']
        removed = restarted.delete('wuwa', {'revision': row['revision']})
        assert removed['freed_bytes'] > 0 and not (tmp_path / 'wuwa').exists()
        assert history.read_bytes() == b'user history' and other.read_bytes() == b'other game'
    finally:
        restarted.close()
