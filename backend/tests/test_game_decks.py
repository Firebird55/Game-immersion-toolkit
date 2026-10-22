import json
from pathlib import Path

import httpx
import pytest

from backend.lexirise import LexiriseError, LexiriseService


def test_explicit_deck_creation_is_repeatable_and_account_scoped(tmp_path):
    decks, creates = [], []
    def respond(request):
        if request.url.path == "/v1/me":
            return httpx.Response(200, json={"user": {"id": "test-account"}})
        if request.method == "GET":
            return httpx.Response(200, json={"success": True, "decks": decks})
        body = json.loads(request.content)
        assert body["language"] == "zh" and body["unit_type"] == "sentence"
        assert body["deck_type"] == "snapshot" and body["import_items"] == []
        creates.append(body)
        deck = {**body, "id": 2100 + len(decks), "owner_user_id": "test-account"}
        decks.append(deck)
        return httpx.Response(200, json={"success": True, "deck": deck})
    service = LexiriseService(tmp_path, transport=httpx.MockTransport(respond), api_key="test-key")
    assert "wwm" not in service.status()["decks"]
    first = service.ensure_game_decks()
    assert first == service.ensure_game_decks()
    assert len(creates) == 9
    assert service.status()["decks"]["cyberpunk"]["id"] == 2103
    assert service.status()["decks"]["wuwa"]["id"] == 2104
    assert service.status()["decks"]["witcher3"]["id"] == 2105
    assert service.status()["decks"]["nte"]["id"] == 2106
    assert service.status()["decks"]["heavyrain"]["id"] == 2108
    assert "honkai3" not in service.status()["decks"]
    other = LexiriseService(tmp_path, api_key="other-test-key")
    assert "wwm" not in other.status()["decks"]


def test_export_without_new_deck_has_safe_error_and_releases_lock(tmp_path):
    service = LexiriseService(tmp_path, api_key="test-key")
    for _ in range(2):
        with pytest.raises(LexiriseError, match="deck has not been configured"):
            service.send(ref="line:1", game="wwm", chinese="你好", english="Hello", speaker="",
                         audio=Path("missing"))
    assert not service._lock.locked()

def test_single_game_provisioning_reuses_owned_deck_and_verifies_readback(tmp_path):
    decks=[];writes=[]
    def reply(request):
        if request.url.path=='/v1/me':return httpx.Response(200,json={'user':{'id':'me'}})
        if request.method=='POST':
            writes.append(request.url.path);decks.append({**json.loads(request.content),'id':42,'owner_user_id':'me'})
            return httpx.Response(200,json={'deck':decks[0]})
        if request.url.path=='/v1/decks':return httpx.Response(200,json={'decks':decks})
        return httpx.Response(200,json={'deck':decks[0]})
    service=LexiriseService(tmp_path,api_key='test',transport=httpx.MockTransport(reply))
    assert service.configure_game_deck('zzz')==service.configure_game_deck('zzz')
    assert writes==['/v1/decks'] and service.status()['decks']['zzz']['id']==42

def test_destination_api_requires_explicit_action_and_guard_header(monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from backend import api
    writes=[]
    service=SimpleNamespace(available_decks=lambda:[],configure_game_deck=lambda game,deck_id:writes.append((game,deck_id)),status=lambda:{'configured':True,'decks':{},'sent':{}})
    monkeypatch.setattr(api,'runtime',SimpleNamespace(lexirise=service),raising=False)
    client=TestClient(api.app, base_url="http://127.0.0.1:8766");headers={'X-Proxy-Transcript':'lexirise'}
    assert client.get('/api/lexirise/decks').status_code==200 and writes==[]
    assert client.post('/api/lexirise/decks',json={'game':'zzz','create':True}).status_code==403
    for payload in [{'game':'zzz'},{'game':'zzz','deck_id':True},{'game':'zzz','create':True,'deck_id':42}]:
        assert client.post('/api/lexirise/decks',headers=headers,json=payload).status_code==422
    assert writes==[]
    assert client.post('/api/lexirise/decks',headers=headers,json={'game':'zzz','deck_id':42}).status_code==200
    assert writes==[('zzz',42)]
