import ctypes
import sys
import threading
from types import SimpleNamespace

import pytest
from PIL import Image

from backend import window_capture
from backend.capture import CaptureService
from backend.windows import WindowInfo


def test_background_crops_use_one_client_frame_with_negative_origin(monkeypatch):
    service = object.__new__(CaptureService)
    service._window_frame = threading.local()
    window = WindowInfo(1, 'fixture', 'game.exe', (-1920, 150, 1280, 720))
    frame = Image.new('RGB', (1280, 720), 'green')
    frame.paste('red', (100, 500, 200, 600))
    calls = []
    monkeypatch.setattr('backend.capture.background_frame', lambda w: calls.append(w) or frame)
    monkeypatch.setattr('backend.capture.mss.mss', lambda: pytest.fail('Background capture read desktop pixels'))
    service._prepare_window_capture(window)
    crop = service._capture((-1820, 650, 100, 100))
    assert crop.size == (100, 100)
    assert crop.getpixel((0, 0)) == (255, 0, 0)
    assert service._capture((-1920, 150, 50, 50)).getpixel((0, 0)) == (0, 128, 0)
    assert calls == [window]


def test_failed_background_frame_does_not_reuse_previous_window(monkeypatch):
    service = object.__new__(CaptureService)
    service._window_frame = threading.local()
    service._window_frame.image = Image.new('RGB', (100, 100), 'red')
    def fail(_):
        raise OSError('Unavailable')
    monkeypatch.setattr('backend.capture.background_frame', fail)
    with pytest.raises(OSError):
        service._prepare_window_capture(WindowInfo(1, 'fixture', 'game.exe', (0, 0, 100, 100)))
    assert service._window_frame.image is None


def test_capture_frames_are_isolated_between_preview_and_ocr_threads(monkeypatch):
    service = object.__new__(CaptureService)
    service._window_frame = threading.local()
    window = WindowInfo(1, 'fixture', 'game.exe', (0, 0, 100, 100))
    monkeypatch.setattr('backend.capture.background_frame', lambda _: Image.new('RGB', (100, 100), 'red'))
    service._prepare_window_capture(window)
    seen = []
    thread = threading.Thread(target=lambda: seen.append(getattr(service._window_frame, 'image', None)))
    thread.start()
    thread.join()
    assert seen == [None]
    assert service._window_frame.image is not None


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows capture')
def test_foreground_game_keeps_desktop_capture(monkeypatch):
    class Foreground:
        restype = None
        def __call__(self):
            return 2**40
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: SimpleNamespace(GetForegroundWindow=Foreground()))
    assert window_capture.background_frame(WindowInfo(2**40, 'fixture', 'game.exe', (0, 0, 100, 100))) is None


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows capture')
def test_native_background_capture_of_restored_unfocused_window():
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    original = user32.GetForegroundWindow()
    # A synthetic STATIC control offscreen, shown without activation. No real
    # game pixels, focus changes, recordings, or account data are involved.
    handle = user32.CreateWindowExW(0x08000000, 'STATIC', 'Capture fixture',
        0x80000000, -30000, -30000, 240, 120, None, None, None, None)
    assert handle
    try:
        user32.ShowWindow(handle, 4)
        image = window_capture.background_frame(WindowInfo(handle, 'fixture', 'fixture.exe', (-30000, -30000, 240, 120)))
        assert image.size == (240, 120)
        assert image.getextrema() != ((0, 0), (0, 0), (0, 0))
        assert user32.GetForegroundWindow() == original
    finally:
        user32.DestroyWindow(handle)
