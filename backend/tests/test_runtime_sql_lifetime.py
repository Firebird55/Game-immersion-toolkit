"""Concrete Runtime SQL composition with owned SQLite and producer adapters.

These tests never construct Runtime(DATA_DIR), access accounts or run native
capture. Producer adapters exercise ordering; actual SQL owners/tokens, reader
pools, cursor scopes and SQLite work are production objects.
"""
import asyncio
from contextlib import closing
import sqlite3
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from backend import api, lexirise
from backend.api import Runtime
from backend.lexirise import LexiriseService
from backend.models import TextMatch
from backend.reading import LexiriseReadingService
from backend.runtime_handoff import CaptureHandoff
from backend.runtime_readers import RuntimeReadingRegistry
from backend.runtime_workers import RequestBarrier
from backend.runtime_writers import QuiesceableExecutor, RuntimeWriterGate, WritersQuiescing
from backend import sqlite_operation_lifetime
from backend.sqlite_operation_lifetime import _SqliteCursorCloseError
from backend.storage import TranscriptStore


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    def forbidden(*_a, **_k):
        pytest.fail('SQL composition must not touch Runtime defaults, credentials, native capture or network.')

    monkeypatch.setattr(Runtime, '__init__', forbidden)
    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(lexirise, 'os', SimpleNamespace(environ=SimpleNamespace(get=forbidden), name='nt'))
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    value = SimpleNamespace(calls=[], readers=[], threads=[], releases=[], publication_entered=None,
        publication_release=None, update_error=None, running=True, freeze_calls=[], resume_calls=[])
    runtime = value.runtime = Runtime.__new__(Runtime)
    runtime._request_stop = None
    runtime._sql_handoff = None
    runtime._quiesce_task = runtime._handoff_state = None
    runtime._handoff_lock, runtime._handoff_drains = asyncio.Lock(), []
    runtime._writer_handoff, runtime._updates_started, runtime.standby = False, False, False
    runtime.request_writers = RuntimeWriterGate()
    runtime.request_barrier = RequestBarrier()
    runtime.transcript = TranscriptStore(tmp_path/'owned-transcript.db')
    runtime.lexirise = LexiriseService(tmp_path/'owned-reading', api_key='test-key',
        accounts=SimpleNamespace(active_key=forbidden), transport=httpx.MockTransport(forbidden))
    runtime._reading_registry = registry = RuntimeReadingRegistry(tmp_path/'owned-reading')
    runtime.reading = registry.create_default(runtime.lexirise)
    value.readers.append(runtime.reading)
    value.pins = [runtime.lexirise.pin(language) for language in ('ja', 'nl')]
    for pin, target in zip(value.pins, ('en', 'fr')):
        with registry.lookup() as lookup:
            reader = registry.get_or_create(lookup, (pin._scope(), pin.source_language, target, 'owned'), pin,
                source_language=pin.source_language, translation_language=target)
        value.readers.append(reader)
    runtime._readers = registry.cached
    value.voice = QuiesceableExecutor(1)
    runtime._voice_pools = lambda: [value.voice]
    runtime.map_task = None
    runtime.hito = SimpleNamespace(close=lambda: None, resume=lambda: None)

    def healthy():
        assert runtime.transcript.count() >= 0
        assert runtime.lexirise._decks() == {}
        for reader in value.readers:
            reader._cached('meaning', '说', 60)

    def resumed(name):
        healthy()
        value.calls.append(name)

    runtime.mobile_exports = SimpleNamespace(drain=lambda: value.calls.append('exports'), resume=lambda: resumed('exports-resume'))
    runtime.automatic_exports = SimpleNamespace(picker=SimpleNamespace(
        drain=lambda: value.calls.append('picker'), resume=lambda: resumed('picker-resume')))
    runtime.installation = SimpleNamespace(pause=lambda: None, quiesce=lambda _timeout: value.calls.append('setup'), resume=lambda: resumed('setup-resume'))
    runtime.languages = SimpleNamespace(close=lambda **_kwargs: value.calls.append('language-closed'))

    async def stop_updates(**options):
        assert options == {'drain': True}
        value.calls.append('updates-drain')

    runtime.stop_updates = stop_updates
    runtime._verify_background_stopped = lambda: value.calls.append('background-stopped')

    async def capture_quiesce(_timeout):
        value.calls.append('capture-drain')
        value.running = False

    async def publications():
        value.calls.append('publications-enter')
        if value.publication_entered is not None:
            value.publication_entered.set()
            await value.publication_release.wait()
        # Final bookkeeping must still be able to use its actual SQL owner.
        line = runtime.transcript.add(TextMatch(text_id='owned-caption', english='Owned caption',
            chinese='合成台词', source_ocr='合成台词', score=100, kind='exact'), 'owned-session')
        runtime.transcript.set_favorite(line.id, True)
        value.calls.append('publications-finished')

    def start_capture():
        resumed('capture-start')
        value.running = True

    runtime.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=value.running),
        quiesce=capture_quiesce, drain_publications=publications, native_stop_pending=False,
        export_handoff=lambda running: CaptureHandoff(running=running, session_id='owned-session'),
        resume_workers=lambda: resumed('capture-resume'), start=start_capture,
        import_handoff=lambda _payload: value.calls.append('capture-import'))

    def updates():
        if value.update_error is not None:
            raise value.update_error
        resumed('updates-start')
        runtime._updates_started = True

    runtime.start_updates = updates
    value.healthy, value.forbidden = healthy, forbidden
    yield value
    for release in value.releases:
        release.set()
    for call in value.threads:
        call.thread.join(5)
        assert not call.thread.is_alive(), 'Owned SQL fixture thread did not finish.'
    for reader in value.readers:
        reader.pool.shutdown(wait=True, cancel_futures=True)
    value.voice.shutdown(wait=True)


def owners(value):
    runtime = value.runtime
    return [runtime.transcript._sql_lifetime, runtime.lexirise._sql_lifetime,
            *[reader._sql_lifetime for reader in value.readers]]


def members(record):
    return (*record.members, *record.readings.members)


def spy(value, monkeypatch):
    for index, owner in enumerate(owners(value)):
        freeze, resume = owner._freeze_until, owner._resume_until

        def observe_freeze(deadline, epoch, controller, *, owner=owner, index=index, original=freeze):
            record = value.runtime._sql_handoff
            assert record is not None and all(member.reserved for member in members(record))
            assert controller.owner is owner and owner._controller is controller
            assert value.runtime._reading_registry._lock.acquire(blocking=False)
            value.runtime._reading_registry._lock.release()
            assert 'publications-finished' in value.calls
            value.freeze_calls.append((owner, deadline, epoch))
            value.calls.append('freeze-'+str(index))
            return original(deadline, epoch, controller)

        def observe_resume(token, deadline, controller, *, owner=owner, original=resume):
            assert value.runtime._reading_registry._lock.acquire(blocking=False)
            value.runtime._reading_registry._lock.release()
            value.resume_calls.append((owner, token, deadline))
            return original(token, deadline, controller)

        monkeypatch.setattr(owner, '_freeze_until', observe_freeze)
        monkeypatch.setattr(owner, '_resume_until', observe_resume)


def worker(value, function):
    call = SimpleNamespace(done=threading.Event(), error=None)

    def run():
        try: function()
        except BaseException as error: call.error = error
        finally: call.done.set()

    call.thread = threading.Thread(target=run)
    value.threads.append(call)
    call.thread.start()
    return call


@pytest.mark.parametrize('primitive', ['_check_until', '_resume_until', '_check_resumed_until'])
@pytest.mark.parametrize('lock_name', ['serialization', 'failure_lock', 'gate'])
def test_absolute_sql_check_and_resume_bound_metadata_locks_without_new_budget(cohort, primitive, lock_name):
    owner = cohort.runtime.transcript._sql_lifetime
    token = cohort.runtime.transcript.freeze_connections(0)
    if primitive == '_check_resumed_until':
        cohort.runtime.transcript.resume_connections(token)
    entered, release = threading.Event(), threading.Event()
    cohort.releases.append(release)
    lock = owner.gate._condition if lock_name == 'gate' else getattr(owner, lock_name)

    def hold():
        with lock:
            entered.set()
            assert release.wait(5)

    holder = worker(cohort, hold)
    assert entered.wait(2)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        getattr(owner, primitive)(token, started+.03)
    assert time.monotonic()-started < .5 and not holder.done.is_set()
    release.set()
    assert holder.done.wait(2) and holder.error is None


def test_strict_runtime_freezes_exact_owners_after_final_bookkeeping_and_resumes_sql_first(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    spy(value, monkeypatch)

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        assert payload.running and record.payload is payload and runtime.standby
        assert record.readings is runtime._reading_registry._sql_set
        assert len(members(record)) == len(owners(value)) == 5
        assert [member.owner for member in members(record)] == owners(value)
        assert len(value.freeze_calls) == 5 and len({deadline for _, deadline, _ in value.freeze_calls}) == 1
        assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting
        for member in members(record):
            assert member.token is member.owner.fence and member.token._epoch == member.epoch
        for pin in (runtime.lexirise, *value.pins):
            with pytest.raises(WritersQuiescing): pin._decks()
        assert await runtime.activate_handoff(payload, writers=True) == {'active': True}
        assert runtime._sql_handoff is runtime._reading_registry._sql_set is None
        assert runtime.request_writers._accepting and runtime._reading_registry._accepting
        assert len(value.resume_calls) == 5 and len({deadline for _, _, deadline in value.resume_calls}) == 1
        assert not runtime._writer_handoff
        line, = runtime.transcript.list()
        assert line.chinese == '合成台词' and line.favorite and line.session_id == 'owned-session'
        for member in members(record):
            assert member.resumed and member.owner.epoch == member.epoch+1
            assert member.owner._controller is None
            with pytest.raises(ValueError): member.owner.check(member.token)

    asyncio.run(run())


def test_sql_reservation_waits_for_actual_final_publication_sql(cohort):
    value, runtime = cohort, cohort.runtime

    async def run():
        value.publication_entered, value.publication_release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(runtime.quiesce_writers(timeout=2))
        try:
            await asyncio.wait_for(value.publication_entered.wait(), 1)
            assert runtime._sql_handoff is None and all(owner.gate._accepting for owner in owners(value))
            assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting
            value.publication_release.set()
            await task
            assert all(not owner.gate._accepting for owner in owners(value))
        finally:
            value.publication_release.set()
            await task

    asyncio.run(run())


def test_partial_sql_freeze_timeout_keeps_same_cohort_tokens_and_epoch_until_real_scope_finishes(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    spy(value, monkeypatch)
    reader = value.readers[-1]
    entered, release = threading.Event(), threading.Event()
    last_stopped, expire = threading.Event(), threading.Event()
    value.releases.append(release)

    def sql():
        with reader._connection_scope() as db:
            with reader._sql_lifetime.cursor(db) as cursor:
                cursor.execute('SELECT COUNT(*) FROM cache').fetchone()
                entered.set()
                assert release.wait(30)

    actual = worker(value, sql)
    assert entered.wait(2)

    async def run():
        # Bootstrap speed does not establish that partial SQL freeze was
        # reached. Only expire the actual helper's received deadline after its
        # last admission stop, with the real SQL scope and retained task live.
        # Separate cases exercise Runtime's total monotonic timeout budget.
        real_clock = sqlite_operation_lifetime.time
        deadlines, actual_errors = [], []
        freeze, stop = reader._sql_lifetime._freeze_until, reader._sql_lifetime.gate.stop_admission

        def phase_clock():
            return deadlines[0]+1 if expire.is_set() and deadlines else real_clock.monotonic()

        def last_freeze(deadline, epoch, controller):
            deadlines.append(deadline)
            try:
                return freeze(deadline, epoch, controller)
            except BaseException as error:
                actual_errors.append(error)
                raise

        def observed_stop():
            stop()
            last_stopped.set()
            assert expire.wait(10), 'Partial SQL test did not release its observed stop.'

        with monkeypatch.context() as phase:
            phase.setattr(sqlite_operation_lifetime, 'time', SimpleNamespace(monotonic=phase_clock, sleep=real_clock.sleep))
            phase.setattr(reader._sql_lifetime, '_freeze_until', last_freeze)
            phase.setattr(reader._sql_lifetime.gate, 'stop_admission', observed_stop)
            task = asyncio.create_task(runtime.quiesce_writers())
            try:
                assert await asyncio.to_thread(last_stopped.wait, 10), 'Last owned SQL stop was not reached.'
                record = runtime._sql_handoff
                assert record is not None and record.readings is runtime._reading_registry._sql_set
                assert all(member.reserved for member in members(record))
                assert all(member.token is not None for member in members(record)[:-1])
                assert members(record)[-1].token is None and not reader._sql_lifetime.gate._accepting
                sql_step = runtime._handoff_drains[-1]
                assert not task.done() and not sql_step.done()
                assert actual.thread.is_alive() and not actual.done.is_set()
                assert len({deadline for _, deadline, _ in value.freeze_calls}) == len(deadlines) == 1
                expire.set()
                with pytest.raises(TimeoutError) as refused: await task
                assert sql_step.done() and not sql_step.cancelled() and sql_step.exception() is refused.value
                # Executor transport may normalize TimeoutError; the retained
                # owner/member must keep the actual worker's original object.
                assert len(actual_errors) == 1 and type(actual_errors[0]) is TimeoutError
                assert record.error is members(record)[-1].error is actual_errors[0]
                assert refused.value.args == actual_errors[0].args
            finally:
                expire.set()
                await asyncio.gather(task, *runtime._handoff_drains, return_exceptions=True)
        tokens, epoch = [member.token for member in members(record)], record.readings.epoch
        assert all(token is not None for token in tokens[:-1]) and tokens[-1] is None
        assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting
        assert actual.thread.is_alive() and record.error is not None
        release.set()
        assert await asyncio.to_thread(actual.done.wait, 5) and actual.error is None
        assert await runtime.quiesce_writers() is record.payload
        assert runtime._sql_handoff is record and runtime._reading_registry._epoch is epoch
        assert all(member.token is token for member, token in zip(members(record)[:-1], tokens[:-1]))
        assert value.calls.count('publications-finished') == 1
        await runtime.activate_handoff(record.payload, writers=True)

    asyncio.run(run())


def test_cancelled_sql_waiter_keeps_actual_task_record_and_creation_exclusion(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    owner = value.readers[-1]._sql_lifetime
    entered, release = threading.Event(), threading.Event()
    value.releases.append(release)
    original = owner._freeze_until

    def hold(deadline, epoch, controller):
        entered.set()
        assert release.wait(5)
        return original(deadline, epoch, controller)

    monkeypatch.setattr(owner, '_freeze_until', hold)

    async def run():
        task = asyncio.create_task(runtime.quiesce_writers(timeout=3))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            record = runtime._sql_handoff
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            assert any(not step.done() for step in runtime._handoff_drains)
            assert runtime._sql_handoff is record and record.readings is runtime._reading_registry._sql_set
            with pytest.raises(TimeoutError):
                await runtime.activate_handoff(record.payload, writers=True)
            assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting
            release.set()
            await asyncio.gather(*runtime._handoff_drains)
            await runtime.activate_handoff(record.payload, writers=True)
        finally:
            release.set()
            if not task.done(): task.cancel()
            await asyncio.gather(task, *runtime._handoff_drains, return_exceptions=True)

    asyncio.run(run())


def test_partial_resume_and_final_activation_failure_do_not_resubmit_successful_tokens(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    spy(value, monkeypatch)
    pending = value.readers[1]._sql_lifetime
    original = pending._resume_until
    resume_error, activation_error = RuntimeError('Authored pending resume error.'), RuntimeError('Authored update activation error.')

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        monkeypatch.setattr(pending, '_resume_until', lambda *_: (_ for _ in ()).throw(resume_error))
        with pytest.raises(RuntimeError) as failed:
            await runtime.activate_handoff(payload, writers=True)
        assert failed.value is resume_error and runtime._sql_handoff is record
        assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting
        assert [member.resumed for member in members(record)] == [True, True, True, False, False]
        assert 'capture-resume' not in value.calls
        monkeypatch.setattr(pending, '_resume_until', original)
        value.update_error = activation_error
        with pytest.raises(RuntimeError) as failed:
            await runtime.activate_handoff(payload, writers=True)
        assert failed.value is activation_error and all(member.resumed for member in members(record))
        assert record.error is resume_error and not runtime.request_writers._accepting
        assert not runtime._reading_registry._accepting
        value.update_error = None
        await runtime.activate_handoff(payload, writers=True)
        assert len(value.resume_calls) == 5 and len({owner for owner, _, _ in value.resume_calls}) == 5
        assert runtime._sql_handoff is None

    asyncio.run(run())


@pytest.mark.parametrize('selected', [0, 1, 4])
def test_unexpected_post_resume_epoch_is_never_adopted_as_new_baseline(cohort, selected):
    runtime = cohort.runtime

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        await runtime._handoff_step(lambda: runtime._resume_sql_handoff(time.monotonic()+2), time.monotonic()+2, blocking=True)
        member = members(record)[selected]
        with pytest.raises(ValueError): member.owner.freeze(0)
        with pytest.raises(ValueError): member.owner.resume(member.token)
        # Private corruption remains a refusal even when public controllers
        # cannot intervene while Runtime retains the actual member binding.
        member.owner.epoch += 1
        with pytest.raises(ValueError):
            await runtime.activate_handoff(payload, writers=True)
        assert runtime._sql_handoff is record and member.owner._controller is member
        assert member.owner.epoch == member.epoch+2
        assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting
        assert 'capture-resume' not in cohort.calls

    asyncio.run(run())


@pytest.mark.parametrize('selected', [0, 1, 3])
def test_forged_current_token_refuses_all_sql_resume_before_any_owner_reopens(cohort, selected):
    runtime = cohort.runtime

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        member = members(record)[selected]
        actual = member.token
        member.token = type(actual)(actual._lifetime_subject, actual._epoch)
        with pytest.raises(ValueError):
            await runtime.activate_handoff(payload, writers=True)
        assert not any(item.resumed for item in members(record))
        assert all(not owner.gate._accepting for owner in owners(cohort))
        assert member.owner.fence is actual and not runtime.request_writers._accepting

    asyncio.run(run())


def test_missing_actual_owner_is_retained_failure_not_permissive_recovery(cohort):
    runtime = cohort.runtime
    runtime.transcript = None

    async def run():
        # Do not run the publication adapter which deliberately uses the removed store.
        runtime.capture.drain_publications = lambda: asyncio.sleep(0)
        with pytest.raises(TypeError):
            await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        assert record is not None and record.transcript is None and record.error is not None
        with pytest.raises(TypeError):
            await runtime.activate_handoff(record.payload, writers=True)
        assert runtime._sql_handoff is record and not runtime.request_writers._accepting
        assert not runtime._reading_registry._accepting

    asyncio.run(run())


def test_handoff_lock_wait_is_inside_total_quiesce_budget(cohort):
    runtime = cohort.runtime

    async def run():
        await runtime._handoff_lock.acquire()
        started = time.monotonic()
        try:
            with pytest.raises(TimeoutError):
                await runtime.quiesce_writers(timeout=.03)
            assert time.monotonic()-started < .5 and runtime._sql_handoff is None
            assert runtime.request_writers._accepting and runtime._reading_registry._accepting
        finally:
            runtime._handoff_lock.release()

    asyncio.run(run())


def test_resume_poison_keeps_actual_failed_cursor_and_never_retries_close(cohort, monkeypatch):
    runtime = cohort.runtime
    reader = cohort.readers[1]
    raw = sqlite3.connect
    observed = []
    close_error = OSError('Authored reading cursor close fault.')

    class Cursor(sqlite3.Cursor):
        def close(self):
            self.close_calls += 1
            super().close()
            raise close_error

    class Connection(sqlite3.Connection):
        def cursor(self):
            cursor = super().cursor(factory=Cursor)
            cursor.close_calls = 0
            self.actual_cursor = cursor
            return cursor

        def close(self):
            self.close_calls += 1
            return super().close()

    def connect(database, *args, **kwargs):
        if database == reader.path:
            assert not args and not kwargs
            connection = raw(database, factory=Connection)
            connection.close_calls = 0
            observed.append(connection)
            return connection
        return raw(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', connect)
    with pytest.raises(_SqliteCursorCloseError) as raised:
        reader._cached('meaning', '说', 60)
    failure = raised.value

    async def run():
        with pytest.raises(RuntimeError) as refused:
            await runtime.quiesce_writers(timeout=2)
        assert refused.value.failure is failure
        record = runtime._sql_handoff
        assert record is not None and record.error is refused.value
        assert not any(member.token is not None for member in members(record))  # Epoch reservation precedes freeze.
        with pytest.raises(RuntimeError) as refused:
            await runtime.activate_handoff(record.payload, writers=True)
        assert refused.value.failure is failure and runtime._sql_handoff is record
        assert failure.connection is observed[0] and len(observed) == 1
        assert failure.connection.close_calls == failure.cursor.close_calls == 1
        assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting

    asyncio.run(run())


@pytest.mark.parametrize('phase', ['reserve', 'freeze', 'resume'])
def test_unknown_member_result_is_owned_and_cannot_be_adopted_from_current_metadata(cohort, monkeypatch, phase):
    runtime = cohort.runtime
    owner = runtime.lexirise._sql_lifetime
    error = RuntimeError('Authored result loss after actual SQL transition.')
    name = {'reserve': '_reserve_until', 'freeze': '_freeze_until', 'resume': '_resume_until'}[phase]
    original = getattr(owner, name)
    actual_results = []

    def lose(*args):
        actual_results.append(original(*args))
        raise error

    async def run():
        if phase == 'resume':
            payload = await runtime.quiesce_writers(timeout=2)
        monkeypatch.setattr(owner, name, lose)
        with pytest.raises(RuntimeError) as failed:
            if phase != 'resume':
                await runtime.quiesce_writers(timeout=2)
            else:
                await runtime.activate_handoff(payload, writers=True)
        assert failed.value is error and len(actual_results) == 1
        record = runtime._sql_handoff
        trace = record.error.__traceback__
        member = record.members[1]
        if phase == 'reserve':
            assert not member.reserved and owner._controller is member and owner.fence is None
            assert actual_results[0] is member and owner.epoch == member.epoch
        elif phase == 'freeze':
            assert member.token is None and owner.fence is actual_results[0]
        else:
            assert not member.resumed and owner.epoch == member.epoch+1
        monkeypatch.setattr(owner, name, original)
        with pytest.raises(ValueError):
            await runtime.activate_handoff(record.payload, writers=True)
        assert runtime._sql_handoff is record and record.error is error and record.error.__traceback__ is trace
        assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting
        assert 'capture-resume' not in cohort.calls

    asyncio.run(run())


def test_foreign_public_pending_stop_is_not_adopted_by_reserved_runtime_group(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    store, owner = runtime.transcript, runtime.transcript._sql_lifetime
    entered, release = threading.Event(), threading.Event()
    value.releases.append(release)

    def sql():
        with store._connection_scope() as db:
            with owner.cursor(db) as cursor:
                cursor.execute('SELECT COUNT(*) FROM transcript_lines').fetchone()
                entered.set()
                assert release.wait(5)

    actual = worker(value, sql)
    assert entered.wait(2)
    # This negative needs no final publication SQL while a different public
    # controller has stopped this actual store. No store/default is replaced.
    runtime.capture.drain_publications = lambda: asyncio.sleep(0)
    original = runtime._reserve_sql_handoff
    reservations = []

    def foreign_stop_after_group_snapshot(payload, deadline):
        record = original(payload, deadline)
        if not reservations:
            reservations.append(record)
            with pytest.raises(TimeoutError): store.freeze_connections(.02)
            assert owner.fence is None and not owner.gate._accepting and owner._controller is None
        return record

    monkeypatch.setattr(runtime, '_reserve_sql_handoff', foreign_stop_after_group_snapshot)

    async def run():
        with pytest.raises(ValueError): await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        member = record.members[0]
        assert record is reservations[0] and not member.reserved and owner._controller is None
        release.set()
        assert await asyncio.to_thread(actual.done.wait, 1) and actual.error is None
        with pytest.raises(ValueError): await runtime.quiesce_writers(timeout=2)
        assert owner.fence is None and not member.reserved
        # Only the original public controller can finish its own pending stop.
        token = store.freeze_connections(0)
        store.resume_connections(token)
        with pytest.raises(ValueError): await runtime.activate_handoff(record.payload, writers=True)
        assert owner.epoch == member.epoch+1 and member.token is None
        assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting

    asyncio.run(run())


@pytest.mark.parametrize('selected', [0, 1, 4])
def test_actual_controller_binding_survives_sql_resume_through_final_admission(cohort, monkeypatch, selected):
    value, runtime = cohort, cohort.runtime
    owner = owners(value)[selected]
    entered, finished = threading.Event(), threading.Event()
    attempts = []

    def competing_public_freeze():
        assert entered.wait(3)
        try:
            attempts.append(owner.freeze(0))
        finally:
            finished.set()

    competing = worker(value, competing_public_freeze)
    original = runtime._reading_registry._reopen_sql_creation

    def at_last_admission(sql_set, gate, deadline):
        # Runtime holds every actual owner serialization lock here. Public
        # admission must refuse without waiting for those non-reentrant locks.
        entered.set()
        assert finished.wait(2)
        assert competing.done.wait(1) and type(competing.error) is ValueError and attempts == []
        member = members(runtime._sql_handoff)[selected]
        assert owner._controller is member and member.resumed and owner.fence is None
        return original(sql_set, gate, deadline)

    monkeypatch.setattr(runtime._reading_registry, '_reopen_sql_creation', at_last_admission)

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        assert await runtime.activate_handoff(payload, writers=True) == {'active': True}
        assert all(member.owner._controller is None for member in members(record))
        assert runtime.request_writers._accepting and runtime._reading_registry._accepting
        value.healthy()
        # Public per-store controls remain usable after successful retirement.
        fresh = owner.freeze(0)
        owner.resume(fresh)
        value.healthy()

    try:
        asyncio.run(run())
    finally:
        entered.set()


def test_public_call_queued_before_reservation_cannot_freeze_after_runtime_final_admission(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    owner = runtime.transcript._sql_lifetime
    entered, release = threading.Event(), threading.Event()
    value.releases.append(release)
    original = owner._public_entry

    def delayed_public_entry():
        entry = original()
        entered.set()
        assert release.wait(5)
        return entry

    monkeypatch.setattr(owner, '_public_entry', delayed_public_entry)
    public = worker(value, lambda: owner.freeze(2))
    assert entered.wait(2)

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        await runtime.activate_handoff(payload, writers=True)
        release.set()
        assert await asyncio.to_thread(public.done.wait, 1) and type(public.error) is ValueError
        assert owner.fence is None and owner.gate._accepting and owner._controller is None
        assert runtime.request_writers._accepting and runtime._reading_registry._accepting
        value.healthy()

    asyncio.run(run())


def test_final_owner_lock_timeout_preserves_all_controllers_before_any_admission(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    entered, release = threading.Event(), threading.Event()
    value.releases.append(release)
    holder = None

    async def run():
        nonlocal holder
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        runtime._resume_sql_handoff(time.monotonic()+2)
        runtime._resume_writer_pools(time.monotonic()+2)
        original = runtime._check_sql_handoff

        def hold_last_owner_after_checks(*args, **kwargs):
            nonlocal holder
            original(*args, **kwargs)

            def hold():
                with members(record)[-1].owner.serialization:
                    entered.set()
                    assert release.wait(5)

            holder = worker(value, hold)
            assert entered.wait(1)

        monkeypatch.setattr(runtime, '_check_sql_handoff', hold_last_owner_after_checks)
        started = time.monotonic()
        with pytest.raises(TimeoutError): runtime.admit_requests(started+.03)
        assert time.monotonic()-started < .5 and not holder.done.is_set()
        assert runtime._sql_handoff is record and runtime._reading_registry._sql_set is record.readings
        assert not runtime.request_writers._accepting and not runtime._reading_registry._accepting
        for member in members(record):
            assert member.owner._controller is member and member.resumed
        for member in members(record)[:-1]:
            assert member.owner.serialization.acquire(blocking=False)
            member.owner.serialization.release()
        release.set()
        assert await asyncio.to_thread(holder.done.wait, 1) and holder.error is None
        monkeypatch.setattr(runtime, '_check_sql_handoff', original)
        await runtime.activate_handoff(payload, writers=True)
        value.healthy()

    asyncio.run(run())


def test_late_registry_lock_contention_bounds_sql_recovery_without_partial_resume(cohort):
    runtime = cohort.runtime
    entered, release = threading.Event(), threading.Event()
    cohort.releases.append(release)

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff

        def hold():
            with runtime._reading_registry._lock:
                entered.set()
                assert release.wait(5)

        holder = worker(cohort, hold)
        assert await asyncio.to_thread(entered.wait, 1)
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            runtime._resume_sql_handoff(started+.03)
        assert time.monotonic()-started < .5 and not holder.done.is_set()
        assert runtime._sql_handoff is record and not any(member.resumed for member in members(record))
        assert not runtime.request_writers._accepting
        release.set()
        assert await asyncio.to_thread(holder.done.wait, 1)
        await runtime.activate_handoff(payload, writers=True)

    asyncio.run(run())


def test_completed_cohort_can_freeze_new_reader_next_generation_without_reusing_tokens(cohort):
    value, runtime = cohort, cohort.runtime

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        old = runtime._sql_handoff
        await runtime.activate_handoff(payload, writers=True)
        pin = runtime.lexirise.pin('fr')
        with runtime._reading_registry.lookup() as lookup:
            new = runtime._reading_registry.get_or_create(lookup, (pin._scope(), 'fr', 'en', 'second-generation'),
                pin, source_language='fr', translation_language='en')
        value.readers.append(new)
        second = await runtime.quiesce_writers(timeout=2)
        current = runtime._sql_handoff
        assert current is not old and current.readings.epoch is not old.readings.epoch
        assert len(members(current)) == 6 and len(members(old)) == 5
        for previous, actual in zip(members(old), members(current)):
            assert previous.owner is actual.owner and previous.token is not actual.token
            assert actual.epoch == previous.epoch+1
        await runtime.activate_handoff(second, writers=True)

    asyncio.run(run())


def test_inflight_retired_constructor_stays_in_actual_sql_cohort_after_creation_closes(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    registry = runtime._reading_registry
    original = LexiriseReadingService.__init__
    entered, release = threading.Event(), threading.Event()
    value.releases.append(release)

    def construct(reader, *args, **kwargs):
        value.readers.append(reader)
        entered.set()
        assert release.wait(5)
        original(reader, *args, **kwargs)

    monkeypatch.setattr(LexiriseReadingService, '__init__', construct)
    pin = runtime.lexirise.pin('fr')

    def create():
        with registry.lookup() as lookup:
            registry.get_or_create(lookup, (pin._scope(), 'fr', 'en', 'retired-constructor'), pin,
                source_language='fr', translation_language='en')

    actual = worker(value, create)
    assert entered.wait(2)

    async def run():
        stopped = asyncio.Event()
        stop = registry.stop_creation
        loop = asyncio.get_running_loop()

        def observe(deadline):
            stop(deadline)
            loop.call_soon_threadsafe(stopped.set)

        monkeypatch.setattr(registry, 'stop_creation', observe)
        task = asyncio.create_task(runtime.quiesce_writers(timeout=2))
        try:
            await asyncio.wait_for(stopped.wait(), 1)
            assert not task.done() and runtime._sql_handoff is None and actual.thread.is_alive()
            release.set()
            payload = await task
            assert actual.done.wait(1) and isinstance(actual.error, WritersQuiescing)
            record = runtime._sql_handoff
            assert len(record.readings.members) == 4
            assert any(member.reader is value.readers[-1] for member in record.readings.members)
            await runtime.activate_handoff(payload, writers=True)
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize('change', ['members', 'default'])
def test_registry_cannot_omit_reserved_sql_owner_or_default_identity(cohort, change):
    runtime = cohort.runtime

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        if change == 'members':
            record.readings.members = record.readings.members[:-1]
        else:
            record.readings.default = cohort.readers[1]
        with pytest.raises(TimeoutError):
            await runtime.activate_handoff(payload, writers=True)
        assert not any(member.resumed for member in record.members)
        assert runtime._sql_handoff is record and not runtime.request_writers._accepting
        assert not runtime._reading_registry._accepting

    asyncio.run(run())


def test_native_cleanup_refusal_retains_frozen_sql_and_recovery_steps_share_one_deadline(cohort, monkeypatch):
    runtime = cohort.runtime
    error = TimeoutError('Authored cleanup refusal; no native call.')
    attempts, deadlines = [], []
    original = runtime._handoff_step

    async def observe(operation, deadline, **options):
        deadlines.append(deadline)
        return await original(operation, deadline, **options)

    async def cleanup():
        attempts.append(True)
        assert all(not member.resumed for member in members(runtime._sql_handoff))
        if len(attempts) == 1:
            raise error
        runtime.capture.native_stop_pending = False

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        runtime.capture.native_stop_pending = True
        runtime.capture.finish_native_stop = cleanup
        monkeypatch.setattr(runtime, '_handoff_step', observe)
        with pytest.raises(TimeoutError) as refused:
            await runtime.activate_handoff(payload, writers=True)
        assert refused.value is error and record.error is error
        assert not any(member.resumed for member in members(record))
        assert len(set(deadlines)) == 1 and not runtime._reading_registry._accepting
        deadlines.clear()
        await runtime.activate_handoff(payload, writers=True)
        # The retained outer request pause joins the same recovery deadline.
        assert len(deadlines) == 6 and len(set(deadlines)) == 1
        assert runtime._sql_handoff is None and len(attempts) == 2

    asyncio.run(run())


def test_request_stop_metadata_timeout_is_bounded_off_loop_before_any_producer_drain(cohort):
    runtime = cohort.runtime
    entered, release = threading.Event(), threading.Event()
    cohort.releases.append(release)

    def hold():
        with runtime.request_writers._condition:
            entered.set()
            assert release.wait(5)

    holder = worker(cohort, hold)
    assert entered.wait(2)

    async def run():
        started = time.monotonic()
        task = asyncio.create_task(runtime.quiesce_writers(timeout=.04))
        await asyncio.sleep(.005)  # Actual holder stays locked; event loop must keep running.
        assert not task.done() and not holder.done.is_set()
        with pytest.raises(TimeoutError):
            await task
        assert time.monotonic()-started < .5 and not holder.done.is_set()
        assert runtime._sql_handoff is None and cohort.calls == []
        await asyncio.gather(*runtime._handoff_drains, return_exceptions=True)
        release.set()
        assert await asyncio.to_thread(holder.done.wait, 1)
        # Explicit recovery still closes/drains requests and reader creation.
        await runtime.activate_handoff(CaptureHandoff(running=True), writers=True)
        assert runtime.request_writers._accepting and runtime._reading_registry._accepting

    asyncio.run(run())


@pytest.mark.parametrize('replacement', ['gate', 'capture'])
def test_retained_retry_refuses_changed_runtime_binding_before_touching_foreign_resource(cohort, replacement):
    runtime = cohort.runtime

    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        if replacement == 'gate':
            foreign = RuntimeWriterGate()
            foreign.stop_admission = cohort.forbidden
            runtime.request_writers = foreign
        else:
            foreign = SimpleNamespace(native_stop_pending=True, finish_native_stop=cohort.forbidden)
            runtime.capture = foreign
        with pytest.raises(TimeoutError):
            await runtime.quiesce_writers(timeout=2)
        with pytest.raises(TimeoutError):
            await runtime.activate_handoff(payload, writers=True)
        assert runtime._sql_handoff is record and not record.gate._accepting
        assert not runtime._reading_registry._accepting
        if replacement == 'gate':
            assert foreign._accepting

    asyncio.run(run())


@pytest.mark.parametrize('foreign_ledger', [False, True])
def test_actual_sql_ledger_type_is_preserved_across_the_existing_grammar_constructor_hook(cohort, monkeypatch, foreign_ledger):
    from backend.runtime_probe import _AuthoredGrammarService
    runtime = cohort.runtime
    actual = runtime.lexirise
    original_type = api.LexiriseService
    grammar = _AuthoredGrammarService(SimpleNamespace(data_root=actual.directory.parent,
        work_root=actual.directory.parent/'owned-grammar-work'), original_type)
    # Exactly the existing frozen grammar probe's scoped constructor binding;
    # its returned production service still has the original class identity.
    monkeypatch.setattr(api, 'LexiriseService', grammar.create)
    assert isinstance(actual, original_type)
    if foreign_ledger:
        runtime.lexirise = SimpleNamespace(_sql_lifetime=actual._sql_lifetime)

    async def run():
        if foreign_ledger:
            with pytest.raises(TypeError, match='actual retained stores'):
                await runtime.quiesce_writers(timeout=2)
            assert actual._sql_lifetime.fence is None
            assert not runtime.request_writers._accepting
            return
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        assert record.lexirise is actual and record.members[1].owner is actual._sql_lifetime
        assert all(member.token is not None for member in members(record))
        await runtime.activate_handoff(payload, writers=True)
        assert runtime._sql_handoff is None and runtime.request_writers._accepting
        cohort.healthy()

    asyncio.run(run())


def test_outer_admission_waits_for_actual_stream_sql_pools_and_epoch_retirement(cohort, monkeypatch):
    """Two real request layers, owned SQLite and an Event-held final metadata commit."""
    from backend.runtime_workers import WriterBarrierMiddleware
    from backend.runtime_writers import RuntimeWriterMiddleware
    value, runtime = cohort, cohort.runtime
    commit_entered, commit_release = threading.Event(), threading.Event()
    value.releases.append(commit_release)
    async def run():
        requests, idle = runtime.request_barrier, runtime.request_barrier._idle
        loop_thread = threading.get_ident()
        for name in ('set', 'clear', 'is_set'):
            original = getattr(idle, name)
            def checked(*args, _original=original):
                assert threading.get_ident() == loop_thread, 'RequestBarrier Event accessed from SQL worker'
                return _original(*args)
            monkeypatch.setattr(idle, name, checked)
        original_wait = idle.wait
        async def checked_wait():
            assert threading.get_ident() == loop_thread
            return await original_wait()
        monkeypatch.setattr(idle, 'wait', checked_wait)
        entered, release, pausing = asyncio.Event(), asyncio.Event(), asyncio.Event()
        outputs, handler_calls = [], []
        async def handler(scope, receive, send):
            handler_calls.append('handler')
            assert await asyncio.to_thread(runtime.transcript.count) >= 0
            await send({'type':'http.response.start', 'status':200, 'headers':[]})
            entered.set()
            await release.wait()
            await send({'type':'http.response.body', 'body':b'complete'})
        middleware = WriterBarrierMiddleware(RuntimeWriterMiddleware(handler, lambda: runtime), lambda: requests)
        scope = {'type':'http', 'path':'/api/lines/1/reading', 'method':'GET'}
        async def receive(): return {'type':'http.request'}
        async def send(message): outputs.append(message)
        streaming = asyncio.create_task(middleware(scope, receive, send))
        await entered.wait()
        original_pause = runtime._pause_outer_requests
        async def pause():
            pausing.set()
            await original_pause()
        monkeypatch.setattr(runtime, '_pause_outer_requests', pause)
        stopping = asyncio.create_task(runtime.quiesce_writers(timeout=2))
        await pausing.wait()
        assert requests.paused and requests._active == 1 and not stopping.done()
        assert runtime._sql_handoff is None and not runtime.request_writers._accepting
        release.set()
        await streaming
        payload = await stopping
        record = runtime._sql_handoff
        assert record.requests is requests and record.requests_idle is idle
        original_reopen = runtime._reading_registry._reopen_sql_creation
        def hold_commit(readings, gate, deadline):
            assert requests.paused and requests._active == 0 and requests._idle is idle
            assert all(member.resumed for member in members(record))
            original_reopen(readings, gate, deadline)
            commit_entered.set()
            assert commit_release.wait(3)
        monkeypatch.setattr(runtime._reading_registry, '_reopen_sql_creation', hold_commit)
        activating = asyncio.create_task(runtime.activate_handoff(payload, writers=True))
        try:
            assert await asyncio.to_thread(commit_entered.wait, 1)
            assert requests.paused and requests._active == 0 and requests._idle is idle
            assert runtime._sql_handoff is record and all(member.resumed for member in members(record))
            outputs.clear()
            await middleware(scope, receive, send)
            assert outputs[0]['status'] == 503 and handler_calls == ['handler']
            assert all(member.owner._controller is member for member in members(record))
        finally:
            commit_release.set()
        assert await activating == {'active':True}
        assert not requests.paused and requests._idle is idle and runtime.request_writers._accepting
        assert runtime._sql_handoff is None and all(member.owner._controller is None for member in members(record))
        outputs.clear()
        await middleware(scope, receive, send)
        assert outputs[0]['status'] == 200 and handler_calls == ['handler', 'handler']
    asyncio.run(run())


@pytest.mark.parametrize('changed', ['barrier', 'idle'])
def test_sql_recovery_refuses_replaced_outer_request_owner_without_opening_either_layer(cohort, changed):
    value, runtime = cohort, cohort.runtime
    async def run():
        payload = await runtime.quiesce_writers(timeout=2)
        record = runtime._sql_handoff
        requests, idle = record.requests, record.requests_idle
        before = list(value.calls)
        if changed == 'barrier': runtime.request_barrier = RequestBarrier(paused=True)
        else: requests._idle = asyncio.Event()
        with pytest.raises(TimeoutError, match='ownership changed'):
            await runtime.activate_handoff(payload, writers=True)
        assert runtime._sql_handoff is record and record.requests is requests and record.requests_idle is idle
        assert not record.gate._accepting and requests.paused and value.calls == before
        assert not any(member.resumed for member in members(record))
    asyncio.run(run())


def test_partial_activation_cannot_reuse_a_successful_cached_sql_stop(cohort):
    value, runtime = cohort, cohort.runtime
    async def run():
        payload = await runtime.quiesce()
        stopped = runtime._quiesce_task
        assert stopped.done() and stopped.exception() is None
        record = runtime._sql_handoff
        failure = RuntimeError('authored update-start refusal after actual SQL resume')
        value.update_error = failure
        with pytest.raises(RuntimeError) as raised:
            await runtime.activate_handoff(payload, writers=True)
        assert raised.value is failure and record.error is failure
        assert all(member.resumed for member in members(record))
        # The real SQL owner is writable again, even though public admission
        # stayed closed: the old completed drain is no longer stop authority.
        runtime.transcript.add(TextMatch(text_id='after-resume', english='After resume',
            chinese='恢复后的台词', source_ocr='恢复后的台词', score=100, kind='exact'), 'owned-session')
        with pytest.raises(TimeoutError, match='Recovered SQL owners'):
            await runtime.quiesce()
        assert runtime._quiesce_task is not stopped and runtime._sql_handoff is record
        assert runtime.request_barrier.paused and not runtime.request_writers._accepting
    asyncio.run(run())


def test_quiesce_selection_waits_for_actual_activation_instead_of_returning_old_stop(cohort, monkeypatch):
    value, runtime = cohort, cohort.runtime
    entered, release = threading.Event(), threading.Event()
    value.releases.append(release)
    original = runtime._resume_writer_pools
    def pools(deadline):
        original(deadline)
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(runtime, '_resume_writer_pools', pools)
    async def run():
        payload = await runtime.quiesce()
        old = runtime._quiesce_task
        old_record = runtime._sql_handoff
        activating = asyncio.create_task(runtime.activate_handoff(payload, writers=True))
        assert await asyncio.to_thread(entered.wait, 1)
        selecting = asyncio.create_task(runtime.quiesce())
        await asyncio.sleep(0)  # The activation already holds the actual lock.
        try:
            assert runtime._handoff_lock.locked() and not selecting.done()
            assert all(member.resumed for member in members(old_record))
        finally:
            release.set()
            assert await activating == {'active':True}
            await selecting
        assert runtime._quiesce_task is not old and runtime._sql_handoff is not old_record
        assert runtime.request_barrier.paused and not runtime.request_writers._accepting
    asyncio.run(run())


@pytest.mark.parametrize('changed', ['barrier', 'idle'])
def test_first_stop_owner_binding_survives_pre_sql_failure_and_cannot_adopt_retry(cohort, monkeypatch, changed):
    runtime = cohort.runtime
    async def run():
        requests, idle = runtime.request_barrier, runtime.request_barrier._idle
        entered, release, selected, continue_pause = (asyncio.Event() for _ in range(4))
        async def handler(scope, receive, send):
            assert await asyncio.to_thread(runtime.transcript.count) >= 0
            entered.set()
            await release.wait()
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'owned'})
        async def receive(): return {'type':'http.request'}
        async def send(message): pass
        from backend.runtime_workers import WriterBarrierMiddleware
        from backend.runtime_writers import RuntimeWriterMiddleware
        middleware = WriterBarrierMiddleware(RuntimeWriterMiddleware(handler, lambda: runtime), lambda: runtime.request_barrier)
        original = runtime._pause_outer_requests
        async def pause():
            selected.set()
            if changed == 'idle':
                await continue_pause.wait()
            await original()
        monkeypatch.setattr(runtime, '_pause_outer_requests', pause)
        streaming = asyncio.create_task(middleware({'type':'http','path':'/api/lines/1/reading'}, receive, send))
        await entered.wait()
        stopping = asyncio.create_task(runtime.quiesce())
        await selected.wait()
        failed_task, stop = runtime._quiesce_task, runtime._request_stop
        assert stop.requests is requests and stop.idle is idle and runtime._sql_handoff is None
        replacement = RequestBarrier() if changed == 'barrier' else asyncio.Event()
        if changed == 'barrier':
            assert requests.paused and requests._active == 1
            runtime.request_barrier = replacement
        else:
            # The first selection already owns the original idle Event even
            # before pause executes. Completion below uses the real leave().
            requests._idle = replacement
        release.set()
        await streaming
        continue_pause.set()
        with pytest.raises(TimeoutError, match='retained paused, idle owner') as failure:
            await stopping
        assert requests._active == 0 and failed_task.done() and failed_task.exception() is failure.value
        assert runtime._request_stop is stop and stop.error is failure.value and stop.failed_task is failed_task
        drains = tuple(runtime._handoff_drains)
        for _ in range(2):
            with pytest.raises(TimeoutError, match='retained paused, idle owner'):
                await runtime.quiesce()
            assert runtime._quiesce_task is failed_task and runtime._request_stop is stop
            assert stop.error is failure.value and stop.failed_task is failed_task
            assert runtime._sql_handoff is None and tuple(runtime._handoff_drains) == drains
        if changed == 'barrier':
            # Only the same actual owner can recover. Its real request ended,
            # so the original Event became idle without any forced completion.
            runtime.request_barrier = requests
            assert idle.is_set()
            payload = await runtime.quiesce()
            assert runtime._request_stop is stop and runtime._sql_handoff.request_stop is stop
            assert stop.error is failure.value and stop.failed_task is failed_task
            assert await runtime.activate_handoff(payload, writers=True) == {'active':True}
            assert runtime._request_stop is None and runtime._sql_handoff is None
            assert not requests.paused and runtime.request_writers._accepting
    asyncio.run(run())
