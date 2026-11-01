"""Probe accounting and limits using authored UI doubles, not native evidence."""
import json
import threading
from types import SimpleNamespace

import pytest

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


def test_ui_actions_require_each_mounted_reader_acknowledgement(tmp_path):
    probe, host, opened = fixture(tmp_path)
    host.open_browser('http://127.0.0.1:12345')
    for _ in range(3):
        probe.tick()
    assert len(opened) == 1 and not host.stop_requested.is_set()
    assert 'browser_open' not in probe.checks
    probe.browser_result.write_text('{"stages":[1]}')
    probe.tick()
    probe.tick()
    assert len(opened) == 2 and not host.stop_requested.is_set()
    probe.browser_result.write_text('{"stages":[1,2]}')
    probe.tick()
    code, value = finish(probe, host, tmp_path)
    assert code == 0 and value['passed']
    assert value['checks']['tray_icon'] and value['checks']['show_logs_action']
    assert value['checks']['open_transcript_action'] and value['checks']['quit_action']
    assert all(url.startswith('http://127.0.0.1:12345/#toolkit-native-probe=') for url in opened)
    assert opened[0].endswith('&stage=1') and opened[1].endswith('&stage=2')
    assert value['browser_navigation'] == 'mounted-reader-observed'
    assert value['checks']['browser_open'] and value['checks']['open_transcript_navigation']


def test_absent_tray_records_supported_visible_window_fallback(tmp_path):
    probe, host, _opened = fixture(tmp_path, tray=False)
    probe.browser_result.write_text('{"stages":[1,2]}')
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


def test_stale_browser_result_is_removed_and_handler_alone_cannot_pass(tmp_path):
    (tmp_path / 'native-browser-probe.json').write_text('{"stages":[1,2]}')
    probe, host, _opened = fixture(tmp_path)
    assert not probe.browser_result.exists()
    host.open_browser('http://127.0.0.1:12345')
    for _ in range(3):
        probe.tick()
    code, value = finish(probe, host, tmp_path)
    assert code == 1 and not value['passed']
    assert value['browser_navigation'] == 'unverified'


def test_initial_checkpoint_never_accepts_an_unfinished_native_run(tmp_path):
    probe, host, _opened = fixture(tmp_path)
    raw = (tmp_path / 'native-ui-probe.json').read_text()
    value = json.loads(raw)
    assert value['complete'] is False and value['passed'] is False
    assert value['status'] == 'failed' and value['phase'] == 'startup'
    assert value['error'] == 'native-ui-incomplete'
    assert host.browser_probe_token not in raw and str(tmp_path) not in raw


def test_native_quit_that_does_not_return_retains_incomplete_failure(tmp_path):
    probe, _host, _opened = fixture(tmp_path)
    def native_exit():
        raise SystemExit(0)
    probe.actions['quit'] = SimpleNamespace(trigger=native_exit)
    with pytest.raises(SystemExit):
        probe.stop('native-ui-timeout')
    value = json.loads((tmp_path / 'native-ui-probe.json').read_text())
    assert value['complete'] is False and value['passed'] is False
    assert value['phase'] == 'stopping' and value['error'] == 'native-ui-timeout'
    assert 'owned_shutdown' not in value['checks'] and 'quit_action' not in value['checks']


def test_checkpoint_does_not_rewrite_unchanged_observations(monkeypatch, tmp_path):
    probe, _host, _opened = fixture(tmp_path)
    writes = []
    monkeypatch.setattr('backend.desktop_ui_probe._atomic_json', lambda *_args: writes.append(True))
    probe.checkpoint()
    probe.checkpoint()
    assert writes == []
    probe.phase = 'logs'
    probe.checkpoint()
    assert writes == [True]


def test_browser_diagnostics_are_checkpointed_without_granting_navigation(tmp_path):
    probe, host, _opened = fixture(tmp_path)
    probe.browser_result.write_text(json.dumps({'stages': [], 'diagnostics': {
        'browser': {'1': 'animation-frame-pending', '2': host.browser_probe_token},
        'http': {'document': 200, 'script': 200, 'snapshot': 'pending', 'private-url': 200},
        'visibility': {'1': 'hidden'}, 'token': host.browser_probe_token,
    }}))
    probe.checkpoint()
    raw = (tmp_path / 'native-ui-probe.json').read_text()
    value = json.loads(raw)
    assert not value['passed'] and not probe.browser_observed(1)
    assert value['browser_diagnostics'] == {
        'browser': {'1': 'animation-frame-pending'}, 'visibility': {'1': 'hidden'},
        'http': {'document': 200, 'script': 200, 'snapshot': 'pending'}}
    assert host.browser_probe_token not in raw and 'private-url' not in raw
