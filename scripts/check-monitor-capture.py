"""Opt-in native monitor probe using only an owned, visible colour window.

No game/account/screen images are saved. This verifies the current host, not
other display topologies or the final packaged runtime.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if sys.platform != 'win32':
        raise SystemExit('This native probe requires Windows.')
    # Import before creating a window so per-monitor DPI awareness is active.
    from backend.windows import list_visible_windows
    from backend.capture import CaptureService
    from backend.window_capture import BackgroundCapture
    import mss
    import tkinter as tk

    title = 'Toolkit owned monitor probe ' + uuid.uuid4().hex
    root = tk.Tk()
    root.title(title)
    root.geometry('480x240')
    canvas = tk.Canvas(root, background='#cf1133', highlightthickness=0)
    canvas.pack(fill='both', expand=True)
    canvas.bind('<Configure>', lambda event: (canvas.delete('all'), canvas.create_rectangle(
        event.width/2, 0, event.width, event.height, fill='#174bd1', outline='#174bd1')))
    capture = object.__new__(CaptureService)
    capture._window_frame = threading.local()
    capture._background_capture = BackgroundCapture()
    move = ctypes.windll.user32.SetWindowPos
    move.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    move.restype = wintypes.BOOL
    reports = []
    try:
        root.update()
        with mss.MSS() as screens:
            monitors = screens.monitors[1:]
        if not monitors:
            raise RuntimeError('No displays available')
        for number, monitor in enumerate(monitors, 1):
            window = next(item for item in list_visible_windows() if item.title == title)
            x, y = monitor['left'] + 60, monitor['top'] + 80
            if not move(window.handle, wintypes.HWND(-1), x, y, 480, 240, 0x0010):
                raise RuntimeError('Could not move the owned fixture window')
            deadline = time.monotonic() + .5
            while time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            window = next(item for item in list_visible_windows() if item.title == title)
            expected = (monitor['left'], monitor['top'], monitor['width'], monitor['height'])
            if not window.monitor or window.monitor.bounds != expected:
                raise RuntimeError('Game-window discovery selected the wrong monitor')
            capture._prepare_window_capture(window)
            pixels = capture._capture(window.bounds)
            for fraction, colour in ((.25, (207, 17, 51)), (.75, (23, 75, 209))):
                actual = pixels.getpixel((round(pixels.width*fraction), pixels.height//2))
                if max(abs(a-b) for a, b in zip(actual, colour)) > 15:
                    raise RuntimeError('Captured pixels did not belong to the owned fixture window')
            reports.append({'display': number, 'monitor_bounds': expected, 'client_bounds': window.bounds,
                            'capture': 'background-worker' if capture._window_frame.image is not None else 'physical-screen',
                            'pixels_verified': True})
            if '--background' in sys.argv:
                cover = tk.Toplevel(root)
                try:
                    cover.title(title + ' cover')
                    cover.configure(background='#00ff00')
                    cover.geometry('520x280')
                    root.update()
                    cover_window = next(item for item in list_visible_windows() if item.title == title + ' cover')
                    move(cover_window.handle, wintypes.HWND(-1), x-10, y-10, 520, 280, 0)
                    cover.focus_force()
                    root.update()
                    capture._prepare_window_capture(window)
                    if capture._window_frame.image is None:
                        raise RuntimeError('Background probe did not use the isolated capture worker')
                    pixels = capture._capture(window.bounds)
                    actual = pixels.getpixel((pixels.width//4, pixels.height//2))
                    if max(abs(a-b) for a, b in zip(actual, (207, 17, 51))) > 15:
                        raise RuntimeError('Background capture read the covering window instead of the fixture')
                    reports[-1]['occluded_pixels_verified'] = True
                finally:
                    capture._background_capture.close()
                    cover.destroy()
        print(json.dumps({'passed': True, 'displays': reports}))
    finally:
        capture._background_capture.close()
        root.destroy()


if __name__ == '__main__':
    main()
