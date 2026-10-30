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
    service._background_capture = window_capture.BackgroundCapture()
    window = WindowInfo(1, 'fixture', 'game.exe', (-1920, 150, 1280, 720))
    frame = Image.new('RGB', (1280, 720), 'green')
    frame.paste('red', (100, 500, 200, 600))
    calls = []
    monkeypatch.setattr('backend.capture.BackgroundCapture.frame', lambda self, w: calls.append(w) or frame)
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
    service._background_capture = window_capture.BackgroundCapture()
    service._window_frame.image = Image.new('RGB', (100, 100), 'red')
    def fail(self, _):
        raise OSError('Unavailable')
    monkeypatch.setattr('backend.capture.BackgroundCapture.frame', fail)
    with pytest.raises(OSError):
        service._prepare_window_capture(WindowInfo(1, 'fixture', 'game.exe', (0, 0, 100, 100)))
    assert service._window_frame.image is None


def test_capture_frames_are_isolated_between_preview_and_ocr_threads(monkeypatch):
    service = object.__new__(CaptureService)
    service._window_frame = threading.local()
    service._background_capture = window_capture.BackgroundCapture()
    window = WindowInfo(1, 'fixture', 'game.exe', (0, 0, 100, 100))
    monkeypatch.setattr('backend.capture.BackgroundCapture.frame', lambda self, _: Image.new('RGB', (100, 100), 'red'))
    service._prepare_window_capture(window)
    seen = []
    thread = threading.Thread(target=lambda: seen.append(getattr(service._window_frame, 'image', None)))
    thread.start()
    thread.join()
    assert seen == [None]
    assert service._window_frame.image is not None


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows capture')
def test_foreground_game_keeps_desktop_capture(monkeypatch):
    monkeypatch.undo()
    class Foreground:
        restype = None
        def __call__(self):
            return 2**40
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: SimpleNamespace(GetForegroundWindow=Foreground()))
    assert window_capture.background_frame(WindowInfo(2**40, 'fixture', 'game.exe', (0, 0, 100, 100))) is None


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows capture API')
def test_background_gpu_session_reuses_frames_and_restarts_after_resize(monkeypatch):
    monkeypatch.undo()
    captures, stopped = [], []
    class Foreground:
        restype = None
        def __call__(self):
            return 99
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: SimpleNamespace(GetForegroundWindow=Foreground()))
    monkeypatch.setattr(window_capture, '_client_crop', lambda image, window: image)
    class Capture:
        def __init__(self, **options):
            captures.append(options)
            self.events = {}
        def event(self, function):
            self.events[function.__name__] = function
            return function
        def start_free_threaded(self):
            control = SimpleNamespace(stop=lambda: stopped.append(True), is_finished=lambda: False)
            self.events['on_frame_arrived'](SimpleNamespace(width=2, height=1,
                frame_buffer=SimpleNamespace(tobytes=lambda: bytes([0, 0, 255, 0] * 2))), control)
            return control
    monkeypatch.setitem(sys.modules, 'windows_capture', SimpleNamespace(WindowsCapture=Capture))
    source = window_capture.BackgroundCapture()
    window = WindowInfo(2**40, 'fixture', 'game.exe', (-100, 50, 2, 1))
    assert source.frame(window).getpixel((0, 0)) == (255, 0, 0)
    assert source.frame(window).size == (2, 1)
    assert len(captures) == 1 and captures[0]['window_hwnd'] == 2**40
    source.frame(WindowInfo(window.handle, 'fixture', 'game.exe', (-100, 50, 3, 1)))
    assert len(captures) == 2 and len(stopped) == 1
    source.close()
    source.close()
    assert len(stopped) == 2


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows physical frame coordinates')
def test_gpu_frame_excludes_titlebar_and_keeps_client_pixels(monkeypatch):
    class Bounds:
        argtypes = None
        def __call__(self, handle, attribute, pointer, size):
            rect = pointer._obj
            rect.left, rect.top, rect.right, rect.bottom = -1900, 100, -1780, 190
            return 0
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: SimpleNamespace(DwmGetWindowAttribute=Bounds()))
    image = Image.new('RGB', (120, 90), 'blue')
    image.paste('red', (0, 30, 120, 90))
    window = WindowInfo(1, 'fixture', 'game.exe', (-1900, 130, 120, 60))
    result = window_capture._client_crop(image, window)
    assert result.size == (120, 60) and result.getpixel((0, 0)) == (255, 0, 0)
    with pytest.raises(OSError, match='resized'):
        window_capture._client_crop(Image.new('RGB', (130, 100)), window)




def test_failed_native_stop_keeps_control_and_session_until_retry_succeeds():
    source = window_capture.BackgroundCapture()
    failing, calls = [True], []
    def stop():
        calls.append('stop')
        if failing[0]:
            raise OSError('Synthetic native stop failed')
    control, target, state = SimpleNamespace(stop=stop), (123, (0, 0, 10, 10)), object()
    source._control, source._target, source._state = control, target, state
    with pytest.raises(OSError, match='native stop failed'):
        source.close()
    assert source._control is control and source._target is target and source._state is state
    failing[0] = False
    source.close()
    assert source._control is source._target is source._state is None
    source.close()
    assert calls == ['stop', 'stop']
