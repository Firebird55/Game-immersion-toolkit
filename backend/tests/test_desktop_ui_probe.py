"""Probe accounting and limits using authored UI doubles, not native evidence."""
import json
import threading
from types import SimpleNamespace

from backend.desktop_ui_probe import DesktopUiProbe


def fixture(tmp_path, *, platform='windows', tray=True, accepts=True):
    opened = []
    host = SimpleNamespace(layout=SimpleNamespace(mode='bundle', state_root=tmp_path),
        ready=threading.Event(), stop_requested=threading.Event(), finished=threading.Event(),
        lease=SimpleNamespace(held=True), exit_code=0, browser=True,
        open_browser=lambda url: opened.append(url) or accepts)
    host.ready.set()
    visible = [True]
    window = SimpleNamespace(isVisible=lambda: visible[0],
        windowHandle=lambda: SimpleNamespace(isExposed=lambda: visible[0]),
        hide=lambda: visible.__setitem__(0, False))
    actions = {
        'logs': SimpleNamespace(trigger=lambda: visible.__setitem__(0, True)),
        'open': SimpleNamespace(trigger=lambda: host.open_browser('http://127.0.0.1:12345'), isEnabled=lambda: True),
        'quit': SimpleNamespace(trigger=host.stop_requested.set)}
    probe = DesktopUiProbe(host, SimpleNamespace(platformName=lambda: platform), window,
        SimpleNamespace(text=lambda: 'Ready'), SimpleNamespace(document=lambda: SimpleNamespace(blockCount=lambda: 3)),
        SimpleNamespace(isVisible=lambda: tray, icon=lambda: SimpleNamespace(isNull=lambda: False)),
        actions, tray_available=tray)
    return probe, host, opened


def finish(probe, host, tmp_path):
    host.finished.set()
    host.lease.held = False
    code = probe.finish()
    return code, json.loads((tmp_path / 'native-ui-probe.json').read_text())


def test_offscreen_never_counts_as_native_window_or_tray(tmp_path):
    probe, host, opened = fixture(tmp_path, platform='offscreen')
    assert host.browser is False
    probe.tick()
    code, value = finish(probe, host, tmp_path)
    assert code == 2 and value['status'] == 'unavailable'
    assert not value['checks'].get('status_window') and not value['checks'].get('tray_icon')
    assert opened == []


def test_ui_actions_use_actual_bound_handlers_without_claiming_browser_navigation(tmp_path):
    probe, host, opened = fixture(tmp_path)
    host.open_browser('http://127.0.0.1:12345')
    for _ in range(3):
        probe.tick()
    code, value = finish(probe, host, tmp_path)
    assert code == 0 and value['passed']
    assert value['checks']['tray_icon'] and value['checks']['show_logs_action']
    assert value['checks']['open_transcript_action'] and value['checks']['quit_action']
    assert opened == ['http://127.0.0.1:12345'] * 2
    assert value['browser_navigation'] == 'not-run'
    assert 'browser_open' not in value['checks']


def test_absent_tray_records_supported_visible_window_fallback(tmp_path):
    probe, host, _opened = fixture(tmp_path, tray=False)
    host.open_browser('http://127.0.0.1:12345')
    for _ in range(3):
        probe.tick()
    code, value = finish(probe, host, tmp_path)
    assert code == 0 and value['native_tray'] == 'unavailable'
    assert not value['checks']['tray_icon'] and value['checks']['tray_unavailable_window_fallback']


def test_missing_browser_handler_is_unavailable_and_does_not_hide_native_window_result(tmp_path):
    probe, host, _opened = fixture(tmp_path, accepts=False)
    host.open_browser('http://127.0.0.1:12345')
    for _ in range(3):
        probe.tick()
    code, value = finish(probe, host, tmp_path)
    assert code == 2 and not value['passed']
    assert value['checks']['status_window'] and value['checks']['tray_icon']
    assert not value['checks']['default_browser_request']
