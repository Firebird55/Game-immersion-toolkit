"""Capture a game's client surface even when another window covers it."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PIL import Image

from .windows import WindowInfo


def background_frame(window: WindowInfo) -> Image.Image | None:
    """Return an unobscured client frame, or None for the foreground game.

    Never fall back to desktop pixels for a background window: those pixels
    could belong to the reader or another app instead of the game.
    """
    if sys.platform != "win32":
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    if user32.GetForegroundWindow() == window.handle:
        return None
    return _print_client(window, user32, ctypes.WinDLL("gdi32", use_last_error=True))


def _print_client(window: WindowInfo, user32, gdi32) -> Image.Image:
    # Explicit pointer-sized signatures are required on 64-bit Windows.
    signatures = [
        (user32.GetDC, [wintypes.HWND], wintypes.HDC),
        (user32.ReleaseDC, [wintypes.HWND, wintypes.HDC], ctypes.c_int),
        (user32.PrintWindow, [wintypes.HWND, wintypes.HDC, wintypes.UINT], wintypes.BOOL),
        (gdi32.CreateCompatibleDC, [wintypes.HDC], wintypes.HDC),
        (gdi32.CreateCompatibleBitmap, [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP),
        (gdi32.SelectObject, [wintypes.HDC, wintypes.HANDLE], wintypes.HANDLE),
        (gdi32.DeleteObject, [wintypes.HANDLE], wintypes.BOOL),
        (gdi32.DeleteDC, [wintypes.HDC], wintypes.BOOL),
        (gdi32.GetDIBits, [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                         wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT], ctypes.c_int),
    ]
    for function, arguments, result in signatures:
        function.argtypes, function.restype = arguments, result

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG),
                    ("height", wintypes.LONG), ("planes", wintypes.WORD),
                    ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("image_size", wintypes.DWORD), ("xppm", wintypes.LONG),
                    ("yppm", wintypes.LONG), ("used", wintypes.DWORD),
                    ("important", wintypes.DWORD)]

    width, height = window.bounds[2:]
    source = user32.GetDC(window.handle)
    memory = bitmap = previous = None
    try:
        if not source:
            raise OSError("Game window capture could not open its client surface")
        memory = gdi32.CreateCompatibleDC(source)
        bitmap = gdi32.CreateCompatibleBitmap(source, width, height) if memory else None
        if not memory or not bitmap:
            raise OSError("Game window capture could not allocate a frame")
        previous = gdi32.SelectObject(memory, bitmap)
        if not previous or previous == ctypes.c_void_p(-1).value:
            previous = None
            raise OSError("Game window capture could not select its frame")
        # PW_CLIENTONLY | PW_RENDERFULLCONTENT includes accelerated content
        # without title bars, borders, or pixels from overlapping windows.
        if not user32.PrintWindow(window.handle, memory, 3):
            raise OSError("Background game capture unavailable; keep the game restored in windowed or borderless mode")
        gdi32.SelectObject(memory, previous)
        previous = None
        header = BitmapInfoHeader(size=ctypes.sizeof(BitmapInfoHeader), width=width,
                                  height=-height, planes=1, bits=32)
        pixels = ctypes.create_string_buffer(width * height * 4)
        if gdi32.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(header), 0) != height:
            raise OSError("Game window capture returned an incomplete frame")
        return Image.frombytes("RGB", (width, height), pixels.raw, "raw", "BGRX")
    finally:
        if previous:
            gdi32.SelectObject(memory, previous)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        if source:
            user32.ReleaseDC(window.handle, source)
