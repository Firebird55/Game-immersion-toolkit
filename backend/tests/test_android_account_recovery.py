"""Recovery preserves protected originals and actual imported profile stores."""
import base64
import hashlib
import hmac
import json
import threading

import httpx
import pytest

from backend.android_account_recovery import MAX_RECOVERED_STORES
from backend.android_accounts import AndroidAccountConflict, AndroidAccountSessions
from backend.android_host import AndroidHost
from backend.lexirise import LexiriseError
from backend.tests.test_android_account_http import capture, headers
from backend.tests.test_android_host import request

KEYS = ('lx_first_authored_account_fixture_only', 'lx_second_authored_account_fixture_only')


class AuthoredProvider:
    """Authenticated fake, deliberately separate from native Keystore proof."""
    def __init__(self):
        self.key = b'authored-test-key-one'
        self.fail_encrypt = self.fail_readback = False
        self.decrypt_calls = 0

    def blob(self, value, decrypt=False):
        if decrypt:
            self.decrypt_calls += 1
            if len(value) < 32 or not hmac.compare_digest(value[:32], hmac.digest(self.key, value[32:], 'sha256')):
                raise ValueError('Authored provider payload must never appear in a DTO')
            return bytes(byte ^ 173 for byte in value[32:])
        if self.fail_encrypt:
            raise ValueError('Authored provider payload must never appear in a DTO')
        raw = bytes(byte ^ 173 for byte in value)
        return (b'bad readback' if self.fail_readback else hmac.digest(self.key, raw, 'sha256')) + raw

    def protect(self, encoded, decrypt):
        return base64.b64encode(self.blob(base64.b64decode(encoded), decrypt)).decode()


def identity_reply(calls, delayed=None):
    def reply(request):
        calls.append((request.method, request.url.path))
        assert request.method == 'GET' and request.url.path == '/v1/me'
        key = request.headers['authorization'].removeprefix('Bearer ')
        if delayed:
            delayed(key)
        if key not in KEYS:
            return httpx.Response(401, json={})
        return httpx.Response(200, json={'user': {'id': 'authored-owner-' + str(KEYS.index(key)), 'name': 'Authored owner'}})
    return httpx.MockTransport(reply)


def reader(tmp_path):
    path = tmp_path / 'reader';path.mkdir(exist_ok=True)
    (path / 'index.html').write_text('<html><head></head><body>Recovery fixture</body></html>')
    return path


def profile_files(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (root / 'profiles').rglob('*') if path.is_file()}


def corrupt_root(tmp_path, provider):
    root = tmp_path / 'application'
    (root / 'credentials').mkdir(parents=True)
    path = root / 'credentials/accounts.gcm';path.write_bytes(b'authored-invalid-protected-store')
    return root, path


@pytest.mark.parametrize('damage', ['tampered', 'lost-key', 'missing', 'bad-locator'])
def test_verified_recovery_reopens_same_owner_imports_history_and_audio_without_overwriting_original(tmp_path, damage):
    native, calls = AuthoredProvider(), []
    root = tmp_path / 'application';web = reader(tmp_path)
    host = AndroidHost(root, web, native, enable_accounts=True, account_transport=identity_reply(calls))
    first = host.account_sessions.register(KEYS[0], 'First', 0)['active']
    line = capture(host, tmp_path / 'first')
    host.session.history.set_favorite(1, True)
    host.session.update_settings({'capture_unvoiced': True})
    original_audio = host.session.audio_path(1).read_bytes()
    second = host.account_sessions.register(KEYS[1], 'Second', host.account_generation)['active']
    capture(host, tmp_path / 'second', '第二个账户有独立的对白。')
    host.close()
    original = root / 'credentials/accounts.gcm'
    if damage == 'tampered':
        raw = bytearray(original.read_bytes());raw[-1] ^= 1;original.write_bytes(raw)
    elif damage == 'lost-key':
        native.key = b'authored-replacement-test-key'
    elif damage == 'missing':
        original.unlink()  # Authored loss fixture, never production cleanup.
    else:
        (root / 'credentials/accounts-current.json').write_text('{"schema":1,"store":"../outside"}')
    original_bytes = original.read_bytes() if original.exists() else None
    before = profile_files(root)
    calls.clear()
    host = AndroidHost(root, web, native, enable_accounts=True, account_transport=identity_reply(calls))
    try:
        status = request(host, 'GET', '/api/lexirise/accounts')[1]
        assert status['active'] == 'recovery' and status['profiles'] == []
        assert status['recovery']['data_preserved'] and status['recovery']['action'] == 'reenter_verified_account'
        assert request(host, 'GET', '/api/snapshot')[1]['lines'] == []
        assert request(host, 'GET', '/api/platform')[1]['library_import'] is False
        assert profile_files(root) == before and calls == []
        for method, route, body in [('POST', '/api/capture/start', b''),
                ('PATCH', '/api/settings', b'{"capture_unvoiced":true}'),
                ('POST', '/api/lexirise/accounts', json.dumps({'key': KEYS[0]}).encode())]:
            result, error = request(host, method, route, body, headers=headers(host))
            assert result == 409 and error['state'] == 'account_recovery_required'
        assert request(host, 'GET', f"/api/lines/{line['id']}/audio")[0] == 409
        assert calls == []
        assert request(host, 'POST', '/api/lexirise/accounts/recover', json.dumps({'key': KEYS[0]}).encode(),
            headers=headers(host, host.account_generation - 1))[0] == 409
        code, status = request(host, 'POST', '/api/lexirise/accounts/recover',
            json.dumps({'key': KEYS[0]}).encode(), headers=headers(host))
        assert code == 200 and status['active'] == first and status['recovery'] is None
        assert calls == [('GET', '/v1/me')]
        assert host.session.root == root / 'profiles' / first
        assert host.session.history.get(1).favorite and host.session.settings.get().capture_unvoiced
        assert host.session.audio_path(1).read_bytes() == original_audio
        assert profile_files(root) == before
        assert host.account_sessions.accounts.path != original
        assert (original.read_bytes() if original.exists() else None) == original_bytes
        assert KEYS[0].encode() not in host.account_sessions.accounts.path.read_bytes()
        assert second not in {row['id'] for row in status['profiles']}  # No guessed/adopted other owner.
    finally:
        host.close()
    reopened = AndroidAccountSessions(root, protect=native.blob, transport=identity_reply(calls))
    try:
        assert reopened.status()['active'] == first and reopened.session.history.count() == 1
        assert reopened.status()['recovery'] is None
        assert reopened.register(KEYS[1], 'Second', reopened.accounts.generation)['active'] == second
        assert reopened.session.history.count() == 1 and profile_files(root) == before
        assert (original.read_bytes() if original.exists() else None) == original_bytes
    finally:
        reopened.close()


@pytest.mark.parametrize('failure', ['verification', 'encrypt', 'readback', 'profile', 'pointer'])
def test_failed_recovery_keeps_runtime_locked_and_original_blob_and_profiles_untouched(tmp_path, monkeypatch, failure):
    native, calls = AuthoredProvider(), []
    root, original = corrupt_root(tmp_path, native)
    old = original.read_bytes()
    manager = AndroidAccountSessions(root, protect=native.blob, transport=identity_reply(calls))
    if failure == 'encrypt': native.fail_encrypt = True
    if failure == 'readback': native.fail_readback = True
    if failure == 'profile':
        manager.session_factory = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('Authored invalid prepared profile'))
    if failure == 'pointer':
        from backend import android_account_recovery
        monkeypatch.setattr(android_account_recovery, 'private_write', lambda *args: (_ for _ in ()).throw(OSError('Authored atomic publication failure')))
    try:
        generation, session = manager.accounts.generation, manager.session
        with pytest.raises((LexiriseError, OSError, ValueError)):
            manager.recover('lx_unknown_authored_account_fixture' if failure == 'verification' else KEYS[0], '', generation)
        assert manager.status()['active'] == 'recovery' and manager.session is session
        assert manager.accounts.generation == generation and manager.accounts.locked
        assert original.read_bytes() == old and not manager.accounts.pointer.exists()
        assert list((root / 'credentials').glob('accounts-recovered-*.gcm')) == []
        assert calls == [('GET', '/v1/me')]
        assert manager._recovery_pending == 0
        with pytest.raises(AndroidAccountConflict): manager.register(KEYS[0], '', generation)
    finally:
        manager.close()


def test_newer_explicit_recovery_wins_and_delayed_verification_cannot_adopt_its_profile(tmp_path):
    native, calls = AuthoredProvider(), []
    root, original = corrupt_root(tmp_path, native)
    entered, release = threading.Event(), threading.Event()
    def delayed(key):
        if key == KEYS[0]: entered.set();assert release.wait(5)
    manager = AndroidAccountSessions(root, protect=native.blob, transport=identity_reply(calls, delayed))
    failures = []
    def recover_first():
        try: manager.recover(KEYS[0], 'First', manager.accounts.generation)
        except AndroidAccountConflict as error: failures.append(error.state)
    worker = threading.Thread(target=recover_first);worker.start();assert entered.wait(3)
    try:
        winner = manager.recover(KEYS[1], 'Second', manager.accounts.generation)['active']
        published = manager.accounts.pointer.read_bytes()
        release.set();worker.join(5)
        assert not worker.is_alive() and failures == ['account_recovery_superseded']
        assert manager.status()['active'] == winner and manager.accounts.pointer.read_bytes() == published
        assert len(list((root / 'credentials').glob('accounts-recovered-*.gcm'))) == 1
        assert original.read_bytes() == b'authored-invalid-protected-store'
    finally:
        release.set();worker.join(5);manager.close()


def test_two_pending_verifications_bound_work_and_rejected_third_intent_cannot_cancel_winner(tmp_path):
    native, calls = AuthoredProvider(), []
    root, _ = corrupt_root(tmp_path, native)
    first_entered, second_entered, release = threading.Event(), threading.Event(), threading.Event()
    def delayed(key):
        (first_entered if key == KEYS[0] else second_entered).set()
        assert release.wait(5)
    manager = AndroidAccountSessions(root, protect=native.blob, transport=identity_reply(calls, delayed))
    outcomes = {}
    def recover(index):
        try: outcomes[index] = manager.recover(KEYS[index], '', manager.accounts.generation)['active']
        except AndroidAccountConflict as error: outcomes[index] = error.state
    first = threading.Thread(target=recover, args=(0,));second = threading.Thread(target=recover, args=(1,))
    first.start();assert first_entered.wait(3);second.start();assert second_entered.wait(3)
    try:
        with pytest.raises(AndroidAccountConflict) as error:
            manager.recover(KEYS[0], '', manager.accounts.generation)
        assert error.value.state == 'account_recovery_busy' and len(calls) == 2
        release.set();first.join(5);second.join(5)
        assert not first.is_alive() and not second.is_alive()
        assert outcomes[0] == 'account_recovery_superseded'
        assert manager.status()['active'] == outcomes[1] and manager._recovery_pending == 0
    finally:
        release.set();first.join(5);second.join(5);manager.close()


def test_runtime_corruption_fences_old_owner_import_callbacks_and_native_ocr_before_empty_snapshot(tmp_path):
    native, calls = AuthoredProvider(), []
    root = tmp_path / 'application'
    host = AndroidHost(root, reader(tmp_path), native, enable_accounts=True, account_transport=identity_reply(calls))
    host.account_sessions.register(KEYS[0], '', 0)
    line = capture(host, tmp_path / 'first')
    old_session, generation = host.session, host.account_generation
    old_source = old_session.generation
    host.receiver_owner = {'id': 'authored-previous-owner', 'revision': 1, 'generation': old_source}
    host.preview_frame = {'authored': True}
    original = host.account_sessions.accounts.path
    original.write_bytes(b'authored-corrupted-during-capture')
    try:
        snapshot = request(host, 'GET', '/api/snapshot')[1]
        assert snapshot['lines'] == [] and snapshot['context']['account_generation'] > generation
        assert host.session is not old_session and not old_session.running
        assert host.session.generation > old_source and host.receiver_owner is host.preview_frame is None
        assert host.accept_ocr(old_source, 3, '{}') == []
        with pytest.raises(AndroidAccountConflict): host.account_sessions.guard_import(old_session, generation)
        assert request(host, 'GET', f"/api/lines/{line['id']}/audio")[0] == 409
        assert old_session.history.count() == 1
        assert original.read_bytes() == b'authored-corrupted-during-capture'
    finally:
        host.close()


def test_recovery_capacity_is_bounded_without_deleting_earlier_stores_or_requesting_identity(tmp_path):
    native, calls = AuthoredProvider(), []
    root, original = corrupt_root(tmp_path, native)
    for number in range(MAX_RECOVERED_STORES):
        (root / 'credentials' / ('accounts-recovered-' + f'{number:032x}' + '.gcm')).write_bytes(b'authored-preserved-store')
    manager = AndroidAccountSessions(root, protect=native.blob, transport=identity_reply(calls))
    try:
        with pytest.raises(LexiriseError, match='full'):
            manager.recover(KEYS[0], '', manager.accounts.generation)
        assert calls == [] and manager.accounts.locked and original.exists()
        assert len(list((root / 'credentials').glob('accounts-recovered-*.gcm'))) == MAX_RECOVERED_STORES
    finally:
        manager.close()


def test_changed_locator_during_verification_is_preserved_and_cannot_be_overwritten(tmp_path):
    native, calls = AuthoredProvider(), []
    root, original = corrupt_root(tmp_path, native)
    changed = json.dumps({'schema': 1, 'store': 'accounts-recovered-' + 'a' * 32 + '.gcm'}).encode()
    def change_locator(key):
        (root / 'credentials/accounts-current.json').write_bytes(changed)
    manager = AndroidAccountSessions(root, protect=native.blob, transport=identity_reply(calls, change_locator))
    try:
        with pytest.raises(LexiriseError, match='locator changed'):
            manager.recover(KEYS[0], '', manager.accounts.generation)
        assert manager.accounts.locked and manager.accounts.pointer.read_bytes() == changed
        assert original.read_bytes() == b'authored-invalid-protected-store'
    finally:
        manager.close()


def test_uncertain_postpublication_error_keeps_new_referenced_blob_for_reopen(tmp_path, monkeypatch):
    from backend import android_account_recovery
    native, calls = AuthoredProvider(), []
    root, original = corrupt_root(tmp_path, native)
    real_write = android_account_recovery.private_write
    def committed_then_failed(path, raw):
        real_write(path, raw)
        raise OSError('Authored response failure after locator replacement')
    monkeypatch.setattr(android_account_recovery, 'private_write', committed_then_failed)
    manager = AndroidAccountSessions(root, protect=native.blob, transport=identity_reply(calls))
    try:
        with pytest.raises(OSError):
            manager.recover(KEYS[0], '', manager.accounts.generation)
        assert manager.accounts.locked
        pointer = json.loads(manager.accounts.pointer.read_bytes())
        assert (root / 'credentials' / pointer['store']).is_file()
        assert original.read_bytes() == b'authored-invalid-protected-store'
    finally:
        manager.close()
    reopened = AndroidAccountSessions(root, protect=native.blob)
    try:
        assert reopened.status()['active'] != 'recovery' and reopened.status()['recovery'] is None
    finally:
        reopened.close()


def test_full_temporary_filesystem_still_hides_old_history_and_stops_receiver(tmp_path):
    native, calls = AuthoredProvider(), []
    host = AndroidHost(tmp_path / 'application', reader(tmp_path), native,
        enable_accounts=True, account_transport=identity_reply(calls))
    host.account_sessions.register(KEYS[0], '', 0)
    line = capture(host, tmp_path / 'first')
    host.session.update_settings({'capture_unvoiced': True})
    host.account_sessions.session_factory = lambda *args, **kwargs: (_ for _ in ()).throw(OSError('Authored filesystem full'))
    host.account_sessions.accounts.path.write_bytes(b'authored-corrupted-store')
    try:
        status, snapshot = request(host, 'GET', '/api/snapshot')
        assert status == 200 and snapshot['lines'] == []
        assert snapshot['status']['capture']['active_game'] is None
        assert not snapshot['status']['settings']['capture_unvoiced']
        assert snapshot['status']['session']['total_line_count'] == 0
        assert host.session.history.count() == 1 and not host.session.running
        assert request(host, 'GET', '/api/settings')[1]['capture_unvoiced'] is False
        assert request(host, 'GET', f"/api/lines/{line['id']}/audio")[0] == 409
    finally:
        host.close()


@pytest.mark.parametrize('damage', ['oversized', 'invalid-owner', 'invalid-profile', 'invalid-key'])
def test_invalid_protected_metadata_is_a_safe_recovery_state(tmp_path, damage):
    native = AuthoredProvider()
    root, original = corrupt_root(tmp_path, native)
    if damage == 'oversized':
        original.write_bytes(b'x' * (1024**2 + 65))
    else:
        identity = '../outside' if damage == 'invalid-owner' else 'a' * 24
        profile = [] if damage == 'invalid-profile' else {'name': 'Authored fixture', 'key': [] if damage == 'invalid-key' else KEYS[0]}
        original.write_bytes(native.blob(json.dumps({'active': identity, 'profiles': {identity: profile}}).encode()))
    original_bytes = original.read_bytes()
    manager = AndroidAccountSessions(root, protect=native.blob)
    try:
        assert manager.status()['active'] == 'recovery'
        assert 'outside' not in json.dumps(manager.status())
        assert original.read_bytes() == original_bytes
        if damage == 'oversized': assert native.decrypt_calls == 0
    finally:
        manager.close()
