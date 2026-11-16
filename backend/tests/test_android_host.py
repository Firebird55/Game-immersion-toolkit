"""The app-local HTTP boundary cannot turn aborts or late cancellation into rollback."""
import http.client
import json
from pathlib import Path
import socket
import threading
import time
import uuid

import pytest

from backend.android_host import AndroidHost
from backend.tests.test_prepared_session import fixture_library


@pytest.fixture
def host(tmp_path):
    frontend = tmp_path / 'reader';frontend.mkdir()
    (frontend / 'index.html').write_text('<html><head></head><body>Authored reader fixture</body></html>')
    value = AndroidHost(tmp_path / 'application', frontend)
    try:
        yield value
    finally:
        value.close()


def request(host, method, path, body=b'', *, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', host.server.server_port, timeout=5)
    connection.request(method, path, body=body, headers={
        'Cookie': f'toolkit_session={host.cookie}', **(headers or {})})
    response = connection.getresponse();data = response.read();status = response.status
    connection.close()
    return status, json.loads(data) if response.getheader('Content-Type', '').startswith('application/json') else data


def upload(host, path, identity):
    return request(host, 'POST', '/api/library/import', path.read_bytes(),
        headers={'Content-Type': 'application/zip', 'X-Toolkit-Import-Id': identity})


def test_cancel_before_server_register_is_not_forgotten(host, tmp_path):
    archive, _ = fixture_library(tmp_path / 'input')
    identity = str(uuid.uuid4())
    status, result = request(host, 'POST', '/api/library/import/cancel', json.dumps({'import_id': identity}).encode())
    assert status == 200 and result['cancelled'] and not result['already_committed']
    assert upload(host, archive, identity)[0] == 400
    assert host.session.libraries.current() is None


def test_late_cancel_reports_commit_and_never_claims_previous_library_kept(host, tmp_path):
    archive, _ = fixture_library(tmp_path / 'input')
    identity = str(uuid.uuid4())
    assert upload(host, archive, identity)[0] == 200
    pointer = host.session.libraries.pointer.read_bytes()
    status, result = request(host, 'POST', '/api/library/import/cancel', json.dumps({'import_id': identity}).encode())
    assert status == 409 and result['already_committed'] and not result['cancelled']
    assert host.session.libraries.pointer.read_bytes() == pointer


def test_real_http_cancel_can_run_while_upload_is_waiting_for_bytes(host, tmp_path):
    first, _ = fixture_library(tmp_path / 'old')
    assert upload(host, first, str(uuid.uuid4()))[0] == 200
    old = host.session.libraries.pointer.read_bytes()
    archive, _ = fixture_library(tmp_path / 'new', text='The new chapter has a new sentence.')
    identity = str(uuid.uuid4());raw = archive.read_bytes()
    connection = http.client.HTTPConnection('127.0.0.1', host.server.server_port, timeout=5)
    connection.putrequest('POST', '/api/library/import')
    for key, value in {'Cookie': f'toolkit_session={host.cookie}', 'Content-Type': 'application/zip',
            'Content-Length': str(len(raw)), 'X-Toolkit-Import-Id': identity}.items():
        connection.putheader(key, value)
    connection.endheaders();connection.send(raw[:80])
    deadline = time.monotonic() + 3
    while identity not in host.import_jobs and time.monotonic() < deadline:
        time.sleep(.01)
    assert host.import_jobs[identity]['working']
    status, result = request(host, 'POST', '/api/library/import/cancel', json.dumps({'import_id': identity}).encode())
    assert status == 200 and result['cancelled']
    connection.sock.shutdown(socket.SHUT_RDWR);connection.close()
    deadline = time.monotonic() + 3
    while host.import_jobs[identity]['working'] and time.monotonic() < deadline:
        time.sleep(.01)
    assert not host.import_jobs[identity]['working']
    assert host.session.libraries.pointer.read_bytes() == old


def test_cancel_racing_real_atomic_pointer_swap_observes_committed(host, tmp_path, monkeypatch):
    archive, _ = fixture_library(tmp_path / 'input')
    identity = str(uuid.uuid4());job = host._import_job(identity, register=True)
    started, done = threading.Event(), threading.Event();result = []
    def cancel():
        started.set();result.append(host.cancel_import(identity));done.set()
    thread = threading.Thread(target=cancel)
    original_replace = Path.replace
    def replace(path, target):
        if target == host.session.libraries.pointer:
            thread.start();assert started.wait(1)
            assert not done.wait(.03)  # Atomic-publication owner already won.
        return original_replace(path, target)
    monkeypatch.setattr(Path, 'replace', replace)
    host.session.import_library(archive, cancelled=job['cancel'].is_set,
        publish_guard=lambda: host.publish_import(job))
    thread.join(3)
    assert not thread.is_alive() and result[0][1] == 409
    assert result[0][0]['already_committed'] and host.session.libraries.current().is_dir()


def test_app_origin_cookie_and_reader_meta_are_real_http_contracts(host):
    status, html = request(host, 'GET', '/')
    assert status == 200 and b'toolkit-host-platform' in html and b'android' in html
    status, _ = request(host, 'PATCH', '/api/settings', b'{"capture_unvoiced":true}',
        headers={'Origin': 'https://unrelated.invalid'})
    assert status == 403 and not host.session.settings.get().capture_unvoiced
    connection = http.client.HTTPConnection('127.0.0.1', host.server.server_port)
    connection.request('GET', '/api/snapshot')
    response = connection.getresponse();response.read();connection.close()
    assert response.status == 403
    status, value = request(host, 'GET', '/api/snapshot')
    assert status == 200 and value['context']['state_version'] == 0


def test_cancel_receipts_are_bounded_without_resurrecting_old_cancelled_ids(host):
    first = str(uuid.uuid4())
    host.cancel_import(first)
    for _ in range(127):
        host.cancel_import(str(uuid.uuid4()))
    with pytest.raises(ValueError):
        host.cancel_import(str(uuid.uuid4()))
    assert host.cancel_import(first)[0]['cancelled']
    assert len(host.import_jobs) == 128
