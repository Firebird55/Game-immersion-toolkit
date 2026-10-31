"""Portable geometry and rejection rules; native grabs run in the platform probe."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import platform_windows as desktop
from backend.windows import MonitorInfo, WindowInfo


LEFT = MonitorInfo('Left', (-1920, -180, 1920, 1080))
RIGHT = MonitorInfo('Right', (0, 0, 2560, 1440), True)


def game_state(bounds=(-1200, 50, 900, 600)):
    window = WindowInfo(40, 'Authored game', 'ZenlessZoneZero.exe', bounds,
                        desktop.choose_monitor(bounds, [LEFT, RIGHT]))
    native = desktop.NativeWindow(window, '/games/ZenlessZoneZero.exe', 41)
    return window, desktop.Snapshot((native,), (desktop.Surface(41, bounds),))


def test_monitor_follows_largest_intersection_not_primary():
    assert desktop.choose_monitor((-800, 50, 1000, 700), [LEFT, RIGHT]) == LEFT
    assert desktop.choose_monitor((-200, 50, 1000, 700), [LEFT, RIGHT]) == RIGHT
    assert desktop.choose_monitor((-5000, 0, 100, 100), [LEFT, RIGHT]) is None


def test_occlusion_and_window_movement_never_capture_foreground_replacement():
    window, state = game_state()
    assert desktop.verified_window(window, state).info == window
    overlay = desktop.Surface(99, (-1000, 80, 200, 200))
    with pytest.raises(OSError, match='covered'):
        desktop.verified_window(window, replace(state, surfaces=(overlay, *state.surfaces)))
    unrelated = desktop.Surface(98, (200, 200, 100, 100))
    assert desktop.verified_window(window, replace(state, surfaces=(unrelated, *state.surfaces)))
    with pytest.raises(OSError, match='moved or changed'):
        desktop.verified_window(replace(window, bounds=(0, 0, 900, 600)), state)
    with pytest.raises(OSError, match='moved or changed'):
        desktop.verified_window(replace(window, process_name='browser'), state)
    with pytest.raises(OSError, match='moved or changed'):
        desktop.verified_window(window, desktop.Snapshot((), ()))


def test_mac_bounds_remain_in_display_points_and_menus_block(monkeypatch):
    monkeypatch.setattr(desktop, '_process_identity', lambda pid: ('Game.exe', '/Game') if pid == 8 else ('', ''))
    record = {'kCGWindowNumber': 4, 'kCGWindowOwnerPID': 8, 'kCGWindowLayer': 0,
              'kCGWindowName': 'Game', 'kCGWindowAlpha': 1, 'kCGWindowIsOnscreen': True,
              'kCGWindowBounds': {'X': -900, 'Y': -80, 'Width': 800, 'Height': 600}}
    state = desktop._mac_records([record], [LEFT, RIGHT])
    assert state.windows[0].info.bounds == (-900, -80, 800, 600)
    assert state.windows[0].info.monitor == LEFT
    menu = {**record, 'kCGWindowNumber': 20, 'kCGWindowLayer': 24}
    with pytest.raises(OSError, match='covered'):
        desktop.verified_window(state.windows[0].info, desktop._mac_records([menu, record], [LEFT, RIGHT]))
    assert not desktop._mac_records([{**record, 'kCGWindowIsOnscreen': False}], [LEFT]).windows


def test_wayland_and_missing_display_are_actionable():
    with pytest.raises(desktop.CaptureUnavailable, match='portal') as error:
        desktop.require_x11({'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'})
    assert error.value.code == 'wayland-portal-required'
    with pytest.raises(desktop.CaptureUnavailable, match='desktop session'):
        desktop.require_x11({})
    desktop.require_x11({'DISPLAY': ':0', 'XDG_SESSION_TYPE': 'x11'})


def test_arbitrary_browser_argument_does_not_become_a_game(monkeypatch):
    process = SimpleNamespace(exe=lambda: '/browser', name=lambda: 'browser',
                              cmdline=lambda: ['/browser', 'ZenlessZoneZero.exe'])
    monkeypatch.setattr(desktop.psutil, 'Process', lambda pid: process)
    assert desktop._process_identity(4) == ('browser', '/browser')


def test_wine_native_executable_resolves_without_title_guess(tmp_path, monkeypatch):
    game = tmp_path / 'ZenlessZoneZero.exe'
    game.write_bytes(b'authored')
    process = SimpleNamespace(exe=lambda: '/usr/bin/wine64', name=lambda: 'wine64',
                              cmdline=lambda: ['/usr/bin/wine64', str(game)])
    monkeypatch.setattr(desktop.psutil, 'Process', lambda pid: process)
    assert desktop._process_identity(4) == ('ZenlessZoneZero.exe', str(game.resolve()))


def test_grab_is_rejected_when_window_changes_during_capture(monkeypatch):
    import mss
    window, state = game_state()
    snapshots = iter([state, desktop.Snapshot((), ())])
    monkeypatch.setattr(desktop, 'snapshot', lambda: next(snapshots))
    class Grabber:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def grab(self, bounds):
            assert bounds == {'left': -1200, 'top': 50, 'width': 900, 'height': 600}
            return SimpleNamespace(size=(900, 600), rgb=b'')
    monkeypatch.setattr(mss, 'MSS', Grabber)
    with pytest.raises(OSError, match='moved or changed'):
        desktop.capture_window(window)


def test_loopback_unavailable_does_not_create_recorder_or_audio_files(tmp_path, monkeypatch):
    from backend import audio
    monkeypatch.setattr(audio, 'pyaudio', None)
    service = audio.AudioCaptureService.__new__(audio.AudioCaptureService)
    service._thread, service.output_dir = None, tmp_path / 'audio'
    service.start()
    assert not service.output_dir.exists() and service._thread is None
    assert 'Original voice from game files remains available' in service.message
