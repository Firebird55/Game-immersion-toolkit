from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .models import AppSettings
from .games import GAME_PROFILES, GameProfile, ordered_profiles
from .steam_games import STEAM_GAMES


@dataclass(frozen=True, slots=True)
class MonitorInfo:
    name: str
    bounds: tuple[int, int, int, int]
    primary: bool = False


@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    process_name: str
    bounds: tuple[int, int, int, int]
    monitor: MonitorInfo | None = None


class _MonitorInfoEx(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD),
                ('szDevice', wintypes.WCHAR * 32)]


def _declare_windows_api(user, kernel):
    # ctypes otherwise assumes a 32-bit int return/argument. HWND, HMONITOR
    # and process handles must keep all pointer bits on 64-bit installations.
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    signatures = [
        (user, 'EnumWindows', [callback, wintypes.LPARAM], wintypes.BOOL),
        (user, 'IsWindowVisible', [wintypes.HWND], wintypes.BOOL),
        (user, 'IsIconic', [wintypes.HWND], wintypes.BOOL),
        (user, 'GetWindowTextLengthW', [wintypes.HWND], ctypes.c_int),
        (user, 'GetWindowTextW', [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        (user, 'GetClientRect', [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        (user, 'GetWindowRect', [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        (user, 'ClientToScreen', [wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
        (user, 'GetWindowThreadProcessId', [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        (user, 'MonitorFromWindow', [wintypes.HWND, wintypes.DWORD], wintypes.HANDLE),
        (user, 'GetMonitorInfoW', [wintypes.HANDLE, ctypes.POINTER(_MonitorInfoEx)], wintypes.BOOL),
        (kernel, 'OpenProcess', [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        (kernel, 'QueryFullProcessImageNameW', [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                              ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        (kernel, 'CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        (kernel, 'GetLogicalDrives', [], wintypes.DWORD),
    ]
    for library, name, args, result in signatures:
        function = getattr(library, name)
        function.argtypes, function.restype = args, result


if sys.platform == "win32":
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    _declare_windows_api(user32, kernel32)
    try:
        # Per-monitor V2 keeps client bounds and screenshots in physical pixels
        # when a window moves between displays with different Windows zoom.
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _process_path_for_window(hwnd: int) -> str:
    if sys.platform != 'win32':
        from .platform_windows import executable_path_for_handle
        return executable_path_for_handle(hwnd)
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    process = kernel32.OpenProcess(0x1000, False, process_id.value)
    if not process:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(process)


def _process_name_for_window(hwnd: int) -> str:
    return Path(_process_path_for_window(hwnd)).name


def executable_path_for_window(window: WindowInfo) -> Path | None:
    executable = _process_path_for_window(window.handle)
    return Path(executable) if executable else None


def game_data_directory(settings: AppSettings) -> Path | None:
    window = find_game_window(settings)
    if window:
        executable = _process_path_for_window(window.handle)
        if executable:
            folder = Path(executable).parent/'ZenlessZoneZero_Data'
            if folder.is_dir():
                return folder
    return None


def installed_zzz_game_data_directory(settings: AppSettings) -> Path | None:
    """Find the running game or a local Steam install after a drive move."""
    live = game_data_directory(settings)
    if live:
        return live
    from .game_paths import discover_install
    configured = discover_install("zzz")
    if configured:
        return configured / "ZenlessZoneZero_Data"
    if sys.platform != "win32":
        return None
    drives = kernel32.GetLogicalDrives()
    suffixes = (
        "SteamLibrary/steamapps/common/Zenless Zone Zero/games/ZenlessZoneZero Game/ZenlessZoneZero_Data",
        "Program Files (x86)/Steam/steamapps/common/Zenless Zone Zero/games/ZenlessZoneZero Game/ZenlessZoneZero_Data",
    )
    for index in range(2, 26):
        if not drives & (1 << index):
            continue
        for suffix in suffixes:
            candidate = Path(f"{chr(65 + index)}:/") / suffix
            try:
                if (candidate / "StreamingAssets").is_dir() or (candidate / "Persistent").is_dir():
                    return candidate
            except OSError:
                # A mounted but locked BitLocker volume is not an install.
                continue
    return None


def find_active_game_window(settings: AppSettings) -> tuple[GameProfile, WindowInfo] | None:
    candidates = list_visible_windows()
    by_process = {}
    for window in candidates:
        by_process.setdefault(window.process_name.casefold(), []).append(window)
    for profile in ordered_profiles(settings.preferred_game):
        for process_name in profile.process_names:
            for window in by_process.get(process_name.casefold(), []):
                if profile.id in STEAM_GAMES and sum(process_name.casefold() in
                        [name.casefold() for name in other.process_names] for other in GAME_PROFILES.values()) > 1:
                    # Portal and Half-Life 2 share hl2.exe. Never choose a reader
                    # from the preferred game or title when the executable is ambiguous.
                    from .game_paths import discover_install
                    install = discover_install(profile.id)
                    actual = executable_path_for_window(window)
                    expected = install / STEAM_GAMES[profile.id].executable if install else None
                    if actual is None or expected is None or actual.resolve() != expected.resolve():
                        continue
                if profile.id == "wuwa":
                    # This generic Unreal executable name is used by other games.
                    titled = any(name.casefold() in window.title.casefold() for name in profile.title_needles)
                    if not titled:
                        from .game_paths import discover_install
                        install = discover_install("wuwa")
                        actual = executable_path_for_window(window)
                        expected = install / "Client/Binaries/Win64/Client-Win64-Shipping.exe" if install else None
                        if actual is None or expected is None or actual.resolve() != expected.resolve():
                            continue
                return profile, window
    return None


def _window_bounds(hwnd: int) -> tuple[int, int, int, int] | None:
    # Windowed games have title bars/borders. OCR regions are relative to the
    # rendered client, just as in borderless/fullscreen mode. DPI awareness
    # above keeps both the client size and screen origin in physical pixels.
    client, origin = wintypes.RECT(), wintypes.POINT()
    try:
        if user32.GetClientRect(hwnd, ctypes.byref(client)) and user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            width, height = client.right - client.left, client.bottom - client.top
            if width > 0 and height > 0:
                return origin.x, origin.y, width, height
    except (AttributeError, OSError):
        pass
    rect = wintypes.RECT()
    try:
        dwmapi = ctypes.windll.dwmapi
        dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
        result = dwmapi.DwmGetWindowAttribute(
            hwnd,
            9,
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if result != 0:
            raise OSError(result)
    except (AttributeError, OSError):
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    return rect.left, rect.top, width, height


def monitor_for_window(hwnd: int) -> MonitorInfo | None:
    """Follow the display containing most of the game; never default to primary.

    Client capture still uses its full physical rectangle, including a game
    spanning two displays. This is identification, not a clipping rectangle.
    """
    handle = user32.MonitorFromWindow(hwnd, 0)  # MONITOR_DEFAULTTONULL
    if not handle:
        return None
    info = _MonitorInfoEx(cbSize=ctypes.sizeof(_MonitorInfoEx))
    if not user32.GetMonitorInfoW(handle, ctypes.byref(info)):
        return None
    rect = info.rcMonitor
    return MonitorInfo(info.szDevice, (rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top),
                       bool(info.dwFlags & 1))


def list_visible_windows() -> list[WindowInfo]:
    if sys.platform != "win32":
        from .platform_windows import list_visible_windows as platform_windows
        return platform_windows()
    windows: list[WindowInfo] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        bounds = _window_bounds(hwnd)
        if bounds is None:
            return True
        windows.append(
            WindowInfo(
                handle=int(hwnd),
                title=title_buffer.value,
                process_name=_process_name_for_window(hwnd),
                bounds=bounds,
                monitor=monitor_for_window(hwnd),
            )
        )
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return windows


def find_game_window(settings: AppSettings) -> WindowInfo | None:
    active = find_active_game_window(settings)
    if active is not None:
        return active[1]
    process_names = {name.casefold() for name in settings.process_names}
    title_needles = [needle.casefold() for needle in settings.window_title_contains]
    candidates = list_visible_windows()
    for window in candidates:
        if window.process_name.casefold() in process_names:
            return window
    # A browser tab, chat, or document can contain "Zenless Zone Zero" in its
    # title. When executable names are configured, never capture such a window
    # merely because the actual game is minimized.
    if process_names:
        return None
    for window in candidates:
        title = window.title.casefold()
        if any(needle in title for needle in title_needles):
            return window
    return None
