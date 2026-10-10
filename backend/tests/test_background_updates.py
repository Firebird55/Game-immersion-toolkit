from __future__ import annotations

import json
import pytest

from backend.textmaps import TextMapIndex
from backend.updates import BackgroundUpdateManager


class VoiceAssetsStub:
    def __init__(self, manifest):
        self.manifest = manifest
        self.reloaded = False

    def reload(self, _manifest):
        self.reloaded = True


def test_background_update_keeps_cached_interface_data_live(tmp_path, monkeypatch):
    maps = TextMapIndex(tmp_path / "data/textmaps")
    maps.data_dir.mkdir(parents=True)
    for name in maps.urls:
        maps.file_path(name).write_text("{}", encoding="utf-8")
    maps.ready = True
    manifest = tmp_path / "data/voice-assets/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"version": 1, "entries": {}}), encoding="utf-8")
    assets = VoiceAssetsStub(manifest)
    updates = BackgroundUpdateManager(tmp_path, maps, assets, game_data_provider=lambda: tmp_path)
    monkeypatch.setattr("backend.game_tools.missing_tools", lambda *_: [])
    monkeypatch.setattr(
        updates,
        "_update_metadata_repository",
        lambda: ("same-commit", False, "Upstream game metadata is current"),
    )
    monkeypatch.setattr(updates, "_run_command", lambda *args, **kwargs: "already current")
    updates.check_once()
    assert maps.ready is True
    assert assets.reloaded is True
    assert updates.status()["progress"] == 100
    assert updates.status()["state"] == "ready"


def test_fresh_install_without_zzz_does_not_download_unselected_game_data(tmp_path, monkeypatch):
    maps = TextMapIndex(tmp_path / "data/textmaps")
    manager = BackgroundUpdateManager(tmp_path, maps, VoiceAssetsStub(tmp_path / "manifest.json"),
                                      game_data_provider=lambda: None)
    monkeypatch.setattr(manager, "_update_metadata_repository", lambda: pytest.fail("Unexpected network operation"))
    manager.check_once()
    assert manager.status()["state"] == "waiting"
    assert not maps.data_dir.exists()
