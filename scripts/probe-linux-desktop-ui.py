"""Run the frozen UI probe with an owned X11 system tray on a hosted display."""
from pathlib import Path
import subprocess
import sys
import time


def main():
    from Xlib.display import Display
    tray = subprocess.Popen(['trayer', '--edge', 'top', '--align', 'right',
        '--widthtype', 'request', '--height', '24'], stdin=subprocess.DEVNULL)
    try:
        display = Display()
        try:
            atom = display.intern_atom('_NET_SYSTEM_TRAY_S' + str(display.get_default_screen()))
            deadline = time.monotonic() + 10
            while not display.get_selection_owner(atom):
                if tray.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Hosted X11 system tray did not become available.')
                time.sleep(.1)
        finally:
            display.close()
        return subprocess.run([sys.executable, str(Path(__file__).with_name('probe-desktop-host.py')),
            '--ui', *sys.argv[1:]], check=False).returncode
    finally:
        if tray.poll() is None:
            tray.terminate()
        try:
            tray.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tray.kill()
            tray.wait(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
