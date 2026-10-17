from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.lexirise import LexiriseError, LexiriseService
from backend.reading import LexiriseReadingService


def test_empty_context_is_retried_instead_of_cached_for_a_month(tmp_path):
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={'meaning': '' if len(requests) == 1 else 'A useful answer'})
    reader = LexiriseReadingService(tmp_path, LexiriseService(tmp_path, api_key='mock', transport=httpx.MockTransport(reply)))
    reader.analyze = lambda text: {'tokens': [{'start': 0, 'end': 2}]}
    reader._save('context', '你好:0:Is this polite?', {'meaning': ''})
    try:
        with pytest.raises(LexiriseError, match='no answer'):
            reader.context('你好', 0, 'Is this polite?')
        assert reader.context('你好', 0, 'Is this polite?')['meaning'] == 'A useful answer'
        assert reader.context('你好', 0, 'Is this polite?')['meaning'] == 'A useful answer'
        assert len(requests) == 2
        assert requests[0].extensions['timeout']['read'] == 120
    finally:
        reader.pool.shutdown(wait=True)


def test_context_question_roundtrip_reports_service_errors(monkeypatch):
    from backend import api
    calls = []
    def context(text, start, question=None):
        calls.append((text, start, question))
        if question == 'Try again':
            raise LexiriseError('Lexirise returned no answer. Please ask again.')
        return {'meaning': 'A useful answer'}
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(
        transcript=SimpleNamespace(get=lambda _: SimpleNamespace(chinese='你好',source_text='你好')),
        reading=SimpleNamespace(context=context)), raising=False)
    client = TestClient(api.app)
    headers = {'X-Proxy-Transcript': 'lexirise', 'X-Reader-Action': 'lexirise'}
    body = {'start': 0, 'question': ' Is this polite? '}
    assert client.post('/api/lines/1/reading/context', json=body).status_code == 403
    response = client.post('/api/lines/1/reading/context', headers=headers, json=body)
    assert response.status_code == 200 and response.json()['meaning'] == 'A useful answer'
    assert calls == [('你好', 0, 'Is this polite?')]
    response = client.post('/api/lines/1/reading/context', headers=headers, json={**body, 'question': 'Try again'})
    assert response.status_code == 503 and 'no answer' in response.json()['detail']
