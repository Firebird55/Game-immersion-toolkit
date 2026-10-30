import asyncio
import threading
import time
import sys
import json
from types import SimpleNamespace
import pytest

from fastapi.testclient import TestClient

from backend.runtime_handoff import CaptureHandoff
from backend.runtime_workers import RequestBarrier, ResumableExecutor, WriterBarrierMiddleware
from backend.tests.test_subtitle_capture import fixture_service


def test_real_runtime_initializes_standby_without_starting_capture_or_updates(tmp_path, monkeypatch):
    from backend import api
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('PROXY_TRANSCRIPT_STANDBY', '1')
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path / 'data')
    monkeypatch.setattr(api.HitoTextIndex, 'ensure_game_files', lambda *_: None)
    async def run():
        runtime = api.Runtime()
        try:
            assert runtime.standby and not runtime._updates_started
            assert runtime.warm_task is None and runtime.index_task is None
            assert not runtime.capture.snapshot().running
        finally:
            await runtime.capture.close()
            runtime.voice_assets.close()
            runtime.pragmata_voice_assets.close()
            for voices in runtime.game_voice_assets.values():
                voices.close()
    asyncio.run(run())


def test_handoff_preserves_session_and_duplicate_suppression(tmp_path):
    old, match, _, _ = fixture_service(tmp_path / 'old')
    fresh, _, _, _ = fixture_service(tmp_path / 'fresh')
    fresh.transcript = old.transcript
    old.transcript.add(match, old.session_id)
    old._can_emit('dialogue\0'+match.text_id+'\0'+match.english, time.monotonic())
    try:
        state = CaptureHandoff.model_validate(old.export_handoff(True).model_dump())
        fresh.import_handoff(state)
        assert fresh.session_id == old.session_id
        assert not fresh._can_emit('cinematic\0'+match.text_id+'\0'+match.english, time.monotonic())
        assert fresh._can_emit('dialogue\0another-line\0A new sentence.', time.monotonic())
        assert old.transcript.count() == 1
    finally:
        old._executor.shutdown()
        fresh._executor.shutdown()


def test_quiescing_capture_drains_native_work_before_exporting_state(tmp_path):
    capture, _, _, _ = fixture_service(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def native_work():
        entered.set()
        assert release.wait(3)
    capture._executor.submit(native_work)
    assert entered.wait(1)
    async def run():
        capture._task = asyncio.create_task(asyncio.sleep(100))
        stopping = asyncio.create_task(capture.stop())
        await asyncio.sleep(.03)
        assert not stopping.done()
        assert capture._scan_epoch == 1
        release.set()
        assert await stopping
    try:
        asyncio.run(run())
    finally:
        release.set()
        capture._executor.shutdown()


def test_runtime_activation_requires_local_action_and_ready_candidate(monkeypatch):
    from backend import api
    calls = []
    capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=False),
        import_handoff=lambda state: calls.append(('import', state.session_id)), start=lambda: calls.append('capture'))
    fake = SimpleNamespace(textmaps=SimpleNamespace(ready=True), pragmata=None, hito=None,
        game_indexes={}, warm_task=SimpleNamespace(done=lambda: False), standby=True,
        accounts=SimpleNamespace(status=lambda: {'active': 'account-one'}),
        languages=SimpleNamespace(selected=lambda *_: 'zh-Hans', prepared=lambda *_: {'targets': ['en']}),
        language_state=lambda *_: {'ready': True},
        capture=capture, start_updates=lambda: calls.append('updates'), activate_workers=lambda: None)
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    assert not client.get('/api/runtime/ready?game=zzz').json()['ready']
    assert client.post('/api/runtime/activate', json={'running': True}).status_code == 403
    headers = {'X-Proxy-Transcript': 'update'}
    assert client.post('/api/runtime/activate', headers=headers, json={'running': True}).status_code == 409
    assert calls == []
    fake.warm_task = None
    response = client.post('/api/runtime/activate', headers=headers, json={'running': True, 'session_id': 'same-session'})
    assert response.status_code == 200
    assert calls == [('import', 'same-session'), 'capture', 'updates']


def test_standby_readiness_uses_only_the_active_accounts_prepared_language(monkeypatch):
    from backend import api
    states = []
    selected = {'account-one': 'nl', 'account-two': 'fr'}
    prepared = {('beyond', 'nl'): {'targets': ['zh-hans']}}
    active = ['account-one']
    ready = [True]
    def language_state(game, locale):
        states.append((game, locale))
        return {'ready': ready[0]}
    fake = SimpleNamespace(textmaps=None, pragmata=None, hito=SimpleNamespace(ready=True),
        game_indexes={'beyond': SimpleNamespace(ready=False)}, warm_task=None, standby=True,
        accounts=SimpleNamespace(status=lambda: {'active': active[0]}),
        languages=SimpleNamespace(selected=lambda game, account: selected.get(account),
                                  prepared=lambda game, locale: prepared.get((game, locale))),
        language_state=language_state)
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    assert client.get('/api/runtime/ready?game=beyond').json() == {'ready': True, 'standby': True}
    assert states == [('beyond', 'nl')]
    ready[0] = False
    assert not client.get('/api/runtime/ready?game=beyond').json()['ready']
    active[0] = 'account-two'
    fake.game_indexes['beyond'].ready = True
    states.clear()
    assert not client.get('/api/runtime/ready?game=beyond').json()['ready']
    assert states == []  # Never fall back to another account or prepare French.
    active[0] = 'legacy-account-without-selection'
    assert client.get('/api/runtime/ready?game=beyond').json()['ready']
    fake.game_indexes['beyond'].source_locale = 'nl'
    assert not client.get('/api/runtime/ready?game=beyond').json()['ready']
    assert states == []
    assert client.get('/api/runtime/ready?game=hito').json()['ready']
    assert not client.get('/api/runtime/ready?game=unknown').json()['ready']


def test_old_capture_remains_active_until_background_work_has_quiesced(monkeypatch):
    from backend import api
    calls = []
    async def stop_updates():
        calls.append('updates')
    async def stop_capture():
        calls.append('capture')
    fake = object.__new__(api.Runtime)
    fake.standby, fake._quiesce_task = False, None
    fake._handoff_state = None
    fake.request_barrier = RequestBarrier()
    fake.stop_updates = stop_updates
    fake.installation = SimpleNamespace(pause=lambda: None)
    fake.mobile_exports = SimpleNamespace(drain=lambda: None)
    fake.hito = SimpleNamespace(close=lambda: None)
    fake.worker_pools = lambda: []
    fake.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True), stop=stop_capture,
        export_handoff=lambda running: CaptureHandoff(running=running, session_id='continued'))
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    response = client.post('/api/runtime/quiesce', headers={'X-Proxy-Transcript': 'update'})
    assert response.status_code == 200 and response.json()['running']
    assert calls == ['updates', 'capture']


def test_pool_drain_waits_for_pending_work_and_cache_completion_callback():
    # A cancelled asyncio Future and an empty replacement queue both missed
    # callbacks writing dictionaries/audio in the retiring runtime.
    pool = ResumableExecutor(max_workers=1)
    entered, release, callback, finish = (threading.Event() for _ in range(4))
    writes = []
    def work():
        entered.set()
        assert release.wait(3)
    def completed(_):
        callback.set()
        assert finish.wait(3)
        writes.append('cache')
    first = pool.submit(work)
    first.add_done_callback(completed)
    second = pool.submit(lambda: writes.append('queued'))
    assert entered.wait(1)
    drain = threading.Thread(target=pool.drain)
    drain.start()
    try:
        with pytest.raises(RuntimeError):
            pool.submit(lambda: None)
        release.set()
        assert callback.wait(1)
        drain.join(.03)
        assert drain.is_alive() and writes == []
        finish.set()
        drain.join(2)
        assert not drain.is_alive() and writes == ['cache', 'queued']
        assert second.done()
        pool.resume()
        assert pool.submit(lambda: 'resumed').result(1) == 'resumed'
    finally:
        release.set(); finish.set()
        drain.join(3)
        pool.shutdown()


def test_request_barrier_counts_get_through_response_completion():
    async def run():
        gate = RequestBarrier()
        entered, release = asyncio.Event(), asyncio.Event()
        messages = []
        async def app(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            entered.set()
            await release.wait()  # A streaming response still owns its cache work.
            await send({'type': 'http.response.body', 'body': b'done'})
        async def send(message):
            messages.append(message)
        middleware = WriterBarrierMiddleware(app, lambda: gate)
        scope = {'type': 'http', 'path': '/api/lines/1/reading', 'method': 'GET'}
        first = asyncio.create_task(middleware(scope, None, send))
        await entered.wait()
        drain = asyncio.create_task(gate.pause())
        await asyncio.sleep(0)
        await middleware(scope, None, send)
        assert messages[-2]['status'] == 503 and not drain.done()
        release.set()
        await first; await drain
        gate.resume()
        assert gate.enter()
        gate.leave()
    asyncio.run(run())


def test_cancelled_handoff_waiter_does_not_release_actual_workers(tmp_path):
    capture, _, _, _ = fixture_service(tmp_path)
    retired = ResumableExecutor(max_workers=1)
    entered, release = threading.Event(), threading.Event()
    def old_scan():
        entered.set()
        assert release.wait(5)
    retired.submit(old_scan)
    assert entered.wait(1)
    capture._retired_executors.append(retired)
    async def run():
        waiter = asyncio.create_task(capture.stop())
        await asyncio.sleep(.03)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        with pytest.raises(RuntimeError, match='previous scan'):
            capture.start()
        assert not capture._stop_task.done()
        release.set()
        await capture.stop()
        assert capture._retired_executors == []
    try:
        asyncio.run(run())
    finally:
        release.set()
        retired.shutdown(); capture._executor.shutdown()


def test_handoff_timeout_keeps_drain_alive_and_blocks_activation(monkeypatch):
    from backend import api
    from starlette.requests import Request
    from fastapi import HTTPException
    fake = object.__new__(api.Runtime)
    fake._quiesce_task = None
    fake._handoff_state = None
    fake.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True),
        export_handoff=lambda running: CaptureHandoff(running=running, session_id='same-session'))
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    monkeypatch.setattr(api, 'HANDOFF_TIMEOUT_SECONDS', .01)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/runtime/quiesce',
                       'headers': [], 'server': ('127.0.0.1', 8766), 'scheme': 'http', 'query_string': b''})
    async def run():
        release = asyncio.Event()
        fake._drain_workers = release.wait
        with pytest.raises(HTTPException) as failure:
            await api.runtime_quiesce(request, 'update')
        assert failure.value.status_code == 503
        assert not fake._quiesce_task.done()
        with pytest.raises(RuntimeError, match='still stopping'):
            fake.activate_workers()
        release.set()
        monkeypatch.setattr(api, 'HANDOFF_TIMEOUT_SECONDS', 1)
        result = await api.runtime_quiesce(request, 'update')
        assert result['running'] and result['session_id'] == 'same-session'
    asyncio.run(run())


def test_export_drain_stops_decoder_left_after_export_parent_exits(tmp_path):
    # Exercise the export manager's actual ownership, not merely the process
    # wrapper: otherwise a clean parent exit could skip descendant cleanup.
    import psutil
    from backend.mobile_export_controls import MobileExportManager
    marker = tmp_path / 'decoder.json'
    script = '''import subprocess, sys, json
from pathlib import Path
p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
Path(sys.argv[1]).write_text(json.dumps({'pid': p.pid}))
print(json.dumps({'state': 'complete', 'progress': 100}), flush=True)
'''
    manager = MobileExportManager(tmp_path)
    manager._worker_args = lambda *_: [sys.executable, '-c', script, str(marker)]
    manager._thread = threading.Thread(target=manager._run, args=('zzz', False, tmp_path))
    manager._thread.start()
    manager._thread.join(15)
    manager.drain()
    assert not manager._thread.is_alive()
    assert manager.status()['state'] == 'complete'
    assert not psutil.pid_exists(json.loads(marker.read_text())['pid'])
