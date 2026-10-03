import asyncio
import threading
import sqlite3
from types import SimpleNamespace

from fastapi import WebSocketDisconnect

from backend import api
from backend.agent_recognition import AgentRecognizer


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


def test_hito_status_skips_unrelated_agent_database_and_survives_sync_errors(tmp_path):
    recognizer = object.__new__(AgentRecognizer)
    recognizer.folder = tmp_path
    recognizer.indexed = 0
    recognizer.library = {'clips': []}
    recognizer._context = (None, False)
    recognizer._last_match = recognizer._last_error = None
    recognizer._diagnostics = {}
    recognizer.updater = None
    calls = []

    def count():
        calls.append(True)
        raise sqlite3.OperationalError('disk I/O error')

    recognizer.store = SimpleNamespace(count=count)
    assert recognizer.status(include_database_counts=False)['saved_lines'] == 0
    assert not calls
    assert recognizer.status()['saved_lines'] == 0
