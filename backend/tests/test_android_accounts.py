"""Actual maintained accounts and prepared sessions must fence A→B→A work."""
import json
import threading
from contextlib import contextmanager

import httpx
import pytest

from backend.android_accounts import AndroidAccountConflict, AndroidAccountSessions
from backend.prepared_session import PreparedCaptureSession
from backend.tests.test_prepared_session import fixture_library


def protected(value, decrypt=False):
    # Authored transport fixture only; the real cryptographic provider has a
    # separate actual AndroidKeystore runtime probe.
    return bytes(byte ^ 173 for byte in value)


def manager(path):
    calls = []
    def reply(request):
        calls.append((request.method, request.url.path))
        identity = 'second' if 'second' in request.headers['authorization'] else 'first'
        return httpx.Response(200, json={'user': {'id': identity, 'name': identity}})
    runtime = AndroidAccountSessions(path, protect=protected, transport=httpx.MockTransport(reply))
    first = runtime.accounts.add('lx_first_authored_fixture_only', select=False)['id']
    second = runtime.accounts.add('lx_second_authored_fixture_only', select=False)['id']
    return runtime, first, second, calls


def capture(session, archive, payload):
    session.import_library(archive)
    generation = session.start();text = payload['records'][0]['source_text']
    assert session.observe(generation, 1, [text], now=1) == []
    return session.observe(generation, 2, [text], now=1.1)[0]


def test_accounts_keep_private_library_history_settings_and_originals_after_return_and_restart(tmp_path):
    runtime, first, second, calls = manager(tmp_path / 'application')
    runtime.select(first, runtime.accounts.generation)
    original = runtime.session
    archive, payload = fixture_library(tmp_path / 'first', identity='authored:first')
    line = capture(original, archive, payload)
    public = runtime.qualify_line(line)
    original.update_settings({'capture_unvoiced': True})
    original.history.set_favorite(line['id'], True)
    generation = original.generation
    runtime.select(second, runtime.accounts.generation)
    assert runtime.session.history.count() == 0 and runtime.session.index is None
    assert not runtime.session.settings.get().capture_unvoiced
    assert runtime.session.generation > generation
    with pytest.raises(AndroidAccountConflict):
        runtime.local_line(public['id'])
    other_archive, other_payload = fixture_library(tmp_path / 'second', identity='authored:second', text='An independent second account has its own dialogue.')
    other = capture(runtime.session, other_archive, other_payload)
    assert line['id'] == other['id'] == 1  # Actual separate SQLite row IDs.
    assert runtime.qualify_line(other)['id'] != public['id']
    before = runtime.session.generation
    runtime.select(first, runtime.accounts.generation)
    assert runtime.session is not original and runtime.session.generation > before
    assert runtime.session.history.get(line['id']).favorite
    assert runtime.session.index._records[0]['text_id'] == 'authored:first'
    assert runtime.session.settings.get().capture_unvoiced
    assert runtime.session.audio_path(line['id']).read_bytes() == original.audio_path(line['id']).read_bytes()
    with pytest.raises(AndroidAccountConflict):
        runtime.local_line(public['id'])  # A→B→A cannot revive an old callback.
    reopened = AndroidAccountSessions(runtime.root, protect=protected)
    assert reopened.status()['active'] == first and reopened.session.history.count() == 1
    assert not reopened.session.running
    assert calls == [('GET', '/v1/me'), ('GET', '/v1/me')]
    assert b'lx_first' not in runtime.accounts.path.read_bytes()
    assert 'lx_' not in json.dumps(runtime.status())


def test_delayed_selection_cannot_replace_a_newer_explicit_selection(tmp_path):
    runtime, first, second, _ = manager(tmp_path / 'application')
    entered, release = threading.Event(), threading.Event()
    def factory(root, **kwargs):
        if root.name == first:
            entered.set();assert release.wait(3)
        return PreparedCaptureSession(root, **kwargs)
    runtime.session_factory = factory
    failures = []
    def select_first():
        try: runtime.select(first, runtime.accounts.generation)
        except AndroidAccountConflict as error: failures.append(error.state)
    worker = threading.Thread(target=select_first);worker.start();assert entered.wait(2)
    runtime.select(second, runtime.accounts.generation)
    release.set();worker.join(3)
    assert failures == ['account_selection_superseded']
    assert runtime.status()['active'] == second and runtime.session.root.name == second
    assert not runtime.transitioning


def test_delayed_registration_saves_verified_profile_without_stealing_newer_selection(tmp_path):
    runtime, first, second, _ = manager(tmp_path / 'application')
    runtime.select(first, runtime.accounts.generation)
    entered, release = threading.Event(), threading.Event()
    def delayed(request):
        entered.set();assert release.wait(3)
        assert request.method == 'GET' and request.url.path == '/v1/me'
        return httpx.Response(200, json={'user': {'id': 'third', 'name': 'third'}})
    runtime.accounts.transport = httpx.MockTransport(delayed)
    failures = []
    def register():
        try: runtime.register('lx_third_authored_fixture_only', 'Third', runtime.accounts.generation)
        except AndroidAccountConflict as error: failures.append(error.state)
    worker = threading.Thread(target=register);worker.start();assert entered.wait(2)
    runtime.select(second, runtime.accounts.generation)
    release.set();worker.join(3)
    assert failures == ['account_registration_not_selected']
    assert runtime.status()['active'] == second and len(runtime.status()['profiles']) == 3


def test_delayed_import_guard_keeps_every_account_library_pointer_unchanged(tmp_path):
    runtime, first, second, _ = manager(tmp_path / 'application')
    runtime.select(first, runtime.accounts.generation)
    session, generation = runtime.session, runtime.accounts.generation
    old, _ = fixture_library(tmp_path / 'old')
    session.import_library(old)
    before = session.libraries.pointer.read_bytes()
    pending, _ = fixture_library(tmp_path / 'pending', text='A delayed import must not replace the restored account library.')
    entered, release = threading.Event(), threading.Event()
    failures = []
    def paused_validation():
        if not entered.is_set():
            entered.set();assert release.wait(3)
        return False
    @contextmanager
    def publication():
        runtime.guard_import(session, generation)
        yield
    def import_old_scope():
        try: session.import_library(pending, cancelled=paused_validation, publish_guard=publication)
        except AndroidAccountConflict as error: failures.append(error.state)
    worker = threading.Thread(target=import_old_scope);worker.start();assert entered.wait(2)
    runtime.select(second, generation)
    runtime.select(first, runtime.accounts.generation)
    release.set();worker.join(3)
    assert not worker.is_alive() and failures == ['account_import_scope_changed']
    with runtime.lock, pytest.raises(AndroidAccountConflict, match='account changed'):
        runtime.guard_import(session, generation)
    assert runtime.session.libraries.pointer.read_bytes() == session.libraries.pointer.read_bytes() == before
    assert runtime.session.index._records[0]['source_text'] == 'Follow the river beyond the bridge.'


def test_native_services_never_resolve_desktop_or_environment_credentials(tmp_path, monkeypatch):
    from backend.lexirise import LexiriseService, LexiriseError, REQUEST_KEY
    from backend import protected_storage
    monkeypatch.setenv('LEXIRISE_API_KEY', 'lx_authored_environment_fixture_only')
    monkeypatch.setattr(protected_storage, 'credential_directory', lambda: pytest.fail('Desktop credential discovery was used'))
    service = LexiriseService(tmp_path / 'services', legacy_credentials=False, trust_env=False)
    token = REQUEST_KEY.set('lx_authored_desktop_context_fixture_only')
    try:
        with pytest.raises(LexiriseError, match='protected account'):
            service._key()
        assert not service.trust_env
    finally:
        REQUEST_KEY.reset(token)


def test_scope_bounds_and_stale_generation_fail_before_selection(tmp_path):
    runtime, first, _, _ = manager(tmp_path / 'application')
    before = runtime.session
    for invalid in (None, True, runtime.accounts.generation - 1):
        with pytest.raises(AndroidAccountConflict): runtime.select(first, invalid)
    for invalid in ('../outside', 'unknown'):
        with pytest.raises(ValueError): runtime.select(invalid, runtime.accounts.generation)
    assert runtime.session is before
    with pytest.raises(ValueError): runtime.qualify_line({'id': 2**32})
    for invalid in (True, 0, 2**53, 2**32):
        with pytest.raises(AndroidAccountConflict): runtime.local_line(invalid)


def test_maintained_service_pin_keeps_old_key_and_rejects_old_response_scope(tmp_path):
    runtime, first, second, _ = manager(tmp_path / 'application')
    runtime.select(first, runtime.accounts.generation)
    pinned = runtime.pin(runtime.accounts.generation, remote=True)
    assert pinned.service._key() == 'lx_first_authored_fixture_only'
    runtime.select(second, runtime.accounts.generation)
    assert pinned.service._key() == 'lx_first_authored_fixture_only'
    assert runtime.pin(runtime.accounts.generation, remote=True).service._key() == 'lx_second_authored_fixture_only'
    with pytest.raises(AndroidAccountConflict, match='account changed'):
        pinned.check()
    runtime.close()
