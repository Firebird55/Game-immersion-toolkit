"""Authored geometry distinguishes obstructed runners from capture regressions."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from backend.windows import MonitorInfo

spec = spec_from_file_location('native_capture_probe', Path(__file__).resolve().parents[2] / 'scripts/probe-native-desktop-capture.py')
probe = module_from_spec(spec)
spec.loader.exec_module(probe)


def window(identifier, name, pid, rectangle, layer=0, alpha=1):
    return {'kCGWindowNumber': identifier, 'kCGWindowOwnerName': name, 'kCGWindowOwnerPID': pid,
        'kCGWindowName': 'Authored probe' if pid == 42 else 'Private application window title',
        'kCGWindowBounds': dict(zip(('X', 'Y', 'Width', 'Height'), rectangle)),
        'kCGWindowLayer': layer, 'kCGWindowAlpha': alpha, 'kCGWindowIsOnscreen': True}


def diagnose(blocker, *, executable='/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock'):
    target = window(10, 'Python', 42, (272, 206, 480, 320))
    return probe.mac_overlap_records([blocker, target], 'Authored probe', 42,
        [MonitorInfo('Authored display', (0, 0, 1024, 768))], lambda _pid: executable)


def test_exact_full_display_system_obstruction_is_unavailable_without_weakening_capture():
    value = diagnose(window(20, 'Dock', 99, (0, 0, 1024, 768), layer=20))
    assert value['full_display_system_obstruction'] is True
    assert value['overlaps'][0]['system_owner'] == 'dock'
    assert probe.unavailable_system_obstruction(OSError(probe.OCCLUDED_MESSAGE), value)
    encoded = json.dumps(value)
    assert 'Private application window title' not in encoded and '/System/Library' not in encoded
    assert 'PID' not in encoded and '99' not in encoded


@pytest.mark.parametrize('blocker, executable', [
    (window(20, 'Unknown app', 99, (0, 0, 1024, 768), layer=20), '/System/Library/Unknown app'),
    (window(20, 'Dock', 99, (0, 0, 1024, 768), layer=20), '/private/user/Dock'),
    (window(20, 'Dock', 99, (0, 0, 1024, 768), layer=20), '/System/LibraryFake/Dock'),
    (window(20, 'Dock', 99, (382, 104, 260, 248), layer=20), '/System/Library/CoreServices/Dock'),
    (window(20, 'Dock', 99, (0, 0, 1024, 768), layer=20, alpha=.5), '/System/Library/CoreServices/Dock'),
])
def test_unknown_spoofed_partial_or_transparent_blocker_keeps_failure(blocker, executable):
    value = diagnose(blocker, executable=executable)
    assert not value['full_display_system_obstruction']
    assert not probe.unavailable_system_obstruction(OSError(probe.OCCLUDED_MESSAGE), value)


def test_unrelated_failure_is_not_reclassified_by_system_geometry():
    value = diagnose(window(20, 'Dock', 99, (0, 0, 1024, 768), layer=20))
    assert not probe.unavailable_system_obstruction(OSError('Pixels did not match'), value)
    assert not probe.unavailable_system_obstruction(RuntimeError(probe.OCCLUDED_MESSAGE), value)


def test_owner_verification_failure_is_private_and_does_not_accept_runner():
    def denied(_pid):
        raise OSError('private process diagnostics')
    target = window(10, 'Python', 42, (272, 206, 480, 320))
    blocker = window(20, 'Dock', 99, (0, 0, 1024, 768), layer=20)
    value = probe.mac_overlap_records([blocker, target], 'Authored probe', 42,
        [MonitorInfo('Authored display', (0, 0, 1024, 768))], denied)
    assert value['overlaps'][0]['system_owner'] == 'unverified'
    assert not value['full_display_system_obstruction']
    assert 'private process diagnostics' not in json.dumps(value)


def test_system_window_behind_authored_target_is_not_an_obstruction():
    target = window(10, 'Python', 42, (272, 206, 480, 320))
    blocker = window(20, 'Dock', 99, (0, 0, 1024, 768), layer=20)
    value = probe.mac_overlap_records([target, blocker], 'Authored probe', 42,
        [MonitorInfo('Authored display', (0, 0, 1024, 768))], lambda _pid: '/System/Library/CoreServices/Dock')
    assert value['overlaps'] == [] and not value['full_display_system_obstruction']
