"""Normal protected startup keeps local data and never adopts desktop credentials."""
import json
import threading
import uuid

import httpx
import pytest

from backend import android_host
from backend.android_authored_accounts import KEYS, transport
from backend.prepared_session import PreparedCaptureSession
from backend.tests.android_recovery_sqlite_evidence import application_profiles, sqlite_profiles
from backend.tests.test_android_account_recovery import AuthoredProvider
from backend.tests.test_android_host import request
from backend.tests.test_prepared_session import fixture_library


class NormalProvider(AuthoredProvider):
    def protectAuthored(self, *args):
        pytest.fail('Normal startup used the DEBUG credential alias')

    def assertAuthoredAccounts(self):
        pytest.fail('Normal startup entered the DEBUG fixture')


@pytest.fixture
def normal(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', lambda *args: pytest.fail('A startup test attempted live network'))
    from backend import lexirise
    monkeypatch.setattr(lexirise, '_protect', lambda *args, **kwargs: pytest.fail('Android adopted a desktop credential'))
    monkeypatch.setenv('LEXIRISE_API_KEY', 'lx_environment_only_authored_fixture_must_be_ignored')
    reader = tmp_path / 'reader';reader.mkdir()
    (reader / 'index.html').write_text('<html><head></head><body>Authored normal reader</body></html>')
    calls = [];inner = transport();state = {'offline': False}
    def reply(request):
        calls.append((request.method, request.url.path))
        assert request.method == 'GET', 'Startup cannot authorize remote writes'
        if state['offline']:
            raise httpx.ConnectError('Authored offline fixture', request=request)
        if state.get('delay') and request.url.path == '/v1/settings':
            entered, release = state['delay'];entered.set()
            assert release.wait(5)
        return inner.handle_request(request)
    host = None
    def start(root, provider=None):
        nonlocal host
        if host is not None:
            host.close()
        host = android_host.AndroidHost(root, reader, provider or NormalProvider(), enable_accounts=True,
            account_transport=httpx.MockTransport(reply))
        return host
    yield start, calls, state, reader
    if host is not None:
        host.close()


def seed_legacy(root, tmp_path):
    archive, payload = fixture_library(tmp_path / 'authored-input')
    session = PreparedCaptureSession(root);session.import_library(archive);generation = session.start()
    text = payload['records'][0]['source_text']
    session.observe(generation, 1, [text], now=1);line = session.observe(generation, 2, [text], now=1.1)[0]
    session.history.set_favorite(line['id'], True);session.update_settings({'capture_unvoiced': True})
    return session, archive


def headers(host):
    return {'Content-Type': 'application/json', 'X-Proxy-Transcript': 'lexirise',
        'X-Toolkit-Account-Generation': str(host.account_generation)}


def test_normal_provider_retains_legacy_chinese_history_library_favorite_voice_and_settings(normal, tmp_path):
    start, calls, _, _ = normal
    # Put the app root under this authored fixture's profiles directory solely
    # so the read-only complete-database evidence helper can inspect it too.
    root = tmp_path / 'profiles' / 'legacy-application'
    old, archive = seed_legacy(root, tmp_path)
    before = old.snapshot()['lines'];audio = old.audio_path(1).read_bytes()
    database = application_profiles(sqlite_profiles(tmp_path))
    obsolete = root / 'lexirise/key.dpapi';obsolete.parent.mkdir();obsolete.write_bytes(b'authored desktop-only opaque blob')
    native = NormalProvider();host = start(root, native)
    for route in ('/api/platform', '/api/snapshot', '/api/status', '/api/lexirise/accounts', '/api/settings'):
        assert request(host, 'GET', route)[0] == 200
    platform = host.platform();snapshot = host.snapshot()
    assert platform['protected_accounts'] and platform['account_protocol'] == 'scoped-accounts-v1'
    assert platform['authored_account_fixture'] is False and platform['account_recovery'] is None
    assert host.session.root == root and snapshot['lexirise'] == {'configured': False, 'sent': {}, 'account': 'legacy'}
    assert snapshot['lines'] == before and snapshot['lines'][0]['chinese'] == '沿河走过桥。'
    assert host.session.settings.get().capture_unvoiced and request(host, 'GET', '/api/lines/1/audio')[1] == audio
    assert application_profiles(sqlite_profiles(tmp_path)) == database
    assert obsolete.read_bytes() == b'authored desktop-only opaque blob'
    assert not (root / 'credentials/accounts.gcm').exists() and calls == [] and native.decrypt_calls == 0
    assert request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[0] == 400
    assert calls == []  # Even an explicit read cannot adopt the environment key.
    # Local capture/import/preview control remains independent of any account.
    assert request(host, 'POST', '/api/capture/start', headers=headers(host))[0] == 200
    generation = host.session.generation;host.pause()
    assert host.session.generation > generation and not host.session.running
    assert host.frame_admissions._pending == {} and host.preview_frame is None
    assert request(host, 'POST', '/api/library/import', archive.read_bytes(), headers={
        **headers(host), 'Content-Type': 'application/zip', 'X-Toolkit-Import-Id': str(uuid.uuid4())})[0] == 200
    assert calls == []


def test_saved_owner_reopens_locally_and_prior_read_authorization_survives_restart(normal, tmp_path):
    start, calls, state, _ = normal;root = tmp_path / 'application';native = NormalProvider()
    host = start(root, native)
    status, owner = request(host, 'POST', '/api/lexirise/accounts', json.dumps({'key': KEYS[0]}).encode(), headers=headers(host))
    assert status == 200 and calls == [('GET', '/v1/me')]
    archive, _ = fixture_library(tmp_path / 'authored-input')
    host.session.import_library(archive)
    host.snapshot();calls.clear();state['offline'] = True
    host = start(root, native)
    assert host.snapshot()['lexirise']['configured'] and host.account_sessions.status()['active'] == owner['active']
    assert host.session.index.ready and not host.session.running and calls == []
    # A restored, explicitly saved owner can perform ordinary settings reads;
    # network failure does not block its local library, settings or capture.
    assert request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[0] == 400
    assert calls and all(method == 'GET' for method, _ in calls)
    assert host.snapshot()['status']['textmaps']['ready']
    assert request(host, 'PATCH', '/api/settings', b'{"capture_unvoiced":true}', headers=headers(host))[0] == 200
    assert request(host, 'POST', '/api/capture/start', headers=headers(host))[0] == 200
    host.pause();state['offline'] = False;calls.clear()
    assert request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[0] == 200
    assert calls and all(method == 'GET' for method, _ in calls)


def test_locked_normal_store_keeps_existing_data_private_and_original_bytes_untouched(normal, tmp_path):
    start, calls, _, _ = normal;root = tmp_path / 'application';old, _ = seed_legacy(root, tmp_path)
    credential = root / 'credentials/accounts.gcm';credential.parent.mkdir();credential.write_bytes(b'authored corrupt normal credential store')
    originals = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    host = start(root)
    assert host.platform()['protected_accounts'] and host.platform()['library_import'] is False
    assert host.platform()['account_recovery']['state'] == 'credentials_unreadable'
    assert host.snapshot()['lines'] == [] and host.snapshot()['lexirise']['account'] == 'recovery'
    assert request(host, 'GET', '/api/lines/1/audio')[0] == 409
    assert request(host, 'POST', '/api/capture/start', headers=headers(host))[0] == 409
    host.pause()
    assert all(path.read_bytes() == raw for path, raw in originals.items()) and calls == []


def test_waiting_remote_settings_does_not_block_local_snapshot_capture_or_import(normal, tmp_path):
    start, _, state, _ = normal;host = start(tmp_path / 'application')
    assert request(host, 'POST', '/api/lexirise/accounts', json.dumps({'key': KEYS[0]}).encode(), headers=headers(host))[0] == 200
    archive, _ = fixture_library(tmp_path / 'authored-input');host.session.import_library(archive)
    entered, release = threading.Event(), threading.Event();state['delay'] = entered, release
    result = []
    worker = threading.Thread(target=lambda: result.append(request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[0]))
    worker.start()
    try:
        assert entered.wait(3)
        assert request(host, 'GET', '/api/snapshot')[0] == 200
        assert request(host, 'POST', '/api/capture/start', headers=headers(host))[0] == 200
        assert request(host, 'POST', '/api/library/import', archive.read_bytes(), headers={
            **headers(host), 'Content-Type': 'application/zip', 'X-Toolkit-Import-Id': str(uuid.uuid4())})[0] == 200
    finally:
        release.set();worker.join(5)
    assert not worker.is_alive() and result == [200]


def test_native_entry_point_cannot_downgrade_the_existing_protected_host(normal, tmp_path, monkeypatch):
    _, calls, _, reader = normal
    monkeypatch.setattr(android_host, '_host', None)
    root = tmp_path / 'application';native = NormalProvider()
    address = android_host.start(root, reader, native, enable_accounts=True)
    host = android_host._host
    try:
        assert host.platform()['protected_accounts'] and not host.platform()['authored_account_fixture']
        assert android_host.start(root, reader, native, enable_accounts=True) == address
        with pytest.raises(ValueError, match='startup mode'):
            android_host.start(root, reader, native, enable_accounts=False)
        assert android_host._host is host and host.platform()['protected_accounts'] and calls == []
    finally:
        host.close();android_host._host = None
