"""Native desktop discovery outside Windows, with verified visible-window grabs.

X11 coordinates are display pixels. CoreGraphics coordinates and MSS's macOS
nominal-resolution images are display points; never scale a global origin by a
Retina factor. Window identity comes from its owner, not a title resemblance.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PureWindowsPath
import sys

import psutil

from .windows import MonitorInfo, WindowInfo


class CaptureUnavailable(OSError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class NativeWindow:
    info: WindowInfo
    executable: str
    surface: int


@dataclass(frozen=True)
class Surface:
    handle: int
    bounds: tuple[int, int, int, int]


@dataclass(frozen=True)
class Snapshot:
    windows: tuple[NativeWindow, ...]
    surfaces: tuple[Surface, ...]  # Front to back, including popups and panels.


def intersection(left, right):
    x, y, w, h = left
    a, b, c, d = right
    return max(0, min(x + w, a + c) - max(x, a)) * max(0, min(y + h, b + d) - max(y, b))


def choose_monitor(bounds, monitors):
    selected = max(monitors, key=lambda monitor: intersection(bounds, monitor.bounds), default=None)
    return selected if selected and intersection(bounds, selected.bounds) else None


def _monitors():
    import mss
    with mss.MSS() as capture:
        return [MonitorInfo(f'Display {i}', (value['left'], value['top'], value['width'], value['height']))
                for i, value in enumerate(capture.monitors[1:], 1)]


def _process_identity(pid):
    try:
        process = psutil.Process(pid)
        executable, name = process.exe(), process.name()
        # Wine's host image is not the game image. Only inspect this actual
        # Wine process, never an arbitrary program's .exe command argument.
        if Path(executable).name.casefold() in {'wine', 'wine64', 'wine-preloader', 'wine64-preloader'}:
            arguments = process.cmdline()[:3]
            game = next((value.strip('"') for value in arguments
                         if value.strip('"').casefold().endswith('.exe')), '')
            if game:
                name = PureWindowsPath(game).name
                if Path(game).is_absolute() and Path(game).is_file():
                    executable = str(Path(game).resolve())
                elif PureWindowsPath(game).drive:
                    prefix = process.environ().get('WINEPREFIX')
                    if not prefix and process.uids().real == os.getuid():
                        prefix = str(Path.home() / '.wine')
                    drive = PureWindowsPath(game).drive[:1].lower()
                    candidate = (Path(prefix) / 'dosdevices' / (drive + ':') /
                                 Path(*PureWindowsPath(game).parts[1:])) if prefix else None
                    executable = str(candidate.resolve()) if candidate and candidate.is_file() else ''
                else:
                    executable = ''
        # Native builds often omit .exe. Keep the same reader identity only for
        # an exact executable stem; do not introduce title-based game selection.
        from .games import GAME_PROFILES
        for profile in GAME_PROFILES.values():
            match = next((value for value in profile.process_names
                          if value.casefold().endswith('.exe') and value[:-4].casefold() == name.casefold()), None)
            if match:
                name = match
                break
        return name, executable
    except (psutil.Error, OSError, ValueError):
        return '', ''


def require_x11(environ=None):
    env = os.environ if environ is None else environ
    if env.get('XDG_SESSION_TYPE', '').casefold() == 'wayland' or env.get('WAYLAND_DISPLAY'):
        raise CaptureUnavailable('wayland-portal-required',
            'Wayland game capture needs a screen-sharing portal backend. Use an X11 desktop session for desktop capture.')
    if not env.get('DISPLAY'):
        raise CaptureUnavailable('display-unavailable', 'No X11 desktop display is available. Start the toolkit in your desktop session.')


def _x11_snapshot():
    require_x11()
    try:
        from Xlib import X, display, error
    except ImportError as exc:
        raise CaptureUnavailable('capture-component-missing', 'The X11 capture component is missing. Repair the toolkit installation.') from exc
    try:
        connection = display.Display()
    except (error.DisplayError, OSError) as exc:
        raise CaptureUnavailable('display-unavailable', 'Cannot access the X11 display. Start the toolkit as your desktop user.') from exc
    try:
        root = connection.screen().root
        monitors = _monitors()

        def property_value(window, name):
            atom = connection.intern_atom(name, only_if_exists=True)
            value = window.get_full_property(atom, X.AnyPropertyType) if atom else None
            return value.value if value is not None else None

        def bounds(window):
            geometry = window.get_geometry()
            position = root.translate_coords(window, 0, 0)
            return (position.x, position.y, geometry.width, geometry.height)

        roots = list(reversed(root.query_tree().children))
        visible_roots, surfaces = {}, []
        for window in roots:
            try:
                attributes = window.get_attributes()
                if attributes.map_state != X.IsViewable or attributes.win_class == X.InputOnly:
                    continue
                opacity = property_value(window, '_NET_WM_WINDOW_OPACITY')
                if opacity is not None and len(opacity) and int(opacity[0]) == 0:
                    continue
                rectangle = bounds(window)
                if rectangle[2] <= 0 or rectangle[3] <= 0:
                    continue
                visible_roots[window.id] = window
                surfaces.append(Surface(window.id, rectangle))
            except error.XError:
                continue  # A window may close between the two server queries.
        clients = property_value(root, '_NET_CLIENT_LIST_STACKING')
        ids = list(reversed(clients)) if clients is not None else list(visible_roots)
        windows = []
        hidden = connection.intern_atom('_NET_WM_STATE_HIDDEN', only_if_exists=True)
        for identifier in ids:
            window = connection.create_resource_object('window', int(identifier))
            try:
                if window.get_attributes().map_state != X.IsViewable:
                    continue
                state = property_value(window, '_NET_WM_STATE')
                if hidden and state is not None and hidden in state:
                    continue
                top = window
                for _ in range(32):
                    if top.id in visible_roots:
                        break
                    parent = top.query_tree().parent
                    if not parent or parent.id == root.id:
                        break
                    top = parent
                if top.id not in visible_roots:
                    continue
                pid = property_value(window, '_NET_WM_PID')
                if pid is None or not len(pid):
                    continue
                name, executable = _process_identity(int(pid[0]))
                title = property_value(window, '_NET_WM_NAME')
                title = title.decode('utf-8', errors='replace') if isinstance(title, bytes) else window.get_wm_name()
                rectangle = bounds(window)
                if not name or not title or rectangle[2] <= 0 or rectangle[3] <= 0:
                    continue
                info = WindowInfo(int(identifier), str(title), name, rectangle, choose_monitor(rectangle, monitors))
                windows.append(NativeWindow(info, executable, top.id))
            except error.XError:
                continue
        return Snapshot(tuple(windows), tuple(surfaces))
    finally:
        connection.close()


def _mac_snapshot():
    try:
        import Quartz
    except ImportError as exc:
        raise CaptureUnavailable('capture-component-missing', 'The macOS capture component is missing. Repair the toolkit installation.') from exc
    if not Quartz.CGPreflightScreenCaptureAccess():
        raise CaptureUnavailable('screen-recording-permission',
            'Allow Game immersion toolkit in System Settings → Privacy & Security → Screen & System Audio Recording, then reopen it.')
    values = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID)
    if values is None:
        raise CaptureUnavailable('display-unavailable', 'macOS could not enumerate this desktop. Unlock your desktop and try again.')
    return _mac_records(values, _monitors())


def _mac_records(values, monitors):
    windows, surfaces = [], []
    # CoreGraphics returns these dictionaries front to back. Keep higher-layer
    # menus as occluders, even though they cannot be selected as game windows.
    for value in values:
        if not value.get('kCGWindowIsOnscreen', False) or float(value.get('kCGWindowAlpha', 0)) <= 0:
            continue
        raw = value.get('kCGWindowBounds', {})
        rectangle = tuple(round(raw.get(key, 0)) for key in ('X', 'Y', 'Width', 'Height'))
        if rectangle[2] <= 0 or rectangle[3] <= 0:
            continue
        identifier = int(value.get('kCGWindowNumber', 0))
        surfaces.append(Surface(identifier, rectangle))
        if value.get('kCGWindowLayer') != 0:
            continue
        title = value.get('kCGWindowName', '')
        name, executable = _process_identity(int(value.get('kCGWindowOwnerPID', 0)))
        if title and name:
            info = WindowInfo(identifier, str(title), name, rectangle, choose_monitor(rectangle, monitors))
            windows.append(NativeWindow(info, executable, identifier))
    return Snapshot(tuple(windows), tuple(surfaces))


def snapshot():
    if sys.platform.startswith('linux'):
        return _x11_snapshot()
    if sys.platform == 'darwin':
        return _mac_snapshot()
    raise CaptureUnavailable('platform-unavailable', 'Desktop capture is unavailable on this platform.')


def list_visible_windows():
    return [window.info for window in snapshot().windows]


def executable_path_for_handle(handle):
    return next((window.executable for window in snapshot().windows if window.info.handle == handle), '')


def verified_window(expected, state):
    target = next((window for window in state.windows if window.info.handle == expected.handle), None)
    if (target is None or target.info.bounds != expected.bounds or target.info.process_name != expected.process_name
            or target.info.title != expected.title):
        raise OSError('The game window moved or changed. Waiting for its next frame.')
    if target.info.monitor is None:
        raise OSError('The game window is outside the available displays. Move it onto a display.')
    for surface in state.surfaces:
        if surface.handle == target.surface:
            return target
        if intersection(surface.bounds, target.info.bounds):
            raise OSError('The game is covered by another window. Uncover or restore it to resume capture.')
    raise OSError('The game window is no longer visible.')


def capture_window(window):
    """Return one verified frame; never silently capture the covering desktop."""
    import mss
    from PIL import Image
    verified_window(window, snapshot())
    left, top, width, height = window.bounds
    with mss.MSS() as capture:
        shot = capture.grab(dict(left=left, top=top, width=width, height=height))
    verified_window(window, snapshot())
    if tuple(shot.size) != (width, height):
        raise OSError('Display scaling changed during capture. Waiting for the game window to settle.')
    return Image.frombytes('RGB', shot.size, shot.rgb)
