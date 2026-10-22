"""Real HTTP/WS endpoint contracts with owned synthetic runtime data only."""
import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
from backend import api
from backend.state_version import StateVersion


def test_snapshot_stamps_before_any_payload_read_and_includes_hito(monkeypatch):
    clock = StateVersion()
    accounts = SimpleNamespace(generation=0)
    visits = []
    def status():
        clock.publish(accounts.generation)
        return {'observed_after_stamp': True}
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(context=lambda: clock.snapshot(accounts.generation),
                                                       accounts=accounts, status=status), raising=False)
    monkeypatch.setattr(api, 'get_lines', lambda **kw: visits.append(('lines', kw['game'])) or [])
    monkeypatch.setattr(api, 'get_favorites', lambda **kw: visits.append(('favorites', kw['game'])) or [])
    monkeypatch.setattr(api, 'integration_status', lambda **kw: {'configured': False})
    response = TestClient(api.app, base_url='http://127.0.0.1:8766').get('/api/snapshot')
    assert response.status_code == 200
    assert response.json()['context']['state_version'] == 0
    assert clock.snapshot(0)['state_version'] == 1
    assert visits == [(kind, game) for game in api.GAMES for kind in ['lines', 'favorites']]
    assert ('lines', 'hito') in visits


def test_snapshot_rejects_account_switch_during_reads(monkeypatch):
    clock = StateVersion()
    accounts = SimpleNamespace(generation=0)
    def status():
        accounts.generation += 1
        return {}
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(context=lambda: clock.snapshot(accounts.generation),
                                                       accounts=accounts, status=status), raising=False)
    monkeypatch.setattr(api, 'get_lines', lambda **kw: [])
    monkeypatch.setattr(api, 'get_favorites', lambda **kw: [])
    monkeypatch.setattr(api, 'integration_status', lambda **kw: {})
    assert TestClient(api.app, base_url='http://127.0.0.1:8766').get('/api/snapshot').status_code == 409


def test_event_revision_is_reserved_before_a_delayed_send():
    asyncio.run(delayed_send())


async def delayed_send():
    clock = StateVersion()
    blocked, release = asyncio.Event(), asyncio.Event()
    events = []
    class Socket:
        async def send_json(self, event):
            if event['type'] == 'first':
                blocked.set()
                await release.wait()
            events.append(event)
    hub = api.EventHub(lambda: clock.publish(3))
    hub.clients.add(Socket())
    first = asyncio.create_task(hub.broadcast({'type': 'first'}))
    await blocked.wait()
    await hub.broadcast({'type': 'second'})
    release.set()
    await first
    assert [e['context']['state_version'] for e in events] == [2, 1]
    assert all(e['context']['account_generation'] == 3 for e in events)


def line_publication_fixture(tmp_path):
    from backend.models import TextMatch
    from backend.storage import TranscriptStore
    transcript = TranscriptStore(tmp_path / 'synthetic-history.db')
    line = transcript.add(TextMatch(game='pragmata', text_id='synthetic', english='Synthetic', chinese='合成',
                                    source_ocr='Synthetic', score=100, kind='exact'), 'synthetic-session')
    events = []
    class Socket:
        async def send_json(self, event):
            events.append(event)
    clock = StateVersion()
    hub = api.EventHub(lambda: clock.publish(0))
    hub.clients.add(Socket())
    runtime = SimpleNamespace(transcript=transcript, present_line=lambda item: item, hub=hub)
    return runtime, line, events


def test_pending_line_publication_reads_current_favorite(tmp_path):
    runtime, line, events = line_publication_fixture(tmp_path)
    async def check():
        # Audio callbacks construct this coroutine before the event loop runs it.
        pending = api.Runtime.on_line(runtime, line)
        latest = runtime.transcript.set_favorite(line.id, True)
        await api.Runtime.on_line(runtime, latest)
        await pending
    asyncio.run(check())
    assert [event['line']['favorite'] for event in events] == [True, True]
    assert [event['context']['state_version'] for event in events] == [1, 2]


def test_pending_line_publication_cannot_resurrect_a_deleted_row(tmp_path):
    runtime, line, events = line_publication_fixture(tmp_path)
    async def check():
        pending = api.Runtime.on_line(runtime, line)
        runtime.transcript.delete(line.id)
        await api.Runtime.on_delete(runtime, line.id)
        await pending
    asyncio.run(check())
    assert [event['type'] for event in events] == ['line_deleted']


def test_pending_audio_notice_cannot_undo_completed_audio(tmp_path):
    runtime, line, events = line_publication_fixture(tmp_path)
    async def check():
        pending = api.Runtime.on_line(runtime, line.model_copy(update={'audio_pending': True}))
        runtime.transcript.update_audio(line.id, 'official-synthetic.wav', True)
        await pending
    asyncio.run(check())
    assert events[0]['line']['has_audio'] is True
    assert events[0]['line']['audio_pending'] is False
    assert events[0]['line']['audio_source'] == 'original'


def test_pending_audio_notice_is_preserved_while_audio_is_unavailable(tmp_path):
    runtime, line, events = line_publication_fixture(tmp_path)
    asyncio.run(api.Runtime.on_line(runtime, line.model_copy(update={'audio_pending': True})))
    assert events[0]['line']['has_audio'] is False
    assert events[0]['line']['audio_pending'] is True
