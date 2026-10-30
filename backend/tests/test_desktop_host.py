"""Host restart/exclusion/log privacy with owned authored services, no accounts."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from backend import desktop_host as host_module
from backend.desktop_host import DesktopHost, HostControl, HostLog, contact_instance, selected_environment
from backend.runtime_bundle import discover_layout


def layout(tmp_path):
    return discover_layout({'PROXY_TRANSCRIPT_PROJECT_ROOT': str(tmp_path / 'instance'),
                            'LOCALAPPDATA': str(tmp_path)})


def test_host_selection_keeps_frozen_app_tree_readonly_and_ignores_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.chdir(tmp_path)
    selected = tmp_path / 'user data'
    env = selected_environment(selected)
    assert env['PROXY_TRANSCRIPT_DATA_ROOT'] == str(selected / 'data')
    assert env['PROXY_TRANSCRIPT_SETTINGS_ROOT'] == str(selected)
    assert env['PROXY_TRANSCRIPT_STATE_ROOT'] == str(selected / 'state')
    assert not selected.exists(), 'Root selection and host-check must not prepare data'
    with pytest.raises(host_module.HostError):
        selected_environment('relative')


def test_log_redacts_secrets_and_has_bounded_retention(tmp_path):
    log = HostLog(tmp_path / 'logs')
    try:
        log.write('Authorization: Bearer top-secret api_key=private-key cookie=private-cookie')
        saved = (tmp_path / 'logs/desktop.log').read_text(encoding='utf-8')
        assert 'top-secret' not in saved and 'private-key' not in saved and 'private-cookie' not in saved
        assert '[Host]' in saved and '[redacted]' in saved
        assert log.handler.maxBytes == 2 * 1024 * 1024 and log.handler.backupCount == 4
    finally:
        log.close()


def test_second_launch_reuses_only_authenticated_current_owner(tmp_path):
    host = DesktopHost(layout(tmp_path), browser=False)
    try:
        assert host.acquire()
        assert not DesktopHost(host.layout, browser=False).acquire()
        assert host.open_requested.is_set()
        host.open_requested.clear()
        value = json.loads(host.control_path.read_text())
        request = Request(f"http://127.0.0.1:{value['port']}/quit", data=b'',
            headers={'X-Toolkit-Control': value['token'], 'Origin': 'https://untrusted.invalid'})
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == 403 and not host.stop_requested.is_set()
        assert contact_instance(host.control_path, 'quit')
        assert host.stop_requested.is_set()
    finally:
        host.control.close()
        host.lease.close()
        host.log.close()


def test_child_restart_publishes_new_route_without_reopening_browser(tmp_path, monkeypatch):
    events, browsers = [], []
    counts = {'API': 0, 'Frontend': 0, 'Gateway': 0}
    class Owner:
        dead = False
        def poll(self):
            return 41 if self.dead else None
    class Service:
        def __init__(self, name, command, **options):
            self.name, self.owner = name, Owner()
            counts[name] += 1
            events.append(('start', name, counts[name]))
        def wait_ready(self, stopping):
            return {'ready': True, 'port': 15000 + counts[self.name] + (100 if self.name == 'Frontend' else 0),
                    'frontendPort': 3000, 'apiPort': 8766}
        def stop(self):
            events.append(('stop', self.name))
    host = DesktopHost(layout(tmp_path), browser=True, service_factory=Service,
                       open_browser=lambda url: browsers.append(url) or True)
    monkeypatch.setattr(host_module, 'request_json', lambda *_a, **_k: {'capture': {'message': 'Waiting for game', 'running': True}})
    assert host.acquire()
    thread = threading.Thread(target=host.run)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not host.browser_opened and time.monotonic() < deadline:
            time.sleep(.02)
        host.services['API'].owner.dead = True
        while counts['API'] < 2 and time.monotonic() < deadline:
            time.sleep(.02)
        while json.loads(host.route_path.read_text())['active']['apiPort'] != 15002 and time.monotonic() < deadline:
            time.sleep(.02)
        assert counts == {'API': 2, 'Frontend': 1, 'Gateway': 1}
        assert browsers == ['http://127.0.0.1:3000']
        assert events.index(('stop', 'API')) < events.index(('start', 'API', 2))
        assert json.loads(host.route_path.read_text())['active']['apiPort'] == 15002
    finally:
        host.stop_requested.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        host.log.close()
    assert host.finished.is_set() and not host.lease.held and not host.route_path.exists()


def test_failed_descendant_cleanup_keeps_instance_lease_and_never_restarts(tmp_path):
    host = DesktopHost(layout(tmp_path), browser=False)
    assert host.acquire()
    class BadService:
        owner = type('Owner', (), {'poll': lambda self: 9})()
        def stop(self):
            raise TimeoutError('Still writing')
    host.services['API'] = BadService()
    try:
        host._shutdown()
        assert host.lease.held and not host.finished.is_set() and host.exit_code == 1
        assert 'API' in host.services
    finally:
        host.services.clear()
        host._shutdown()
        host.log.close()
