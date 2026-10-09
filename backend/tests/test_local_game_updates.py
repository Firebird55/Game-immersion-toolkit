import json
from types import SimpleNamespace

from backend.local_game import LocalGameTextIndex
from backend.local_game_updates import LocalGameUpdateManager


def test_failed_or_interrupted_index_refresh_keeps_previous_snapshot(tmp_path, monkeypatch):
    import backend.local_game_updates as module
    import backend.cyberpunk_assets as assets
    payload = {"format": 1, "install": str(tmp_path), "fingerprint": "old", "records": [{
        "text_id": "cyberpunk:1:female", "english": "Stay close!", "chinese": "跟紧我！", "audio": {"depot": "a.wem"}}]}
    path = tmp_path / "textmap.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    index = LocalGameTextIndex("cyberpunk", tmp_path)
    voices = SimpleNamespace(reload=lambda: None)
    updater = LocalGameUpdateManager("cyberpunk", index, voices)
    monkeypatch.setattr(module, "discover_install", lambda _: tmp_path)
    monkeypatch.setattr(assets, "fingerprint", lambda _: "new")
    def fail(*_):
        raise RuntimeError("Steam is updating")
    monkeypatch.setattr(assets, "index_install", fail)
    updater._run()
    assert updater.status()["state"] == "retrying"
    assert json.loads(path.read_text())["fingerprint"] == "old"
    assert index.match_lines(["Stay close!"]).text_id == "cyberpunk:1:female"
    monkeypatch.setattr(assets, "index_install", lambda *_: {**payload, "records": [{"unexpected": "bad"}]})
    updater._run()
    assert json.loads(path.read_text())["fingerprint"] == "old"
