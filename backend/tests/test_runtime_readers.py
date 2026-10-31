"""Actual reading constructors/SQL/pools, explicit fake account transport only."""
import asyncio
import copy
import sqlite3
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from backend import lexirise
from backend.lexirise import LexiriseService
from backend.reading import LexiriseReadingService, ReadingConnectionCloseError
from backend.runtime_readers import RuntimeReadingRegistry, ReadingRegistryPoisonedError
from backend.runtime_writers import WritersQuiescing


@pytest.fixture
def state(tmp_path, monkeypatch):
    raw, constructor = sqlite3.connect, LexiriseReadingService.__init__
    value = SimpleNamespace(opened=[], readers=[], threads=[], releases=[], configure=None,
        before_init=None, on_close=None, close_error=None, transport=None, requests=[], init_calls=[])

    def forbidden(*_a, **_k):
        pytest.fail('Registry tests must not access credential fallback or a real account.')

    def transport(request):
        assert request.method == 'GET' and request.url.path == '/v1/settings'
        value.requests.append((request.method, request.url.path))
        if value.transport is None:
            forbidden()
        return value.transport(request)

    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(lexirise, 'os', SimpleNamespace(environ=SimpleNamespace(get=forbidden), name='nt'))
    value.service = LexiriseService(tmp_path/'owned', api_key='authored-key',
        accounts=SimpleNamespace(active_key=forbidden), transport=httpx.MockTransport(transport))
    value.registry = RuntimeReadingRegistry(tmp_path/'owned')

    class Observed(sqlite3.Connection):
        def close(self):
            self.close_calls += 1
            if value.on_close is not None:
                value.on_close(self)
            if self.close_entered is not None:
                self.close_entered.set()
                assert self.close_release.wait(5), 'Authored constructor close was not released.'
            if self.close_error is not None:
                raise self.close_error
            super().close()
            self.closed_cleanly = True

    def connect(database, *args, **options):
        assert not args and options == {}  # Reading's exact existing C5 factory.
        connection = raw(database, factory=Observed, check_same_thread=False)
        connection.close_calls, connection.closed_cleanly = 0, False
        connection.close_error = value.close_error
        connection.close_entered = connection.close_release = None
        value.opened.append(connection)
        if value.configure is not None:
            value.configure(connection)
        return connection

    def init(reader, *args, **options):
        # The actual object is retained before the first line of __init__,
        # while constructor SQL/account/pool work owns no registry lock.
        assert any(record.reader is reader for record in value.registry.owned_snapshot(time.monotonic()+1))
        assert value.registry._lock.acquire(blocking=False)
        value.registry._lock.release()
        value.readers.append(reader)
        value.init_calls.append((args, options.copy()))
        if value.before_init is not None:
            value.before_init(reader)
        constructor(reader, *args, **options)

    monkeypatch.setattr(sqlite3, 'connect', connect)
    monkeypatch.setattr(LexiriseReadingService, '__init__', init)
    value.raw, value.forbidden = raw, forbidden
    yield value
    for event in value.releases:
        event.set()
    for call in value.threads:
        call.thread.join(5)
        assert not call.thread.is_alive(), 'Authored registry call did not finish.'
    for reader in value.readers:
        pool = vars(reader).get('pool')
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
    # Dispose failed authored connections only after assertions. Product code
    # must never retry their close or count this as physical-resource proof.
    for connection in value.opened:
        if not connection.closed_cleanly:
            sqlite3.Connection.close(connection)


def settings_payload():
    return {'languages': ['zh', 'ja'], 'global': {'effectiveTranslationLanguage': 'en'},
            'languageSettings': {'ja': {'effectiveTranslationLanguage': 'fr'}}}


def event(state):
    result = threading.Event()
    state.releases.append(result)
    return result


def spawn(state, operation):
    result = SimpleNamespace(value=None, error=None, done=threading.Event())
    def run():
        try:
            result.value = operation()
        except BaseException as error:
            result.error = error
        finally:
            result.done.set()
    result.thread = threading.Thread(target=run)
    state.threads.append(result)
    result.thread.start()
    return result


def get(state, *, source='zh', target='en', settings='settings-one', entered=None):
    with state.registry.lookup() as lookup:
        if entered is not None: entered.set()
        session = state.service.pin(source)
        key = (session._scope(), source, target, settings)
        return state.registry.get_or_create(lookup, key, session,
            source_language=source, translation_language=target)


def hold_first_close(state):
    entered, release = event(state), event(state)
    def configure(connection):
        state.configure = None
        connection.close_entered, connection.close_release = entered, release
    state.configure = configure
    return entered, release


def test_same_key_has_one_actual_constructor_and_independent_key_is_not_locked(state):
    default = state.registry.create_default(state.service)
    entered, release = hold_first_close(state)
    first = spawn(state, lambda: get(state))
    assert entered.wait(1)
    duplicate_entered = event(state)
    duplicate = spawn(state, lambda: get(state, entered=duplicate_entered))
    assert duplicate_entered.wait(1)
    other = spawn(state, lambda: get(state, source='ja', target='fr'))
    assert other.done.wait(1) and other.error is None
    assert len(state.readers) == 3  # Default + held zh constructor + independent ja.
    assert not first.done.is_set() and not duplicate.done.is_set()
    release.set()
    assert first.done.wait(1) and duplicate.done.wait(1)
    assert first.error is duplicate.error is None
    assert first.value is duplicate.value and first.value is not other.value
    records = state.registry.owned_snapshot(time.monotonic()+1)
    assert {record.reader for record in records} == {default, first.value, other.value}
    assert all(record.state == 'ready' for record in records)
    assert len(state.registry.cached) == 2
    with pytest.raises(TypeError): state.registry.cached[('forged',)] = default
    state.registry.shutdown(time.monotonic()+1)
    for record in records:
        with pytest.raises(WritersQuiescing): record.reader.pool.submit(lambda: None)


def test_lookup_stop_during_constructor_retains_object_without_return_or_replacement(state, monkeypatch):
    entered, release = hold_first_close(state)
    first = spawn(state, lambda: get(state))
    assert entered.wait(1)
    duplicate_entered = event(state)
    duplicate = spawn(state, lambda: get(state, entered=duplicate_entered))
    assert duplicate_entered.wait(1)
    stopped = event(state)
    original = state.registry.stop_creation
    def stop(deadline):
        original(deadline); stopped.set()
    monkeypatch.setattr(state.registry, 'stop_creation', stop)
    drain = spawn(state, lambda: state.registry.quiesce_owned(time.monotonic()+3))
    assert stopped.wait(1)
    assert duplicate.done.wait(1) and isinstance(duplicate.error, WritersQuiescing)
    with pytest.raises(TimeoutError): state.registry.resume_pools()
    assert not drain.done.is_set() and len(state.readers) == 1
    release.set()
    assert first.done.wait(1) and isinstance(first.error, WritersQuiescing)
    assert drain.done.wait(1) and drain.error is None
    record, = state.registry.owned_snapshot(time.monotonic()+1)
    assert record.reader is state.readers[0] and record.state == 'ready'
    assert list(state.registry.cached.values()) == [record.reader]
    with pytest.raises(WritersQuiescing): get(state)
    state.registry.resume_pools()
    with pytest.raises(WritersQuiescing): get(state)
    state.registry.reopen_creation()
    assert get(state) is record.reader and len(state.readers) == 1


def test_mock_settings_lookup_is_owned_before_key_and_cannot_construct_after_stop(state):
    from backend.api import Runtime
    entered, release = event(state), event(state)
    def transport(request):
        assert request.method == 'GET' and request.url.path == '/v1/settings'
        entered.set(); assert release.wait(5)
        return httpx.Response(200, json=settings_payload())
    state.transport = transport
    runtime = Runtime.__new__(Runtime)
    runtime.lexirise, runtime._reading_registry = state.service, state.registry
    call = spawn(state, lambda: runtime.reading_for(SimpleNamespace(source_language='zh')))
    assert entered.wait(1)
    state.registry.stop_creation(time.monotonic()+.2)
    with pytest.raises(TimeoutError): state.registry.quiesce_owned(time.monotonic()+.02)
    assert len(state.registry._lookups) == 1 and not state.readers
    with pytest.raises(TimeoutError): state.registry.resume_pools()
    release.set()
    assert call.done.wait(1) and isinstance(call.error, WritersQuiescing)
    assert not state.readers and not state.opened
    state.registry.quiesce_owned(time.monotonic()+1)
    state.registry.resume_pools(); state.registry.reopen_creation()
    reader = runtime.reading_for(SimpleNamespace(source_language='zh'))
    assert reader.source_language == 'zh' and len(state.readers) == 1
    assert state.requests == [('GET', '/v1/settings')]


def test_settings_failure_keeps_its_original_retry_semantics_without_poison(state):
    from backend.api import Runtime
    from backend.lexirise import LexiriseError
    state.transport = lambda request: httpx.Response(503, json={'error': 'authored unavailable'})
    runtime = Runtime.__new__(Runtime)
    runtime.lexirise, runtime._reading_registry = state.service, state.registry
    with pytest.raises(LexiriseError): runtime.reading_for(SimpleNamespace(source_language='zh'))
    assert not state.registry._lookups and not state.readers and state.registry._failure is None
    state.transport = lambda request: httpx.Response(200, json=settings_payload())
    assert runtime.reading_for(SimpleNamespace(source_language='zh')) is state.readers[0]


@pytest.mark.parametrize('default', [False, True])
def test_actual_constructor_close_failure_keeps_partial_owner_and_original_traceback(state, default):
    state.close_error = OSError('authored constructor close failure')
    operation = (lambda: state.registry.create_default(state.service)) if default else lambda: get(state)
    with pytest.raises(ReadingRegistryPoisonedError) as first:
        operation()
    record, = state.registry.owned_snapshot(time.monotonic()+1)
    original = record.error
    assert record.state == 'failed' and record.reader is state.readers[0]
    assert isinstance(original, ReadingConnectionCloseError)
    assert first.value.record is record and first.value.__cause__ is original
    assert original.service is record.reader and original.owner is record.reader._sql_lifetime
    assert original.connection is state.opened[0] and original.close_error is state.close_error
    traceback, wrappers = original.__traceback__, [first.value]
    for operation in (lambda: get(state), state.registry.resume_pools,
                      lambda: state.registry.quiesce_owned(time.monotonic()+1),
                      lambda: state.registry.shutdown(time.monotonic()+1)):
        with pytest.raises(ReadingRegistryPoisonedError) as failure:
            operation()
        wrappers.append(failure.value)
        assert failure.value.__cause__ is original and original.__traceback__ is traceback
    assert len({id(wrapper) for wrapper in wrappers}) == len(wrappers)
    assert len(state.readers) == len(state.opened) == state.opened[0].close_calls == 1
    assert record.reader.pool._drained.is_set()  # Actual partial pool joined; SQL remains poisoned.
    assert state.registry._failure is record and not state.registry._lookups


def test_constructor_failure_before_fields_still_retains_actual_default_and_refuses_cleanup_success(state):
    original = ValueError('authored early constructor failure')
    def fail(reader):
        assert vars(reader) == {}
        raise original
    state.before_init = fail
    with pytest.raises(ReadingRegistryPoisonedError): state.registry.create_default(state.service)
    record, = state.registry.owned_snapshot(time.monotonic()+1)
    assert record.reader is state.readers[0] and record.error is original and not vars(record.reader)
    assert not state.opened
    with pytest.raises(ReadingRegistryPoisonedError): state.registry.shutdown(time.monotonic()+1)
    with pytest.raises(ReadingRegistryPoisonedError): state.registry.reopen_creation()


def test_lookup_cannot_be_forged_transferred_between_threads_or_reused_after_return(state):
    from backend import runtime_readers
    key = (state.service._scope(), 'zh', 'en', 'settings-one')
    def use(lookup):
        return state.registry.get_or_create(lookup, key, state.service,
            source_language='zh', translation_language='en')
    with state.registry.lookup() as lookup:
        forged = copy.copy(lookup)
        for rejected in (None, True, object(), forged):
            with pytest.raises(WritersQuiescing): use(rejected)
        other_thread = spawn(state, lambda: use(lookup))
        assert other_thread.done.wait(1) and isinstance(other_thread.error, WritersQuiescing)
        assert isinstance(lookup, runtime_readers._Lookup)
    with pytest.raises(WritersQuiescing): use(lookup)
    assert not state.readers


@pytest.mark.parametrize('deadline', [None, True, '1', float('inf'), float('nan'), 10**1000])
def test_lifecycle_refuses_nonfinite_or_non_numeric_deadlines(state, deadline):
    for operation in (state.registry.stop_creation, state.registry.quiesce_owned,
                      state.registry.owned_snapshot, state.registry.shutdown):
        with pytest.raises(ValueError): operation(deadline)
    assert state.registry._accepting and not state.registry._shutdown


def test_one_deadline_bounds_initial_and_late_metadata_contention(state, monkeypatch):
    locked, release = event(state), event(state)
    def hold():
        with state.registry._lock:
            locked.set(); assert release.wait(5)
    holder = spawn(state, hold)
    assert locked.wait(1)
    start = time.monotonic()
    with pytest.raises(TimeoutError): state.registry.quiesce_owned(start+.04)
    assert time.monotonic()-start < .3 and not holder.done.is_set()
    release.set(); assert holder.done.wait(1)

    # The second metadata acquisition also uses the original deadline. A
    # holder enters only after stop has finished, not by a timing sleep.
    late_locked, late_release, may_hold = event(state), event(state), event(state)
    def late_hold():
        assert may_hold.wait(5)
        with state.registry._lock:
            late_locked.set(); assert late_release.wait(5)
    late = spawn(state, late_hold)
    stop = state.registry.stop_creation
    deadlines = []
    def stopped(deadline):
        deadlines.append(deadline)
        stop(deadline); may_hold.set(); assert late_locked.wait(1)
    monkeypatch.setattr(state.registry, 'stop_creation', stopped)
    start = time.monotonic()
    with pytest.raises(TimeoutError): state.registry.quiesce_owned(start+.04)
    assert deadlines == [start+.04] and time.monotonic()-start < .3
    assert not state.registry._accepting and not late.done.is_set()
    late_release.set(); assert late.done.wait(1)


def test_resume_metadata_never_waits_in_event_loop_and_requires_final_reopen(state):
    state.registry.quiesce_owned(time.monotonic()+1)
    locked, release = event(state), event(state)
    def hold():
        with state.registry._lock:
            locked.set(); assert release.wait(5)
    holder = spawn(state, hold)
    assert locked.wait(1)
    start = time.monotonic()
    with pytest.raises(TimeoutError): state.registry.resume_pools()
    assert time.monotonic()-start < .2
    release.set(); assert holder.done.wait(1)
    state.registry.resume_pools()
    with pytest.raises(WritersQuiescing): get(state)
    state.registry.reopen_creation()
    assert get(state).source_language == 'zh'


def test_partial_pool_resume_does_not_reopen_creation_and_concurrent_stop_retires_recovery(state, monkeypatch):
    default, cached = state.registry.create_default(state.service), get(state)
    state.registry.quiesce_owned(time.monotonic()+1)
    original = cached.resume
    attempts = []
    def incomplete():
        attempts.append(True)
        raise TimeoutError('Authored partial pool resume')
    monkeypatch.setattr(cached, 'resume', incomplete)
    with pytest.raises(TimeoutError): state.registry.resume_pools()
    assert attempts == [True] and not state.registry._accepting
    with pytest.raises(TimeoutError): state.registry.reopen_creation()
    with pytest.raises(WritersQuiescing): get(state)
    def stop_during_resume():
        original()
        state.registry.stop_creation(time.monotonic()+1)
    monkeypatch.setattr(cached, 'resume', stop_during_resume)
    with pytest.raises(TimeoutError): state.registry.resume_pools()
    with pytest.raises(TimeoutError): state.registry.reopen_creation()
    monkeypatch.setattr(cached, 'resume', original)
    state.registry.resume_pools(); state.registry.reopen_creation()
    assert get(state) is cached and state.registry.create_default(state.service) is default


def test_shutdown_drains_default_and_cached_actual_workers_and_callbacks(state):
    default, cached = state.registry.create_default(state.service), get(state)
    work_entered, work_release = event(state), event(state)
    callback_entered, callback_release = event(state), event(state)
    def work():
        work_entered.set(); assert work_release.wait(5)
    def callback(_):
        callback_entered.set(); assert callback_release.wait(5)
    default.pool.submit(work)
    future = cached.pool.submit(lambda: 'actual callback')
    # Force a callback on an owned worker, rather than an already-done inline one.
    ready, finish = event(state), event(state)
    held_future = cached.pool.submit(lambda: (ready.set(), finish.wait(5)))
    assert ready.wait(1)
    held_future.add_done_callback(callback)
    finish.set(); assert callback_entered.wait(1) and held_future.done()
    assert work_entered.wait(1) and future.result(timeout=1) == 'actual callback'
    with pytest.raises(TimeoutError): state.registry.shutdown(time.monotonic()+.03)
    assert len(state.registry.owned_snapshot(time.monotonic()+1)) == 2
    assert not state.registry._accepting and state.registry._shutdown
    with pytest.raises(TimeoutError): state.registry.resume_pools()
    work_release.set(); callback_release.set()
    state.registry.shutdown(time.monotonic()+1)
    assert all(reader.pool._drained.is_set() for reader in (default, cached))
    with pytest.raises(TimeoutError): state.registry.reopen_creation()


def test_runtime_exact_account_language_target_and_settings_key_semantics(state):
    from backend.api import Runtime
    runtime = Runtime.__new__(Runtime)
    runtime.lexirise, runtime._reading_registry = state.service, state.registry
    def settings(request):
        assert request.method == 'GET' and request.url.path == '/v1/settings'
        return httpx.Response(200, json=settings_payload())
    state.transport = settings
    chinese = SimpleNamespace(source_language='zh')
    first = runtime.reading_for(chinese)
    assert runtime.reading_for(chinese) is first
    japanese = runtime.reading_for(SimpleNamespace(source_language='ja'))
    assert japanese is not first and japanese.source_language == 'ja'
    assert japanese.translation_language == 'fr' and first.translation_language == 'en'
    original_key = state.service._api_key
    state.service._api_key = 'second-authored-key'
    other_account = runtime.reading_for(chinese)
    assert other_account is not first
    state.service._api_key = original_key
    assert runtime.reading_for(chinese) is first
    payload, scope = next(iter(state.service._settings_cache.values()))
    translated = copy.deepcopy(payload)
    translated['languageSettings']['zh'] = {'effectiveTranslationLanguage': 'de'}
    state.service._settings_cache[state.service._scope()] = (translated, scope)
    different_target = runtime.reading_for(chinese)
    assert different_target is not first and different_target.translation_language == 'de'
    # A changed settings identity is intentionally a different exact key even
    # when the effective language target happens to remain the same.
    state.service._settings_cache[state.service._scope()] = (payload, scope+'-changed')
    changed = runtime.reading_for(chinese)
    assert changed is not first and changed.translation_language == first.translation_language
    keys = tuple(state.registry.cached)
    assert len(keys) == len(state.registry.owned_snapshot(time.monotonic()+1)) == 5
    assert all(len(key) == 4 for key in keys)
    assert not state.registry._lookups and state.requests == [('GET', '/v1/settings')]*2


def test_real_strict_c2_closes_creation_before_request_drain_with_one_deadline(state, monkeypatch):
    from backend.api import Runtime
    from backend.runtime_handoff import CaptureHandoff
    from backend.runtime_writers import RuntimeWriterGate
    async def run():
        runtime = Runtime.__new__(Runtime)
        runtime.lexirise, runtime._reading_registry = state.service, state.registry
        runtime._handoff_drains, runtime._handoff_lock = [], asyncio.Lock()
        runtime._writer_handoff, runtime.standby = False, False
        runtime._sql_handoff = None
        # This fixture isolates creation/drain ordering; real SQL composition
        # is exercised by test_runtime_sql_lifetime's actual full owner cohort.
        runtime._freeze_sql_handoff = lambda payload, _deadline: payload
        runtime.request_writers = RuntimeWriterGate()
        entered, release = event(state), event(state)
        def transport(request):
            entered.set(); assert release.wait(5)
            return httpx.Response(200, json=settings_payload())
        state.transport = transport
        def request():
            runtime.request_writers.enter()
            try:
                return runtime.reading_for(SimpleNamespace(source_language='zh'))
            finally:
                runtime.request_writers.leave()
        caller = spawn(state, request)
        assert await asyncio.to_thread(entered.wait, 1)
        captures, deadlines = [], []
        wait = runtime._wait_requests_until
        def wait_requests(deadline):
            assert not state.registry._accepting
            wait(deadline)
        monkeypatch.setattr(runtime, '_wait_requests_until', wait_requests)
        for name in ('stop_creation', 'quiesce_owned'):
            original = getattr(state.registry, name)
            def observe(deadline, original=original, name=name):
                deadlines.append((name, deadline))
                return original(deadline)
            monkeypatch.setattr(state.registry, name, observe)
        runtime.mobile_exports = SimpleNamespace(quiesce=lambda: None)
        runtime.automatic_exports = SimpleNamespace(picker=SimpleNamespace(quiesce=lambda: None))
        runtime.installation = SimpleNamespace(quiesce=lambda _timeout: None)
        async def stop_updates(**_): pass
        runtime.stop_updates, runtime._verify_background_stopped = stop_updates, lambda: None
        runtime.map_task, runtime.hito = None, None
        runtime._voice_pools = lambda: []
        async def capture_stop(_timeout): captures.append(True)
        runtime.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True),
            quiesce=capture_stop, drain_publications=lambda: asyncio.sleep(0),
            export_handoff=lambda running: CaptureHandoff(running=running))
        try:
            with pytest.raises(TimeoutError): await runtime.quiesce_writers(timeout=.04)
            assert caller.thread.is_alive() and not captures and not state.readers
            assert len(runtime._handoff_drains) == 3
            release.set()
            await asyncio.to_thread(caller.thread.join, 1)
            assert not caller.thread.is_alive() and isinstance(caller.error, WritersQuiescing)
            outcomes = await asyncio.gather(*runtime._handoff_drains, return_exceptions=True)
            # The request-drain thread can itself reach the same deadline
            # before or after the async waiter's TimeoutError. Both outcomes
            # stay owned/observed; the held settings lookup still must finish.
            assert all(outcome is None or isinstance(outcome, TimeoutError) for outcome in outcomes)
            assert all(task.done() for task in runtime._handoff_drains)
            deadlines.clear()
            result = await runtime.quiesce_writers(timeout=1)
            assert result.running and captures == [True] and runtime.standby
            assert [name for name, _ in deadlines] == ['stop_creation', 'quiesce_owned', 'stop_creation']
            assert len({deadline for _, deadline in deadlines}) == 1
            assert not state.registry._accepting and not state.readers
        finally:
            release.set()
            for task in runtime._handoff_drains:
                if not task.done(): await task
    asyncio.run(run())


def test_registry_default_preserves_exact_three_store_c5_constructor_interception(tmp_path, monkeypatch):
    from backend import runtime_probe
    from backend.storage import TranscriptStore
    data = (tmp_path/'authored-c5').resolve()
    data.mkdir()
    observed, original = [], sqlite3.connect
    def forbidden(*_a, **_k):
        pytest.fail('Authored registry C5 test must not access credentials or account transport.')
    def connect(path, *args, **options):
        assert not args
        observed.append((path.name, options.copy()))
        return original(path, **options)
    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(lexirise, 'os', SimpleNamespace(environ=SimpleNamespace(get=forbidden), name='nt'))
    monkeypatch.setattr(sqlite3, 'connect', connect)
    registry = RuntimeReadingRegistry(data/'lexirise')
    try:
        with runtime_probe._authored_wal_connections(SimpleNamespace(data_root=data)) as policy:
            store = TranscriptStore(data/'transcript-v2.db')
            service = LexiriseService(data/'lexirise', api_key='authored-key',
                accounts=SimpleNamespace(active_key=forbidden), transport=httpx.MockTransport(forbidden))
            reader = registry.create_default(service)
            policy.require_stores()
            assert policy.opens == 3 and policy.configured == {'transcript', 'exports', 'reading'}
            assert not store._connection_failures and not service._sql_lifetime.failures
            assert not reader._sql_lifetime.failures
        record, = registry.owned_snapshot(time.monotonic()+1)
        assert record.reader is reader and record.state == 'ready'
        assert observed == [('transcript-v2.db', {'timeout': 10}), ('exports-v2.db', {'timeout': 10}),
                            ('reading-cache-v2.db', {})]
    finally:
        registry.shutdown(time.monotonic()+1)


def test_failed_constructor_partial_pool_is_really_drained_without_retrying_sql_close(state):
    entered, release = event(state), event(state)
    state.close_error = OSError('authored partial constructor close failure')
    def work():
        entered.set(); assert release.wait(5)
    def start_partial_pool(_connection):
        state.on_close = None
        state.readers[-1].pool.submit(work)
        assert entered.wait(1)
    state.on_close = start_partial_pool
    with pytest.raises(ReadingRegistryPoisonedError): state.registry.create_default(state.service)
    record, = state.registry.owned_snapshot(time.monotonic()+1)
    original = record.error
    with pytest.raises(TimeoutError): state.registry.shutdown(time.monotonic()+.03)
    assert isinstance(record.cleanup_error, TimeoutError)
    assert not record.reader.pool._drained.is_set() and state.opened[0].close_calls == 1
    with pytest.raises(ReadingRegistryPoisonedError): state.registry.resume_pools()
    release.set()
    with pytest.raises(ReadingRegistryPoisonedError) as failure:
        state.registry.shutdown(time.monotonic()+1)
    assert failure.value.__cause__ is original and record.reader.pool._drained.is_set()
    assert state.opened[0].close_calls == 1 and record.error is original


def test_one_constructor_failure_does_not_drop_another_actual_inflight_reader(state):
    entered, release = hold_first_close(state)
    first = spawn(state, lambda: get(state))
    assert entered.wait(1)
    state.close_error = OSError('authored independent constructor close failure')
    with pytest.raises(ReadingRegistryPoisonedError) as failure:
        get(state, source='ja')
    records = state.registry.owned_snapshot(time.monotonic()+1)
    assert len(records) == 2 and [record.state for record in records] == ['constructing', 'failed']
    with pytest.raises(TimeoutError): state.registry.shutdown(time.monotonic()+.03)
    assert first.thread.is_alive() and not first.done.is_set()
    release.set()
    assert first.done.wait(1) and isinstance(first.error, ReadingRegistryPoisonedError)
    assert first.error.__cause__ is failure.value.error
    with pytest.raises(ReadingRegistryPoisonedError): state.registry.shutdown(time.monotonic()+1)
    assert [record.state for record in records] == ['ready', 'failed']
    assert {record.reader for record in records} == set(state.readers)
    assert all(record.reader.pool._drained.is_set() for record in records)
    assert all(connection.close_calls == 1 for connection in state.opened)


def test_short_competing_control_does_not_wait_behind_a_live_pool_drain(state, monkeypatch):
    reader = state.registry.create_default(state.service)
    entered, release, draining = event(state), event(state), event(state)
    def work():
        entered.set(); assert release.wait(5)
    reader.pool.submit(work)
    assert entered.wait(1)
    quiesce = reader.quiesce
    def observe(timeout):
        draining.set()
        quiesce(timeout)
    monkeypatch.setattr(reader, 'quiesce', observe)
    first = spawn(state, lambda: state.registry.quiesce_owned(time.monotonic()+3))
    assert draining.wait(1)
    start = time.monotonic()
    with pytest.raises(TimeoutError): state.registry.quiesce_owned(start+.04)
    assert time.monotonic()-start < .3 and not first.done.is_set()
    with pytest.raises(TimeoutError): state.registry.resume_pools()
    release.set()
    assert first.done.wait(1) and first.error is None
    state.registry.resume_pools(); state.registry.reopen_creation()
    assert state.registry.create_default(state.service) is reader


def test_terminal_control_can_be_reaped_after_bounded_final_metadata_acquire_loses(state, monkeypatch):
    reader = state.registry.create_default(state.service)
    locked, release, may_hold = event(state), event(state), event(state)
    def holder():
        assert may_hold.wait(5)
        with state.registry._lock:
            locked.set(); assert release.wait(5)
    holding = spawn(state, holder)
    finish = state.registry._finish_control
    def finish_after_holder(control, deadline):
        monkeypatch.setattr(state.registry, '_finish_control', finish)
        assert reader.pool._drained.is_set()  # Actual pool work already returned.
        may_hold.set(); assert locked.wait(1)
        finish(control, deadline)
    monkeypatch.setattr(state.registry, '_finish_control', finish_after_holder)
    start = time.monotonic()
    with pytest.raises(TimeoutError): state.registry.quiesce_owned(start+.04)
    assert time.monotonic()-start < .3 and not holding.done.is_set()
    assert not state.registry._accepting and state.registry._control is not None
    release.set(); assert holding.done.wait(1)
    state.registry.quiesce_owned(time.monotonic()+1)
    state.registry.resume_pools(); state.registry.reopen_creation()
    assert state.registry.create_default(state.service) is reader


def test_rollback_handles_stop_timeout_before_creation_admission_was_closed(state):
    reader = state.registry.create_default(state.service)
    locked, release = event(state), event(state)
    def holder():
        with state.registry._lock:
            locked.set(); assert release.wait(5)
    holding = spawn(state, holder)
    assert locked.wait(1)
    with pytest.raises(TimeoutError): state.registry.stop_creation(time.monotonic()+.04)
    assert state.registry._accepting  # The stop failed before its transition.
    release.set(); assert holding.done.wait(1)
    state.registry.resume_pools()
    assert not state.registry._accepting  # Recovery must await final admission.
    state.registry.reopen_creation()
    assert state.registry.create_default(state.service) is reader


def test_rollback_after_failed_stop_retires_a_still_live_lookup_before_pool_recovery(state):
    reader = state.registry.create_default(state.service)
    entered, lookup_release = event(state), event(state)
    def lookup():
        with state.registry.lookup():
            entered.set(); assert lookup_release.wait(5)
    caller = spawn(state, lookup)
    assert entered.wait(1)
    locked, release = event(state), event(state)
    def holder():
        with state.registry._lock:
            locked.set(); assert release.wait(5)
    holding = spawn(state, holder)
    assert locked.wait(1)
    with pytest.raises(TimeoutError): state.registry.stop_creation(time.monotonic()+.04)
    release.set(); assert holding.done.wait(1)
    assert state.registry._accepting
    with pytest.raises(TimeoutError): state.registry.resume_pools()
    assert not state.registry._accepting and not caller.done.is_set()
    with pytest.raises(TimeoutError): state.registry.reopen_creation()
    lookup_release.set()
    assert caller.done.wait(1) and isinstance(caller.error, WritersQuiescing)
    state.registry.resume_pools(); state.registry.reopen_creation()
    assert state.registry.create_default(state.service) is reader


def test_terminal_metadata_recovery_does_not_clear_constructor_failure_or_retry_close(state, monkeypatch):
    state.close_error = OSError('authored failed default close')
    with pytest.raises(ReadingRegistryPoisonedError): state.registry.create_default(state.service)
    record, = state.registry.owned_snapshot(time.monotonic()+1)
    original = record.error
    locked, release, may_hold = event(state), event(state), event(state)
    def holder():
        assert may_hold.wait(5)
        with state.registry._lock:
            locked.set(); assert release.wait(5)
    holding = spawn(state, holder)
    finish = state.registry._finish_control
    def finish_after_holder(control, deadline):
        monkeypatch.setattr(state.registry, '_finish_control', finish)
        assert record.reader.pool._drained.is_set()
        may_hold.set(); assert locked.wait(1)
        finish(control, deadline)
    monkeypatch.setattr(state.registry, '_finish_control', finish_after_holder)
    with pytest.raises(TimeoutError): state.registry.quiesce_owned(time.monotonic()+.04)
    release.set(); assert holding.done.wait(1)
    with pytest.raises(ReadingRegistryPoisonedError) as failure:
        state.registry.quiesce_owned(time.monotonic()+1)
    assert failure.value.__cause__ is original
    assert state.registry._failure is record and record.state == 'failed'
    assert state.opened[0].close_calls == 1 and not state.registry._accepting
    with pytest.raises(ReadingRegistryPoisonedError): state.registry.resume_pools()
