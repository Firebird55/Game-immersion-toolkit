import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import api
from backend.config import SettingsStore
from backend.game_paths import load_paths, save_install
from backend.installation import InstallationService
from backend.tests.test_game_paths import make_game


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    root = tmp_path / "toolkit"
    root.mkdir()
    (root / "package.json").write_text('{"version":"0.0.0"}', encoding="utf-8")
    settings = SettingsStore(tmp_path / "local/Proxy Transcript/settings.json")
    refreshes = []
    installs = {}
    service = InstallationService(root, settings=settings, game_state=lambda game: {
        "index_ready": True, "audio_ready": False, "indexed_lines": 3,
        "index_message": "private transcript marker", "update_message": str(tmp_path / "private"),
        "update_state": "idle"}, refresh=refreshes.append, account_configured=lambda: True,
        install_lookup=lambda game: installs.get(game))
    runtime = SimpleNamespace(installation=service, refresh_game=refreshes.append,
        setup_install=lambda game: installs.get(game), capture=SimpleNamespace(start=lambda: refreshes.append("capture")))
    monkeypatch.setattr(api, "runtime", runtime, raising=False)
    return service, settings, refreshes, installs


def test_setup_completion_preserves_capture_calibration_and_creates_only_per_pc_preferences(setup):
    service, settings, _, _ = setup
    before = settings.get().model_dump()
    assert service.status()["completed"] is False
    service.complete(False)
    after = settings.get().model_dump()
    assert {key: value for key, value in before.items() if key != "auto_start"} == {
        key: value for key, value in after.items() if key != "auto_start"}
    assert service.path.parent.name == "Proxy Transcript"
    assert json.loads(service.path.read_text())["completed"]


def test_support_report_has_no_paths_account_details_errors_or_transcript_text(setup, tmp_path):
    service, _, _, installs = setup
    root = make_game(tmp_path, "zzz")
    save_install("zzz", root)
    installs["zzz"] = root
    snapshot = service.status()
    assert snapshot["games"][0]["configured_path"] == str(root)
    report = json.dumps(service.report())
    assert str(tmp_path) not in report
    assert "private transcript marker" not in report
    assert "lexirise" not in report
    assert "index_message" not in report


def test_setup_mutations_need_local_host_origin_and_explicit_action_header(setup, tmp_path):
    _, _, refreshes, _ = setup
    root = make_game(tmp_path, "hito")
    client = TestClient(api.app, base_url="http://127.0.0.1:8766")
    path = "/api/setup/games/hito"
    assert client.post(path, json={"path": str(root)}).status_code == 403
    headers = {"X-Proxy-Transcript": "setup", "Origin": "https://example.test"}
    assert client.post(path, headers=headers, json={"path": str(root)}).status_code == 403
    headers = {"X-Proxy-Transcript": "setup", "Origin": "http://localhost:3000"}
    assert client.post(path, headers={**headers, "Host": "example.test"}, json={"path": str(root)}).status_code == 403
    assert client.post(path, headers=headers, json={"path": str(root)}).status_code == 200
    assert load_paths()["hito"] == str(root)
    assert refreshes == ["hito"]


def test_bad_path_or_conflicting_folder_action_preserves_existing_settings(setup, tmp_path):
    _, _, _, _ = setup
    root = make_game(tmp_path, "hito")
    save_install("hito", root)
    client = TestClient(api.app, base_url="http://127.0.0.1:8766")
    headers = {"X-Proxy-Transcript": "setup"}
    for payload in ({"path": str(tmp_path)}, {"path": str(root), "use_automatic": True}, {},
                    {"path": str(root), "unexpected": True}, {"use_automatic": "yes"}):
        assert client.post("/api/setup/games/hito", headers=headers, json=payload).status_code in {400, 422}
        assert load_paths()["hito"] == str(root)
    assert client.post("/api/setup/games/hito", headers=headers, json={"use_automatic": True}).status_code == 200
    assert "hito" not in load_paths()


def test_tools_run_in_background_and_duplicate_preparation_is_rejected(setup, monkeypatch):
    service, _, _, _ = setup
    working, finish = threading.Event(), threading.Event()
    def prepare(*_args):
        working.set()
        assert finish.wait(2)
    monkeypatch.setattr("backend.installation.prepare_tools", prepare)
    monkeypatch.setattr("backend.installation.missing_tools", lambda *_: [])
    assert service.prepare("zzz")
    assert working.wait(1)
    try:
        assert not service.prepare("pragmata")
        assert service.status()["jobs"]["zzz"]["state"] == "preparing"
    finally:
        finish.set()
        service._tool_thread.join(2)
    assert service.status()["jobs"]["zzz"]["state"] == "ready"


def test_tool_download_failure_is_recoverable_and_does_not_expose_raw_errors(setup, monkeypatch):
    service, _, _, _ = setup
    def failed(*_args):
        raise OSError("private transcript marker")
    monkeypatch.setattr("backend.installation.prepare_tools", failed)
    service._prepare("zzz")
    job = service.status()["jobs"]["zzz"]
    assert job["state"] == "error"
    assert "private transcript marker" not in job["message"]


def test_native_key_prompt_passes_no_credential_to_subprocess_or_browser(setup, monkeypatch):
    service, _, _, _ = setup
    launched = []
    class Process:
        def poll(self):
            return 0
        def wait(self):
            return 0
    monkeypatch.setattr("backend.installation.sys.platform", "win32")
    monkeypatch.setattr("backend.installation.subprocess.Popen", lambda args, **kwargs: launched.append((args, kwargs)) or Process())
    assert service.launch_native("lexirise")
    assert launched[0][0][-2:] == ["-m", "scripts.set_lexirise_key"]
    assert "stdin" not in launched[0][1]
    assert "env" not in launched[0][1]


def test_manual_refresh_dispatches_only_the_selected_game(setup, tmp_path, monkeypatch):
    _, _, refreshes, installs = setup
    installs["hito"] = make_game(tmp_path, "hito")
    monkeypatch.setattr("backend.game_tools.missing_tools", lambda *_: [])
    client = TestClient(api.app, base_url="http://127.0.0.1:8766")
    response = client.post("/api/setup/games/hito/refresh", headers={"X-Proxy-Transcript": "setup"}, json={})
    assert response.status_code == 200
    assert refreshes == ["hito"]
    assert client.post("/api/setup/games/unknown/refresh", headers={"X-Proxy-Transcript": "setup"}, json={}).status_code == 404
