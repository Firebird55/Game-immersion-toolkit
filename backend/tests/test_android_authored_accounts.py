"""Exercise the same account UI API with immutable, network-free native fixtures."""
import base64
import json

import httpx
import pytest

from backend.android_authored_accounts import KEYS, transport
from backend.android_host import AndroidHost
from backend.tests.test_android_account_http import capture, headers
from backend.tests.test_android_host import request


class Native:
    def __init__(self):
        self.authorizations = self.blobs = 0

    def assertAuthoredAccounts(self):
        self.authorizations += 1

    def protect(self, *args):
        pytest.fail('The authored UI accessed the production credential alias')

    def protectAuthored(self, encoded, decrypt):
        self.blobs += 1
        # Explicit desktop mock; actual Android uses the separate Keystore alias.
        return base64.b64encode(bytes(n ^ 173 for n in base64.b64decode(encoded))).decode()


def test_actual_ui_routes_isolate_owners_history_settings_reading_and_mocked_exports(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', lambda *args: pytest.fail('An authored account attempted live network'))
    reader = tmp_path / 'reader';reader.mkdir()
    (reader / 'index.html').write_text('<html><head></head><body>Authored fixture</body></html>')
    native = Native()
    host = AndroidHost(tmp_path / 'authored-account-ui', reader, native, authored_accounts=True)
    try:
        assert native.authorizations == 1
        assert request(host, 'GET', '/api/platform')[1]['authored_account_fixture'] is True
        def register(key):
            status, value = request(host, 'POST', '/api/lexirise/accounts',
                json.dumps({'key': key}).encode(), headers=headers(host))
            assert status == 200
            return value['active']
        first = register(KEYS[0])
        line = capture(host, tmp_path / 'first')
        original = request(host, 'GET', f"/api/lines/{line['id']}/audio")[1]
        assert original[:4] == b'RIFF'
        assert request(host, 'PATCH', '/api/lexirise/settings',
            b'{"global":{"translationLanguage":"ja"}}', headers=headers(host))[0] == 200
        assert request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[1]['global']['translationLanguage'] == 'ja'
        status, analysis = request(host, 'GET', f"/api/lines/{line['id']}/reading", headers=headers(host))
        assert status == 200 and analysis['tokens']
        assert analysis['tokens'][0]['meaning'] == 'Authored fixture definition'
        status, _ = request(host, 'POST', '/api/lexirise/decks', b'{"game":"zzz","create":true}', headers=headers(host))
        assert status == 200
        status, exported = request(host, 'POST', f"/api/lines/{line['id']}/lexirise", headers=headers(host))
        assert status == 200 and exported['sent'] and exported['audio_included']
        old_generation = host.account_generation
        second = register(KEYS[1])
        assert first != second and request(host, 'GET', '/api/snapshot')[1]['lines'] == []
        assert request(host, 'GET', '/api/lexirise/settings', headers=headers(host))[1]['global']['translationLanguage'] == 'en'
        assert request(host, 'GET', '/api/lexirise/decks', headers=headers(host))[1]['decks'] == []
        assert request(host, 'GET', f"/api/lines/{line['id']}/audio")[0] == 409
        assert request(host, 'PATCH', '/api/settings', b'{"capture_unvoiced":true}', headers=headers(host, old_generation))[0] == 409
        assert request(host, 'POST', '/api/lexirise/accounts/select', json.dumps({'id': first}).encode(), headers=headers(host))[0] == 200
        restored = request(host, 'GET', '/api/snapshot')[1]['lines'][0]
        assert restored['id'] != line['id']
        assert request(host, 'GET', f"/api/lines/{restored['id']}/audio")[1] == original
        assert request(host, 'POST', f"/api/lines/{restored['id']}/lexirise", headers=headers(host))[1]['already_sent']
        assert native.blobs > 0 and KEYS[0].encode() not in host.account_sessions.accounts.path.read_bytes()
        status, error = request(host, 'POST', '/api/lexirise/accounts',
            b'{"key":"lx_unrecognized_real_key_must_never_be_accepted"}', headers=headers(host))
        assert status == 400 and 'lx_' not in json.dumps(error)
        assert len(host.account_sessions.status()['profiles']) == 2
    finally:
        host.close()
    reopened = AndroidHost(tmp_path / 'authored-account-ui', reader, native, authored_accounts=True)
    try:
        assert reopened.account_sessions.status()['active'] == first
        assert reopened.session.history.count() == 1 and not reopened.session.running
        assert not (tmp_path / 'toolkit').exists()
    finally:
        reopened.close()


def test_authored_startup_requires_native_debug_authorization_before_storage(tmp_path):
    class Release(Native):
        def assertAuthoredAccounts(self):
            raise RuntimeError('Debug mode unavailable')
    with pytest.raises(RuntimeError):
        AndroidHost(tmp_path / 'never-created', tmp_path, Release(), authored_accounts=True)
    assert not (tmp_path / 'never-created').exists()
    with pytest.raises(ValueError):
        AndroidHost(tmp_path / 'never-created', tmp_path, Native(), authored_accounts=True, account_transport=transport())


def test_fixture_transport_rejects_unknown_keys_hosts_and_unimplemented_mutations():
    with httpx.Client(transport=transport()) as client:
        for host, key, expected in [('api.lexirise.app', 'lx_real_key', 401), ('unexpected.invalid', KEYS[0], 403)]:
            assert client.get('https://' + host + '/v1/me', headers={'Authorization': 'Bearer ' + key}).status_code == expected
        assert client.post('https://api.lexirise.app/v1/unknown', headers={'Authorization': 'Bearer ' + KEYS[0]}).status_code == 404


@pytest.mark.parametrize('authored', [False, True])
def test_existing_native_host_cannot_adopt_a_different_mode_or_private_root(tmp_path, monkeypatch, authored):
    from backend import android_host
    monkeypatch.setattr(android_host, '_host', None)
    root = tmp_path / 'private'
    address = android_host.start(root, tmp_path, Native(), authored_accounts=authored)
    host = android_host._host
    try:
        assert android_host.start(root, tmp_path, Native(), authored_accounts=authored) == address
        with pytest.raises(ValueError, match='startup mode'):
            android_host.start(root, tmp_path, Native(), authored_accounts=not authored)
        with pytest.raises(ValueError, match='startup mode'):
            android_host.start(tmp_path / 'different-root', tmp_path, Native(), authored_accounts=authored)
        assert android_host._host is host and host.authored_accounts is authored
        assert not (tmp_path / 'different-root').exists()
    finally:
        host.close()
