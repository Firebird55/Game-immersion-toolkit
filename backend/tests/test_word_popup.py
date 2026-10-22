import httpx
from fastapi.testclient import TestClient
from types import SimpleNamespace

from backend.lexirise import LexiriseService
from backend.reading import LexiriseReadingService


def test_popup_words_and_notes_read_dictionary_and_saved_vocabulary(tmp_path):
    calls = []
    def reply(request):
        calls.append((request.method, request.url.path))
        if request.url.path == '/v1/vocabulary/88':
            return httpx.Response(200, json={'notes': 'Remember this usage.'})
        return httpx.Response(200, json={'translations': [], 'characterInfo': {
            'char': '的', 'statistics': {'topWords': [{'word': '我的', 'gloss': 'my', 'share': .4}]}}})
    service = LexiriseService(tmp_path, api_key='test', transport=httpx.MockTransport(reply))
    reader = LexiriseReadingService(tmp_path, service)
    reader.analyze = lambda text: {'tokens': [{'start': 0, 'word': '的', 'pinyin': 'de',
                                             'zhuyin': '', 'tones': [5], 'proficiency': 4,
                                             'meaning': 'of', 'savedExpressionId': 88}]}
    try:
        assert reader.lookup('的', 0)['topWords'] == [{'word': '我的', 'trad': '', 'gloss': 'my', 'share': .4}]
        assert reader.notes('的', 0) == {'notes': 'Remember this usage.'}
        assert reader.notes('的', 1) is None
        assert calls == [('POST', '/v1/dictionary/lookup'), ('GET', '/v1/vocabulary/88')]
    finally:
        reader.pool.shutdown(wait=True)


def test_notes_endpoint_uses_only_the_selected_transcript_line(monkeypatch):
    from backend import api
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(
        transcript=SimpleNamespace(get=lambda line_id: SimpleNamespace(chinese='的',source_text='的') if line_id == 1 else None),
        reading=SimpleNamespace(notes=lambda text, start: {'notes': 'A saved note'} if text == '的' and start == 0 else None)), raising=False)
    client = TestClient(api.app, base_url="http://127.0.0.1:8766")
    assert client.get('/api/lines/1/reading/notes?start=0').json() == {'notes': 'A saved note'}
    assert client.get('/api/lines/1/reading/notes?start=1').status_code == 404
    assert client.get('/api/lines/2/reading/notes?start=0').status_code == 404
    assert client.get('/api/lines/1/reading/notes?start=-1').status_code == 422
