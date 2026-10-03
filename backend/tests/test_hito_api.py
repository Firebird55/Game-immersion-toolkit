import asyncio
import threading
from types import SimpleNamespace

from fastapi import WebSocketDisconnect

from backend import api


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
