"""Unobscured game frames using Windows Graphics Capture."""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes

from PIL import Image

from .windows import WindowInfo


class BackgroundCapture:
    """Keep one GPU capture session alive while OCR reads the latest frame."""

    def __init__(self):
        self._lock = threading.RLock()
        self._control = None
        self._target = None
        self._state = None

    def close(self):
        with self._lock:
            # A failed stop is still owned. Keep both control and its session
            # state so recovery can retry instead of starting a replacement.
            if self._control is not None:
                self._control.stop()
            self._control = None
            self._target = self._state = None

    def frame(self, window: WindowInfo) -> Image.Image | None:
        if sys.platform != 'win32':
            return None
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        with self._lock:
            if user32.GetForegroundWindow() == window.handle:
                self.close()
                return None
            target = (window.handle, window.bounds)
            if self._control is None or self._target != target or self._control.is_finished():
                self.close()
                self._start(window)
            ready, frames, errors = self._state
            if not ready.wait(3):
                self.close()
                raise OSError('Background game capture timed out; keep the game restored in windowed or borderless mode')
            if errors:
                error = errors[-1]
                self.close()
                raise OSError('Could not read the background game frame') from error
            if not frames:
                self.close()
                raise OSError('The game window closed before a frame was available')
            return frames[-1]

    def _start(self, window):
        from windows_capture import WindowsCapture

        # Callback state belongs to this session. A closing session must never
        # overwrite frames from a replacement window or a resized client.
        ready, frames, errors = threading.Event(), [], []
        capture = WindowsCapture(window_hwnd=window.handle, cursor_capture=False,
                                 draw_border=False, minimum_update_interval=100)

        @capture.event
        def on_frame_arrived(frame, capture_control):
            try:
                # Copy before returning: the mapped GPU buffer is valid only
                # inside this callback, while OCR runs on a separate thread.
                image = Image.frombytes('RGB', (frame.width, frame.height),
                                        frame.frame_buffer.tobytes(), 'raw', 'BGRX')
                frames[:] = [_client_crop(image, window)]
            except Exception as error:
                errors.append(error)
                capture_control.stop()
            finally:
                ready.set()

        @capture.event
        def on_closed():
            errors.append(OSError('Game window capture closed'))
            ready.set()

        self._control = capture.start_free_threaded()
        self._target = (window.handle, window.bounds)
        self._state = (ready, frames, errors)


def background_frame(window: WindowInfo) -> Image.Image | None:
    """One-shot capture for diagnostics; the OCR service reuses its session."""
    source = BackgroundCapture()
    try:
        return source.frame(window)
    finally:
        source.close()


def _client_crop(image: Image.Image, window: WindowInfo) -> Image.Image:
    # WGC includes the title bar but excludes the invisible resize border.
    # DWM extended bounds locate that frame in physical screen coordinates.
    rect = wintypes.RECT()
    dwmapi = ctypes.WinDLL('dwmapi')
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                            ctypes.c_void_p, wintypes.DWORD]
    if dwmapi.DwmGetWindowAttribute(window.handle, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        raise OSError('Game window bounds unavailable')
    x, y, width, height = window.bounds
    left, top = x - rect.left, y - rect.top
    if (image.size != (rect.right - rect.left, rect.bottom - rect.top)
            or left < 0 or top < 0 or left + width > image.width or top + height > image.height):
        raise OSError('Game window resized during capture; retrying with current bounds')
    return image.crop((left, top, left + width, top + height))
