"""Real localhost ordering must fence stale receiver controls and queued frames."""
import http.client
import json
import re
import uuid

from backend.android_host import AndroidHost
from backend.tests.test_android_host import host, request, upload
from backend.tests.test_prepared_session import fixture_library


class NativeQueue:
    def __init__(self):
        self.frames = []

    def submit(self, *frame):
        self.frames.append(frame)


def ready(host, path):
    archive, _ = fixture_library(path)
    host.session.import_library(archive)
    host.native = NativeQueue()


def control(host, identity, revision, action, *, generation=None, epoch=None):
    value = {'id': identity, 'revision': revision, 'action': action}
    if action == 'start':
        value['expected_generation'] = host.session.generation if generation is None else generation
    return request(host, 'POST', '/api/capture/receiver', json.dumps(value).encode(),
        headers={'X-Toolkit-Document-Epoch': host.document_epoch if epoch is None else epoch})


def frame(host, identity, revision, generation, *, epoch=None):
    headers = {'Content-Type': 'image/png', 'X-Toolkit-Generation': str(generation), 'X-Toolkit-Frame': '1',
        'X-Toolkit-Document-Epoch': host.document_epoch if epoch is None else epoch}
    if identity is not None:
        headers.update({'X-Toolkit-Receiver-Id': identity, 'X-Toolkit-Receiver-Revision': str(revision)})
    return request(host, 'POST', '/api/capture/frame', b'authored-admission-only-fixture', headers=headers)


def test_stop_delivered_before_earlier_partial_start_fences_that_start(host, tmp_path):
    ready(host, tmp_path / 'input')
    identity = str(uuid.uuid4())
    body = json.dumps({'id': identity, 'revision': 1, 'action': 'start',
        'expected_generation': host.session.generation}).encode()
    connection = http.client.HTTPConnection('127.0.0.1', host.server.server_port, timeout=5)
    connection.putrequest('POST', '/api/capture/receiver')
    for name, value in {'Cookie': f'toolkit_session={host.cookie}',
            'X-Toolkit-Document-Epoch': host.document_epoch, 'Content-Length': str(len(body))}.items():
        connection.putheader(name, value)
    connection.endheaders();connection.send(body[:20])
    status, stopped = control(host, identity, 2, 'stop')
    assert status == 200 and not stopped['running']
    connection.send(body[20:])
    response = connection.getresponse();result = json.loads(response.read());connection.close()
    assert response.status == 409 and result['state'] == 'receiver_revision_stale'
    assert not host.session.running and host.receiver_owner is None
    assert control(host, identity, 3, 'start')[0] == 200


def test_foreign_stop_and_old_frames_cannot_take_over_new_owner(host, tmp_path):
    ready(host, tmp_path / 'input')
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    _, original = control(host, first, 1, 'start')
    assert control(host, second, 1, 'start')[0] == 409
    assert control(host, first, 2, 'stop')[0] == 200
    status, active = control(host, second, 2, 'start')
    assert status == 200 and active['running']
    status, foreign = control(host, first, 3, 'stop')
    assert status == 200 and foreign['running'] and foreign['generation'] == active['generation']
    assert frame(host, first, 1, original['generation'])[0] == 409
    assert frame(host, first, 3, active['generation'])[0] == 409
    assert frame(host, second, 1, active['generation'])[0] == 409
    assert frame(host, second, 2, active['generation'])[0] == 202
    assert len(host.native.frames) == 1
    assert host.accept_ocr(original['generation'], 3, 'not parsed for an obsolete source') == []
    assert host.session.history.count() == 0


def test_leased_receiver_rejects_unscoped_start_stop_source_and_frames(host, tmp_path):
    ready(host, tmp_path / 'input')
    _, active = control(host, str(uuid.uuid4()), 1, 'start')
    for route in ('start', 'stop', 'source'):
        status, value = request(host, 'POST', '/api/capture/' + route)
        assert status == 409 and value['generation'] == active['generation']
    assert frame(host, None, None, active['generation'])[0] == 409
    assert not host.native.frames
    assert host.session.running


def test_pause_releases_without_retiring_and_import_changes_library_scope(host, tmp_path):
    ready(host, tmp_path / 'input')
    identity = str(uuid.uuid4());epoch = host.document_epoch
    revision = host.session.snapshot()['status']['capture']['library_revision']
    assert re.fullmatch('[0-9a-f]{64}', revision)
    _, first = control(host, identity, 1, 'start')
    host.pause()
    assert host.receiver_owner is None and host.document_epoch == epoch
    assert control(host, identity, 2, 'start', generation=first['generation'])[0] == 409
    assert control(host, identity, 3, 'start')[0] == 200
    archive, _ = fixture_library(tmp_path / 'update', text='The next normal update keeps its new complete sentence.')
    assert upload(host, archive, str(uuid.uuid4()))[0] == 200
    assert host.receiver_owner is None and not host.session.running
    current = host.session.snapshot()['status']['capture']['library_revision']
    assert current != revision and re.fullmatch('[0-9a-f]{64}', current)
    assert control(host, identity, 4, 'start')[0] == 200


def test_document_replacement_retires_old_ids_without_mutating_on_asset_or_snapshot_fetch(host, tmp_path):
    ready(host, tmp_path / 'input')
    _, html = request(host, 'GET', '/', headers={'Sec-Fetch-Dest': 'document'})
    epoch = host.document_epoch
    assert f'name="toolkit-document-epoch" content="{epoch}"'.encode() in html
    identity = str(uuid.uuid4())
    _, first = control(host, identity, 1, 'start')
    request(host, 'GET', '/api/snapshot')
    request(host, 'GET', '/missing.png', headers={'Sec-Fetch-Dest': 'image'})
    request(host, 'GET', '/', headers={'Sec-Fetch-Dest': 'empty'})
    assert host.session.generation == first['generation'] and host.session.running
    request(host, 'GET', '/index.html', headers={'Sec-Fetch-Dest': 'document'})
    assert host.document_epoch != epoch and host.receiver_owner is None and not host.session.running
    assert control(host, identity, 2, 'start', epoch=epoch)[0] == 409
    assert control(host, identity, 3, 'start')[1]['state'] == 'receiver_document_retired'
    fresh = str(uuid.uuid4())
    _, active = control(host, fresh, 1, 'start')
    assert control(host, identity, 4, 'stop', epoch=epoch)[0] == 409
    assert host.session.generation == active['generation'] and host.session.running


def test_bad_document_and_repeated_revision_do_not_publish_a_new_capture(host, tmp_path):
    ready(host, tmp_path / 'input')
    identity = str(uuid.uuid4())
    assert control(host, identity, 1, 'start', epoch='obsolete-document')[0] == 409
    assert identity not in host.receiver_revisions
    generation = host.session.generation
    assert control(host, identity, 5, 'start', generation=generation - 1)[0] == 409
    assert control(host, identity, 4, 'start')[0] == 409
    assert not host.session.running
    _, accepted = control(host, identity, 6, 'start')
    assert control(host, identity, 6, 'stop')[0] == 409
    assert host.session.generation == accepted['generation'] and host.session.running


def test_receiver_registry_never_evicts_stop_tombstones(host):
    identities = [str(uuid.uuid4()) for _ in range(128)]
    for identity in identities:
        assert control(host, identity, 1, 'stop')[0] == 200
    status, value = control(host, str(uuid.uuid4()), 1, 'stop')
    assert status == 409 and value['state'] == 'receiver_registry_full'
    assert 'Reopen the app' in value['detail']
    assert control(host, identities[0], 2, 'stop')[0] == 200
    assert control(host, identities[0], 1, 'start')[0] == 409
    assert len(host.receiver_revisions) == 128


def test_process_restart_resets_registry_and_rejects_previous_cookie(tmp_path):
    frontend = tmp_path / 'reader';frontend.mkdir()
    (frontend / 'index.html').write_text('<html><head></head><body>Authored</body></html>')
    first = AndroidHost(tmp_path / 'application', frontend)
    identity = str(uuid.uuid4())
    try:
        assert control(first, identity, 4, 'stop')[0] == 200
        cookie, epoch = first.cookie, first.document_epoch
    finally:
        first.close()
    second = AndroidHost(tmp_path / 'application', frontend)
    try:
        assert second.document_epoch != epoch and not second.session.running
        assert request(second, 'GET', '/api/platform', headers={'Cookie': f'toolkit_session={cookie}'})[0] == 403
        assert control(second, identity, 1, 'stop')[0] == 200
        assert second.platform()['receiver_protocol'] == 'leased-frames-v1'
    finally:
        second.close()
