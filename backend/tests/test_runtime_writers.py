"""Real thread/request drain cases missing from synthetic coordinator fixtures."""
import asyncio
from types import SimpleNamespace
import threading

import pytest

from backend.runtime_workers import RequestBarrier
from backend.runtime_writers import QuiesceableExecutor, RuntimeWriterGate, RuntimeWriterMiddleware, WritersQuiescing


def test_admission_tickets_bind_gate_and_epoch_and_retire_across_resume():
    gate, other = RuntimeWriterGate(), RuntimeWriterGate()
    ticket = gate.capture_ticket()
    for rejected in (None, True, {}, other.capture_ticket()):
        with pytest.raises(WritersQuiescing): gate.enter(rejected)
    gate.wait_drained(0)
    gate.enter(ticket)
    gate.stop_admission()
    with pytest.raises(WritersQuiescing): gate.capture_ticket()
    with pytest.raises(WritersQuiescing): gate.enter(ticket)
    with pytest.raises(TimeoutError): gate.wait_drained(0)
    gate.leave()
    gate.wait_drained(0)
    gate.resume()
    with pytest.raises(WritersQuiescing): gate.enter(ticket)
    replacement = gate.capture_ticket()
    gate.enter(replacement); gate.leave()
    gate.enter(); gate.leave()  # Legacy unticketed admission remains usable.
    gate.stop_admission(); gate.stop_admission(); gate.resume()
    with pytest.raises(WritersQuiescing): gate.enter(replacement)
    gate.wait_drained(0)


def test_done_future_callback_must_finish_before_resume_or_drain_proof():
    work_release, callback_entered, callback_release = threading.Event(), threading.Event(), threading.Event()
    pool = QuiesceableExecutor(1)
    try:
        future = pool.submit(lambda: work_release.wait(3))
        def callback(_):
            callback_entered.set()
            assert callback_release.wait(3)
        future.add_done_callback(callback)
        work_release.set()
        assert callback_entered.wait(1) and future.done()
        with pytest.raises(TimeoutError): pool.quiesce(.01)
        with pytest.raises(WritersQuiescing): pool.submit(lambda: None)
        with pytest.raises(TimeoutError): pool.resume()
        callback_release.set()
        pool.quiesce(1)
        pool.resume()
        assert pool.submit(lambda: 'resumed').result(timeout=1) == 'resumed'
    finally:
        work_release.set(); callback_release.set()
        pool.shutdown()


def test_unbounded_drain_waits_for_actual_done_callback_completion():
    work_release, callback_entered, callback_release = threading.Event(), threading.Event(), threading.Event()
    draining, finished = threading.Event(), threading.Event()
    errors = []
    pool = QuiesceableExecutor(1)
    def drain():
        draining.set()
        try:
            pool.drain()
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()
    waiter = threading.Thread(target=drain)
    try:
        future = pool.submit(lambda: work_release.wait(3))
        def callback(_):
            callback_entered.set()
            assert callback_release.wait(3)
        future.add_done_callback(callback)
        work_release.set()
        assert callback_entered.wait(1) and future.done()
        waiter.start()
        assert draining.wait(1)
        assert not finished.wait(.02)
        with pytest.raises(WritersQuiescing): pool.submit(lambda: None)
        with pytest.raises(TimeoutError): pool.resume()
        callback_release.set()
        assert finished.wait(1) and not errors
        pool.resume()
        assert pool.submit(lambda: 'resumed').result(timeout=1) == 'resumed'
    finally:
        work_release.set(); callback_release.set()
        if waiter.ident is not None:
            waiter.join(3)
        pool.shutdown()


def test_shutdown_cannot_be_reversed_after_retired_worker_finishes():
    entered, release = threading.Event(), threading.Event()
    pool = QuiesceableExecutor(1)
    def native_work():
        entered.set()
        assert release.wait(3)
    try:
        future = pool.submit(native_work)
        assert entered.wait(1)
        pool.shutdown(wait=False, cancel_futures=True)
        with pytest.raises(RuntimeError, match='permanently closed'): pool.resume()
        with pytest.raises(TimeoutError): pool.quiesce(.01)
        release.set()
        pool.quiesce(1)
        assert future.result(timeout=1) is None
        with pytest.raises(RuntimeError, match='permanently closed'): pool.resume()
        with pytest.raises(WritersQuiescing): pool.submit(lambda: None)
    finally:
        release.set(); pool.shutdown()


def test_request_scope_includes_stream_completion_and_blocks_cache_writing_gets():
    async def run():
        gate = RuntimeWriterGate()
        started, finish = asyncio.Event(), asyncio.Event()
        calls, output = [], []
        async def app(scope, receive, send):
            calls.append(scope['path'])
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            if scope['path'] == '/api/lines/1/reading':
                await send({'type': 'http.response.body', 'body': b'first', 'more_body': True})
                started.set(); await finish.wait()
            await send({'type': 'http.response.body', 'body': b'finished'})
        middleware = RuntimeWriterMiddleware(app, lambda: SimpleNamespace(request_writers=gate))
        async def receive(): return {'type': 'http.request'}
        async def send(message): output.append(message)
        scope = {'type': 'http', 'path': '/api/lines/1/reading', 'method': 'GET'}
        old = asyncio.create_task(middleware(scope, receive, send))
        await started.wait()
        gate.stop_admission()
        try:
            with pytest.raises(TimeoutError): await asyncio.to_thread(gate.wait_drained, .01)
            output.clear()
            await middleware(scope, receive, send)
            assert output[0]['status'] == 503
            assert calls == ['/api/lines/1/reading']
            output.clear()
            await middleware({**scope, 'path': '/api/health'}, receive, send)
            assert output[0]['status'] == 200
        finally:
            finish.set(); await old
        await asyncio.to_thread(gate.wait_drained, 1)
        gate.resume()
        gate.enter(); gate.leave()
    asyncio.run(run())


def test_timed_out_handoff_owns_its_real_thread_and_refuses_early_recovery():
    from backend.api import Runtime
    async def run():
        entered, release = threading.Event(), threading.Event()
        runtime = Runtime.__new__(Runtime)
        runtime._handoff_drains = []
        def write():
            entered.set(); assert release.wait(3)
        try:
            with pytest.raises(TimeoutError):
                await runtime._handoff_step(write, __import__('time').monotonic()+.02, blocking=True)
            assert entered.is_set() and not runtime._handoff_drains[0].done()
            with pytest.raises(TimeoutError): runtime.resume_writers()
            release.set()
            await runtime._handoff_drains[0]
        finally:
            release.set()
    asyncio.run(run())


def test_retired_ocr_thread_is_retained_until_quiesce_and_recovery_finish(tmp_path):
    from backend.tests.test_subtitle_capture import fixture_service
    capture, _, _, _ = fixture_service(tmp_path)
    retired = QuiesceableExecutor(1)
    entered, release = threading.Event(), threading.Event()
    def old_native():
        entered.set(); assert release.wait(3)
    retired.submit(old_native)
    assert entered.wait(1)
    retired.shutdown(wait=False, cancel_futures=True)
    capture._retired_executors.append(retired)
    async def run():
        try:
            with pytest.raises(TimeoutError): await capture.quiesce(.02)
            # The timed-out waiter leaves the real stop task and retired native
            # worker owned on this same application event loop.
            assert capture._stop_task is not None and not capture._stop_task.done()
            assert retired in capture._retired_executors
            with pytest.raises(TimeoutError): capture.resume_workers()
        finally:
            release.set()
            await capture.stop()
        capture.resume_workers()
        assert not capture._retired_executors
        with pytest.raises(WritersQuiescing): retired.submit(lambda: None)
        assert capture._executor.submit(lambda: 'new native work').result(timeout=1) == 'new native work'
    try:
        asyncio.run(run())
    finally:
        release.set(); retired.shutdown(); capture._executor.shutdown()


def test_manual_export_cancelled_label_cannot_hide_a_live_writer(tmp_path, monkeypatch):
    from backend.mobile_export_controls import MobileExportManager
    manager = MobileExportManager(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def export():
        entered.set(); assert release.wait(3)
    worker = manager._thread = threading.Thread(target=export)
    worker.start(); assert entered.wait(1)
    manager._status['state'] = 'cancelled'
    monkeypatch.setattr(manager, 'cancel', lambda: pytest.fail('Handoff must not infer native cleanup from cancel'))
    try:
        with pytest.raises(TimeoutError): manager.quiesce()
        assert manager.start('zzz') is False
    finally:
        release.set(); worker.join(1)
    manager.quiesce()
    manager.resume()


def test_setup_process_exit_does_not_precede_its_write_callback(tmp_path, monkeypatch):
    from backend import installation
    from backend.config import SettingsStore
    entered, release = threading.Event(), threading.Event()
    def refresh(_game):
        entered.set(); assert release.wait(3)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    service = installation.InstallationService(tmp_path,
        settings=SettingsStore(tmp_path/'settings.json'), game_state=lambda _: {},
        refresh=refresh, account_configured=lambda: False, install_lookup=lambda _: None)
    process = SimpleNamespace(wait=lambda: 0, poll=lambda: 0)
    service._native_owners['folders'] = SimpleNamespace(stop=lambda: None, close_streams=lambda: None)
    monkeypatch.setattr(installation, 'load_paths', lambda: {'zzz': 'authored-folder'})
    worker = threading.Thread(target=service._native_finished, args=('folders', process, {}))
    service._native_threads.add(worker); service._native['folders'] = process
    worker.start(); assert entered.wait(1)
    try:
        with pytest.raises(TimeoutError): service.quiesce(.01)
        assert service.prepare('zzz') is False
    finally:
        release.set(); worker.join(1)
    service.quiesce(1); service.resume()


def test_queued_capture_publication_is_still_owned_after_native_worker_returns(tmp_path):
    from backend.tests.test_subtitle_capture import fixture_service
    capture, _, _, _ = fixture_service(tmp_path)
    async def run():
        capture._event_loop = asyncio.get_running_loop()
        entered, release = asyncio.Event(), asyncio.Event()
        async def persist():
            entered.set()
            await release.wait()
        capture._queue_publication(persist())
        await entered.wait()
        draining = asyncio.create_task(capture.drain_publications())
        await asyncio.sleep(0)
        assert not draining.done()
        release.set()
        await draining
        assert not capture._publications
    try:
        asyncio.run(run())
    finally:
        capture._executor.shutdown()


def test_activation_serializes_with_the_complete_quiesce_operation():
    from backend.api import Runtime
    from backend.runtime_handoff import CaptureHandoff
    async def run():
        runtime = Runtime.__new__(Runtime)
        runtime._request_stop = None
        runtime._handoff_lock, runtime._writer_handoff = asyncio.Lock(), True
        runtime._sql_handoff = None
        runtime._quiesce_task = None
        runtime.request_barrier = RequestBarrier(paused=True)
        runtime._prepare_recovery_requests = lambda _deadline: None  # Serialization-only adapter.
        calls = []
        runtime._resume_writer_pools = lambda _deadline: calls.append('resume')
        runtime._handoff_drains = []
        runtime.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True), native_stop_pending=False)
        runtime.start_updates = lambda: calls.append('updates')
        runtime.admit_requests = lambda _deadline: calls.append('admit')
        await runtime._handoff_lock.acquire()
        activating = asyncio.create_task(runtime.activate_handoff(CaptureHandoff(running=True), writers=True))
        await asyncio.sleep(0)
        assert calls == [] and not activating.done()
        runtime._handoff_lock.release()
        assert await activating == {'active': True}
        assert calls == ['resume', 'updates', 'admit']
    asyncio.run(run())


def test_disconnected_handoff_waiter_does_not_cancel_the_actual_drain():
    from backend.api import Runtime
    import time
    async def run():
        entered, release = threading.Event(), threading.Event()
        runtime = Runtime.__new__(Runtime)
        runtime._handoff_drains = []
        def write():
            entered.set()
            assert release.wait(3)
        waiting = asyncio.create_task(runtime._handoff_step(write, time.monotonic()+2, blocking=True))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError): await waiting
            assert not runtime._handoff_drains[0].done()
            with pytest.raises(TimeoutError): runtime.resume_writers()
        finally:
            release.set()
            await runtime._handoff_drains[0]
    asyncio.run(run())


def test_failed_native_cleanup_retains_ownership_and_blocks_strict_activation(tmp_path, monkeypatch):
    from backend import api
    from backend.runtime_handoff import CaptureHandoff
    from backend.tests.test_subtitle_capture import fixture_service
    capture, _, _, _ = fixture_service(tmp_path)
    failing, calls = [True], []
    def stop_native():
        calls.append('native-stop')
        if failing[0]:
            raise TimeoutError('Synthetic background cleanup is incomplete')
    worker = SimpleNamespace(close=stop_native)
    capture._background_capture._worker = worker
    monkeypatch.setattr(capture, 'start', lambda: calls.append('capture-start'))
    async def run():
        capture._update_snapshot(running=True)
        capture._task = asyncio.create_task(asyncio.sleep(100))
        with pytest.raises(TimeoutError): await capture.quiesce(.2)
        assert capture._task is None and not capture.snapshot().running
        assert capture.native_stop_pending and capture._background_capture._worker is worker
        with pytest.raises(TimeoutError): capture.resume_workers()
        runtime = api.Runtime.__new__(api.Runtime)
        runtime._request_stop = None
        runtime._handoff_lock, runtime._writer_handoff, runtime._handoff_drains = asyncio.Lock(), True, []
        runtime._sql_handoff = None
        runtime._quiesce_task = None
        runtime.request_barrier = RequestBarrier(paused=True)
        runtime._prepare_recovery_requests = lambda _deadline: None  # Native-stop-only adapter.
        runtime.capture = capture
        def resume():
            calls.append('resume')
            capture.resume_workers()
        runtime._resume_writer_pools = lambda _deadline: resume()
        runtime.start_updates = lambda: calls.append('updates')
        runtime.admit_requests = lambda _deadline: calls.append('admit')
        payload = CaptureHandoff(running=True)
        with pytest.raises(TimeoutError): await runtime.activate_handoff(payload, writers=True)
        assert calls == ['native-stop', 'native-stop']
        assert capture._background_capture._worker is worker and runtime._writer_handoff
        failing[0] = False
        assert await runtime.activate_handoff(payload, writers=True) == {'active': True}
        assert capture._background_capture._worker is None and not capture.native_stop_pending
        assert calls == ['native-stop', 'native-stop', 'native-stop', 'resume', 'capture-start', 'updates', 'admit']
    try:
        asyncio.run(run())
    finally:
        capture._executor.shutdown()


@pytest.mark.parametrize('strict', [False, True])
def test_index_drain_keeps_actual_writer_owned_for_both_stop_protocols(strict):
    from backend.api import Runtime
    async def run():
        release = asyncio.Event()
        index = asyncio.create_task(release.wait())
        idle = SimpleNamespace(close=lambda: None)
        runtime = SimpleNamespace(_updates_started=True, languages=idle, repair_task=None,
            index_task=index, map_task=None, update_manager=idle, pragmata_updater=idle, game_updaters={})
        stopping = asyncio.create_task(Runtime.stop_updates(runtime, drain=strict))
        await asyncio.sleep(.01)
        try:
            # The source protocol must not cancel a to_thread waiter either:
            # its actual catalog/cache writer can outlive that cancellation.
            assert not stopping.done() and not index.cancelled()
        finally:
            release.set()
            await stopping
        assert runtime.index_task is None
    asyncio.run(run())


def test_cancelled_reading_drain_retains_actual_creation_thread_and_requires_final_admission(tmp_path):
    from backend.api import Runtime
    from backend.runtime_readers import RuntimeReadingRegistry
    import time
    async def run():
        registry = RuntimeReadingRegistry(tmp_path/'owned-readers')
        runtime = Runtime.__new__(Runtime)
        runtime._handoff_drains = []
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def lookup():
            try:
                with registry.lookup():
                    entered.set()
                    assert release.wait(5)
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=lookup)
        worker.start()
        assert await asyncio.to_thread(entered.wait, 1)
        original = registry.stop_creation
        def stop(deadline):
            original(deadline); stopped.set()
        registry.stop_creation = stop
        waiter = asyncio.create_task(runtime._handoff_step(
            lambda: registry.quiesce_owned(time.monotonic()+3), time.monotonic()+3, blocking=True))
        try:
            assert await asyncio.to_thread(stopped.wait, 1)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError): await waiter
            drain, = runtime._handoff_drains
            assert not drain.done() and worker.is_alive() and registry._lookups
            with pytest.raises(TimeoutError): runtime.resume_writers()
            with pytest.raises(TimeoutError): registry.resume_pools()
            release.set()
            await drain
            await asyncio.to_thread(worker.join, 1)
            assert not worker.is_alive() and len(errors) == 1 and isinstance(errors[0], WritersQuiescing)
            registry.resume_pools()
            with pytest.raises(WritersQuiescing):
                with registry.lookup(): pass
            registry.reopen_creation()
            with registry.lookup(): pass
        finally:
            release.set()
            await asyncio.to_thread(worker.join, 5)
            for task in runtime._handoff_drains:
                if not task.done(): await task
    asyncio.run(run())
