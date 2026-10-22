"""Synthetic runtime for the real FastAPI browser boundary test; never starts capture."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from backend.models import AppSettings, CaptureSnapshot

if baseline := os.environ.get('TOOLKIT_ACCESS_BASELINE'):
    spec = importlib.util.spec_from_file_location('backend._access_baseline', baseline)
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
else:
    from backend import api

calls, received = [], []

def record(kind, value=None):
    calls.append(kind)
    return value

async def stop():
    return record('stop', True)

async def no_op():
    pass

with tempfile.TemporaryDirectory(prefix='toolkit-access-data-') as temporary:
    api.DATA_DIR = Path(temporary)
    (api.DATA_DIR / 'audio').mkdir()
    with wave.open(str(api.DATA_DIR / 'audio' / 'synthetic.wav'), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b'\0' * 1600)
    api.runtime = SimpleNamespace(
        capture=SimpleNamespace(start=lambda: record('start', True), stop=stop,
            snapshot=lambda: record('capture_snapshot', CaptureSnapshot())),
        settings=SimpleNamespace(get=AppSettings, save=lambda settings: record('save', settings)),
        installation=SimpleNamespace(status=lambda: record('setup', {'completed': False}),
            complete=lambda auto: record('setup_complete')),
        transcript=SimpleNamespace(list=lambda **_: record('lines', []),
            audio_path=lambda _: record('audio', 'synthetic.wav')),
        speakers=SimpleNamespace(enrich=lambda line: line),
        hub=api.EventHub(), status=lambda: record('status', {'synthetic': True}))

    @api.app.get('/__test_observations')
    def observations():
        return {'calls': calls, 'received': received}

    @api.app.post('/__test_reset')
    def reset():
        calls.clear()
        received.clear()
        return {'reset': True}

    async def observed(scope, receive, send):
        if scope['type'] in {'http', 'websocket'} and scope['path'].startswith('/api/'):
            headers = dict(scope.get('headers', []))
            received.append({'type': scope['type'], 'path': scope['path'],
                'method': scope.get('method'), 'origin': headers.get(b'origin', b'').decode('latin-1')})
        await api.app(scope, receive, send)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    print(json.dumps({'port': listener.getsockname()[1]}), flush=True)
    server = uvicorn.Server(uvicorn.Config(observed, lifespan='off', log_level='error'))
    server.run(sockets=[listener])
