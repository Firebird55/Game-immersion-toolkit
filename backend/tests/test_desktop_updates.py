"""Ordering/failure and real copied-store tests, not frozen native acceptance."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

from backend import desktop_host as hosts
from backend import desktop_updates as updates
from backend.desktop_control import configure_updates, host_status, request_update
from backend.runtime_bundle import RuntimeLayout, EXPERIMENT_CHILDREN


def layout(root, version='1.0.0'):
    app = root / ('app-' + version)
    app.mkdir(exist_ok=True)
    executable = app / 'runtime.exe'
    executable.write_bytes(b'authored nonexecutable fixture')
    user = root / 'user'
    return RuntimeLayout(mode='bundle', application_root=app, resource_root=app,
        executable=executable, version=version, children=EXPERIMENT_CHILDREN,
        settings_root=user, data_root=user / 'data', cache_root=user / 'cache',
        tool_root=user / 'tools', work_root=user / 'work', state_root=user / 'state',
        default_export_root=user / 'exports', profile='runtime')


def test_closed_state_copy_keeps_sqlite_favorites_and_private_test_credentials_isolated(tmp_path):
    current = layout(tmp_path)
    current.data_root.mkdir(parents=True)
    (current.settings_root / 'credentials').mkdir()
    (current.settings_root / 'credentials/protected-key').write_bytes(b'protected-TEST-only')
    (current.settings_root / 'settings.json').write_text('{"preferred_game":"zzz"}')
    (current.data_root / 'companion-operation.lock').write_text('lease must not copy')
    current.default_export_root.mkdir()
    (current.default_export_root / 'saved-library').write_bytes(b'complete library')
    connection = sqlite3.connect(current.data_root / 'transcript-v2.db')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('CREATE TABLE favorites(id INTEGER PRIMARY KEY, sentence TEXT)')
    connection.execute('INSERT INTO favorites VALUES(1, ?)', ('测试',))
    connection.commit()
    connection.close()
    copied = updates.copy_test_state(current, threading.Event())
    assert copied.settings_root != current.settings_root
    with sqlite3.connect(copied.data_root / 'transcript-v2.db') as database:
        assert database.execute('SELECT sentence FROM favorites').fetchone() == ('测试',)
        database.execute('DELETE FROM favorites')
    with sqlite3.connect(current.data_root / 'transcript-v2.db') as database:
        assert database.execute('SELECT count(*) FROM favorites').fetchone() == (1,)
    assert not (copied.data_root / 'companion-operation.lock').exists()
    assert list(copied.default_export_root.iterdir()) == []
    assert (copied.settings_root / 'credentials/protected-key').read_bytes() == b'protected-TEST-only'
    assert copied.settings_root.stat().st_mode & 0o077 == 0 if __import__('os').name != 'nt' else True


def test_snapshot_rejects_size_overflow_and_cancellation(tmp_path):
    current = layout(tmp_path)
    current.data_root.mkdir(parents=True)
    (current.data_root / 'state').write_bytes(b'12345')
    with pytest.raises(updates.UpdateError, match='bounded'):
        updates.copy_test_state(current, threading.Event(), max_bytes=4)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(updates.UpdateError, match='cancelled'):
        updates.copy_test_state(current, cancelled)


@pytest.fixture
def transaction(tmp_path, monkeypatch):
    old, new = layout(tmp_path), layout(tmp_path, '1.0.1')
    candidate = SimpleNamespace(layout=new, slot_root=new.application_root, frontend_root=new.resource_root / 'desktop',
        receipt_digest='a' * 64, storage_epoch=1, host_protocol=1)
    events, failures = [], {}
    class Service:
        def __init__(self, name, command, **options):
            self.name, self.owner = name, SimpleNamespace(poll=lambda: None)
            events.append(('start', name, options['env'].get('PROXY_TRANSCRIPT_STANDBY')))
        def wait_ready(self, _stop):
            return {'ready': True, 'port': 20000 + len(events)}
        def stop(self):
            events.append(('stop', self.name))
            if failures.get('stop') == self.name:
                raise TimeoutError('Authored descendant remains alive')
    host = hosts.DesktopHost(old, frontend_root=old.resource_root / 'desktop', service_factory=Service, browser=False)
    assert host.acquire()
    host._start('API')
    host._start('Frontend')
    host._publish()
    original_copy = updates.copy_test_state
    def copy(current, stop):
        events.append(('copy',))
        assert ('stop', 'API') in events
        assert 'API' not in host.services
        return original_copy(current, stop)
    monkeypatch.setattr(updates, 'copy_test_state', copy)
    def http(port, path, **options):
        events.append(('http', path, options.get('payload')))
        if failures.get('http') == path:
            failures.pop('http')
            raise TimeoutError('Authored API failure')
        if path == '/api/status':
            return {'capture': {'running': True, 'active_game': 'zzz'}}
        if path == '/api/runtime/quiesce':
            return {'running': True, 'session_id': 'TEST-session', 'last_emitted_key_by_channel': {'dialogue': 'TEST-line'}}
        if path.startswith('/api/runtime/ready'):
            return {'ready': True, 'standby': True}
        if path == '/api/runtime/activate':
            return {'active': True}
        raise AssertionError(path)
    monkeypatch.setattr(hosts, 'request_json', http)
    try:
        yield host, candidate, events, failures
    finally:
        failures.clear()
        host._shutdown()
        assert host.finished.is_set()
        host.log.close()


def test_update_stops_writer_before_copy_then_warms_both_copies_and_transfers_state(transaction):
    host, candidate, events, _ = transaction
    host.install_update(candidate)
    assert host.layout.version == '1.0.1' and host.lease.held
    assert events.index(('stop', 'API')) < events.index(('copy',))
    assert events.index(('stop', 'Candidate test API')) < events.index(('start', 'Candidate API', '1'))
    assert ('http', '/api/runtime/ready?game=zzz', None) in events
    activation = next(event[2] for event in events if event[:2] == ('http', '/api/runtime/activate'))
    assert activation['session_id'] == 'TEST-session' and activation['last_emitted_key_by_channel'] == {'dialogue': 'TEST-line'}
    assert host.retained_frontends == [candidate.layout.application_root.parent / 'app-1.0.0/desktop']
    route = json.loads(host.route_path.read_text())
    assert route['active']['apiPort'] == host.ports['API']
    assert set(host.services) == {'API', 'Frontend'}
    assert host.updates.status()['state'] == 'installed'


@pytest.mark.parametrize('failure', ['/api/runtime/quiesce', '/api/runtime/activate'])
def test_failed_handoff_retires_candidate_before_restart_previous_without_restoring_data(transaction, failure):
    host, candidate, events, failures = transaction
    failures['http'] = failure
    host.install_update(candidate)
    assert host.layout.version == '1.0.0' and host.lease.held
    assert set(host.services) == {'API', 'Frontend'}
    assert not (host.updates.home / 'active-slot.json').exists()
    assert ('start', 'API', '1') in events
    if failure.endswith('activate'):
        assert events.index(('stop', 'Candidate API')) < events.index(('start', 'API', '1'))
    assert host.updates.status()['state'] == 'error'


def test_unknown_descendant_lifetime_forbids_snapshot_and_replacement(transaction):
    host, candidate, events, failures = transaction
    failures['stop'] = 'API'
    with pytest.raises(TimeoutError):
        host.install_update(candidate)
    assert ('copy',) not in events and ('start', 'Candidate API', '1') not in events
    assert host.lease.held and 'API' in host.services


def test_epoch_mismatch_rejected_before_any_service_spawn(transaction):
    host, candidate, events, _ = transaction
    candidate.storage_epoch = 2
    before = list(events)
    with pytest.raises(updates.UpdateError, match='storage'):
        host.install_update(candidate)
    assert before == events and host.lease.held


def test_authenticated_host_update_queues_once_and_preferences_are_persisted(transaction):
    host, _candidate, _events, _ = transaction
    gate = threading.Event()
    def prepare(*_):
        gate.wait(3)
        return None
    host.updates.prepare = prepare
    assert configure_updates(False, layout=host.layout)['enabled'] is False
    assert json.loads((host.updates.home / 'preferences.json').read_text()) == {'enabled': False}
    try:
        assert request_update(layout=host.layout)['started'] is True
        assert request_update(layout=host.layout)['started'] is False
        assert host_status(layout=host.layout)['state'] == 'checking'
    finally:
        gate.set()
        host.updates.thread.join(3)


def test_restart_revalidates_selected_runtime_before_starting_services_and_retains_initial_chunks(transaction, monkeypatch):
    from backend import desktop_release
    host, candidate, events, _ = transaction
    previous, previous_frontend = host.layout, host.frontend_root
    host.install_update(candidate)
    host._shutdown()
    calls = []
    def verify(layout, slot, receipt):
        calls.append((slot, receipt))
        assert layout.data_root == previous.data_root
        return candidate
    monkeypatch.setattr(desktop_release, 'verify_selected', verify)
    restarted = hosts.DesktopHost(previous, frontend_root=previous_frontend, browser=False)
    try:
        before = list(events)
        assert restarted.acquire()
        assert before == events
        assert restarted.layout == candidate.layout
        assert restarted.retained_frontends == [previous_frontend]
        assert calls == [(candidate.slot_root, candidate.receipt_digest)]
    finally:
        restarted._shutdown()
        restarted.log.close()


def test_unknown_saved_storage_epoch_fails_before_services_and_releases_unused_lease(tmp_path):
    from backend.bundle_host import ExclusiveFileLease
    current = layout(tmp_path)
    home = current.state_root / 'desktop-updates'
    home.mkdir(parents=True)
    (home / 'storage-contract.json').write_text('{"storage_epoch":2,"host_protocol":1}')
    host = hosts.DesktopHost(current, browser=False)
    with pytest.raises(updates.UpdateError, match='different storage'):
        host.acquire()
    assert not host.services and not host.lease.held
    lease = ExclusiveFileLease(host.lease.path)
    lease.acquire()
    lease.close()


def test_newer_installer_is_not_downgraded_by_saved_automatic_selection(transaction, monkeypatch):
    from backend import desktop_release
    host, candidate, _, _ = transaction
    host.install_update(candidate)
    host._shutdown()
    installed = layout(candidate.layout.application_root.parent, '2.0.0')
    monkeypatch.setattr(desktop_release, 'verify_selected', lambda *_: candidate)
    restarted = hosts.DesktopHost(installed, frontend_root=installed.resource_root / 'desktop', browser=False)
    try:
        assert restarted.acquire()
        assert restarted.layout.version == '2.0.0'
        assert restarted.retained_frontends == [candidate.frontend_root]
        assert restarted.selected_slot is None
    finally:
        restarted._shutdown()
        restarted.log.close()
