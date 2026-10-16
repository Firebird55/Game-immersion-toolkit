import asyncio
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.runtime_handoff import CaptureHandoff
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
        capture=capture, start_updates=lambda: calls.append('updates'))
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


def test_old_capture_remains_active_until_background_work_has_quiesced(monkeypatch):
    from backend import api
    calls = []
    async def stop_updates():
        calls.append('updates')
    async def stop_capture():
        calls.append('capture')
    fake = SimpleNamespace(standby=False, stop_updates=stop_updates,
        capture=SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True), stop=stop_capture,
            export_handoff=lambda running: CaptureHandoff(running=running, session_id='continued')))
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    response = client.post('/api/runtime/quiesce', headers={'X-Proxy-Transcript': 'update'})
    assert response.status_code == 200 and response.json()['running']
    assert calls == ['updates', 'capture']
