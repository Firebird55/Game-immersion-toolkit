"""Owned SQLite statements and error identities, without physical-detach claims.

These actual Cursor/Connection fixtures catch resources which an operation
counter alone cannot settle, including execute failing before cursor handover.
Native/frame/credential/account work is forbidden; all HTTP uses strict mocks.
"""
from contextlib import closing
import sqlite3
import threading
from types import SimpleNamespace

import httpx
import pytest

from backend import lexirise
from backend.lexirise import LexiriseService, LexiriseLedgerPoisonedError
from backend.reading import LexiriseReadingService
from backend.sqlite_operation_lifetime import _SqliteCursorCloseError
from backend.storage import TranscriptStore


class FalseyError(RuntimeError):
    def __bool__(self):
        return False


@pytest.fixture
def sql_state(tmp_path, monkeypatch):
    raw = sqlite3.connect
    state = SimpleNamespace(opened=[], threads=[], releases=[], cursor_error=None,
        cursor_before_close=False, connection_error=None, factory_error=None,
        execute_hook=None, cursor_entered=None, cursor_release=None, exit_error=None,
        explicit_commits=[], readers=[])

    def forbidden(*_args, **_kwargs):
        pytest.fail('Owned statement tests must not access credentials or real account transport.')

    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(lexirise, 'os', SimpleNamespace(environ=SimpleNamespace(get=forbidden), name='nt'))

    class Cursor(sqlite3.Cursor):
        def execute(self, sql, parameters=()):
            self.connection.order.append(('execute', self))
            try:
                result = super().execute(sql, parameters)
            except BaseException as error:
                self.sql_error = error
                raise
            if state.execute_hook is not None:
                state.execute_hook(self, sql)
            return result

        def close(self):
            self.close_calls += 1
            self.connection.order.append(('cursor-close-enter', self))
            if self.close_entered is not None:
                self.close_entered.set()
                assert self.close_release.wait(5), 'Authored cursor holder was not released.'
            if self.close_error is not None and self.before_close:
                raise self.close_error
            super().close()
            self.native_closed = True
            self.connection.order.append(('cursor-close-return', self))
            if self.close_error is not None:
                raise self.close_error

    class Connection(sqlite3.Connection):
        def cursor(self):
            if self.factory_error is not None:
                raise self.factory_error
            cursor = super().cursor(factory=Cursor)
            cursor.close_calls, cursor.native_closed, cursor.sql_error = 0, False, None
            cursor.close_error, cursor.before_close = state.cursor_error, state.cursor_before_close
            cursor.close_entered, cursor.close_release = state.cursor_entered, state.cursor_release
            self.cursors.append(cursor)
            return cursor

        def __enter__(self):
            self.enters += 1
            return super().__enter__()

        def __exit__(self, *args):
            self.exits += 1
            try:
                result = super().__exit__(*args)
                if self.exit_error is not None:
                    raise self.exit_error
                return result
            except BaseException as error:
                self.transaction_error = error
                raise

        def commit(self):
            # Production's explicit commits must follow all prior cursor closes.
            assert all(cursor.close_calls == 1 for cursor in self.cursors)
            state.explicit_commits.append(self)
            return super().commit()

        def close(self):
            self.close_calls += 1
            self.order.append(('connection-close', self))
            if self.close_error is not None:
                raise self.close_error
            super().close()
            self.closed_cleanly = True

    def connect(database, *args, **options):
        assert not args
        assert options == ({} if database.name == 'reading-cache-v2.db' else {'timeout': 10})
        db = raw(database, **options, factory=Connection, check_same_thread=False)
        db.cursors, db.order = [], []
        db.close_calls = db.enters = db.exits = 0
        db.closed_cleanly, db.transaction_error = False, None
        db.close_error, db.factory_error, db.exit_error = state.connection_error, state.factory_error, state.exit_error
        state.opened.append(db)
        return db

    monkeypatch.setattr(sqlite3, 'connect', connect)

    def make(kind, *, transport=None):
        if kind == 'transcript':
            value = TranscriptStore(tmp_path/'owned-transcript.db')
        else:
            root = LexiriseService(tmp_path/'owned-lexirise', api_key='test-key',
                accounts=SimpleNamespace(active_key=forbidden),
                transport=transport or httpx.MockTransport(forbidden))
            if kind == 'reading':
                value = LexiriseReadingService(tmp_path/'owned-lexirise', root)
                state.readers.append(value)
            else:
                value = root
        return value

    state.raw, state.make, state.forbidden = raw, make, forbidden
    yield state
    for release in state.releases:
        release.set()
    for call in state.threads:
        call.thread.join(5)
        assert not call.thread.is_alive(), 'Authored statement worker remains live.'
    for reader in state.readers:
        reader.pool.shutdown(wait=True)
    for db in state.opened:
        if not db.closed_cleanly:
            # Dispose only authored failed fixtures after assertions. Pre-close
            # cursor faults keep this connection open via an additional authored
            # connection-close refusal; no product retry or release proof follows.
            for cursor in db.cursors:
                if not cursor.native_closed:
                    sqlite3.Cursor.close(cursor)
            sqlite3.Connection.close(db)


def scope(value, *, read=False):
    if isinstance(value, TranscriptStore):
        return value._connection_scope()
    if isinstance(value, LexiriseService):
        return value._connect()
    return value._connection_scope(transaction=not read)


def read(value):
    if isinstance(value, TranscriptStore):
        return value.count()
    if isinstance(value, LexiriseService):
        return value._decks()
    return value._cached('meaning', '说', 60)


def path(value):
    return value.db_path if isinstance(value, LexiriseService) else value.path


def thread_call(state, operation):
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


def exclusive(state, value):
    with closing(state.raw(path(value), timeout=0)) as db:
        cursor = db.cursor()
        try:
            cursor.execute('BEGIN EXCLUSIVE')
            db.rollback()
        finally:
            cursor.close()


@pytest.mark.parametrize('kind', ['transcript', 'ledger', 'reading'])
def test_normal_production_statements_close_before_connection_and_materialize_values(sql_state, kind):
    state = sql_state
    value = state.make(kind)
    result = read(value)
    assert not isinstance(result, sqlite3.Cursor)
    for db in state.opened:
        assert db.close_calls == 1 and db.closed_cleanly and db.cursors
        assert all(cursor.close_calls == 1 and cursor.native_closed for cursor in db.cursors)
        assert db.order[-1] == ('connection-close', db)
        for cursor in db.cursors:
            with pytest.raises(sqlite3.ProgrammingError):
                cursor.fetchone()
    assert not value._sql_lifetime.failures


@pytest.mark.parametrize('kind', ['transcript', 'ledger', 'reading'])
def test_owned_unfinished_cursor_and_body_traceback_can_remain_referenced_after_scope_cleanup(sql_state, kind):
    state = sql_state
    value = state.make(kind)
    owner = value._sql_lifetime
    with scope(value) as db:
        with owner.cursor(db) as cursor:
            assert cursor.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete'
        with owner.cursor(db) as cursor:
            cursor.execute('CREATE TABLE owned_rows (id INTEGER PRIMARY KEY, text TEXT)')
        with owner.cursor(db) as cursor:
            cursor.executemany('INSERT INTO owned_rows VALUES (?,?)', [(1, '甲'), (2, '乙')])
    body = RuntimeError('Authored retained body error.')
    with pytest.raises(RuntimeError) as raised:
        with scope(value, read=True) as db:
            with owner.cursor(db) as retained:
                assert tuple(retained.execute('SELECT id,text FROM owned_rows').fetchone()) == (1, '甲')
                raise body
    assert raised.value is body and body.__traceback__ is not None
    assert retained.close_calls == db.close_calls == 1 and retained.native_closed
    if kind == 'reading':
        assert db.enters == db.exits == 0
    value.freeze_connections(0).check(value)
    with pytest.raises(sqlite3.ProgrammingError):
        retained.fetchone()
    exclusive(state, value)  # Retained cursor/error/traceback are all still alive.


@pytest.mark.parametrize('kind', ['transcript', 'ledger', 'reading'])
@pytest.mark.parametrize('close_fault', [False, True])
def test_blocked_actual_cursor_close_holds_operation_and_precedes_connection_close(sql_state, kind, close_fault):
    state = sql_state
    value = state.make(kind)
    entered, release = threading.Event(), threading.Event()
    state.releases.append(release)
    state.cursor_entered, state.cursor_release = entered, release
    if close_fault:
        state.cursor_error = OSError('Authored late cursor close fault.')
    worker = thread_call(state, lambda: read(value))
    try:
        assert entered.wait(2)
        db = state.opened[-1]
        assert db.close_calls == 0 and not worker.done.is_set()
        with pytest.raises(TimeoutError):
            value.freeze_connections(.03)
        assert not value._sql_lifetime.gate._accepting and value._sql_lifetime.fence is None
        release.set()
        assert worker.done.wait(2)
        assert db.close_calls == 1 and db.cursors[-1].close_calls == 1
        if close_fault:
            assert type(worker.error) is _SqliteCursorCloseError
            with pytest.raises(RuntimeError) as refused:
                value.freeze_connections(0)
            assert refused.value.failure is worker.error
            assert value._sql_lifetime.fence is None
        else:
            assert worker.error is None
            value.freeze_connections(0).check(value)
    finally:
        release.set()


@pytest.mark.parametrize('kind', ['transcript', 'ledger', 'reading'])
@pytest.mark.parametrize('connection_fault', [False, True])
def test_cursor_factory_failure_before_handover_closes_connection_without_inventing_cursor(sql_state, kind, connection_fault):
    state = sql_state
    value = state.make(kind)
    error = RuntimeError('Authored cursor factory failure before handover.')
    state.factory_error = error
    if connection_fault:
        state.connection_error = OSError('Authored factory cleanup fault.')
    with pytest.raises(RuntimeError) as raised:
        read(value)
    db = state.opened[-1]
    assert db.cursors == [] and db.close_calls == 1
    if connection_fault:
        failure, = value._sql_lifetime.failures
        assert raised.value is failure and failure.body_error is error
        assert failure.close_error is state.connection_error
        assert failure.transaction_error is None and failure.__cause__ is error
    else:
        assert raised.value is error and db.closed_cleanly and not value._sql_lifetime.failures
        value.freeze_connections(0).check(value)


@pytest.mark.parametrize('kind', ['transcript', 'ledger', 'reading'])
def test_constructor_statement_failure_retains_actual_partial_owner_before_schema_completes(sql_state, kind):
    state = sql_state
    if kind == 'reading':
        root = state.make('ledger')
    state.cursor_error = OSError('Authored constructor statement close fault.')
    with pytest.raises(_SqliteCursorCloseError) as raised:
        if kind == 'reading':
            LexiriseReadingService(root.directory, root)
        else:
            state.make(kind)
    failure = raised.value
    partial = failure.owner.subject
    if kind == 'reading':
        state.readers.append(partial)  # Dispose the actual failed constructor pool.
    assert partial._sql_lifetime is failure.owner and failure.owner.failures[0] is failure
    assert failure.cursor is failure.connection.cursors[0]
    assert failure.cursor.close_calls == failure.connection.close_calls == 1
    opened = len(state.opened)
    with pytest.raises(RuntimeError) as refused:
        partial.freeze_connections(0)
    assert refused.value.failure is failure and len(state.opened) == opened


@pytest.mark.parametrize('fault', ['no-body', 'body', 'sql', 'explicit-commit', 'rollback'])
@pytest.mark.parametrize('connection_fault', [False, True])
def test_original_sql_body_transaction_and_actual_close_identities_survive_cursor_cleanup_failure(sql_state, fault, connection_fault):
    state = sql_state
    value = state.make('transcript')
    owner = value._sql_lifetime
    # Fixture setup uses owned statements and an ordinary commit.
    with scope(value) as db:
        with owner.cursor(db) as cursor:
            cursor.execute('CREATE TABLE owned_rollback (id INTEGER)')
    cursor_error, connection_error = FalseyError('Authored cursor fault.'), FalseyError('Authored connection fault.')
    body = FalseyError('Authored body fault.')
    state.cursor_error = cursor_error  # Actual cursor closes, then fixture raises; still poison.
    if connection_fault:
        state.connection_error = connection_error
    with pytest.raises(BaseException) as raised:
        with scope(value) as db:
            with owner.cursor(db) as cursor:
                if fault == 'sql':
                    cursor.execute('SELECT missing_column FROM owned_rollback')
                elif fault == 'explicit-commit':
                    # A real failed commit inside an owned statement body.
                    cursor.execute('PRAGMA foreign_keys=ON')
                    cursor.execute('CREATE TABLE owned_parent (id INTEGER PRIMARY KEY)')
                    cursor.execute('CREATE TABLE owned_child (id INTEGER REFERENCES owned_parent(id) DEFERRABLE INITIALLY DEFERRED)')
                    cursor.execute('INSERT INTO owned_child VALUES (1)')
                    # Bypass the fixture's production-only closed-cursor
                    # assertion to fault a real commit inside this owned body.
                    sqlite3.Connection.commit(db)
                else:
                    cursor.execute('INSERT INTO owned_rollback VALUES (1)')
                    if fault == 'rollback':
                        db.set_authorizer(lambda action, first, *_:
                            sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and first == 'ROLLBACK'
                            else sqlite3.SQLITE_OK)
                    if fault in {'body', 'rollback'}:
                        raise body
    cursor_failure = owner.failures[0]
    assert type(cursor_failure) is _SqliteCursorCloseError
    assert cursor_failure.owner is owner and cursor_failure.connection is db and cursor_failure.cursor is cursor
    assert cursor_failure.close_error is cursor_error and cursor.close_calls == db.close_calls == 1
    original_body = cursor.sql_error if fault == 'sql' else body if fault in {'body', 'rollback'} else None
    if fault == 'explicit-commit':
        original_body = cursor_failure.body_error
        assert isinstance(original_body, sqlite3.IntegrityError)
    assert cursor_failure.body_error is original_body
    transaction = db.transaction_error if fault == 'rollback' else None
    assert cursor_failure.transaction_error is transaction
    if connection_fault:
        connection_failure = owner.failures[1]
        assert raised.value is connection_failure and connection_failure.connection is db
        assert connection_failure.body_error is original_body and connection_failure.transaction_error is transaction
        assert connection_failure.close_error is connection_error
        expected_cause = transaction if transaction is not None else original_body if original_body is not None else connection_error
        assert connection_failure.__cause__ is expected_cause
    else:
        assert raised.value is (transaction if transaction is not None else cursor_failure)
    assert owner.gate._active == 0
    opened, trace = len(state.opened), cursor_failure.__traceback__
    previous = None
    for _ in range(20):
        for operation in (lambda: read(value), lambda: value.freeze_connections(0),
                          lambda: value.resume_connections(None)):
            with pytest.raises(RuntimeError) as refused:
                operation()
            assert refused.value is not previous and refused.value.failure is cursor_failure
            assert cursor_failure.__traceback__ is trace
            previous = refused.value
    assert len(state.opened) == opened and cursor.close_calls == db.close_calls == 1


def test_preclose_cursor_refusal_retains_real_locked_objects_and_never_retries(sql_state):
    state = sql_state
    value = state.make('transcript')
    owner = value._sql_lifetime
    with scope(value) as db:
        with owner.cursor(db) as cursor:
            cursor.execute('PRAGMA journal_mode=DELETE')
        with owner.cursor(db) as cursor:
            cursor.execute('CREATE TABLE owned_rows (id INTEGER)')
        with owner.cursor(db) as cursor:
            cursor.executemany('INSERT INTO owned_rows VALUES (?)', [(1,), (2,)])
    state.cursor_error, state.connection_error = OSError('Authored cursor refusal.'), OSError('Authored connection refusal.')
    state.cursor_before_close = True
    with pytest.raises(RuntimeError) as raised:
        with scope(value) as db:
            with owner.cursor(db) as cursor:
                assert cursor.execute('SELECT id FROM owned_rows').fetchone()[0] == 1
    cursor_failure, connection_failure = owner.failures
    assert raised.value is connection_failure and cursor_failure.cursor is cursor and connection_failure.connection is db
    assert not cursor.native_closed and not db.closed_cleanly
    with pytest.raises(sqlite3.OperationalError, match='locked'):
        exclusive(state, value)
    with pytest.raises(RuntimeError) as refused:
        value.freeze_connections(0)
    assert refused.value.failure is cursor_failure and cursor.close_calls == db.close_calls == 1


def test_error_unwrap_requires_issued_object_identity_even_with_equal_class_fields(sql_state, monkeypatch):
    state = sql_state
    value = state.make('transcript')
    owner = value._sql_lifetime
    marker = RuntimeError('Authored imitation body marker.')
    state.cursor_error, state.connection_error = OSError('Actual cursor fault.'), OSError('Actual connection fault.')
    with pytest.raises(RuntimeError) as raised:
        with scope(value) as db:
            with pytest.raises(_SqliteCursorCloseError) as actual:
                with owner.cursor(db) as cursor:
                    cursor.execute('SELECT 1')
            real = actual.value
            forged = _SqliteCursorCloseError(owner, db, cursor, marker, state.cursor_error)
            monkeypatch.setattr(_SqliteCursorCloseError, '__eq__', lambda _self, _other: True, raising=False)
            assert forged is not real and forged == real  # Equality cannot authorize unwrap.
            raise forged
    connection_failure = raised.value
    assert owner.failures[0] is real and owner.failures[1] is connection_failure
    assert connection_failure.body_error is forged and connection_failure.body_error is not marker
    assert connection_failure.__cause__ is forged and all(item is not forged for item in owner.failures)
    assert cursor.close_calls == db.close_calls == 1


def test_issued_pin_cursor_failure_cannot_unwrap_body_for_another_connection_in_same_owner(sql_state):
    state = sql_state
    root = state.make('ledger')
    pin = root.pin('ja')
    body = RuntimeError('Authored original pinned body.')
    with pytest.raises(RuntimeError) as raised:
        with root._connect() as outer:
            state.cursor_error = OSError('Authored inner cursor close fault.')
            with pytest.raises(_SqliteCursorCloseError) as inner:
                with pin._connect() as db:
                    with pin._sql_lifetime.cursor(db) as cursor:
                        cursor.execute('SELECT 1')
                        raise body
            actual = inner.value
            outer.close_error = OSError('Authored outer connection close fault.')
            raise actual
    failure = raised.value
    assert root._sql_lifetime is pin._sql_lifetime and actual.owner is root._sql_lifetime
    assert actual.body_error is body and actual.connection is db and failure.connection is outer
    assert failure.body_error is failure.__cause__ is actual  # Different actual connection: no unwrap.
    assert cursor.close_calls == db.close_calls == outer.close_calls == 1


def test_falsey_transaction_exit_error_is_retained_with_both_cleanup_faults(sql_state):
    state = sql_state
    value = state.make('transcript')
    body, transaction = FalseyError('Authored body.'), FalseyError('Authored transaction exit.')
    state.cursor_error, state.connection_error, state.exit_error = FalseyError('Authored cursor close.'), FalseyError('Authored connection close.'), transaction
    with pytest.raises(RuntimeError) as raised:
        with scope(value) as db:
            with value._sql_lifetime.cursor(db) as cursor:
                cursor.execute('SELECT 1')
                raise body
    cursor_failure, connection_failure = value._sql_lifetime.failures
    assert raised.value is connection_failure
    assert cursor_failure.body_error is connection_failure.body_error is body
    assert cursor_failure.transaction_error is connection_failure.transaction_error is transaction
    assert connection_failure.__cause__ is transaction and cursor.close_calls == db.close_calls == 1


@pytest.mark.parametrize('connection_fault', [False, True])
def test_real_transaction_exit_commit_failure_follows_owned_cursor_close(sql_state, connection_fault):
    state = sql_state
    value = state.make('transcript')
    if connection_fault:
        state.connection_error = OSError('Authored post-commit cleanup fault.')
    with pytest.raises(BaseException) as raised:
        with scope(value) as db:
            with value._sql_lifetime.cursor(db) as cursor:
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.execute('CREATE TABLE owned_parent (id INTEGER PRIMARY KEY)')
                cursor.execute('CREATE TABLE owned_child (id INTEGER REFERENCES owned_parent(id) DEFERRABLE INITIALLY DEFERRED)')
                cursor.execute('INSERT INTO owned_child VALUES (1)')
    assert isinstance(db.transaction_error, sqlite3.IntegrityError)
    assert cursor.close_calls == db.close_calls == 1 and cursor.native_closed
    if connection_fault:
        failure, = value._sql_lifetime.failures
        assert raised.value is failure and failure.body_error is None
        assert failure.transaction_error is failure.__cause__ is db.transaction_error
    else:
        assert raised.value is db.transaction_error and not value._sql_lifetime.failures
        value.freeze_connections(0).check(value)


@pytest.mark.parametrize('connection_fault', [False, True])
def test_reading_cursor_failure_preserves_nontransactional_original_body(sql_state, connection_fault):
    state = sql_state
    value = state.make('reading')
    body = FalseyError('Authored read body fault.')
    state.cursor_error = FalseyError('Authored read cursor fault.')
    if connection_fault:
        state.connection_error = FalseyError('Authored read connection fault.')

    def fail(_cursor, _sql):
        raise body

    state.execute_hook = fail
    with pytest.raises(RuntimeError) as raised:
        read(value)
    cursor_failure = value._sql_lifetime.failures[0]
    db = cursor_failure.connection
    assert cursor_failure.body_error is body and cursor_failure.transaction_error is None
    assert db.enters == db.exits == 0 and cursor_failure.cursor.close_calls == db.close_calls == 1
    if connection_fault:
        failure = value._sql_lifetime.failures[1]
        assert raised.value is failure and failure.body_error is failure.__cause__ is body
        assert failure.transaction_error is None
    else:
        assert raised.value is cursor_failure


def test_caught_cursor_failure_cannot_allocate_another_owned_statement(sql_state):
    state = sql_state
    value = state.make('transcript')
    state.cursor_error = OSError('Authored caught cursor close fault.')
    with scope(value) as db:
        with pytest.raises(_SqliteCursorCloseError) as failed:
            with value._sql_lifetime.cursor(db) as cursor:
                cursor.execute('SELECT 1')
        count = len(db.cursors)
        with pytest.raises(RuntimeError) as refused:
            with value._sql_lifetime.cursor(db):
                pytest.fail('Poison must refuse before a second actual cursor.')
        assert refused.value.failure is failed.value and len(db.cursors) == count == 1
    with pytest.raises(RuntimeError) as refused:
        value.freeze_connections(0)
    assert refused.value.failure is failed.value and cursor.close_calls == db.close_calls == 1


def test_pin_cursor_failure_uses_exact_root_owner_and_refuses_other_pin_sql(sql_state):
    state = sql_state
    root = state.make('ledger')
    pin, other = root.pin('ja'), root.pin('nl')
    assert pin._sql_lifetime is other._sql_lifetime is root._sql_lifetime
    state.cursor_error = OSError('Authored pinned statement fault.')
    with pytest.raises(_SqliteCursorCloseError) as raised:
        read(pin)
    failure = raised.value
    assert failure.owner is root._sql_lifetime and failure.owner.subject is root
    opened = len(state.opened)
    for service in (root, pin, other, root.pin('zh')):
        with pytest.raises(LexiriseLedgerPoisonedError) as refused:
            read(service)
        assert refused.value.failure is failure
    assert len(state.opened) == opened and failure.cursor.close_calls == failure.connection.close_calls == 1


def test_ledger_materializes_selects_before_mock_http_and_keeps_intermediate_commits(sql_state):
    state = sql_state
    requests = []

    def transport(request):
        assert request.headers['Authorization'] == 'Bearer test-key'
        assert all(cursor.close_calls == 1 for db in state.opened for cursor in db.cursors)
        item = (request.method, request.url.path)
        requests.append(item)
        if item == ('GET', '/v1/me'):
            result = {'user': {'id': 'owned-user'}}
        elif item == ('GET', '/v1/decks/1'):
            result = {'deck': {'owner_user_id': 'owned-user', 'language': 'zh',
                              'unit_type': 'sentence', 'deck_type': 'snapshot'}, 'items': []}
        elif item == ('GET', '/v1/vocabulary'):
            result = {'items': []}
        elif item == ('POST', '/v1/vocabulary'):
            result = {'item': {'id': 7}}
        elif item == ('POST', '/v1/decks/1/items'):
            result = {'added_count': 1}
        else:
            pytest.fail('Unexpected authored account operation.')
        return httpx.Response(200, json=result)

    root = state.make('ledger', transport=httpx.MockTransport(transport))
    with root._connect() as db:
        with root._sql_lifetime.cursor(db) as cursor:
            cursor.execute('INSERT INTO game_decks VALUES (?,?,?,?)', (root._scope(), 'zzz', 1, 'Owned deck'))
    assert root.send(ref='owned-ref', game='zzz', chinese='合成句子', english='Owned sentence',
                     speaker='', audio=None) == {'sent': True, 'already_sent': False, 'deck_id': 1}
    assert len(state.explicit_commits) == 2
    assert ('POST', '/v1/vocabulary') in requests and ('POST', '/v1/decks/1/items') in requests
    assert root.status()['sent'] == {'owned-ref': 1}
