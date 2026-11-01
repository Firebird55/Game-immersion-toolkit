"""Real SQL operation scopes shared by a root and pins; no real accounts."""
from contextlib import closing
import json
import sqlite3
import threading
from types import SimpleNamespace

import httpx
import pytest

from backend import lexirise
from backend.lexirise import (LexiriseService, LexiriseError, LexiriseConnectionCloseError,
                             LexiriseLedgerPoisonedError, LexiriseConnectionFence)
from backend.runtime_writers import WritersQuiescing


@pytest.fixture
def ledger_state(tmp_path, monkeypatch):
    raw = sqlite3.connect
    state = SimpleNamespace(opened=[], calls=[], close_error=None, transaction_errors=[])
    def forbidden(*_a, **_k):
        pytest.fail('Owned SQL tests must not reach credential fallback or real account transport.')
    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(lexirise, 'os', SimpleNamespace(environ=SimpleNamespace(get=forbidden), name='nt'))
    class Observed(sqlite3.Connection):
        def __exit__(self, *args):
            try: return super().__exit__(*args)
            except BaseException as error:
                state.transaction_errors.append(error)
                raise
        def close(self):
            self.close_calls += 1
            if self.close_entered is not None:
                self.close_entered.set()
                assert self.close_release.wait(5)
            if self.close_error is not None: raise self.close_error
            super().close()
            self.closed_cleanly = True
    def connect(database, *args, **options):
        assert not args and options == {'timeout': 10}  # Unchanged production factory shape.
        state.calls.append((database, options.copy()))
        connection = raw(database, timeout=10, factory=Observed, check_same_thread=False)
        connection.close_calls, connection.closed_cleanly = 0, False
        connection.close_error = state.close_error
        connection.close_entered = connection.close_release = None
        state.opened.append(connection)
        return connection
    monkeypatch.setattr(sqlite3, 'connect', connect)
    def make(*, transport=None):
        return LexiriseService(tmp_path/'owned-ledger', api_key='test-key',
            accounts=SimpleNamespace(active_key=forbidden),
            transport=transport or httpx.MockTransport(forbidden))
    state.make, state.raw, state.forbidden = make, raw, forbidden
    yield state
    # Dispose authored test-only failed fixtures after assertions. Product code
    # never retries these close calls or uses disposal as detach evidence.
    for connection in state.opened:
        if not connection.closed_cleanly: sqlite3.Connection.close(connection)


def _thread_call(operation):
    result = SimpleNamespace(done=threading.Event(), value=None, error=None)
    def call():
        try: result.value = operation()
        except BaseException as error: result.error = error
        finally: result.done.set()
    result.thread = threading.Thread(target=call)
    result.thread.start()
    return result


def _observe_stop(owner, monkeypatch):
    event = threading.Event()
    original = owner.gate.stop_admission
    def stop():
        original(); event.set()
    monkeypatch.setattr(owner.gate, 'stop_admission', stop)
    return event


@pytest.mark.parametrize('fault', ['initialize', 'success', 'body', 'transaction-exit', 'body-and-rollback'])
def test_real_ledger_errors_and_failed_close_keep_root_pin_ownership(ledger_state, fault):
    state = ledger_state
    body_error, close_error = RuntimeError('authored body fault'), OSError('authored close fault')
    if fault != 'initialize':
        root = state.make()
        pin = root.pin('nl')
        if fault == 'body-and-rollback':
            with root._connect() as db: db.execute('CREATE TABLE owned_rollback (id INTEGER)')
    state.close_error = close_error
    with pytest.raises(LexiriseConnectionCloseError) as raised:
        if fault == 'initialize': state.make()
        elif fault == 'success': root.status()
        else:
            with pin._connect() as db:
                if fault == 'transaction-exit':
                    db.execute('PRAGMA foreign_keys=ON')
                    db.execute('CREATE TABLE owned_parent (id INTEGER PRIMARY KEY)')
                    db.execute('CREATE TABLE owned_child (id INTEGER REFERENCES owned_parent(id) DEFERRABLE INITIALLY DEFERRED)')
                    db.execute('INSERT INTO owned_child VALUES (1)')
                elif fault == 'body-and-rollback':
                    db.execute('INSERT INTO owned_rollback VALUES (1)')
                    db.set_authorizer(lambda action, first, *_:
                        sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and first == 'ROLLBACK' else sqlite3.SQLITE_OK)
                    raise body_error
                else:
                    db.execute('SELECT 1')
                    raise body_error
    failure = raised.value
    root = failure.service
    owner = root._sql_lifetime
    assert failure.owner is owner and failure.connection is state.opened[-1]
    assert owner.subject is root and owner.failures == [failure] and failure.close_error is close_error
    assert failure.body_error is (body_error if fault in {'body', 'body-and-rollback'} else None)
    if fault in {'transaction-exit', 'body-and-rollback'}:
        assert failure.transaction_error is state.transaction_errors[-1]
        assert isinstance(failure.transaction_error, sqlite3.DatabaseError)
        assert failure.__cause__ is failure.transaction_error
    else:
        assert failure.transaction_error is None
        assert failure.__cause__ is (body_error if fault == 'body' else close_error)
    assert failure.connection.execute('SELECT 1').fetchone() == (1,)
    assert not isinstance(failure, LexiriseError)
    assert 'test-key' not in str(failure) and str(root.directory) not in str(failure)
    traceback, opened = failure.__traceback__, len(state.opened)
    clients = [root, root.pin('zh'), root.pin('nl')]
    if fault != 'initialize': clients.append(pin)
    previous = None
    for client in clients:
        assert client._sql_lifetime is owner
        for operation in (client.status, lambda: client.freeze_connections(0),
                          lambda: client.resume_connections(None)):
            with pytest.raises(LexiriseLedgerPoisonedError) as refused: operation()
            assert refused.value is not previous and refused.value.failure is failure
            assert refused.value.__cause__ is failure and failure.__traceback__ is traceback
            previous = refused.value
    assert len(state.opened) == opened and failure.connection.close_calls == 1


@pytest.mark.parametrize('fault', ['body', 'transaction'])
def test_ledger_rollback_errors_with_successful_close_preserve_error_and_allow_fence(ledger_state, fault):
    state = ledger_state
    root = state.make()
    body = RuntimeError('authored body fault')
    with pytest.raises(RuntimeError if fault == 'body' else sqlite3.IntegrityError) as raised:
        with root.pin('zh')._connect() as db:
            if fault == 'body':
                db.execute('INSERT INTO exports VALUES (?,?)', ('owned', '{}'))
                raise body
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE owned_parent (id INTEGER PRIMARY KEY)')
            db.execute('CREATE TABLE owned_child (id INTEGER REFERENCES owned_parent(id) DEFERRABLE INITIALLY DEFERRED)')
            db.execute('INSERT INTO owned_child VALUES (1)')
    assert raised.value is (body if fault == 'body' else state.transaction_errors[-1])
    assert not root._sql_lifetime.failures
    assert state.opened[-1].close_calls == 1 and state.opened[-1].closed_cleanly
    fence = root.freeze_connections(0)
    fence.check(root.pin('nl')); root.resume_connections(fence)
    with root._connect() as db:
        if fault == 'body': assert db.execute('SELECT COUNT(*) FROM exports').fetchone()[0] == 0
        else: assert db.execute('SELECT COUNT(*) FROM owned_child').fetchone()[0] == 0


def test_root_freeze_waits_for_both_real_pin_scopes_and_closes_before_new_pin_sql(ledger_state, monkeypatch):
    state = ledger_state
    root = state.make()
    first, second = root.pin('zh'), root.pin('nl')
    independent = state.make()
    owner = root._sql_lifetime
    assert first._sql_lifetime is second._sql_lifetime is owner
    stopped = _observe_stop(owner, monkeypatch)
    entered = [threading.Event(), threading.Event()]
    body_release = [threading.Event(), threading.Event()]
    close_entered = [threading.Event(), threading.Event()]
    close_release = [threading.Event(), threading.Event()]
    def read(pin, index):
        with pin._connect() as db:
            db.execute('SELECT COUNT(*) FROM scoped_exports').fetchone()
            db.close_entered, db.close_release = close_entered[index], close_release[index]
            entered[index].set()
            assert body_release[index].wait(5)
    threads = [_thread_call(lambda: read(first, 0)), _thread_call(lambda: read(second, 1))]
    freezer = short = None
    try:
        assert all(event.wait(2) for event in entered)
        freezer = _thread_call(lambda: root.freeze_connections(4))
        assert stopped.wait(2)
        short = _thread_call(lambda: second.freeze_connections(.02))
        assert short.done.wait(2) and isinstance(short.error, TimeoutError)
        later_pin = first.pin('en')
        opened = len(state.opened)
        for client in (root, first, second, later_pin):
            with pytest.raises(WritersQuiescing): client.status()
        assert len(state.opened) == opened
        for event in body_release: event.set()
        assert all(event.wait(2) for event in close_entered)
        close_release[0].set()
        assert threads[0].done.wait(2) and not freezer.done.is_set()
        close_release[1].set()
        assert threads[1].done.wait(2) and freezer.done.wait(2)
        assert all(thread.error is None for thread in threads) and freezer.error is None
        fence = freezer.value
        assert type(fence) is LexiriseConnectionFence
        for client in (root, first, second, later_pin):
            fence.check(client)
            assert client.freeze_connections(0) is fence
        for invalid in (None, True, LexiriseConnectionFence(root, fence._epoch)):
            with pytest.raises(ValueError): first.resume_connections(invalid)
        with pytest.raises(ValueError): fence.check(independent)
        with pytest.raises(ValueError): independent.resume_connections(fence)
        original_resume = owner.gate.resume
        def resume():
            with pytest.raises(ValueError): owner.check_locked(fence)
            with pytest.raises(WritersQuiescing): second.status()
            original_resume()
        monkeypatch.setattr(owner.gate, 'resume', resume)
        later_pin.resume_connections(fence)
        with pytest.raises(ValueError): fence.check(root)
        assert root.status()['sent'] == {} and second.status()['decks'] == {}
        assert all(connection.close_calls == 1 and connection.closed_cleanly for connection in state.opened)
    finally:
        for event in (*body_release, *close_release): event.set()
        for thread in threads: thread.thread.join(5)
        if freezer is not None: freezer.thread.join(5)
        if short is not None: short.thread.join(5)
        assert all(not thread.thread.is_alive() for thread in (*threads, *([freezer] if freezer else []), *([short] if short else [])))


def test_pin_freeze_budget_bounds_late_gate_contention_and_keeps_scope_owned(ledger_state, monkeypatch):
    root = ledger_state.make()
    pin, owner = root.pin('nl'), root._sql_lifetime
    entered, finish, held, release = [threading.Event() for _ in range(4)]
    stopped = _observe_stop(owner, monkeypatch)
    def read():
        with pin._connect() as db:
            db.execute('SELECT COUNT(*) FROM exports').fetchone()
            entered.set(); assert finish.wait(5)
    def hold():
        assert stopped.wait(2)
        with owner.gate._condition:
            held.set(); assert release.wait(5)
    reader = _thread_call(read)
    holder = freezer = None
    try:
        assert entered.wait(2)
        holder = _thread_call(hold)
        freezer = _thread_call(lambda: pin.freeze_connections(.05))
        assert held.wait(2) and freezer.done.wait(.5)
        assert isinstance(freezer.error, TimeoutError) and owner.fence is None
        assert not reader.done.is_set() and not holder.done.is_set() and not owner.gate._accepting
    finally:
        release.set(); finish.set(); reader.thread.join(5)
        if holder is not None: holder.thread.join(5)
        if freezer is not None: freezer.thread.join(5)
        assert all(not thread.thread.is_alive() for thread in (reader, *([holder] if holder else []), *([freezer] if freezer else [])))
    assert reader.error is None and holder.error is None
    fence = root.freeze_connections(0); pin.resume_connections(fence)


def test_freeze_does_not_take_ledger_lock_or_prevent_admitted_mock_http_bookkeeping(ledger_state, monkeypatch):
    state = ledger_state
    entered, release = threading.Event(), threading.Event()
    calls = []
    def reply(request):
        assert request.headers['Authorization'] == 'Bearer test-key'
        calls.append((request.method, request.url.path))
        if request.method == 'GET' and request.url.path == '/v1/me':
            return httpx.Response(200, json={'user': {'id': 'owned-test-user'}})
        assert request.method == 'GET' and request.url.path == '/v1/decks/7'
        entered.set(); assert release.wait(5)
        return httpx.Response(200, json={'deck': {'id': 7, 'title': 'Owned fixture',
            'owner_user_id': 'owned-test-user', 'language': 'zh', 'unit_type': 'sentence', 'deck_type': 'snapshot'}})
    root = state.make(transport=httpx.MockTransport(reply))
    pin, owner = root.pin('zh'), root._sql_lifetime
    stopped = _observe_stop(owner, monkeypatch)
    operation = _thread_call(lambda: pin.configure_game_deck('zzz', 7))
    freezer = None
    try:
        assert entered.wait(2) and root._lock is pin._lock and root._lock.locked()
        freezer = _thread_call(lambda: root.freeze_connections(4))
        assert stopped.wait(2) and not freezer.done.is_set()
        release.set()
        assert operation.done.wait(2) and freezer.done.wait(2)
        assert operation.error is None and freezer.error is None and not root._lock.locked()
        assert operation.value == {'id': 7, 'title': 'Owned fixture'}
        root.resume_connections(freezer.value)
        assert pin.status()['decks']['zzz'] == operation.value and root.status()['decks']['zzz'] == operation.value
        assert calls == [('GET', '/v1/me'), ('GET', '/v1/decks/7')]
    finally:
        release.set(); operation.thread.join(5)
        if freezer is not None: freezer.thread.join(5)
        assert not operation.thread.is_alive() and (freezer is None or not freezer.thread.is_alive())


def test_intermediate_export_commits_survive_remote_and_close_fault_without_automatic_retry(ledger_state, tmp_path):
    from backend.tests.test_lexirise import FakeAPI
    state, remote = ledger_state, FakeAPI()
    close_error = OSError('authored close fault')
    def reply(request):
        if remote.fail_after_add and request.method == 'POST' and request.url.path == '/v1/decks/1951/items':
            state.opened[-1].close_error = close_error
        return remote(request)
    root = state.make(transport=httpx.MockTransport(reply))
    pin = root.pin('zh')
    pin.configure_game_deck('pragmata', 1951)
    audio = tmp_path/'authored.mp3'; audio.write_bytes(b'owned test audio')
    payload = dict(ref='owned-line', game='pragmata', chinese='这是保留的中文。', english='Owned caption',
                   speaker='Owned fixture', audio=audio)
    remote.fail_after_add = True
    with pytest.raises(LexiriseConnectionCloseError) as raised: pin.send(**payload)
    failure = raised.value
    assert failure.owner is root._sql_lifetime and failure.service is root
    assert isinstance(failure.body_error, LexiriseError) and failure.transaction_error is None
    assert failure.close_error is close_error and not root._lock.locked()
    with closing(state.raw(root.db_path)) as independent:
        rows = independent.execute('SELECT state FROM scoped_exports').fetchall()
    assert len(rows) == 1
    saved = json.loads(rows[0][0])
    assert saved['audio_url'] and saved['vocabulary_id'] and saved.get('complete') is not True
    calls = list(remote.calls)
    for client in (root, pin, root.pin('zh')):
        with pytest.raises(LexiriseLedgerPoisonedError): client.send(**payload)
    assert remote.calls == calls
    assert calls.count(('POST', '/v1/vocabulary/audio')) == calls.count(('POST', '/v1/vocabulary')) == 1
    assert len(remote.decks[1951]) == 1 and failure.connection.close_calls == 1


def test_shared_lifetime_preserves_exact_three_store_wal_constructor_interception(tmp_path, monkeypatch):
    from backend import runtime_probe
    from backend.storage import TranscriptStore
    from backend.reading import LexiriseReadingService
    data = (tmp_path/'owned-data').resolve(); data.mkdir()
    layout = SimpleNamespace(data_root=data)
    original = sqlite3.connect
    def forbidden(*_a, **_k): pytest.fail('No credentials or network during owned WAL constructor proof.')
    monkeypatch.setattr(lexirise, '_protect', forbidden)
    reading = None
    try:
        with runtime_probe._authored_wal_connections(layout) as policy:
            transcript = TranscriptStore(data/'transcript-v2.db')
            root = LexiriseService(data/'lexirise', api_key='test-key', transport=httpx.MockTransport(forbidden))
            reading = LexiriseReadingService(data/'lexirise', root)
            policy.require_stores()
            assert policy.opens == 3 and policy.configured == {'transcript', 'exports', 'reading'}
            assert not transcript._connection_failures and not root._sql_lifetime.failures
    finally:
        if reading is not None: reading.pool.shutdown(wait=True)
    assert sqlite3.connect is original


def test_pin_operation_fence_does_not_imply_physical_sqlite_resource_release(ledger_state):
    root = ledger_state.make()
    pin = root.pin('nl')
    with pin._connect() as db:
        assert db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete'
        db.execute('CREATE TABLE owned_cursor_rows (id INTEGER)')
        db.executemany('INSERT INTO owned_cursor_rows VALUES (?)', [(1,), (2,)])
    cursor = None
    try:
        with pin._connect() as db:
            cursor = db.execute('SELECT id FROM owned_cursor_rows')
            assert cursor.fetchone()[0] == 1
        fence = root.freeze_connections(0)
        fence.check(pin)
        with pytest.raises(sqlite3.ProgrammingError, match='closed'): db.execute('SELECT 1')
        with closing(ledger_state.raw(root.db_path, timeout=0)) as independent:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                independent.execute('BEGIN EXCLUSIVE')
        pin.resume_connections(fence)
    finally:
        cursor = None  # Authored test disposal, never a product resource-release proof.
