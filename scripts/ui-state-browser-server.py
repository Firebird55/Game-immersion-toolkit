"""Owned synthetic FastAPI runtime; all external account traffic is MockTransport."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import uvicorn
from backend import api
from backend.accounts import AccountStore
from backend.lexirise import LexiriseService
from backend.lexirise_settings import account_settings
from backend.models import AppSettings, TextMatch
from backend.state_version import StateVersion
from backend.storage import TranscriptStore

remote_calls = []
def remote(request):
    remote_calls.append((request.method, request.url.path))
    assert request.method == 'GET', 'No remote writes are allowed in this fixture'
    if request.url.path == '/v1/me':
        return httpx.Response(200, json={'user': {'id': request.headers['Authorization'][-1]}})
    if request.url.path == '/v1/settings':
        return httpx.Response(200, json={'languages': ['zh'], 'global': {'translationLanguage': 'en'},
                                      'languageSettings': {'zh': {'effectiveTranslationLanguage': 'en'}}})
    raise AssertionError('Unexpected external request ' + request.url.path)

with tempfile.TemporaryDirectory(prefix='toolkit-state-fixture-') as directory:
    root = Path(directory)
    store = AccountStore(root / 'fixture.dpapi', protect=lambda value, **_: value, transport=httpx.MockTransport(remote))
    accounts = [store.add('lx_synthetic_fixture_only_' + letter)['id'] for letter in 'AB']
    store.select(accounts[0])
    service = LexiriseService(root / 'lexirise', accounts=store, transport=httpx.MockTransport(remote))
    transcript = TranscriptStore(root / 'history.db')
    line = transcript.add(TextMatch(game='zzz', text_id='synthetic', english='Synthetic current line', chinese='合成台词',
                                   source_ocr='Synthetic', score=100, kind='exact'), 'fixture')
    transcript.update_audio(line.id, 'synthetic.wav', True)
    clock = StateVersion()
    context = lambda: clock.snapshot(store.generation)
    status = lambda: {'context': context(), 'capture': {'running': True, 'active_game': 'zzz', 'phase': 'matched',
        'message': 'Ready', 'visible_text_ids': ['synthetic']}, 'textmaps': {'ready': True, 'entry_count': 1},
        'audio': {'ready': True}, 'settings': AppSettings().model_dump(mode='json'),
        'session': {'id': 'fixture', 'line_count': 1, 'total_line_count': 1}}
    languages = SimpleNamespace(selected=lambda *_: 'zh-Hans', status=lambda *_: {'selected': 'zh-Hans', 'locales': [
        {'locale': 'zh-Hans', 'language': 'zh', 'name': 'Chinese', 'reader_available': True, 'prepared': {'targets': ['en'], 'mapped_lines': 1}}]})
    hub = api.EventHub(lambda: clock.publish(store.generation))
    api.runtime = SimpleNamespace(context=context, accounts=store, lexirise=service, transcript=transcript, status=status,
        languages=languages, language_inventory=SimpleNamespace(status=lambda *_: {'locales': {}}),
        account_preferences=lambda: account_settings(service.pin()), speakers=SimpleNamespace(enrich=lambda item: item),
        game_indexes={}, textmaps=SimpleNamespace(is_capture_text=lambda *_: True),
        hub=hub, capture=SimpleNamespace(_scan_epoch=0),
        installation=SimpleNamespace(status=lambda: {'completed': True, 'version': 'fixture', 'games': [],
            'requirements': [], 'jobs': {}, 'native': {}, 'auto_start': False, 'free_gb': 1, 'lexirise_configured': True}))
    async def on_line(item):
        await hub.broadcast({'type': 'line', 'line': item.model_dump(mode='json')})
    api.runtime.on_line = on_line
    holds, waiting = {}, {}
    counts = {'snapshot': 0, 'languages': 0}

    @api.app.middleware('http')
    async def hold_complete_response(request, call_next):
        kind = 'snapshot' if request.url.path == '/api/snapshot' else 'languages' if request.url.path.endswith('/languages') else None
        if kind:
            counts[kind] += 1
        gate = holds.pop(kind, None) if kind else None
        response = await call_next(request)
        if gate:
            waiting[kind] = gate
            await gate.wait()
            waiting.pop(kind, None)
        return response

    @api.app.post('/__test/hold/{kind}')
    async def hold(kind: str):
        holds[kind] = asyncio.Event()
        return {'held': kind}

    @api.app.post('/__test/release/{kind}')
    async def release(kind: str):
        if gate := waiting.get(kind):
            gate.set()
        return {'released': kind}

    @api.app.post('/__test/replace-runtime')
    async def replace_runtime():
        global clock
        clock = StateVersion()
        for websocket in list(hub.clients):
            await websocket.close()
        return {'context': context()}

    @api.app.get('/__test/state')
    async def state():
        return {'waiting': list(waiting), 'counts': counts, 'accounts': accounts, 'context': context(),
                'remote_calls': remote_calls}

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    print(json.dumps({'port': listener.getsockname()[1]}), flush=True)
    uvicorn.Server(uvicorn.Config(api.app, lifespan='off', log_level='error')).run(sockets=[listener])
