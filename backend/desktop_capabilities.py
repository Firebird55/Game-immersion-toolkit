"""Cheap platform requirements for setup; native probes remain separate."""
import sys


def capture_capability():
    result = {'id': 'desktop', 'title': 'Desktop capture', 'ready': False,
              'help': 'Desktop capture is unavailable on this platform.'}
    if sys.platform == 'win32':
        result.update(ready=True, help='Game window and monitor detection are available.')
    elif sys.platform.startswith('linux'):
        from .platform_windows import CaptureUnavailable, require_x11
        try:
            require_x11()
        except CaptureUnavailable as error:
            result['help'] = str(error)
        else:
            result.update(ready=True, help='X11 capture is available. Keep the game visible and uncovered.')
    elif sys.platform == 'darwin':
        try:
            import Quartz
            ready = bool(Quartz.CGPreflightScreenCaptureAccess())
        except ImportError:
            result['help'] = 'The macOS capture component is missing. Repair the toolkit installation.'
        else:
            result.update(ready=ready, help='Keep the game visible and uncovered.' if ready else
                'Allow Game immersion toolkit in System Settings → Privacy & Security → Screen & System Audio Recording, then reopen it.')
    return result
