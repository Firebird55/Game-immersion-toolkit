import json
from pathlib import Path

import httpx
import pytest

from backend.lexirise import LexiriseError, LexiriseService


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.items = []
        self.decks = {1950: [], 1951: []}
        self.fail_after_add = False

    def __call__(self, request):
        self.calls.append((request.method, request.url.path))
        assert request.headers['Authorization'] == 'Bearer test-key'
        path = request.url.path
        if path == '/v1/vocabulary/audio':
            assert b'voice.mp3' in request.content
            return httpx.Response(200, json={'publicUrl': 'https://audio.lexirise.test/voice.mp3'})
        if path == '/v1/vocabulary':
            if request.method == 'POST':
                data = json.loads(request.content)
                assert data['language'] == 'zh' and data['mode'] == 'sentence'
                item = {'id': len(self.items) + 100, 'expression_text': data['text'], 'audio_urls': data['audioUrls']}
                self.items.append(item)
                return httpx.Response(200, json={'result': 'created', 'item': item})
            return httpx.Response(200, json={'items': self.items, 'nextOffset': None})
        if path.startswith('/v1/vocabulary/'):
            return httpx.Response(200, json={'id': 100})
        if path.startswith('/v1/decks/'):
            deck_id = int(path.split('/')[3])
            if request.method == 'POST':
                payload = json.loads(request.content)
                vid = payload['saved_expression_selection']['ids'][0]
                self.decks[deck_id].append(next(i for i in self.items if i['id'] == vid))
                if self.fail_after_add:
                    self.fail_after_add = False
                    raise httpx.ReadTimeout('lost response with sensitive information', request=request)
                return httpx.Response(200, json={'success': True, 'added_count': 1})
            return httpx.Response(200, json={'success': True, 'deck': {'lang': 'zh', 'unit_type': 'sentence', 'deck_type': 'snapshot'},
                                            'items': self.decks[deck_id], 'hasMore': False})
        raise AssertionError(path)


def fixture(tmp_path):
    api = FakeAPI()
    service = LexiriseService(tmp_path / 'lexirise', transport=httpx.MockTransport(api), api_key='test-key')
    audio = tmp_path / 'voice.mp3'
    audio.write_bytes(b'test audio bytes')
    kwargs = dict(ref='line:1', game='pragmata', chinese='你好。', english='Hello.', speaker='Ken', audio=audio)
    return api, service, kwargs


def test_both_games_route_to_separate_decks(tmp_path):
    api, service, kwargs = fixture(tmp_path)
    assert service.send(**kwargs)['deck_id'] == 1951
    kwargs.update(ref='line:2', game='zzz')
    assert service.send(**kwargs)['deck_id'] == 1950
    assert len(api.decks[1950]) == len(api.decks[1951]) == 1
    assert len(api.items) == 1  # Shared vocabulary, independent deck membership.


def test_repeat_and_restart_deduplicate_even_if_history_id_changes(tmp_path):
    api, service, kwargs = fixture(tmp_path)
    service.send(**kwargs)
    count = len(api.calls)
    restarted = LexiriseService(service.directory, transport=service.transport, api_key='test-key')
    kwargs['ref'] = 'line:999'
    kwargs['audio'].unlink()  # Already exported: local retention doesn't matter.
    assert restarted.send(**kwargs)['already_sent']
    assert len(api.calls) == count
    assert restarted.status()['sent'] == {'line:1': 1951, 'line:999': 1951}
    assert 'test-key' not in json.dumps(restarted.status())
    assert b'test-key' not in restarted.db_path.read_bytes()


def test_lost_deck_response_resumes_without_duplicate_upload_or_card(tmp_path):
    api, service, kwargs = fixture(tmp_path)
    api.fail_after_add = True
    with pytest.raises(LexiriseError, match='Could not confirm'):
        service.send(**kwargs)
    assert service.status()['sent'] == {}
    assert service.send(**kwargs)['sent']
    assert len(api.decks[1951]) == 1
    assert api.calls.count(('POST', '/v1/vocabulary/audio')) == 1
    assert api.calls.count(('POST', '/v1/vocabulary')) == 1


def test_existing_notes_and_proficiency_are_not_overwritten(tmp_path):
    api, service, kwargs = fixture(tmp_path)
    api.items = [{'id': 100, 'expression_text': kwargs['chinese'], 'audio_urls': [], 'notes': 'my notes', 'proficiency': 4}]
    service.send(**kwargs)
    assert ('POST', '/v1/vocabulary') not in api.calls
    assert ('PATCH', '/v1/vocabulary/100') in api.calls


def test_wrong_deck_type_fails_before_upload(tmp_path):
    _, service, kwargs = fixture(tmp_path)
    calls = []
    def wrong(request):
        calls.append(request.method)
        return httpx.Response(200, json={'deck': {'lang': 'zh', 'unit_type': 'word', 'deck_type': 'snapshot'}})
    service.transport = httpx.MockTransport(wrong)
    with pytest.raises(LexiriseError, match='sentence snapshot'):
        service.send(**kwargs)
    assert calls == ['GET']


def test_rate_limit_is_safe_and_missing_audio_does_not_upload(tmp_path):
    _, service, kwargs = fixture(tmp_path)
    service.transport = httpx.MockTransport(lambda _: httpx.Response(429, text='secret key test-key'))
    with pytest.raises(LexiriseError, match='request limit') as err:
        service.send(**kwargs)
    assert 'test-key' not in str(err.value)
    kwargs['audio'] = Path('missing-audio.mp3')
    with pytest.raises(LexiriseError, match='missing'):
        service.send(**kwargs)


def test_api_uses_stored_game_and_requires_browser_header(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from backend import api
    from backend.models import TranscriptLine
    line = TranscriptLine(id=1, created_at=datetime.now(timezone.utc), session_id='test', game='pragmata',
        source_ocr='Hello.', english='Hello.', chinese='你好。', text_id='test', score=100,
        match_kind='exact', voiced=True, has_audio=True)
    sent = []
    def send(**kwargs):
        sent.append(kwargs)
        return {'sent': True, 'deck_id': 1951}
    runtime = SimpleNamespace(transcript=SimpleNamespace(get=lambda _: line, audio_path=lambda _: 'voice.mp3'),
                              speakers=SimpleNamespace(enrich=lambda x: x), lexirise=SimpleNamespace(send=send))
    monkeypatch.setattr(api, 'runtime', runtime, raising=False)
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path)
    client = TestClient(api.app)  # No lifespan: never start real capture in tests.
    assert client.post('/api/lines/1/lexirise').status_code == 403
    assert client.post('/api/lines/1/lexirise', headers={'X-Proxy-Transcript': 'lexirise'},
                       json={'game': 'zzz', 'audio': 'C:/private/file'}).status_code == 200
    assert sent[0]['game'] == 'pragmata'
    assert sent[0]['audio'] == (tmp_path / 'audio/voice.mp3').resolve()
    line.voiced = False
    assert client.post('/api/lines/1/lexirise', headers={'X-Proxy-Transcript': 'lexirise'}).status_code == 409
    assert len(sent) == 1
