from backend.models import AppSettings
from backend.windows import WindowInfo, find_game_window
import pytest


def test_monitor_lookup_preserves_large_handles_and_negative_physical_coordinates(monkeypatch):
    from types import SimpleNamespace
    from backend import windows
    import ctypes
    window_handle, monitor_handle = 0x1_12345678, 0x2_12345678
    def find(hwnd, flags):
        assert hwnd == window_handle and flags == 0
        return monitor_handle
    def info(handle, pointer):
        assert handle == monitor_handle
        value = pointer._obj
        assert value.cbSize == ctypes.sizeof(windows._MonitorInfoEx)
        value.rcMonitor.left, value.rcMonitor.top = -3840, -240
        value.rcMonitor.right, value.rcMonitor.bottom = 0, 1920
        value.szDevice = 'Secondary display'
        return True
    monkeypatch.setattr(windows, 'user32', SimpleNamespace(MonitorFromWindow=find, GetMonitorInfoW=info), raising=False)
    assert windows.monitor_for_window(window_handle) == windows.MonitorInfo('Secondary display', (-3840, -240, 3840, 2160))
    monkeypatch.setattr(windows.user32, 'MonitorFromWindow', lambda *_: 0)
    assert windows.monitor_for_window(window_handle) is None


def test_windows_native_handles_have_pointer_sized_signatures():
    import sys
    if sys.platform != 'win32':
        pytest.skip('Windows ABI verification requires Windows')
    import ctypes
    from backend import windows
    assert ctypes.sizeof(windows.kernel32.OpenProcess.restype) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(windows.user32.MonitorFromWindow.restype) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(windows.user32.GetClientRect.argtypes[0]) == ctypes.sizeof(ctypes.c_void_p)


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


def test_shared_valve_executable_requires_its_verified_installation(tmp_path, monkeypatch):
    from backend.windows import find_active_game_window
    portal = WindowInfo(40, 'Half-Life 2', 'hl2.exe', (0, 0, 1920, 1080))
    half = WindowInfo(41, 'Portal', 'hl2.exe', (0, 0, 1920, 1080))
    installs = {game: tmp_path / game for game in ('portal', 'halflife2')}
    paths = {40: installs['portal'] / 'hl2.exe', 41: installs['halflife2'] / 'hl2.exe'}
    monkeypatch.setattr('backend.game_paths.discover_install', installs.get)
    monkeypatch.setattr('backend.windows.executable_path_for_window', lambda window: paths.get(window.handle))
    monkeypatch.setattr('backend.windows.list_visible_windows', lambda: [portal, half])
    assert find_active_game_window(AppSettings(preferred_game='portal'))[1] == portal
    assert find_active_game_window(AppSettings(preferred_game='halflife2'))[1] == half
    paths.clear()
    assert find_active_game_window(AppSettings(preferred_game='portal')) is None


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
