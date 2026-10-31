"""Windows Graphics Capture isolation. Binary stdout is request/response only."""
from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import time

from PIL import Image

from .windows import WindowInfo
from .window_capture import FRAME_HEADER, _client_crop, validate_frame_header


class NativeCapture:
    def __init__(self, window):
        from windows_capture import WindowsCapture

        self.ready = threading.Event()
        self.latest = None
        self.error = None
        self.control = None
        capture = WindowsCapture(window_hwnd=window.handle, cursor_capture=False,
                                 draw_border=False, minimum_update_interval=100)

        @capture.event
        def on_frame_arrived(frame, capture_control):
            try:
                # Copy inside the callback: the GPU buffer expires on return.
                image = Image.frombytes('RGB', (frame.width, frame.height),
                                        frame.frame_buffer.tobytes(), 'raw', 'BGRX')
                self.latest = (_client_crop(image, window), time.monotonic())
            except Exception as error:
                self.error = error
                capture_control.stop()
            finally:
                self.ready.set()

        @capture.event
        def on_closed():
            self.error = OSError('Game window capture closed')
            self.ready.set()

        self.control = capture.start_free_threaded()

    def frame(self):
        if not self.ready.wait(3):
            raise OSError('No background game frame arrived')
        latest = self.latest
        if self.error or self.control.is_finished() or latest is None:
            raise OSError('Background game capture is unavailable') from self.error
        image, captured = latest
        if time.monotonic() - captured > 3:
            raise OSError('Background game frame expired')
        return image

    def close(self):
        control, self.control = self.control, None
        if control is not None:
            control.stop()


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if sys.platform != 'win32' or len(arguments) != 5:
        return 2
    handle, x, y, width, height = map(int, arguments)
    validate_frame_header(FRAME_HEADER.pack(b'RGB1', width, height, width * height * 3))
    faulthandler.enable()
    # Keep native messages off the private frame channel. No images touch disk.
    output = sys.stdout.buffer
    sys.stdout = sys.stderr
    session = None
    try:
        session = NativeCapture(WindowInfo(handle, '', '', (x, y, width, height)))
        while sys.stdin.buffer.read(1) == b'f':
            image = session.frame()
            pixels = image.tobytes()
            output.write(FRAME_HEADER.pack(b'RGB1', image.width, image.height, len(pixels)))
            output.write(pixels)
            output.flush()
        return 0
    except Exception:
        logging.exception('Native background capture worker failed')
        return 1
    finally:
        if session is not None:
            session.close()


if __name__ == '__main__':
    raise SystemExit(main())
