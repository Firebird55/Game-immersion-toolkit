import asyncio
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

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
        accounts=SimpleNamespace(status=lambda: {'active': 'account-one'}),
        languages=SimpleNamespace(selected=lambda *_: 'zh-Hans', prepared=lambda *_: {'targets': ['en']}),
        language_state=lambda *_: {'ready': True},
        capture=capture, start_updates=lambda: calls.append('updates'))
    fake._handoff_lock, fake._writer_handoff = asyncio.Lock(), False
    fake.resume_writers = lambda: None
    fake.admit_requests = lambda: None
    fake.activate_handoff = lambda payload, **options: api.Runtime.activate_handoff(fake, payload, **options)
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


@pytest.mark.parametrize('hito_active', [False, True])
def test_old_capture_remains_active_until_background_work_has_quiesced(monkeypatch, hito_active):
    from backend import api
    calls = []
    async def stop_updates(**_options):
        calls.append('updates')
    async def stop_capture():
        calls.append('capture')
    from backend.runtime_writers import RuntimeWriterGate
    fake = api.Runtime.__new__(api.Runtime)
    fake.standby, fake.stop_updates = False, stop_updates
    fake.request_writers, fake._handoff_lock, fake._handoff_drains = RuntimeWriterGate(), asyncio.Lock(), []
    fake.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True), quiesce=lambda _timeout: stop_capture(),
        export_handoff=lambda running: CaptureHandoff(running=running, session_id='continued'))
    fake.mobile_exports = SimpleNamespace(quiesce=lambda: calls.append('manual-exports'))
    fake.installation = SimpleNamespace(quiesce=lambda _timeout: calls.append('setup'))
    fake.reading = type('Reader', (), {'quiesce': lambda _self, _timeout: calls.append('reading')})()
    fake.automatic_exports = SimpleNamespace(picker=SimpleNamespace(quiesce=lambda: calls.append('automatic-picker')))
    fake.capture.drain_publications = lambda: asyncio.sleep(0)
    fake._readers, fake.map_task = {}, None
    fake.hito = SimpleNamespace(_process=SimpleNamespace(poll=lambda: None)) if hito_active else None
    fake._voice_pools = lambda: []
    fake._verify_background_stopped = lambda: None
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    response = client.post('/api/runtime/quiesce?writers=true', headers={'X-Proxy-Transcript': 'update'})
    if hito_active:
        assert response.status_code == 409 and 'Hito grammar worker' in response.json()['detail']
        assert not fake.standby
    else:
        assert response.status_code == 200 and response.json()['running']
    assert calls == ['manual-exports', 'automatic-picker', 'setup', 'updates', 'reading', 'capture']


def test_source_handoff_keeps_legacy_behavior_with_a_live_hito_worker(monkeypatch):
    from backend import api
    from backend.runtime_writers import RuntimeWriterGate
    calls, running = [], [True]
    old = api.Runtime.__new__(api.Runtime)
    old._handoff_lock, old._writer_handoff = asyncio.Lock(), False
    old.request_writers, old.standby = RuntimeWriterGate(), False
    old.textmaps = old.pragmata = None
    old.game_indexes, old.warm_task = {}, None
    old.hito = SimpleNamespace(ready=True, _process=SimpleNamespace(poll=lambda: None))
    async def stop_updates(): calls.append('updates-stop')
    async def stop_capture():
        calls.append('capture-stop')
        running[0] = False
    old.stop_updates = stop_updates
    old.start_updates = lambda: calls.append('updates-start')
    old.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=running[0]), stop=stop_capture,
        export_handoff=lambda active: CaptureHandoff(running=active, session_id='legacy-session'),
        import_handoff=lambda state: calls.append(('import', state.session_id)),
        start=lambda: (calls.append('capture-start'), running.__setitem__(0, True)))
    monkeypatch.setattr(api, 'runtime', old, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    headers = {'X-Proxy-Transcript': 'update'}
    response = client.post('/api/runtime/quiesce', headers=headers)
    assert response.status_code == 200 and response.json()['running']
    old.request_writers.enter(); old.request_writers.leave()
    assert client.post('/api/runtime/activate', headers=headers, json=response.json()).status_code == 200
    assert running[0] and not old.standby and not old._writer_handoff
    assert calls == ['updates-stop', 'capture-stop', ('import', 'legacy-session'), 'capture-start', 'updates-start']


def test_legacy_activation_cannot_bypass_explicit_strict_handoff():
    from backend.api import Runtime
    async def run():
        old = Runtime.__new__(Runtime)
        old._handoff_lock, old._writer_handoff = asyncio.Lock(), True
        with pytest.raises(TimeoutError, match='explicit writers protocol'):
            await old.activate_handoff(CaptureHandoff(running=True))
        with pytest.raises(TimeoutError, match='explicit writers protocol'):
            await old.quiesce_capture_handoff()
    asyncio.run(run())
