from backend.models import AppSettings
from backend.windows import WindowInfo, find_game_window


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
