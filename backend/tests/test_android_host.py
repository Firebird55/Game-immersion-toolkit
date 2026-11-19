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
from backend.prepared_library import write_prepared_library
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


def test_android_reader_reports_existing_game_data_opening(host):
    host.game_restored[host.session] = 'restoring'
    status, result = request(host, 'GET', '/api/snapshot')
    assert status == 200
    capture = result['status']['capture']
    assert capture['phase'] == 'restoring_game_data'
    assert capture['message'] == 'Opening downloaded game data…'

def test_zzz_static_comic_uses_positioned_rows_and_owns_overlapping_dialogue(host, tmp_path):
    _, payload = fixture_library(tmp_path / 'input')
    texts = ['We have to cross the river before daylight. Keep watch.',
             'The road ahead will be difficult. Avoid the old bridge.',
             'Keep watch.']
    ids = ['Comic_' + digit * 32 for digit in 'abc']
    payload['records'] = [
        dict(payload['records'][0], text_id=identity, source_text=text, english=text,
             texts={'en': text}, dialogue_kind='comic',
             channels=['cinematic'] if index < 2 else ['cinematic', 'dialogue'])
        for index, (identity, text) in enumerate(zip(ids, texts))
    ]
    archive = write_prepared_library(payload, tmp_path / 'comic.zip',
        dict.fromkeys(ids, tmp_path / 'input' / 'tone.wav'))
    host.session.import_library(archive)
    generation = host.session.start()
    # The comic response can contain greatly separated columns and the lower
    # dialogue crop can contain just the last separately recognized sentence.
    def span(text, left, top, right, bottom):
        return {'text': text, 'confidence': .99, 'bounding_rect': {
            'x1': left, 'x2': right, 'x3': right, 'x4': left,
            'y1': top, 'y2': top, 'y3': bottom, 'y4': bottom,
        }}

    rows = [span('The road ahead will be difficult.', 600, 82, 840, 104),
            span('Avoid the old bridge.', 600, 109, 740, 130),
            span('We have to cross the river before daylight.', 270, 262, 547, 283),
            span('Keep watch.', 270, 288, 376, 309)]
    raw = json.dumps({'width': 900, 'height': 400, 'presentation_lines': rows,
        'blocks': [
            {'text': texts[1], 'rect': [600, 82, 840, 130]},
            {'text': 'We have to cross the river before daylight.', 'rect': [270, 262, 547, 283]},
            {'text': texts[2], 'rect': [270, 288, 376, 309]},
        ]})
    reported = host._accept_ocr(generation, 1, raw)
    assert [(line['text_id'], line['channel']) for line in reported] == [
        (ids[0], 'cinematic'), (ids[1], 'cinematic')]
    assert all(line['audio_source'] == 'original' for line in reported)
    assert host._accept_ocr(generation, 2, raw) == []
    assert host._accept_ocr(generation, 3, raw) == []
    assert host.session.history.count() == 2

    # A high-quality full observation owns a shared short sentence even if
    # spelling errors make the whole bubble score below that exact fragment.
    fuzzy = 'We have ta crass the riveer befare daylite. Keep watch.'
    hit, = host.session.index.match_line_groups([fuzzy])
    assert hit.text_id == ids[0] and hit.kind == 'fuzzy'
    clipped = 'We have to cross the river before day'
    hit, = host.session.index.match_line_groups([clipped])
    assert hit.text_id == ids[0] and hit.kind == 'fuzzy' and hit.english == texts[0]


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
    connection = http.client.HTTPConnection('127.0.0.1', host.server.server_port)
    connection.request('GET', '/')
    response = connection.getresponse();response.read();connection.close()
    assert response.status == 403  # Another Android app cannot mint a private session cookie.
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


def test_native_rotation_invalidates_confirmation_and_rejects_old_geometry(host, tmp_path):
    archive, _ = fixture_library(tmp_path / 'input')
    host.session.import_library(archive)
    generation = host.session.start()
    raw = json.dumps({'width': 1600, 'height': 240, 'blocks': [
        {'text': 'Follow the river beyond the bridge.', 'rect': [40, 70, 1200, 145]}]})
    assert host.accept_ocr(generation, 1, raw) == []
    rotated = json.dumps({'width': 240, 'height': 1600, 'blocks': []})
    assert host.accept_ocr(generation, 2, rotated) == []
    assert not host.session.running and host.session.generation != generation
    assert host.accept_ocr(generation, 3, raw) == []
    assert host.session.history.count() == 0
    generation = host.session.start()
    invalid = json.dumps({'width': 240, 'height': 1600, 'blocks': [
        {'text': 'Follow the river beyond the bridge.', 'rect': [-1, 0, 200, 200]}]})
    with pytest.raises(ValueError):
        host.accept_ocr(generation, 1, invalid)


def test_real_http_audio_ranges_keep_authored_original_bytes(host, tmp_path):
    archive, payload = fixture_library(tmp_path / 'input')
    host.session.import_library(archive)
    generation = host.session.start()
    text = payload['records'][0]['source_text']
    host.session.observe(generation, 1, [text], now=1)
    identity = host.session.observe(generation, 2, [text], now=1.1)[0]['id']
    original = host.session.audio_path(identity).read_bytes()
    route = f'/api/lines/{identity}/audio'
    assert request(host, 'GET', route, headers={'Range': 'bytes=0-43'}) == (206, original[:44])
    assert request(host, 'GET', route, headers={'Range': 'bytes=-20'}) == (206, original[-20:])
    assert request(host, 'GET', route, headers={'Range': 'bytes=10-'}) == (206, original[10:])
    assert request(host, 'GET', route, headers={'Range': 'bytes=999999-'}) == (416, b'')
    assert request(host, 'GET', route, headers={'Range': 'bytes=0-4,8-12'}) == (416, b'')
