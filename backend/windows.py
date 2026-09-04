from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .models import AppSettings


@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    process_name: str
    bounds: tuple[int, int, int, int]


if sys.platform == "win32":
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _process_path_for_window(hwnd: int) -> str:
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


def game_data_directory(settings: AppSettings) -> Path | None:
    window = find_game_window(settings)
    if window:
        executable = _process_path_for_window(window.handle)
        if executable:
            folder = Path(executable).parent/'ZenlessZoneZero_Data'
            if folder.is_dir():
                return folder
    return None


def _window_bounds(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = wintypes.RECT()
    try:
        dwmapi = ctypes.windll.dwmapi
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


def list_visible_windows() -> list[WindowInfo]:
    if sys.platform != "win32":
        return []
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
            )
        )
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return windows


def find_game_window(settings: AppSettings) -> WindowInfo | None:
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
