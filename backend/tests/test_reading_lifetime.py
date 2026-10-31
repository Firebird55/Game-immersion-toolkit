"""Actual reading SQL scopes; fake keys/transport, no physical-detach claim."""
from concurrent.futures import Future
from contextlib import closing
import json
import sqlite3
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from backend import lexirise
from backend.lexirise import LexiriseError, LexiriseService
from backend.reading import (LexiriseReadingService, ReadingConnectionCloseError,
                             ReadingConnectionFence, ReadingConnectionsPoisonedError)
from backend.runtime_writers import WritersQuiescing


TEXT = '说了'
ANALYSIS = {'occurrences': [{'charStart': 0, 'charEnd': 1, 'word': '说', 'isWordLike': True,
                            'entryId': 1},
                           {'charStart': 1, 'charEnd': 2, 'word': '了', 'isWordLike': True,
                            'entryId': 2}],
            'entryMetaById': {'1': {'gloss': 'speak'}, '2': {'gloss': 'completed'}},
            'grammar': [{'slug': 'le-completion', 'indices': [1]}],
            'grammarStates': {'le-completion': 0}}


@pytest.fixture
def reading_state(tmp_path, monkeypatch):
    raw = sqlite3.connect
    state = SimpleNamespace(opened=[], calls=[], readers=[], threads=[], releases=[],
                            close_error=None, configure=None, on_execute=None,
                            transaction_errors=[])

    def forbidden(*_a, **_k):
        pytest.fail('Reading SQL tests must not reach credential fallback or real account transport.')

    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(lexirise, 'os', SimpleNamespace(environ=SimpleNamespace(get=forbidden), name='nt'))
    # Construct the independent ledger before observing reading's exact factory.
    service = LexiriseService(tmp_path/'owned-reading', api_key='test-key',
        accounts=SimpleNamespace(active_key=forbidden), transport=httpx.MockTransport(forbidden))

    class ObservedCursor(sqlite3.Cursor):
        def execute(self, sql, parameters=()):
            self.connection.statements.append(sql)
            cursor = super().execute(sql, parameters)
            if state.on_execute is not None:
                state.on_execute(self.connection, sql, parameters)
            return cursor

        def close(self):
            self.close_calls += 1
            return super().close()

    class Observed(sqlite3.Connection):
        def cursor(self):
            cursor = super().cursor(factory=ObservedCursor)
            cursor.close_calls = 0
            self.cursors.append(cursor)
            return cursor

        def __enter__(self):
            self.enters += 1
            return super().__enter__()

        def __exit__(self, *args):
            self.exits += 1
            try:
                return super().__exit__(*args)
            except BaseException as error:
                state.transaction_errors.append(error)
                raise

        def execute(self, sql, parameters=()):
            self.statements.append(sql)
            cursor = super().execute(sql, parameters)
            if state.on_execute is not None:
                state.on_execute(self, sql, parameters)
            return cursor

        def close(self):
            self.close_calls += 1
            if self.close_entered is not None:
                self.close_entered.set()
                assert self.close_release.wait(5), 'Authored close holder was not released.'
            if self.close_error is not None:
                raise self.close_error
            super().close()
            self.closed_cleanly = True

    def connect(database, *args, **options):
        assert not args and options == {}  # Preserve sqlite3.connect(self.path).
        state.calls.append((database, options.copy()))
        connection = raw(database, factory=Observed, check_same_thread=False)
        connection.enters = connection.exits = connection.close_calls = 0
        connection.statements = []
        connection.cursors = []
        connection.closed_cleanly = False
        connection.close_error = state.close_error
        connection.close_entered = connection.close_release = None
        state.opened.append(connection)
        if state.configure is not None:
            state.configure(connection)
        return connection

    monkeypatch.setattr(sqlite3, 'connect', connect)

    def make():
        reader = LexiriseReadingService(tmp_path/'owned-reading', service)
        state.readers.append(reader)
        return reader

    state.make, state.raw, state.service, state.forbidden = make, raw, service, forbidden
    yield state
    for event in state.releases:
        event.set()
    for call in state.threads:
        call.thread.join(5)
        assert not call.thread.is_alive(), 'Authored operation did not finish.'
    for reader in state.readers:
        reader.pool.shutdown(wait=True, cancel_futures=True)
    # Dispose failed authored fixtures only after assertions. Product code never
    # retries their close or uses this disposal as physical-detach evidence.
    for connection in state.opened:
        if not connection.closed_cleanly:
            sqlite3.Connection.close(connection)


def _event(state):
    event = threading.Event()
    state.releases.append(event)
    return event


def _thread_call(state, operation):
    result = SimpleNamespace(done=threading.Event(), value=None, error=None)

    def call():
        try:
            result.value = operation()
        except BaseException as error:
            result.error = error
        finally:
            result.done.set()

    result.thread = threading.Thread(target=call)
    state.threads.append(result)
    result.thread.start()
    return result


def _observe_stop(owner, monkeypatch):
    stopped = threading.Event()
    original = owner.gate.stop_admission

    def stop():
        original()
        stopped.set()

    monkeypatch.setattr(owner.gate, 'stop_admission', stop)
    return stopped


def test_all_five_reading_boundaries_keep_factory_transaction_and_local_grammar_semantics(reading_state):
    state = reading_state
    reader = state.make()
    assert state.opened[0].enters == state.opened[0].exits == 1
    reader._save('analysis-full', TEXT, ANALYSIS)
    assert reader._cached('analysis-full', TEXT, 600) == ANALYSIS
    assert reader.analyze(TEXT)['grammar'][0]['proficiency'] == 0
    assert reader.set_grammar_known(TEXT, 'le-completion', True) == {
        'slug': 'le-completion', 'proficiency': 4, 'localOverride': True}
    assert reader.analyze(TEXT)['grammar'][0]['localOverride'] is True
    with closing(state.raw(reader.path)) as db:
        rows = db.execute('SELECT slug,proficiency FROM grammar_choices').fetchall()
    assert rows == [(state.service._scope()+':zh:le-completion', 4)]
    assert all(path == reader.path and options == {} for path, options in state.calls)
    queries = {sql for db in state.opened for sql in db.statements}
    assert {'SELECT value,at FROM cache WHERE kind=? AND key=?',
            'SELECT slug,proficiency FROM grammar_choices',
            'INSERT OR REPLACE INTO grammar_choices VALUES (?,?)'} <= queries
    for db in state.opened:
        writes = any(sql.startswith(('CREATE', 'INSERT')) for sql in db.statements)
        assert db.enters == db.exits == int(writes)
    assert all(db.enters == db.exits and db.close_calls == 1 and db.closed_cleanly for db in state.opened)
    assert all(cursor.close_calls == 1 for db in state.opened for cursor in db.cursors)
    assert not reader._sql_lifetime.failures


def test_read_scope_does_not_enter_transaction_or_commit_an_accidental_private_write(reading_state):
    state = reading_state
    reader = state.make()
    with reader._connection_scope() as db:
        db.execute('INSERT INTO cache VALUES (?,?,?,?)', ('owned', 'private', '{}', 0))
        assert db.in_transaction
    assert db.enters == db.exits == 0 and db.close_calls == 1
    with closing(state.raw(reader.path)) as independent:
        assert independent.execute('SELECT COUNT(*) FROM cache').fetchone()[0] == 0
    fence = reader.freeze_connections(0)
    fence.check(reader)


@pytest.mark.parametrize('mode', ['read', 'write', 'transaction-exit'])
def test_successful_close_preserves_body_or_transaction_error_and_write_rollback(reading_state, mode):
    state = reading_state
    reader = state.make()
    body = RuntimeError('Authored reading body fault.')
    with pytest.raises(RuntimeError if mode != 'transaction-exit' else sqlite3.IntegrityError) as raised:
        with reader._connection_scope(transaction=mode != 'read') as db:
            if mode == 'transaction-exit':
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('CREATE TABLE owned_parent (id INTEGER PRIMARY KEY)')
                db.execute('CREATE TABLE owned_child (id INTEGER REFERENCES owned_parent(id) DEFERRABLE INITIALLY DEFERRED)')
                db.execute('INSERT INTO owned_child VALUES (1)')
            else:
                db.execute('INSERT INTO cache VALUES (?,?,?,?)', ('owned', 'rollback', '{}', 0))
                raise body
    assert raised.value is (state.transaction_errors[-1] if mode == 'transaction-exit' else body)
    assert db.enters == db.exits == (0 if mode == 'read' else 1)
    assert db.close_calls == 1 and db.closed_cleanly and not reader._sql_lifetime.failures
    with closing(state.raw(reader.path)) as independent:
        assert independent.execute('SELECT COUNT(*) FROM cache').fetchone()[0] == 0
    reader.freeze_connections(0).check(reader)


def test_write_early_return_commits_before_close_and_fence(reading_state):
    state = reading_state
    reader = state.make()

    def write():
        with reader._connection_scope(transaction=True) as db:
            db.execute('INSERT INTO cache VALUES (?,?,?,?)', ('owned', '早退', '{"meaning":"中文"}', 0))
            return db

    db = write()
    assert db.enters == db.exits == db.close_calls == 1
    reader.freeze_connections(0).check(reader)
    with closing(state.raw(reader.path)) as independent:
        assert json.loads(independent.execute('SELECT value FROM cache').fetchone()[0]) == {'meaning': '中文'}


@pytest.mark.parametrize('fault', ['initialize', 'initialize-body', 'read', 'write', 'read-body', 'write-body',
                                 'transaction-exit', 'body-and-rollback'])
def test_failed_close_retains_actual_reading_owner_errors_and_poisons_without_retry(reading_state, fault):
    state = reading_state
    body = RuntimeError('Authored reading body fault.')
    close = OSError('Authored reading close fault.')
    if not fault.startswith('initialize'):
        reader = state.make()
    if fault == 'initialize-body':
        def fail_body(_db, _sql, _params):
            raise body
        state.on_execute = fail_body
    state.close_error = close
    with pytest.raises(ReadingConnectionCloseError) as raised:
        if fault.startswith('initialize'):
            state.make()
        elif fault == 'read':
            reader._cached('meaning', '说', 600)
        elif fault == 'write':
            reader._save('meaning', '说', {'meaning': 'speak'})
        else:
            with reader._connection_scope(transaction=fault != 'read-body') as db:
                if fault == 'transaction-exit':
                    db.execute('PRAGMA foreign_keys=ON')
                    db.execute('CREATE TABLE owned_parent (id INTEGER PRIMARY KEY)')
                    db.execute('CREATE TABLE owned_child (id INTEGER REFERENCES owned_parent(id) DEFERRABLE INITIALLY DEFERRED)')
                    db.execute('INSERT INTO owned_child VALUES (1)')
                else:
                    db.execute('INSERT INTO cache VALUES (?,?,?,?)', ('owned', 'failure', '{}', 0))
                    if fault == 'body-and-rollback':
                        db.set_authorizer(lambda action, first, *_:
                            sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and first == 'ROLLBACK'
                            else sqlite3.SQLITE_OK)
                    raise body
    failure = raised.value
    reader = failure.service
    if reader not in state.readers:
        state.readers.append(reader)
    owner = reader._sql_lifetime
    assert failure.owner is owner and owner.subject is reader and owner.failures == [failure]
    assert failure.connection is state.opened[-1] and failure.close_error is close
    assert failure.body_error is (body if fault in {'initialize-body', 'read-body', 'write-body', 'body-and-rollback'} else None)
    if fault in {'transaction-exit', 'body-and-rollback'}:
        assert failure.transaction_error is state.transaction_errors[-1]
        assert failure.__cause__ is failure.transaction_error
    else:
        assert failure.transaction_error is None
        assert failure.__cause__ is (body if fault in {'initialize-body', 'read-body', 'write-body'} else close)
    state.on_execute = None
    assert failure.connection.execute('SELECT 1').fetchone() == (1,)
    assert not isinstance(failure, LexiriseError)
    assert 'test-key' not in str(failure) and str(reader.path) not in str(failure)
    original_traceback, opened = failure.__traceback__, len(state.opened)
    previous = None
    for _ in range(20):
        for operation in (lambda: reader._cached('meaning', '说', 600),
                          lambda: reader._save('meaning', '说', {}),
                          lambda: reader.freeze_connections(0),
                          lambda: reader.resume_connections(None)):
            with pytest.raises(ReadingConnectionsPoisonedError) as refused:
                operation()
            assert refused.value is not previous and refused.value.failure is failure
            assert refused.value.__cause__ is failure and failure.__traceback__ is original_traceback
            previous = refused.value
    assert len(state.opened) == opened and failure.connection.close_calls == 1
    assert owner.gate._active == 0


@pytest.mark.parametrize('transaction', [False, True])
def test_actual_sql_body_exception_identity_survives_failed_close(reading_state, transaction):
    state = reading_state
    reader = state.make()
    state.close_error = OSError('Authored reading close fault.')
    body = None
    with pytest.raises(ReadingConnectionCloseError) as raised:
        with reader._connection_scope(transaction=transaction) as db:
            try:
                db.execute('SELECT missing_column FROM cache')
            except sqlite3.OperationalError as error:
                body = error
                raise
    failure = raised.value
    assert isinstance(body, sqlite3.OperationalError)
    assert failure.body_error is failure.__cause__ is body
    assert failure.transaction_error is None and failure.connection is db
    assert db.enters == db.exits == int(transaction) and db.close_calls == 1


@pytest.mark.parametrize('write', [False, True])
def test_freeze_waits_for_actual_read_or_write_body_then_close_without_taking_reader_lock(reading_state, monkeypatch, write):
    state = reading_state
    reader = state.make()
    body_entered, body_release = threading.Event(), _event(state)
    close_entered, close_release = threading.Event(), _event(state)
    state.configure = lambda db: (setattr(db, 'close_entered', close_entered),
                                  setattr(db, 'close_release', close_release))

    def hold(_db, sql, _params):
        if sql.startswith('INSERT' if write else 'SELECT'):
            body_entered.set()
            assert body_release.wait(5)

    state.on_execute = hold
    operation = _thread_call(state, lambda: reader._save('meaning', '说', {}) if write
                             else reader._cached('meaning', '说', 600))
    assert body_entered.wait(2)
    stopped = _observe_stop(reader._sql_lifetime, monkeypatch)
    freeze = _thread_call(state, lambda: reader.freeze_connections(3))
    assert stopped.wait(2) and not freeze.done.is_set()
    assert not reader.lock.acquire(blocking=False)  # Freeze must not need this held lock.
    body_release.set()
    assert close_entered.wait(2) and not freeze.done.is_set()
    with pytest.raises(TimeoutError):
        reader.freeze_connections(0)
    close_release.set()
    assert operation.done.wait(2) and freeze.done.wait(2)
    assert operation.error is None and freeze.error is None
    assert state.opened[-1].closed_cleanly and state.opened[-1].close_calls == 1
    fence, opened = freeze.value, len(state.opened)
    fence.check(reader)
    assert reader.freeze_connections(0) is fence
    with pytest.raises(WritersQuiescing):
        reader._cached('meaning', '说', 600)
    assert len(state.opened) == opened
    reader.resume_connections(fence)
    with pytest.raises(ValueError):
        fence.check(reader)


def test_timeout_keeps_reading_admission_closed_until_actual_scope_finishes(reading_state):
    state = reading_state
    reader = state.make()
    entered, release = threading.Event(), _event(state)

    def hold(_db, sql, _params):
        if sql.startswith('SELECT'):
            entered.set()
            assert release.wait(5)

    state.on_execute = hold
    operation = _thread_call(state, lambda: reader._cached('meaning', '说', 600))
    assert entered.wait(2)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        reader.freeze_connections(.04)
    assert time.monotonic()-started < .5 and not operation.done.is_set()
    owner, opened = reader._sql_lifetime, len(state.opened)
    assert not owner.gate._accepting and owner.fence is None
    with pytest.raises(WritersQuiescing):
        with reader._connection_scope():
            pytest.fail('Closed admission must refuse before connection creation.')
    assert len(state.opened) == opened
    release.set()
    assert operation.done.wait(2) and operation.error is None
    fence = reader.freeze_connections(0)
    fence.check(reader)
    reader.resume_connections(fence)


def test_late_gate_contention_cannot_extend_reading_total_freeze_budget(reading_state, monkeypatch):
    state = reading_state
    reader = state.make()
    entered, release = threading.Event(), _event(state)

    def hold(_db, _sql, _params):
        entered.set()
        assert release.wait(5)

    state.on_execute = hold
    operation = _thread_call(state, lambda: reader._cached('meaning', '说', 60))
    assert entered.wait(2)
    owner = reader._sql_lifetime
    stopped = _observe_stop(owner, monkeypatch)
    held, unlock = threading.Event(), _event(state)

    def contend():
        assert stopped.wait(2)
        with owner.gate._condition:
            held.set()
            assert unlock.wait(5)

    holder = _thread_call(state, contend)
    started = time.monotonic()
    freeze = _thread_call(state, lambda: reader.freeze_connections(.06))
    assert held.wait(2)
    assert freeze.done.wait(.5) and time.monotonic()-started < .5
    assert isinstance(freeze.error, TimeoutError) and freeze.value is None
    assert not holder.done.is_set() and not operation.done.is_set()
    assert owner.fence is None and not owner.gate._accepting
    unlock.set()
    release.set()
    assert holder.done.wait(2) and operation.done.wait(2)
    assert holder.error is operation.error is None
    reader.freeze_connections(0).check(reader)


def test_pending_close_failure_is_published_before_scope_leave_and_never_mints_fence(reading_state, monkeypatch):
    state = reading_state
    reader = state.make()
    entered, release = threading.Event(), _event(state)
    state.close_error = OSError('Authored held close fault.')
    state.configure = lambda db: (setattr(db, 'close_entered', entered), setattr(db, 'close_release', release))
    operation = _thread_call(state, lambda: reader._cached('meaning', '说', 60))
    assert entered.wait(2)
    owner = reader._sql_lifetime
    stopped = _observe_stop(owner, monkeypatch)
    freeze = _thread_call(state, lambda: reader.freeze_connections(2))
    assert stopped.wait(2) and not freeze.done.is_set() and not owner.failures
    release.set()
    assert operation.done.wait(2) and freeze.done.wait(2)
    assert isinstance(operation.error, ReadingConnectionCloseError)
    assert isinstance(freeze.error, ReadingConnectionsPoisonedError)
    assert owner.failures == [operation.error] and freeze.error.failure is operation.error
    assert owner.gate._active == 0 and not owner.gate._accepting and owner.fence is None
    assert state.opened[-1].close_calls == 1


def test_factory_failure_balances_admission_without_claiming_an_unreturned_connection(reading_state, monkeypatch):
    state = reading_state
    reader = state.make()
    error = sqlite3.OperationalError('Authored factory refusal.')
    opened = len(state.opened)

    def fail(path, *args, **kwargs):
        assert path == reader.path and not args and not kwargs
        raise error

    monkeypatch.setattr(sqlite3, 'connect', fail)
    with pytest.raises(sqlite3.OperationalError) as raised:
        reader._cached('meaning', '说', 60)
    assert raised.value is error and len(state.opened) == opened
    assert not reader._sql_lifetime.failures and reader._sql_lifetime.gate._active == 0
    reader.freeze_connections(0).check(reader)


def test_fence_is_exact_reader_object_epoch_and_not_a_path_lock(reading_state):
    state = reading_state
    reader, independent = state.make(), state.make()
    assert reader.path == independent.path and reader._sql_lifetime is not independent._sql_lifetime
    fence = reader.freeze_connections(0)
    forged = ReadingConnectionFence(reader, fence._epoch)
    with pytest.raises(ValueError):
        forged.check(reader)
    with pytest.raises(ValueError):
        fence.check(independent)
    with pytest.raises(ValueError):
        independent.resume_connections(fence)
    independent._save('meaning', '说', {'meaning': 'independent'})
    fence.check(reader)
    reader.resume_connections(fence)
    assert reader._cached('meaning', '说', 600) == {'meaning': 'independent'}
    with pytest.raises(ValueError):
        reader.resume_connections(fence)
    current = reader.freeze_connections(0)
    assert current is not fence
    with pytest.raises(ValueError):
        fence.check(reader)


@pytest.mark.parametrize('timeout', [True, None, -1, float('nan'), float('inf'), threading.TIMEOUT_MAX*2])
def test_reading_rejects_invalid_timeout_without_changing_admission(reading_state, timeout):
    reader = reading_state.make()
    with pytest.raises(ValueError):
        reader.freeze_connections(timeout)
    assert reader._sql_lifetime.gate._accepting


def test_worker_callback_future_done_and_pool_join_do_not_precede_actual_callback_sql_close(reading_state, monkeypatch):
    state = reading_state
    reader = state.make()
    worker_entered, worker_release = threading.Event(), _event(state)
    close_entered, close_release = threading.Event(), _event(state)

    def worker(_word):
        worker_entered.set()
        assert worker_release.wait(5)
        raise LexiriseError('Authored dictionary failure.')

    monkeypatch.setattr(reader, '_meaning', worker)
    original_submit, futures = reader.pool.submit, []

    def submit(*args):
        future = original_submit(*args)
        futures.append(future)
        return future

    monkeypatch.setattr(reader.pool, 'submit', submit)
    assert reader._schedule_meaning('说') and worker_entered.wait(2)
    state.configure = lambda db: (setattr(db, 'close_entered', close_entered),
                                  setattr(db, 'close_release', close_release))
    worker_release.set()
    assert close_entered.wait(2) and futures[0].done()
    assert reader.pending_meanings == {'说'}
    drain = _thread_call(state, lambda: reader.quiesce(3))
    stopped = _observe_stop(reader._sql_lifetime, monkeypatch)
    freeze = _thread_call(state, lambda: reader.freeze_connections(3))
    assert stopped.wait(2) and not drain.done.is_set() and not freeze.done.is_set()
    close_release.set()
    assert drain.done.wait(2) and freeze.done.wait(2)
    assert drain.error is freeze.error is None and not reader.pending_meanings
    freeze.value.check(reader)
    reader.resume_connections(freeze.value)
    assert reader._cached('meaning-pending', '说', 60) == {'meaning': ''}


def test_already_done_future_callback_runs_inline_and_sql_fence_covers_what_pool_drain_does_not(reading_state, monkeypatch):
    state = reading_state
    reader = state.make()
    completed = Future()
    completed.set_exception(LexiriseError('Authored completed dictionary failure.'))
    monkeypatch.setattr(reader.pool, 'submit', lambda *_a: completed)
    close_entered, close_release = threading.Event(), _event(state)

    def configure(db):
        # _schedule_meaning's initial read closes before its inline callback.
        if len(state.opened) == 3:
            db.close_entered, db.close_release = close_entered, close_release

    state.configure = configure
    schedule = _thread_call(state, lambda: reader._schedule_meaning('说'))
    assert close_entered.wait(2) and not schedule.done.is_set()
    reader.quiesce(1)  # This real pool has no worker owning the inline callback.
    assert not schedule.done.is_set() and reader.pending_meanings == {'说'}
    with pytest.raises(TimeoutError):
        reader.freeze_connections(.04)
    close_release.set()
    assert schedule.done.wait(2) and schedule.error is None and schedule.value is True
    assert not reader.pending_meanings
    reader.freeze_connections(0).check(reader)


def test_worker_close_fault_stays_owned_after_pool_join_without_callback_connection_retry(reading_state, monkeypatch, caplog):
    state = reading_state
    reader = state.make()
    entered, release = threading.Event(), _event(state)
    close = OSError('Authored worker close fault.')

    def worker(word):
        entered.set()
        assert release.wait(5)
        reader._save('meaning', word, {'meaning': 'speak'})

    monkeypatch.setattr(reader, '_meaning', worker)
    assert reader._schedule_meaning('说') and entered.wait(2)
    state.close_error = close
    release.set()
    reader.quiesce(2)
    assert not reader.pending_meanings
    failure, = reader._sql_lifetime.failures
    assert failure.connection is state.opened[-1] and failure.close_error is close
    assert failure.connection.close_calls == 1 and len(state.opened) == 3
    assert 'exception calling callback' in caplog.text
    with pytest.raises(ReadingConnectionsPoisonedError) as refused:
        reader.freeze_connections(0)
    assert refused.value.failure is failure and len(state.opened) == 3
    # Pool replacement cannot clear a SQL owner's failed-close record.
    reader.resume()
    with pytest.raises(ReadingConnectionsPoisonedError):
        reader._cached('meaning', '说', 60)
    assert len(state.opened) == 3 and failure.connection.close_calls == 1


def test_sql_only_fence_does_not_claim_http_work_or_retire_outer_operations(reading_state):
    state = reading_state
    reader = state.make()
    entered, release = threading.Event(), _event(state)
    requests = []

    def transport(request):
        assert request.method == 'POST' and request.url.path == '/v1/dictionary/lookup'
        assert request.headers['Authorization'] == 'Bearer test-key'
        assert json.loads(request.content) == {'text': '说', 'language': 'zh'}
        requests.append(request.url.path)
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, json={'translations': [{'target_lang': 'en', 'translation': 'speak'}]})

    state.service.transport = httpx.MockTransport(transport)
    meaning = _thread_call(state, lambda: reader._meaning('说'))
    assert entered.wait(2)
    fence = reader.freeze_connections(0)
    fence.check(reader)
    assert not meaning.done.is_set()  # Deliberate negative: HTTP is outside SQL.
    opened = len(state.opened)
    release.set()
    assert meaning.done.wait(2) and isinstance(meaning.error, WritersQuiescing)
    assert len(state.opened) == opened and requests == ['/v1/dictionary/lookup']
    fence.check(reader)
    reader.resume_connections(fence)


def test_private_read_cursor_can_outlive_successful_close_and_operation_fence(reading_state):
    state = reading_state
    reader = state.make()
    with reader._connection_scope(transaction=True) as db:
        assert db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete'
        db.executemany('INSERT INTO cache VALUES (?,?,?,?)', [('owned', '1', '{}', 0), ('owned', '2', '{}', 0)])
    cursor = None
    try:
        with reader._connection_scope() as db:
            cursor = db.execute('SELECT key FROM cache')
            assert cursor.fetchone()[0] == '1'
        reader.freeze_connections(0).check(reader)
        assert db.closed_cleanly
        with closing(state.raw(reader.path, timeout=0)) as independent:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                independent.execute('BEGIN EXCLUSIVE')
    finally:
        cursor = None  # Fixture disposal, never product release evidence.


def test_reading_scope_preserves_exact_three_store_c5_factory_and_no_checkpoint_policy(tmp_path, monkeypatch):
    from backend import runtime_probe
    from backend.storage import TranscriptStore
    data = (tmp_path/'owned-c5-data').resolve()
    data.mkdir()
    layout = SimpleNamespace(data_root=data)
    original, observed = sqlite3.connect, []

    def forbidden(*_a, **_k):
        pytest.fail('Owned C5 constructors must not reach credentials or network.')

    def connect(path, *args, **kwargs):
        assert not args
        observed.append((path.name, kwargs.copy()))
        connection = original(path, **kwargs)
        return connection

    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    reader = None
    try:
        with runtime_probe._authored_wal_connections(layout) as policy:
            store = TranscriptStore(data/'transcript-v2.db')
            service = LexiriseService(data/'lexirise', api_key='test-key', transport=httpx.MockTransport(forbidden))
            reader = LexiriseReadingService(data/'lexirise', service)
            policy.require_stores()
            assert policy.opens == 3 and policy.configured == {'transcript', 'exports', 'reading'}
            assert not store._connection_failures and not service._sql_lifetime.failures
            assert not reader._sql_lifetime.failures
        assert observed == [('transcript-v2.db', {'timeout': 10}), ('exports-v2.db', {'timeout': 10}),
                            ('reading-cache-v2.db', {})]
    finally:
        if reader is not None:
            reader.pool.shutdown(wait=True)
