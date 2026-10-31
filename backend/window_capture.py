"""Unobscured game frames using Windows Graphics Capture."""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import struct
import subprocess
import sys
import threading
import time
from ctypes import wintypes

from PIL import Image

from .windows import WindowInfo
from .runtime_bundle import discover_layout

log = logging.getLogger(__name__)
FRAME_HEADER = struct.Struct('!4sIII')
MAX_FRAME_BYTES = 128 * 1024 * 1024


def validate_frame_header(header):
    magic, width, height, size = FRAME_HEADER.unpack(header)
    if (magic != b'RGB1' or not 0 < width <= 16384 or not 0 < height <= 8640
            or size != width * height * 3 or size > MAX_FRAME_BYTES):
        raise OSError('Invalid background capture frame')
    return width, height, size


def _read_exact(stream, size):
    result = bytearray()
    while len(result) < size:
        part = stream.read(size - len(result))
        if not part:
            raise OSError('Background capture worker exited before delivering a complete frame')
        result.extend(part)
    return bytes(result)


class FrameProcess:
    """Bounded frame IPC; retain ownership through native failure and shutdown."""

    def __init__(self, command, *, cwd=None, env=None):
        self.process = None
        self.tree = None
        self.reader = None
        self.frames = queue.Queue(maxsize=1)
        self.stopping = threading.Event()
        try:
            if os.name == 'nt':
                from .windows_preparation_process import WindowsPreparationProcess
                self.tree = WindowsPreparationProcess()
            self.process = subprocess.Popen(self.tree.command(command) if self.tree else command,
                cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                # Native errors go to the host's log, never into the binary pipe.
                stderr=None, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                start_new_session=self.tree is None)
            self.reader = threading.Thread(target=self._read_frames, args=(self.process.stdout,),
                                           daemon=True, name='capture-frame-reader')
            self.reader.start()
        except BaseException:
            self.close()
            raise

    def _read_frames(self, stream):
        try:
            while not self.stopping.is_set():
                width, height, size = validate_frame_header(_read_exact(stream, FRAME_HEADER.size))
                item = (width, height, _read_exact(stream, size))
                self.frames.put_nowait(item)
        except (OSError, ValueError, queue.Full) as error:
            if not self.stopping.is_set():
                # Preserve an already completed response; EOF will be observed
                # by poll() before the next request. Never retain old sessions.
                try:
                    self.frames.put_nowait(error)
                except queue.Full:
                    pass

    def frame(self, timeout=5):
        if self.process.poll() is not None:
            raise OSError('Background capture worker exited')
        try:
            self.process.stdin.write(b'f')
            self.process.stdin.flush()
            result = self.frames.get(timeout=timeout)
        except queue.Empty as error:
            raise OSError('Background capture timed out; keep the game restored in windowed or borderless mode') from error
        if isinstance(result, Exception):
            raise OSError('Background capture worker failed') from result
        width, height, pixels = result
        return Image.frombytes('RGB', (width, height), pixels)

    def close(self):
        self.stopping.set()
        process, self.process = self.process, None
        tree, self.tree = self.tree, None
        try:
            if process is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass
                try:
                    process.wait(timeout=.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            # Kill/reap the bootstrap first, then stop its owned descendants.
            if tree is not None:
                tree.terminate()
        finally:
            if tree is not None:
                tree.close()
            if self.reader is not None:
                self.reader.join(timeout=3)
            if process is not None:
                process.stdout.close()


class BackgroundCapture:
    """Native GPU sessions live outside the transcript/API process."""

    def __init__(self):
        self._lock = threading.RLock()
        self._worker = None
        self._target = None
        self._retry_at = 0.0
        self._failures = 0

    def close(self):
        with self._lock:
            worker, self._worker = self._worker, None
            self._target = None
            if worker is not None:
                worker.close()

    def frame(self, window: WindowInfo) -> Image.Image | None:
        if sys.platform != 'win32':
            from .platform_windows import capture_window
            return capture_window(window)
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        with self._lock:
            if user32.GetForegroundWindow() == window.handle:
                self.close()
                return None
            target = (window.handle, window.bounds)
            if time.monotonic() < self._retry_at:
                raise OSError('Background capture is recovering; retrying shortly')
            try:
                if self._worker is None or self._target != target:
                    self.close()
                    self._start(window)
                image = self._worker.frame()
                if image.size != window.bounds[2:]:
                    raise OSError('Game window resized during capture; retrying with current bounds')
                self._failures = 0
                return image
            except (OSError, ValueError) as error:
                code = self._worker.process.poll() if self._worker and self._worker.process else None
                self.close()
                self._failures += 1
                delay = min(15, 2 ** min(self._failures - 1, 4))
                self._retry_at = time.monotonic() + delay
                exit_status = f'0x{code & 0xffffffff:08x}' if code is not None else 'unavailable'
                log.warning('Background capture stopped (exit %s); restarting in %ss. Transcript remains available.', exit_status, delay)
                raise OSError('Background game capture interrupted; automatically restarting') from error

    def _start(self, window):
        layout = discover_layout()
        arguments = [str(window.handle), *(str(value) for value in window.bounds)]
        self._worker = FrameProcess(layout.child_command('window-capture', arguments),
            cwd=layout.application_root, env=layout.child_environment('window-capture'))
        self._target = (window.handle, window.bounds)
        log.info('Background capture started in an isolated worker (%sx%s).', *window.bounds[2:])


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
