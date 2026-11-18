"""Real localhost account routes with maintained services and mocked remote writes."""
import base64
import json
import threading
import uuid
import weakref
import gc
import http.client
import time
import io
from PIL import Image

import httpx
import pytest

from backend.android_host import AndroidHost
from backend.prepared_library import write_prepared_library
from backend.tests.test_android_host import request
from backend.tests.test_android_preview import BitmapAdapter
from backend.tests.test_prepared_session import fixture_library
from backend.tests.test_lexirise import FakeAPI


class Native(BitmapAdapter):
    def protect(self, value, decrypt):
        # Explicit mocked native provider. Actual crypto has its native probe.
        return base64.b64encode(bytes(n ^ 173 for n in base64.b64decode(value))).decode()


@pytest.fixture
def account_host(tmp_path):
    reader = tmp_path / 'reader';reader.mkdir()
    (reader / 'index.html').write_text('<html><head></head><body>Authored account fixture</body></html>')
    calls, apis = [], {}
    settings = {'languages': ['zh', 'en'], 'global': {'effectiveTranslationLanguage': 'en'}, 'languageSettings': {}}
    def respond(original):
        owner = 'second' if 'second' in original.headers['Authorization'] else 'first'
        assert original.headers['Authorization'].startswith('Bearer lx_')
        calls.append((original.method, original.url.path, owner))
        path = original.url.path
        if path == '/v1/settings':
            return httpx.Response(200, json=settings)
        if path == '/v1/analyze/text':
            return httpx.Response(200, json={'occurrences': [], 'stateByEntryId': {}})
        if path == '/v1/vocabulary/audio':
            assert b'RIFF' in original.content and b'voice.wav' in original.content
            return httpx.Response(200, json={'publicUrl': 'https://audio.lexirise.test/authored.wav'})
        if path == '/v1/decks':
            return httpx.Response(200, json={'decks': [{'id': 1950, 'title': 'Authored destination',
                'owner_user_id': owner, 'lang': 'zh', 'unit_type': 'sentence', 'deck_type': 'snapshot'}]})
        api = apis.setdefault(owner, FakeAPI())
        headers = dict(original.headers);headers['authorization'] = 'Bearer test-key'
        response = api(httpx.Request(original.method, original.url, headers=headers, content=original.content))
        value = response.json()
        if path == '/v1/me': value['user'] = {'id': owner, 'name': owner}
        if 'deck' in value: value['deck']['owner_user_id'] = owner
        return httpx.Response(response.status_code, json=value)
    host = AndroidHost(tmp_path / 'application', reader, Native(), enable_accounts=True,
        account_transport=httpx.MockTransport(respond))
    host.authored_calls, host.authored_apis = calls, apis
    host.authored_settings = settings
    try: yield host
    finally: host.close()


def headers(host, generation=None):
    return {'X-Toolkit-Account-Generation': str(host.account_generation if generation is None else generation),
        'X-Proxy-Transcript': 'lexirise'}


def register(host, name):
    status, result = request(host, 'POST', '/api/lexirise/accounts',
        json.dumps({'key': f'lx_{name}_authored_fixture_only', 'name': name}).encode(), headers=headers(host))
    assert status == 200
    return result['active']


def test_pinned_account_discovery_cannot_mix_settings_after_a_b_a(account_host):
    host = account_host
    first = register(host, 'first')
    old = host.account_generation
    before = request(host, 'GET', '/api/lexirise/accounts', headers=headers(host, old))
    assert before[0] == 200 and before[1]['active'] == first
    register(host, 'second')
    assert request(host, 'POST', '/api/lexirise/accounts/select',
        json.dumps({'id': first}).encode(), headers=headers(host))[0] == 200
    assert host.account_generation > old
    for route in ('/api/lexirise/accounts', '/api/lexirise/settings'):
        status, value = request(host, 'GET', route, headers=headers(host, old))
        assert status == 409 and value['state'] == 'account_generation_changed'
    status, value = request(host, 'GET', '/api/lexirise/accounts', headers=headers(host))
    assert status == 200 and value['active'] == first
    assert value['generation'] == host.account_generation


def capture(host, tmp_path, text='沿河走过桥。'):
    _, payload = fixture_library(tmp_path / 'input')
    row = payload['records'][0]
    payload['source_locale'] = row['source_locale'] = 'zh-Hans'
    row['audio_locale'] = 'zh-Hans'
    row['source_text'] = row['chinese'] = text;row['texts']['zh-Hans'] = text
    archive = write_prepared_library(payload, tmp_path / 'library.zip', {row['text_id']: tmp_path / 'input/tone.wav'})
    assert request(host, 'POST', '/api/library/import', archive.read_bytes(), headers={**headers(host),
        'X-Toolkit-Import-Id': str(uuid.uuid4()), 'Content-Type': 'application/zip'})[0] == 200
    generation = host.session.start()
    host.session.observe(generation, 1, [text], now=1)
    assert host.session.observe(generation, 2, [text], now=1.1)
    return request(host, 'GET', '/api/snapshot')[1]['lines'][0]


def test_actual_account_routes_preserve_separate_histories_and_reject_old_media_ids(account_host, tmp_path):
    host = account_host
    first = register(host, 'first');line = capture(host, tmp_path / 'first')
    original = request(host, 'GET', f"/api/lines/{line['id']}/audio")[1]
    old_generation = host.account_generation
    second = register(host, 'second')
    assert second != first and request(host, 'GET', '/api/snapshot')[1]['lines'] == []
    other = capture(host, tmp_path / 'second', '第二个账户有独立的对白。')
    assert other['id'] != line['id']
    assert request(host, 'GET', f"/api/lines/{line['id']}/audio")[0] == 409
    assert request(host, 'PATCH', f"/api/lines/{line['id']}/favorite", b'{"favorite":true}', headers=headers(host))[0] == 409
    assert request(host, 'PATCH', '/api/settings', b'{"capture_unvoiced":true}', headers=headers(host, old_generation))[0] == 409
    assert not host.session.settings.get().capture_unvoiced
    assert request(host, 'POST', '/api/lexirise/accounts/select', json.dumps({'id': first}).encode(), headers=headers(host))[0] == 200
    restored = request(host, 'GET', '/api/snapshot')[1]['lines'][0]
    assert restored['id'] != line['id'] and restored['text_id'] == line['text_id']
    assert request(host, 'GET', f"/api/lines/{restored['id']}/audio", headers={'Range': 'bytes=0-43'}) == (206, original[:44])
    assert request(host, 'GET', f"/api/lines/{line['id']}/audio")[0] == 409
    assert b'lx_first' not in host.account_sessions.accounts.path.read_bytes()


def test_same_actual_services_read_settings_analyze_select_destination_and_export_only_to_mock(account_host, tmp_path):
    host = account_host;register(host, 'first');line = capture(host, tmp_path / 'source')
    assert request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[0] == 200
    assert request(host, 'GET', '/api/lexirise/decks?language=zh', headers=headers(host))[1]['decks'][0]['id'] == 1950
    assert request(host, 'GET', f"/api/lines/{line['id']}/reading", headers=headers(host))[1]['tokens'] == []
    assert request(host, 'POST', '/api/lexirise/decks', b'{"game":"zzz","deck_id":1950,"language":"zh"}', headers=headers(host))[0] == 200
    status, result = request(host, 'POST', f"/api/lines/{line['id']}/lexirise", headers=headers(host))
    assert status == 200 and result['sent'] and result['audio_included']
    count = len(host.authored_calls)
    assert request(host, 'POST', f"/api/lines/{line['id']}/lexirise", headers=headers(host))[1]['already_sent']
    assert len(host.authored_calls) == count
    snapshot = request(host, 'GET', '/api/snapshot')[1]
    assert snapshot['lexirise']['sent'] == {f"line:{line['id']}": 1950}
    assert all(owner == 'first' for _, _, owner in host.authored_calls)


def test_requested_text_only_export_uses_omission_note_and_never_reads_audio(account_host, tmp_path, monkeypatch):
    host = account_host; register(host, 'first')
    _, payload = fixture_library(tmp_path / 'source')
    row = payload['records'][0]
    payload.update(source_locale='zh-Hans', content_mode='text')
    row.update(source_locale='zh-Hans', source_text=row['chinese'], audio_locale='zh-Hans',
        audio_omitted_by_request=True, source_voice_binding=row['audio'], audio=None,
        text_capture_verified=True)
    archive = write_prepared_library(payload, tmp_path / 'text.zip', {})
    assert request(host, 'POST', '/api/library/import', archive.read_bytes(), headers={**headers(host),
        'X-Toolkit-Import-Id': str(uuid.uuid4()), 'Content-Type': 'application/zip'})[0] == 200
    generation = host.session.start()
    host.session.observe(generation, 1, [row['source_text']], now=1)
    assert host.session.observe(generation, 2, [row['source_text']], now=1.1)
    line = request(host, 'GET', '/api/snapshot')[1]['lines'][0]
    monkeypatch.setattr(host.session, 'audio_path', lambda _: pytest.fail('Text choice must never resolve audio'))
    assert request(host, 'POST', '/api/lexirise/decks', b'{"game":"zzz","deck_id":1950,"language":"zh"}', headers=headers(host))[0] == 200
    status, result = request(host, 'POST', f"/api/lines/{line['id']}/lexirise", headers=headers(host))
    assert status == 200 and result['sent'] and not result['audio_included']
    assert not any(path == '/v1/vocabulary/audio' for _, path, _ in host.authored_calls)
    api = host.authored_apis['first']
    # The actual maintained service carries a truthful note to the mocked API.
    assert 'audio omitted by download choice' in api.items[0]['notes']
    assert 'Unvoiced' not in api.items[0]['notes'] and api.items[0]['audio_urls'] == []


def test_delayed_mocked_settings_response_is_rejected_after_account_switch(account_host):
    host = account_host;first = register(host, 'first');second = register(host, 'second')
    assert request(host, 'POST', '/api/lexirise/accounts/select', json.dumps({'id': first}).encode(), headers=headers(host))[0] == 200
    entered, release = threading.Event(), threading.Event()
    original = host.account_sessions._services.get(first)
    if original is None:
        original = host.account_sessions.pin(host.account_generation, remote=True).service
        original = host.account_sessions._services[first]
    transport = original.transport
    def respond(value):
        if value.url.path == '/v1/settings': entered.set();assert release.wait(3)
        return transport.handle_request(value)
    original.transport = httpx.MockTransport(respond)
    result = []
    worker = threading.Thread(target=lambda: result.append(request(host, 'GET', '/api/lexirise/settings', headers=headers(host))))
    worker.start();assert entered.wait(2)
    assert request(host, 'POST', '/api/lexirise/accounts/select', json.dumps({'id': second}).encode(), headers=headers(host))[0] == 200
    release.set();worker.join(3)
    assert not worker.is_alive() and result[0][0] == 409
    assert result[0][1]['state'] == 'account_request_scope_changed'


def test_scope_headers_fail_closed_without_echoing_submitted_keys(account_host):
    host = account_host;register(host, 'first')
    key = 'lx_invalid_authored_fixture_only'
    status, value = request(host, 'POST', '/api/lexirise/accounts', json.dumps({'key': key}).encode(),
        headers={'X-Proxy-Transcript': 'lexirise'})
    assert status == 409 and key not in json.dumps(value)
    assert request(host, 'POST', '/api/capture/start')[0] == 409
    assert request(host, 'GET', '/api/capture/preview.jpg?account_generation=0')[0] != 200


def test_completed_import_receipts_do_not_retain_obsolete_full_game_indices(account_host, tmp_path):
    host = account_host;register(host, 'first');capture(host, tmp_path / 'source')
    previous = weakref.ref(host.session)
    assert host.import_jobs
    register(host, 'second')
    gc.collect()
    assert previous() is None


def test_partial_http_import_cannot_commit_after_a_b_a_and_old_cancel_is_fenced(account_host, tmp_path):
    host = account_host;first = register(host, 'first');capture(host, tmp_path / 'old')
    old_session, old_generation = host.session, host.account_generation
    pointer = old_session.libraries.pointer.read_bytes()
    archive, _ = fixture_library(tmp_path / 'pending', text='This delayed upload belongs only to the earlier account activation.')
    raw = archive.read_bytes();identity = str(uuid.uuid4())
    connection = http.client.HTTPConnection('127.0.0.1', host.server.server_port, timeout=5)
    connection.putrequest('POST', '/api/library/import')
    for key, value in {**headers(host), 'Cookie': f'toolkit_session={host.cookie}',
            'Content-Length': str(len(raw)), 'X-Toolkit-Import-Id': identity}.items():
        connection.putheader(key, value)
    connection.endheaders();connection.send(raw[:80])
    deadline = time.monotonic() + 3
    while identity not in host.import_jobs and time.monotonic() < deadline: time.sleep(.01)
    assert identity in host.import_jobs
    register(host, 'second')
    assert request(host, 'POST', '/api/library/import/cancel', json.dumps({'import_id': identity}).encode(),
        headers=headers(host, old_generation))[0] == 409
    assert request(host, 'POST', '/api/lexirise/accounts/select', json.dumps({'id': first}).encode(), headers=headers(host))[0] == 200
    connection.send(raw[80:]);response = connection.getresponse();value = json.loads(response.read());connection.close()
    assert response.status == 409 and value['state'] == 'account_import_scope_changed'
    assert host.session.libraries.pointer.read_bytes() == old_session.libraries.pointer.read_bytes() == pointer


def test_old_receiver_controls_frames_and_preview_token_cannot_read_or_stop_next_account(account_host, tmp_path):
    host = account_host;register(host, 'first');capture(host, tmp_path / 'first')
    old_generation = host.account_generation
    register(host, 'second');capture(host, tmp_path / 'second')
    receiver = str(uuid.uuid4())
    control_headers = {**headers(host), 'X-Toolkit-Document-Epoch': host.document_epoch}
    value = {'id': receiver, 'revision': 1, 'action': 'start', 'expected_generation': host.session.generation}
    status, result = request(host, 'POST', '/api/capture/receiver', json.dumps(value).encode(), headers=control_headers)
    assert status == 200
    frame = io.BytesIO();Image.new('RGB', (160, 120), 'red').save(frame, format='PNG')
    frame_headers = {**control_headers, 'Content-Type': 'image/png', 'X-Toolkit-Generation': str(result['generation']),
        'X-Toolkit-Frame': '1', 'X-Toolkit-Receiver-Id': receiver, 'X-Toolkit-Receiver-Revision': '1'}
    assert request(host, 'POST', '/api/capture/frame', frame.getvalue(), headers=frame_headers)[0] == 202
    assert request(host, 'GET', f'/api/capture/preview.jpg?account_generation={host.account_generation}')[0] == 200
    assert request(host, 'GET', f'/api/capture/preview.jpg?account_generation={old_generation}')[0] != 200
    old_headers = {**control_headers, 'X-Toolkit-Account-Generation': str(old_generation)}
    stop = json.dumps({'id': receiver, 'revision': 2, 'action': 'stop'}).encode()
    assert request(host, 'POST', '/api/capture/receiver', stop, headers=old_headers)[0] == 409
    assert request(host, 'POST', '/api/capture/frame', frame.getvalue(),
        headers={**frame_headers, 'X-Toolkit-Frame': '2', 'X-Toolkit-Account-Generation': str(old_generation)})[0] == 409
    assert host.session.running and host.receiver_owner['id'] == receiver


def test_account_translation_uses_official_rows_and_never_falls_back_to_another_locale(account_host, tmp_path):
    host = account_host;register(host, 'first');line = capture(host, tmp_path / 'source')
    host.authored_settings['global']['effectiveTranslationLanguage'] = 'nl'
    assert request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[0] == 200
    current = request(host, 'GET', '/api/snapshot')[1]['lines'][0]
    assert current['translation_locale'] == 'nl' and current['translation_text'] == ''
    assert current['english'] == line['english'] and current['source_text'] == line['source_text']
    assert current['texts'] == line['texts']
    host.authored_settings['global']['effectiveTranslationLanguage'] = 'en'
    assert request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[0] == 200
    restored = request(host, 'GET', '/api/snapshot')[1]['lines'][0]
    assert restored['translation_text'] == line['english'] and restored['translation_locale'] == 'en'
