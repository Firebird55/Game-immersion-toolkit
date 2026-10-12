from types import SimpleNamespace
from fastapi.testclient import TestClient
from backend import api


def test_mobile_export_endpoints_require_local_setup_access(monkeypatch):
    calls = []
    manager = SimpleNamespace(start=lambda game, audio, folder: calls.append((game, audio, folder)) or True,
                              cancel=lambda: calls.append("cancel"), status=lambda: {"state": "idle"})
    monkeypatch.setattr(api, "runtime", SimpleNamespace(mobile_exports=manager), raising=False)
    client = TestClient(api.app, base_url="http://127.0.0.1:8766")
    path = "/api/setup/games/zzz/mobile-export"
    assert client.post(path, json={}).status_code == 403
    headers = {"X-Proxy-Transcript": "setup", "Origin": "http://127.0.0.1:3000"}
    assert client.post(path, json={}, headers={**headers, "Origin": "https://example.com"}).status_code == 403
    assert client.post(path, json={}, headers={**headers, "Host": "example.com"}).status_code == 403
    assert client.post(path, json={"include_audio": False}, headers=headers).status_code == 200
    assert calls == [("zzz", False, None)]
    assert client.post(path, json={"output": "arbitrary"}, headers=headers).status_code == 422
    assert client.get("/api/setup/mobile-export").json()["state"] == "idle"
    assert client.post("/api/setup/mobile-export/cancel", headers=headers).status_code == 200
    assert calls[-1] == "cancel"


def test_export_folder_and_estimate_actions_keep_setup_protections(monkeypatch):
    calls = []
    manager = SimpleNamespace(start=lambda *a: calls.append(a) or True,
        preview=lambda *a: {'estimatedBytes': 1000}, browse=lambda *a: True)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(mobile_exports=manager), raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8766')
    headers = {'X-Proxy-Transcript': 'setup', 'Origin': 'http://127.0.0.1:3000'}
    paths = ['/api/setup/games/zzz/mobile-export/preview', '/api/setup/mobile-export/browse']
    for path in paths:
        assert client.post(path, json={}).status_code == 403
        assert client.post(path, json={}, headers={**headers, 'Origin': 'https://example.com'}).status_code == 403
        assert client.post(path, json={}, headers={**headers, 'Host': 'example.com'}).status_code == 403
        assert client.post(path, json={}, headers=headers).status_code == 200
    assert client.post('/api/setup/games/zzz/mobile-export', json={'destination_folder': 'test-folder'}, headers=headers).status_code == 200
    assert calls == [('zzz', True, 'test-folder')]
    manager.start = lambda *a: (_ for _ in ()).throw(ValueError('private path'))
    response = client.post('/api/setup/games/zzz/mobile-export', json={}, headers=headers)
    assert response.status_code == 400 and 'private path' not in response.text
