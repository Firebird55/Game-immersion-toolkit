"""Actual FastAPI middleware and Lexirise transport; synthetic accounts only."""
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import api
from backend.accounts import AccountStore
from backend.lexirise import LexiriseService
from backend.models import TextMatch
from backend.storage import TranscriptStore


KEYS = {owner: f'lx_{owner}_synthetic_fixture_only' for owner in ['first', 'second']}
SETTINGS = {'languages': ['zh'], 'global': {}, 'languageSettings': {'zh': {}}}
REQUESTS = [('GET', '/api/lexirise/settings', None), ('PATCH', '/api/lexirise/settings', {}),
            ('GET', '/api/lexirise/decks', None), ('POST', '/api/lexirise/decks', {'game': 'cyberpunk', 'create': True}),
            ('GET', '/api/lines/1/reading', None), ('GET', '/api/lines/1/reading/lookup?start=0', None),
            ('POST', '/api/lines/1/reading/proficiency', {'start': 0, 'proficiency': 3}),
            ('POST', '/api/lines/1/reading/grammar', {'slug': 'synthetic', 'known': True}),
            ('POST', '/api/lines/1/reading/context', {'start': 0, 'question': 'Synthetic?'}),
            ('POST', '/api/lines/1/reading/examples/0/save', {'start': 0}),
            ('POST', '/api/lines/1/lexirise', {})]


@pytest.fixture
def pinned_api(tmp_path, monkeypatch):
    monkeypatch.delenv('LEXIRISE_API_KEY', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'host-fixture'))
    calls, switch = [], []
    deck = {'id': 41, 'owner_user_id': 'first', 'language': 'zh', 'unit_type': 'sentence',
            'deck_type': 'snapshot', 'title': 'Synthetic deck'}
    def reply(request):
        owner = next(owner for owner, key in KEYS.items() if request.headers['Authorization'] == f'Bearer {key}')
        path = request.url.path
        calls.append((owner, request.method, path))
        if switch:
            store.select(switch.pop())
        if path == '/v1/me':
            return httpx.Response(200, json={'user': {'id': owner}})
        if path == '/v1/settings':
            return httpx.Response(200, json=SETTINGS)
        if path == '/v1/decks':
            return httpx.Response(200, json={'decks': [deck], 'deck': deck})
        if path == '/v1/decks/41':
            return httpx.Response(200, json={'deck': deck, 'items': []})
        if path == '/v1/vocabulary/audio':
            return httpx.Response(200, json={'publicUrl': 'https://audio.example.test/synthetic.mp3'})
        if path == '/v1/vocabulary':
            return httpx.Response(200, json={'items': [], 'item': {'id': 51}})
        if path == '/v1/decks/41/items':
            return httpx.Response(200, json={'added_count': 1})
        raise AssertionError(f'Unexpected synthetic transport request {request.method} {path}')
    transport = httpx.MockTransport(reply)
    store = AccountStore(tmp_path / 'fixture.dpapi', protect=lambda value, **_: bytes(b ^ 173 for b in value), transport=transport)
    profiles = {owner: store.add(key) for owner, key in KEYS.items()}
    store.select(profiles['first']['id'])
    service = LexiriseService(tmp_path / 'lexirise', accounts=store, transport=transport)
    transcript = TranscriptStore(tmp_path / 'history.db')
    line = transcript.add(TextMatch(game='cyberpunk', text_id='synthetic:1', english='Hello.', chinese='你好。',
                                    source_ocr='Hello.', score=100, kind='exact'), 'synthetic')
    transcript.update_audio(line.id, 'official-synthetic.mp3', True)
    (tmp_path / 'audio').mkdir()
    (tmp_path / 'audio/official-synthetic.mp3').write_bytes(b'synthetic audio fixture')
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(accounts=store, lexirise=service, transcript=transcript), raising=False)
    calls.clear()
    return SimpleNamespace(client=TestClient(api.app, base_url='http://127.0.0.1:8766'), calls=calls,
                           store=store, service=service, profiles=profiles, switch=switch)


@pytest.mark.parametrize('method,path,body', REQUESTS)
def test_stale_account_header_rejects_before_transport(pinned_api, method, path, body):
    fixture = pinned_api
    response = fixture.client.request(method, path, json=body, headers={
        'X-Proxy-Transcript': 'lexirise', 'X-Proxy-Transcript-Account': fixture.profiles['second']['id']})
    assert response.status_code == 409
    assert fixture.calls == []
    assert fixture.service.status()['sent'] == {} and fixture.service.status()['decks'] == {}


@pytest.mark.parametrize('method,path,body', REQUESTS)
def test_unconfigured_account_fails_without_any_transport(pinned_api, method, path, body):
    fixture = pinned_api
    fixture.store.select('legacy')
    response = fixture.client.request(method, path, json=body, headers={'X-Proxy-Transcript': 'lexirise'})
    assert response.status_code == 503
    assert fixture.calls == []


@pytest.mark.parametrize('header', [False, True])
def test_current_or_absent_header_pins_entire_request_through_account_switch(pinned_api, header):
    fixture = pinned_api
    fixture.switch.append(fixture.profiles['second']['id'])
    response = fixture.client.get('/api/lexirise/decks', headers={
        'X-Proxy-Transcript-Account': fixture.profiles['first']['id']} if header else {})
    assert response.status_code == 200 and response.json()['decks'] == [{'id': 41, 'title': 'Synthetic deck'}]
    assert fixture.calls == [('first', 'GET', '/v1/me'), ('first', 'GET', '/v1/decks')]
    assert fixture.store.status()['active'] == fixture.profiles['second']['id']
    # A new request observes the selected account; the old ContextVar is reset.
    assert fixture.client.get('/api/lexirise/settings').status_code == 200
    assert fixture.calls[-1] == ('second', 'GET', '/v1/settings')


@pytest.mark.parametrize('header', [False, True])
def test_configured_legacy_account_pins_mock_credential_through_switch(pinned_api, monkeypatch, header):
    fixture = pinned_api
    fixture.store.select('legacy')
    # Synthetic fallback credential only; every request uses MockTransport.
    monkeypatch.setenv('LEXIRISE_API_KEY', KEYS['first'])
    fixture.switch.append(fixture.profiles['second']['id'])
    response = fixture.client.get('/api/lexirise/decks', headers={
        'X-Proxy-Transcript-Account': 'legacy'} if header else {})
    assert response.status_code == 200 and response.json()['decks'] == [{'id': 41, 'title': 'Synthetic deck'}]
    assert fixture.calls == [('first', 'GET', '/v1/me'), ('first', 'GET', '/v1/decks')]
    assert fixture.store.status()['active'] == fixture.profiles['second']['id']
    assert fixture.client.get('/api/lexirise/settings').status_code == 200
    assert fixture.calls[-1] == ('second', 'GET', '/v1/settings')


def test_export_and_settings_write_remain_pinned_to_original_account(pinned_api):
    fixture = pinned_api
    fixture.service.pin().configure_game_deck('cyberpunk', 41)
    fixture.calls.clear()
    fixture.switch.append(fixture.profiles['second']['id'])
    first_headers = {'X-Proxy-Transcript': 'lexirise',
                     'X-Proxy-Transcript-Account': fixture.profiles['first']['id']}
    response = fixture.client.post('/api/lines/1/lexirise', json={}, headers=first_headers)
    assert response.status_code == 200 and response.json()['sent']
    assert fixture.calls and {owner for owner, _, _ in fixture.calls} == {'first'}
    assert ('first', 'POST', '/v1/vocabulary') in fixture.calls
    assert ('first', 'POST', '/v1/decks/41/items') in fixture.calls
    assert fixture.service.status()['sent'] == {}  # The second profile has no first-profile markers.
    fixture.store.select(fixture.profiles['first']['id'])
    assert fixture.service.status()['sent'] == {'line:1': 41}
    fixture.calls.clear()
    fixture.switch.append(fixture.profiles['second']['id'])
    assert fixture.client.patch('/api/lexirise/settings', json={'global': {'interfaceLanguage': 'en'}},
                                headers=first_headers).status_code == 200
    assert fixture.calls == [('first', 'PATCH', '/v1/settings')]
