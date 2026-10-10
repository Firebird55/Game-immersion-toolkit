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
    assert len(creates) == 6
    assert service.status()["decks"]["cyberpunk"]["id"] == 2103
    assert service.status()["decks"]["wuwa"]["id"] == 2104
    assert service.status()["decks"]["witcher3"]["id"] == 2105
    other = LexiriseService(tmp_path, api_key="other-test-key")
    assert "wwm" not in other.status()["decks"]


def test_export_without_new_deck_has_safe_error_and_releases_lock(tmp_path):
    service = LexiriseService(tmp_path, api_key="test-key")
    for _ in range(2):
        with pytest.raises(LexiriseError, match="deck has not been configured"):
            service.send(ref="line:1", game="wwm", chinese="你好", english="Hello", speaker="",
                         audio=Path("missing"))
    assert not service._lock.locked()
