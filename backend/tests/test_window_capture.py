import ctypes
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from backend import window_capture
from backend import window_capture_worker
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
def test_native_gpu_session_copies_frames_and_rejects_expired_buffers(monkeypatch):
    monkeypatch.undo()
    captures, stopped = [], []
    class Foreground:
        restype = None
        def __call__(self):
            return 99
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: SimpleNamespace(GetForegroundWindow=Foreground()))
    monkeypatch.setattr(window_capture_worker, '_client_crop', lambda image, window: image)
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
    window = WindowInfo(2**40, 'fixture', 'game.exe', (-100, 50, 2, 1))
    source = window_capture_worker.NativeCapture(window)
    assert source.frame().getpixel((0, 0)) == (255, 0, 0)
    assert source.frame().size == (2, 1)
    assert len(captures) == 1 and captures[0]['window_hwnd'] == 2**40
    source.latest = (source.latest[0], time.monotonic() - 4)
    with pytest.raises(OSError, match='expired'):
        source.frame()
    source.close()
    source.close()
    assert len(stopped) == 1


def frame_process(mode):
    script = Path(__file__).parent / 'fixtures/capture_worker.py'
    return window_capture.FrameProcess([sys.executable, '-u', str(script), mode])


@pytest.mark.parametrize('mode', ['crash', 'hang', 'oversized', 'truncated'])
def test_worker_fault_is_bounded_and_owned_process_is_reaped(mode):
    worker = frame_process(mode)
    process = worker.process
    started = time.monotonic()
    try:
        with pytest.raises(OSError):
            worker.frame(timeout=1)
    finally:
        worker.close()
    assert process.poll() is not None
    assert not worker.reader.is_alive()
    assert time.monotonic() - started < 8


def test_real_frame_channel_reuses_child_and_never_buffers_unsolicited_frames():
    worker = frame_process('frames')
    try:
        assert worker.frame().getpixel((0, 0)) == (255, 0, 0)
        assert worker.frame().getpixel((0, 0)) == (0, 255, 0)
        assert worker.frames.empty()
    finally:
        worker.close()
        worker.close()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows foreground selection')
def test_background_recovers_after_child_crash_and_replaces_resized_session(monkeypatch, caplog):
    monkeypatch.undo()
    class Foreground:
        restype = None
        def __call__(self):
            return 99
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: SimpleNamespace(GetForegroundWindow=Foreground()))
    # Real IPC/process cleanup is covered above. This test drives session selection
    # without faking the actual Win32 Job Object used by those process tests.
    workers = []
    class Worker:
        process = SimpleNamespace(poll=lambda: 0xc0000005)
        closed = False
        def __init__(self, window):
            self.window = window
        def frame(self):
            if len(workers) == 1:
                raise OSError('native access violation')
            return Image.new('RGB', self.window.bounds[2:], 'green')
        def close(self):
            self.closed = True
    def start(self, window):
        workers.append(Worker(window))
        self._worker = workers[-1]
        self._target = (window.handle, window.bounds)
    monkeypatch.setattr(window_capture.BackgroundCapture, '_start', start)
    source = window_capture.BackgroundCapture()
    window = WindowInfo(2**40, '', '', (-100, 50, 2, 1))
    with pytest.raises(OSError, match='automatically restarting'):
        source.frame(window)
    assert workers[0].closed and '0xc0000005' in caplog.text
    with pytest.raises(OSError, match='recovering'):
        source.frame(window)
    assert len(workers) == 1
    source._retry_at = 0
    assert source.frame(window).size == (2, 1)
    assert source.frame(window).size == (2, 1) and len(workers) == 2
    assert source.frame(WindowInfo(window.handle, '', '', (100, -50, 3, 1))).size == (3, 1)
    assert len(workers) == 3 and workers[1].closed
    source.close()
    assert workers[2].closed


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



