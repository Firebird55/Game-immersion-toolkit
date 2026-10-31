"""Capture an independently painted native window; never read game/account data."""
from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.platform_windows import CaptureUnavailable, require_x11


def mac_overlap_diagnostics(title):
    """Geometry only: never include other applications' titles or identities."""
    import Quartz
    from backend.platform_windows import intersection
    values = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    def bounds(value):
        raw = value.get('kCGWindowBounds', {})
        return tuple(round(raw.get(key, 0)) for key in ('X', 'Y', 'Width', 'Height'))
    target = next((value for value in values or []
        if value.get('kCGWindowOwnerPID') == os.getpid() and value.get('kCGWindowName') == title), None)
    if target is None:
        return {'target_found': False}
    blockers = []
    for value in values:
        if value.get('kCGWindowNumber') == target.get('kCGWindowNumber'):
            break
        if (value.get('kCGWindowIsOnscreen') and float(value.get('kCGWindowAlpha', 0)) > 0
                and intersection(bounds(value), bounds(target))):
            blockers.append({'layer': value.get('kCGWindowLayer'), 'bounds': bounds(value),
                'alpha': value.get('kCGWindowAlpha'), 'owned': value.get('kCGWindowOwnerPID') == os.getpid()})
    return {'target_found': True, 'target_bounds': bounds(target), 'overlaps': blockers[:12]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = {'schema': 'toolkit-native-window-probe-v1', 'platform': sys.platform,
              'architecture': platform.machine(), 'status': 'failed', 'native_game_capture': 'not-run'}
    started = time.monotonic()
    try:
        if sys.platform.startswith('linux'):
            require_x11()
        elif sys.platform == 'darwin':
            import Quartz
            if not Quartz.CGPreflightScreenCaptureAccess():
                raise CaptureUnavailable('screen-recording-permission', 'Screen recording permission is unavailable on this runner.')
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtGui import QColor, QPainter
        from PySide6.QtWidgets import QApplication, QWidget
        from backend.windows import list_visible_windows
        from backend.window_capture import BackgroundCapture
        import mss
        from PIL import Image
        application = QApplication(sys.argv[:1])
        if sys.platform == 'darwin':
            from AppKit import NSApplication, NSApplicationActivationPolicyRegular
            native_application = NSApplication.sharedApplication()
            native_application.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        title = 'Toolkit authored capture probe ' + uuid.uuid4().hex
        colors = [(40, 130, 210), (130, 210, 40)]
        class AuthoredWindow(QWidget):
            def paintEvent(self, event):
                painter = QPainter(self)
                painter.fillRect(0, 0, self.width() // 2, self.height(), QColor(*colors[0]))
                painter.fillRect(self.width() // 2, 0, self.width(), self.height(), QColor(*colors[1]))
        window = AuthoredWindow()
        window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        window.setWindowTitle(title)
        window.resize(480, 320)
        # Keep the authored content clear of the desktop's menu bar and Dock.
        screen = application.primaryScreen()
        if screen is None:
            raise CaptureUnavailable('display-unavailable', 'No desktop display is available.')
        window.move(screen.availableGeometry().center() - window.rect().center())
        window.show()
        if sys.platform == 'darwin':
            # A command-line Python process is not activated by Finder. This
            # explicit probe owns the foreground; normal capture never does so.
            native_application.activateIgnoringOtherApps_(True)
        window.raise_()
        window.activateWindow()

        def verify():
            capture = BackgroundCapture()
            try:
                native = next((value for value in list_visible_windows() if value.title == title), None)
                if native is None:
                    raise RuntimeError('Authored native window was not discovered.')
                image = capture.frame(native)
                if image is None:  # Windows foreground fast path.
                    left, top, width, height = native.bounds
                    with mss.MSS() as screen:
                        shot = screen.grab(dict(left=left, top=top, width=width, height=height))
                    image = Image.frombytes('RGB', shot.size, shot.rgb)
                if image.size != native.bounds[2:]:
                    raise RuntimeError('Native window and capture coordinate spaces differ.')
                for fraction, color in zip((.25, .75), colors):
                    actual = image.getpixel((round(image.width * fraction), image.height // 2))
                    if any(abs(a - b) > 12 for a, b in zip(actual, color)):
                        raise RuntimeError('Captured pixels do not match the authored window.')
                result.update(status='passed', discovery=True, monitor=native.monitor is not None,
                              bounds_match=True, pixels_match=True, size=list(image.size))
            except CaptureUnavailable as error:
                result.update(status='unavailable', reason=error.code)
            except Exception as error:
                result.update(status='failed', reason=type(error).__name__, message=str(error))
                if sys.platform == 'darwin':
                    try:
                        result['window_diagnostics'] = mac_overlap_diagnostics(title)
                    except Exception as diagnostic_error:
                        result['window_diagnostics'] = {'error': type(diagnostic_error).__name__}
            finally:
                capture.close()
                window.close()
                application.quit()
        QTimer.singleShot(1500, verify)
        application.exec()
    except CaptureUnavailable as error:
        result.update(status='unavailable', reason=error.code)
    except Exception as error:
        result.update(status='failed', reason=type(error).__name__, message=str(error))
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return {'passed': 0, 'unavailable': 2}.get(result['status'], 1)


if __name__ == '__main__':
    raise SystemExit(main())
