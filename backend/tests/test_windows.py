from backend.models import AppSettings
from backend.windows import WindowInfo, find_game_window
import pytest


def test_title_match_cannot_capture_browser_when_game_executable_is_configured(monkeypatch):
    browser = WindowInfo(1, "Zenless Zone Zero notes", "chrome.exe", (0, 0, 100, 100))
    monkeypatch.setattr("backend.windows.list_visible_windows", lambda: [browser])
    assert find_game_window(AppSettings()) is None


def test_game_executable_still_wins_regardless_of_title(monkeypatch):
    game = WindowInfo(2, "ZenlessZoneZero", "ZenlessZoneZero.exe", (0, 0, 100, 100))
    monkeypatch.setattr("backend.windows.list_visible_windows", lambda: [game])
    assert find_game_window(AppSettings()) == game


def test_title_fallback_remains_available_when_explicitly_configured(monkeypatch):
    custom = WindowInfo(3, "Custom capture target", "unknown.exe", (0, 0, 100, 100))
    monkeypatch.setattr("backend.windows.list_visible_windows", lambda: [custom])
    settings = AppSettings(process_names=[], window_title_contains=["Custom capture"])
    assert find_game_window(settings) == custom


@pytest.mark.parametrize("game,process", [("nte", "HTGame.exe")])
def test_new_games_require_actual_game_process_instead_of_browser_or_launcher_title(monkeypatch, game, process):
    from backend.windows import find_active_game_window
    from backend.games import GAME_PROFILES
    browser = WindowInfo(1, "NTE Honkai Impact 3rd", "chrome.exe", (0,0,1920,1080))
    launcher = WindowInfo(2, "NTE Honkai Impact 3rd", "NTEGlobalLauncher.exe", (0,0,1920,1080))
    monkeypatch.setattr("backend.windows.list_visible_windows", lambda: [browser, launcher])
    assert find_active_game_window(AppSettings(preferred_game=game)) is None
    actual = WindowInfo(3, "Game", process, (0,0,1920,1080))
    monkeypatch.setattr("backend.windows.list_visible_windows", lambda: [browser, launcher, actual])
    assert find_active_game_window(AppSettings(preferred_game=game)) == (GAME_PROFILES[game], actual)
