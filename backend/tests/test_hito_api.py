import asyncio
import threading
from types import SimpleNamespace

from fastapi import WebSocketDisconnect

from backend import api
from backend.models import AppSettings, CaptureSnapshot


def test_browser_snapshot_does_not_block_capture_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    events = []

    def slow_status():
        started.set()
        assert release.wait(2)
        return {'capture': {'active_game': 'hito'}}

    class Socket:
        async def send_json(self, value):
            events.append(value)

        async def receive_text(self):
            raise WebSocketDisconnect()

    class Hub:
        async def connect(self, socket):
            pass

        async def disconnect(self, socket):
            pass

    monkeypatch.setattr(api, 'runtime', SimpleNamespace(status=slow_status, hub=Hub()), raising=False)

    async def check():
        task = asyncio.create_task(api.websocket_endpoint(Socket()))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            assert not task.done()
        finally:
            release.set()
        await task

    asyncio.run(check())
    assert events[0]['snapshot']['capture']['active_game'] == 'hito'


def test_status_exposes_hito_capture_and_text_index():
    runtime = object.__new__(api.Runtime)
    runtime.capture = SimpleNamespace(session_id='test', snapshot=lambda: CaptureSnapshot(active_game='hito'))
    for name in ('textmaps', 'pragmata'):
        setattr(runtime, name, SimpleNamespace(status=lambda: {}))
    runtime.voice_assets = SimpleNamespace(ready=True, status=lambda: {})
    runtime.pragmata_voice_assets = SimpleNamespace(ready=True, status=lambda: {})
    runtime.game_indexes = {"cyberpunk": SimpleNamespace(status=lambda: {"ready": True, "entry_count": 12})}
    runtime.game_voice_assets = {"cyberpunk": SimpleNamespace(ready=True, status=lambda: {})}
    runtime.hito = SimpleNamespace(status=lambda: {
        'ready': True, 'state': 'ready', 'message': 'ready', 'entry_count': 123,
    })
    runtime.settings = SimpleNamespace(get=AppSettings)
    runtime.update_status = lambda: {}
    runtime.transcript = SimpleNamespace(count=lambda session_id=None: 2 if session_id else 30)

    runtime.languages = SimpleNamespace(selected=lambda *_: None)
    runtime.accounts = SimpleNamespace(status=lambda: {'active':'legacy'})
    status = runtime.status()
    assert status['capture']['active_game'] == 'hito'
    assert status['game_textmaps']['hito']['entry_count'] == 123
    assert status['session'] == {'id': 'test', 'line_count': 2, 'total_line_count': 30}


def test_hito_update_endpoint_refreshes_last_detected_archive(monkeypatch):
    hito = SimpleNamespace(
        refresh=lambda: True,
        status=lambda: {'ready': True, 'entry_count': 321},
    )
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(hito=hito), raising=False)

    assert api.update_hito_text() == {
        'started': True,
        'hito': {'ready': True, 'entry_count': 321},
    }
