import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.accounts import AccountStore
from backend.lexirise import LexiriseError, LexiriseService
from backend.lexirise_settings import account_settings
from backend.languages import translation_language, resolve_locale, normalize_text
from backend.reading import LexiriseReadingService


def protected(data, decrypt=False):
    return bytes(value ^ 173 for value in data)


def profile_store(tmp_path):
    calls = []
    def reply(request):
        calls.append((request.method, request.url.path))
        owner = 'second' if 'second' in request.headers['authorization'] else 'first'
        return httpx.Response(200, json={'user': {'id': owner, 'name': owner}})
    return AccountStore(tmp_path / 'accounts.dpapi', protect=protected, transport=httpx.MockTransport(reply)), calls


def test_verified_profiles_are_protected_and_status_contains_no_credentials(tmp_path):
    store, calls = profile_store(tmp_path)
    key = 'lx_first_fixture_credential_only'
    first = store.add(key)
    second = store.add('lx_second_fixture_credential_only')
    assert calls == [('GET', '/v1/me'), ('GET', '/v1/me')]
    assert key.encode() not in store.path.read_bytes()
    assert key not in json.dumps(store.status())
    assert store.active_key().startswith('lx_second')
    store.select(first['id'])
    assert store.active_key() == key
    pinned = LexiriseService(tmp_path / 'service', accounts=store).pin('nl')
    store.select(second['id'])
    assert pinned._key() == key
    assert pinned.source_language == 'nl'
    store.remove(second['id'])
    assert store.status()['active'] == 'legacy'


def test_failed_identity_never_replaces_a_working_profile(tmp_path):
    store, _ = profile_store(tmp_path)
    store.add('lx_first_fixture_credential_only')
    before = store.path.read_bytes()
    store.transport = httpx.MockTransport(lambda _: httpx.Response(401))
    with pytest.raises(LexiriseError, match='rejected'):
        store.add('lx_invalid_fixture_credential_only')
    assert store.path.read_bytes() == before


def test_each_learning_language_resolves_its_own_target_and_never_falls_back_to_english(tmp_path):
    settings = {'languages': ['nl', 'de'], 'global': {'effectiveTranslationLanguage': 'en'},
                'languageSettings': {'nl': {'effectiveTranslationLanguage': 'zh-hans'},
                                     'de': {'effectiveTranslationLanguage': 'nl'}}}
    assert translation_language(settings, 'nl') == 'zh-hans'
    assert translation_language(settings, 'de') == 'nl'
    assert translation_language(settings, 'ja') == 'en'
    assert resolve_locale('zh-hant', ['en', 'zh-Hans']) is None
    assert resolve_locale('pt', ['pt-PT', 'pt-BR']) == 'pt-BR'
    assert resolve_locale('pt', ['pt-PT']) == 'pt-PT'
    assert normalize_text('안녕하세요', 'ko')
    assert normalize_text('Счастливого пути!', 'ru')
    service = LexiriseService(tmp_path, api_key='fixture')
    reader = LexiriseReadingService(tmp_path, service.pin('nl'), source_language='nl', translation_language='zh-hans')
    try:
        assert reader._translations({'translations': [{'target_lang': 'en', 'translation': 'hello'}]}) == []
        assert reader._translations({'translations': [{'target_lang': 'zh-hans', 'translation': '你好'}]})[0]['translation'] == '你好'
    finally:
        reader.pool.shutdown(wait=True)


def test_settings_cache_and_deck_destinations_are_pinned_to_account_and_language(tmp_path):
    store, _ = profile_store(tmp_path)
    first = store.add('lx_first_fixture_credential_only')
    service = LexiriseService(tmp_path / 'service', accounts=store, transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={'languages': ['nl'], 'global': {'effectiveTranslationLanguage': 'en'},
            'languageSettings': {'nl': {'effectiveTranslationLanguage': 'zh-hans'}}})))
    pinned = service.pin('nl')
    account_settings(pinned)
    assert service.pin('nl')._settings_payload['languageSettings']['nl']['effectiveTranslationLanguage'] == 'zh-hans'
    with pinned._connect() as db:
        db.execute('INSERT INTO game_decks VALUES (?,?,?,?)', (pinned._scope(), 'cyberpunk', 42, 'Dutch game'))
    assert service.pin('nl').status()['decks']['cyberpunk']['id'] == 42
    assert service.pin('zh').status()['decks'] == {}
    store.add('lx_second_fixture_credential_only')
    assert not hasattr(service.pin('nl'), '_settings_payload')
    assert service.pin('nl').status()['decks'] == {}
    store.select(first['id'])
    assert service.pin('nl').status()['decks']['cyberpunk']['id'] == 42


def test_stale_account_requests_cannot_read_or_write_with_new_credentials(tmp_path, monkeypatch):
    from backend import api
    store, _ = profile_store(tmp_path)
    first = store.add('lx_first_fixture_credential_only')
    service = LexiriseService(tmp_path / 'service', accounts=store)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(accounts=store, lexirise=service), raising=False)
    store.add('lx_second_fixture_credential_only')
    client = TestClient(api.app)
    for method, path, body in [('GET', '/api/lines/1/reading', None),
                               ('POST', '/api/lines/1/lexirise', {}),
                               ('PATCH', '/api/lexirise/settings', {})]:
        response = client.request(method, path, json=body,
            headers={'X-Proxy-Transcript-Account': first['id'], 'X-Proxy-Transcript': 'lexirise'})
        assert response.status_code == 409
    assert client.post('/api/lexirise/accounts/select', json={'id': first['id']}).status_code == 403


def test_account_selection_invalidates_a_pending_native_scan(tmp_path, monkeypatch):
    from backend import api
    store, _ = profile_store(tmp_path)
    first = store.add('lx_first_fixture_credential_only')
    store.add('lx_second_fixture_credential_only')
    events = []
    async def broadcast(event):
        events.append(event)
    capture = SimpleNamespace(_scan_epoch=7)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(accounts=store, capture=capture,
        hub=SimpleNamespace(broadcast=broadcast)), raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8766')
    response = client.post('/api/lexirise/accounts/select', json={'id': first['id']},
                           headers={'X-Proxy-Transcript': 'lexirise'})
    assert response.status_code == 200 and capture._scan_epoch == 8
    assert events == [{'type': 'account_changed', 'account': first['id']}]
