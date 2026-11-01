"""Real setup/account readers may run while preparation publishes activation."""
import threading
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from backend import api
from backend.accounts import AccountStore
from backend.language_preparation import LanguagePreparation
from backend.scoped_mobile_exports import ScopedMobileExports


class BoundedAccountLock:
    """Make a regression fail rather than leave the test's threads deadlocked."""
    def __init__(self):
        self.lock = threading.RLock()
        self.timed_out = False

    def __enter__(self):
        if not self.lock.acquire(timeout=2):
            self.timed_out = True
            raise TimeoutError('Account/language lock inversion')
        return self

    def __exit__(self, *_):
        self.lock.release()


@pytest.mark.parametrize('switch_account', [False, True])
def test_cold_setup_inspection_does_not_block_transcript_account_reads(tmp_path, monkeypatch, switch_account):
    accounts = AccountStore(tmp_path / 'accounts.dpapi', protect=lambda value, **_: value)
    accounts._write({'active': 'first', 'profiles': {
        'first': {'key': 'synthetic-first', 'name': 'First'},
        'second': {'key': 'synthetic-second', 'name': 'Second'}}})
    inspecting, release, observed = threading.Event(), threading.Event(), threading.Event()
    results, errors = [], []

    def inspect():
        inspecting.set()
        assert release.wait(3)
        return {'completed': False}

    runtime = SimpleNamespace(accounts=accounts, installation=SimpleNamespace(status=inspect),
                              status=accounts.status)
    monkeypatch.setattr(api, 'runtime', runtime, raising=False)
    request = Request({'type': 'http', 'headers': [(b'host', b'127.0.0.1:8766')]})

    def read_setup():
        try:
            results.append(api.setup_status(request, game='zzz'))
        except Exception as error:
            errors.append(error)

    def read_transcript_account():
        api.get_status()
        if switch_account:
            accounts.select('second')
        observed.set()

    setup_thread = threading.Thread(target=read_setup, daemon=True)
    status_thread = threading.Thread(target=read_transcript_account, daemon=True)
    try:
        setup_thread.start()
        assert inspecting.wait(1)
        status_thread.start()
        assert observed.wait(1), 'Slow game/tool inspection blocked the transcript account read'
    finally:
        release.set()
        setup_thread.join(3)
        if status_thread.ident is not None:
            status_thread.join(3)
    assert not setup_thread.is_alive() and not status_thread.is_alive()
    if switch_account:
        assert not results and len(errors) == 1
        assert isinstance(errors[0], api.HTTPException) and errors[0].status_code == 409
    else:
        assert not errors and results == [{'completed': False, 'mobile_export': None}]


@pytest.mark.parametrize('switch_account', [False, True])
def test_setup_read_and_account_switch_do_not_deadlock_preparation(tmp_path, monkeypatch, switch_account):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path / 'isolated-game-data')
    accounts = AccountStore(tmp_path / 'accounts.dpapi', protect=lambda value, **_: value)
    accounts._write({'active': 'first', 'profiles': {
        'first': {'key': 'synthetic-first', 'name': 'First'}, 'second': {'key': 'synthetic-second', 'name': 'Second'}}})
    accounts.lock = BoundedAccountLock()
    runtime = api.Runtime.__new__(api.Runtime)
    runtime.accounts = accounts
    runtime.installation = SimpleNamespace(status=lambda: {})
    held, entering_activation = threading.Event(), threading.Event()
    def activate(*args):
        entering_activation.set()
        return api.Runtime.activate_language(runtime, *args)
    manager = runtime.languages = LanguagePreparation(lambda *_: None, activate,
        lambda *_: {'ready': True}, path=tmp_path / 'languages.json', supported=lambda _: ('en',))
    runtime.mobile_exports = ScopedMobileExports(tmp_path, accounts, manager)
    monkeypatch.setattr(api, 'runtime', runtime, raising=False)
    request = Request({'type': 'http', 'headers': [(b'host', b'127.0.0.1:8766')]})
    results, errors = [], []
    def read_setup():
        try:
            with accounts.lock:
                held.set()
                assert entering_activation.wait(2)
                if switch_account:
                    accounts.select('second')
                results.append(api.setup_status(request, game='cyberpunk'))
        except Exception as error:
            errors.append(error)
    reader = threading.Thread(target=read_setup, daemon=True)
    try:
        reader.start()
        assert held.wait(1)
        assert manager.request('cyberpunk', 'en', 'nl', 'first')
        reader.join(timeout=4)
        # Wait for ordinary completion before close deliberately cancels work.
        for worker in list(manager._workers):
            worker.join(timeout=3)
        assert not reader.is_alive() and not manager._workers
        assert not accounts.lock.timed_out and not errors
        assert results[0]['mobile_export']['selectedGame'] == 'cyberpunk'
        assert manager.jobs[('cyberpunk', 'en')]['state'] == 'ready'
        assert accounts.status()['active'] == ('second' if switch_account else 'first')
    finally:
        manager.close()
