"""Parent-owned idle source control: private pipes/Events, no default Runtime or accounts."""
import asyncio
import copy
import io
import os
import threading
import time
from types import SimpleNamespace

import pytest

from backend import api, desktop_host as host, main, owned_process as owned, runtime_writers as writers

_RETAINED_CONSTRUCTOR_CLEANUP_FAILURES = []


@pytest.fixture
def pipes(tmp_path):
    left_read, left_write = os.pipe()
    right_read, right_write = os.pipe()
    streams = [io.FileIO(fd, mode, closefd=True) for fd, mode in
        ((left_read, 'rb'), (left_write, 'wb'), (right_read, 'rb'), (right_write, 'wb'))]
    yield SimpleNamespace(input=streams[0], parent_write=streams[1], parent_read=streams[2], output=streams[3], directory=tmp_path / 'reading')
    for stream in streams:
        if not stream.closed:
            stream.close()


def initial_runtime(binding, directory):
    value = api.Runtime.__new__(api.Runtime)  # Never invoke real DATA_DIR constructors.
    value._parent_control = binding
    binding.attach_runtime(value)
    value.request_writers = binding.gate
    value.request_barrier = api.RequestBarrier(paused=True)
    value._handoff_lock, value._handoff_drains = asyncio.Lock(), []
    value._quiesce_task = value._handoff_state = value._request_stop = value._sql_handoff = None
    value._writer_handoff, value._updates_started, value.standby = False, False, True
    value._reading_registry = api.RuntimeReadingRegistry(directory)
    value.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=False), native_stop_pending=False,
        resume_workers=lambda: None, import_handoff=lambda payload: None,
        start=lambda: pytest.fail('Idle activation started native capture'))
    value.hito = SimpleNamespace(resume=lambda: None)
    value._voice_pools = lambda: []
    value.languages = SimpleNamespace(close=lambda **kw: None, start=lambda: None)
    value.installation = SimpleNamespace(resume=lambda: None)
    value.mobile_exports = SimpleNamespace(resume=lambda: None)
    value.automatic_exports = SimpleNamespace(picker=SimpleNamespace(resume=lambda: None), start=lambda: None)
    value._verify_background_stopped = lambda: None
    value.start_audio_repair = lambda: None
    binding.pin_initial()
    return value


def test_actual_pipe_fragmentation_and_byte_cap():
    read_fd, write_fd = os.pipe()
    stream = io.FileIO(read_fd, 'rb')
    done = threading.Event()
    def send():
        for part in (b'TPC1|', b'1|BI', b'ND\n'):
            os.write(write_fd, part)
        os.close(write_fd)
        done.set()
    thread = threading.Thread(target=send)
    thread.start()
    try:
        assert writers.read_parent_frame(stream) == b'TPC1|1|BIND\n'
        assert writers.read_parent_frame(stream) is None
    finally:
        thread.join(1)
        stream.close()
    assert done.is_set()
    for bad in (b'BIND\r\n', b'B\x00\n', b'\xef\xbb\xbfB\n', b'B\xff\n', b'partial'):
        with pytest.raises(writers.WritersQuiescing):
            writers.read_parent_frame(io.BytesIO(bad))
    bounded = io.BytesIO(b'x' * 128 + b'\n')
    with pytest.raises(writers.WritersQuiescing):
        writers.read_parent_frame(bounded)
    assert bounded.tell() == 128


def test_one_real_pipe_command_retains_actual_task_and_only_final_idle_admission(pipes):
    async def scenario():
        binding = writers.ParentControlBinding(pipes.input, pipes.output)
        gate = writers.RuntimeWriterGate(parent_control=binding)
        pipes.parent_write.write(b'TPC1|1|BIND\n')
        binding.bind_input()
        value = initial_runtime(binding, pipes.directory)
        entered, release, stopping = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def action(grant):
            entered.set()
            await release.wait()
            await value.activate_handoff(api.CaptureHandoff(running=False), writers=True, parent_grant=grant)
        binding.start(18767, action, stopping.set)
        assert await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read) == b'TPC1|1|BOUND|18767\n'
        pipes.parent_write.write(b'TPC1|2|ACTIVATE-IDLE\n')
        await asyncio.wait_for(entered.wait(), 1)
        task = binding.task
        assert task is not None and not task.done()
        with pytest.raises(writers.WritersQuiescing):
            binding.require_grant(copy.copy(binding.grant), value)
        with pytest.raises(writers.WritersQuiescing):
            value.resume_writers()
        with pytest.raises(writers.WritersQuiescing):
            gate.capture_ticket()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), .01)
        assert binding.task is task and not task.done()
        release.set()
        await asyncio.wait_for(asyncio.shield(task), 1)
        assert await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read) == b'TPC1|2|ACTIVE\n'
        assert value.standby is False and value.request_barrier.paused is False
        ticket = gate.capture_ticket()
        gate.enter(ticket); gate.leave()
        value.start_updates()  # Ordinary already-active work needs no spent grant.
        with pytest.raises(writers.WritersQuiescing):
            value.admit_requests()
        with pytest.raises(writers.WritersQuiescing):
            gate.resume()
        original_binding = gate._parent_control
        gate._parent_control = None
        try:
            with pytest.raises(writers.WritersQuiescing): gate.capture_ticket()
        finally:
            gate._parent_control = original_binding
        pipes.parent_write.close()  # Actual parent EOF, never read-side close as unblock.
        await asyncio.wait_for(stopping.wait(), 1)
        await asyncio.to_thread(binding.finish_io, 1)
        assert binding.task is task and binding.retired
    asyncio.run(scenario())


def test_real_retained_sql_cohort_cannot_mint_initial_grant(tmp_path, monkeypatch, pipes):
    from backend.tests.test_runtime_sql_lifetime import cohort
    generator = cohort.__wrapped__(tmp_path, monkeypatch)
    actual = next(generator)
    try:
        binding = writers.ParentControlBinding(pipes.input, pipes.output)
        writers.RuntimeWriterGate(parent_control=binding)
        pipes.parent_write.write(b'TPC1|1|BIND\n'); binding.bind_input()
        binding.attach_runtime(actual.runtime)
        actual.runtime._parent_control = binding
        actual.runtime.request_writers = binding.gate
        actual.runtime.standby = actual.runtime.request_barrier.paused = True
        actual.running = False
        binding.pin_initial()
        assert type(actual.runtime) is api.Runtime
        assert type(actual.runtime.request_writers) is writers.RuntimeWriterGate
        assert type(actual.runtime.request_barrier) is api.RequestBarrier
        asyncio.run(actual.runtime.quiesce_writers(timeout=2))
        record = actual.runtime._sql_handoff
        assert record is not None and record.members and record.readings.members
        with pytest.raises(writers.WritersQuiescing):
            binding.require_initial()
        assert actual.runtime._sql_handoff is record and binding.grant is binding.task is None
    finally:
        with pytest.raises(StopIteration):
            next(generator)


def test_partial_owner_is_retained_before_service_constructor_failure(monkeypatch):
    error = OSError('authored-constructor-error')
    seen = []
    class PartialOwner:
        def __init__(self, *a, **kw):
            self.stream = io.BytesIO(b'actual retained private stream')
            seen.append(self)
            raise error
    monkeypatch.setattr(host, 'OwnedProcess', PartialOwner)
    service = host.Service.__new__(host.Service)
    with pytest.raises(OSError) as caught:
        host.Service.__init__(service, 'Owned API', ['authored-only'], cwd='.', env={},
            log=SimpleNamespace(write=lambda *a, **k: None), parent_control=True)
    assert caught.value is error and service.owner is seen[0]
    assert service._parent_errors[0] is error and not service.owner.stream.closed
    for operation in (service.stop, lambda: service.wait_ready(threading.Event(), .01)):
        with pytest.raises(host.HostError): operation()
    assert not service.owner.stream.closed
    service.owner.stream.close()  # Known authored stand-in only.


def test_no_decoded_parent_command_cannot_mint_an_activation_task(pipes):
    async def scenario():
        binding = writers.ParentControlBinding(pipes.input, pipes.output)
        writers.RuntimeWriterGate(parent_control=binding)
        pipes.parent_write.write(b'TPC1|1|BIND\n'); binding.bind_input()
        initial_runtime(binding, pipes.directory)
        ended = asyncio.Event()
        async def forbidden(grant): pytest.fail('No actual activation input was received')
        binding.start(18767, forbidden, ended.set)
        assert await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read) == b'TPC1|1|BOUND|18767\n'
        binding._schedule(None, forbidden)
        assert binding.grant is binding.task is None
        assert await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read) == b'TPC1|2|REFUSED|binding\n'
        pipes.parent_write.close()
        await asyncio.to_thread(binding.finish_io, 1)
        closed = writers.RuntimeWriterGate(closed_candidate=True)
        with pytest.raises(writers.WritersQuiescing): closed.resume(parent_grant=object())
    asyncio.run(scenario())


def test_partial_popen_and_actual_liveness_pipe_retained_without_retry(monkeypatch):
    error = OSError('authored-partial-popen')
    seen = []
    class PartialPopen:
        def __init__(self, *a, **kw):
            self.stream = io.BytesIO(b'actual partial creation resource')
            seen.append(self)
            raise error
        def poll(self): pytest.fail('Queried unknown partial process')
    monkeypatch.setattr(owned.subprocess, 'Popen', PartialPopen)
    owner = owned.OwnedProcess.__new__(owned.OwnedProcess)
    with pytest.raises(OSError) as caught:
        owned.OwnedProcess.__init__(owner, ['authored-only'], env={},
            independent_session=True, parent_control=True)
    assert caught.value is error and owner.process is seen[0] and owner._parent_errors == [error]
    for operation in (owner.poll, owner.stop, owner.close_streams):
        with pytest.raises(RuntimeError): operation()
    assert not owner.process.stream.closed and owner._control is not None
    # PartialPopen never invokes a Popen superclass/native spawn. The exact
    # test-created empty Job (Windows) and pipe may therefore end here; this
    # is not a production retry or evidence of native descendant cleanup.
    try:
        os.close(owner._control)
        owner._control = None
        owner.process.stream.close()
        if owner.tree is not None:
            owner.tree.close()
    except BaseException as cleanup_error:
        _RETAINED_CONSTRUCTOR_CLEANUP_FAILURES.append((owner, cleanup_error))
        raise


def test_actual_stream_close_fault_is_attempted_once_and_original_resource_stays_owned():
    error = OSError('authored-close-failure')
    class FailedClose(io.BytesIO):
        attempts = 0
        def close(self):
            self.attempts += 1
            raise error
    stream = FailedClose(b'authored actual open stream')
    owner = owned.OwnedProcess.__new__(owned.OwnedProcess)
    owner._parent_control = owner._parent_constructed = owner._parent_stopped = True
    owner._parent_errors, owner._parent_closed, owner._parent_io_threads = [], [], ()
    owner.process = SimpleNamespace(stdin=stream, stdout=None, stderr=None)
    try:
        with pytest.raises(OSError) as first: owner.close_streams()
        assert first.value is error
        with pytest.raises(RuntimeError) as second: owner.close_streams()
        assert second.value.__cause__ is error
        assert stream.attempts == 1 and not stream.closed
        assert owner._parent_closed == [stream] and owner._parent_errors == [error]
    finally:
        io.BytesIO.close(stream)  # Explicit cleanup of this known authored test resource.


def test_actual_asgi_parent_standby_blocks_options_http_activation_and_ws_before_status(pipes, monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    monkeypatch.setenv('PROXY_TRANSCRIPT_STANDBY', '1')
    binding = writers.ParentControlBinding(pipes.input, pipes.output)
    writers.RuntimeWriterGate(parent_control=binding)
    pipes.parent_write.write(b'TPC1|1|BIND\n'); binding.bind_input()
    value = initial_runtime(binding, pipes.directory)
    value.status = lambda: pytest.fail('Closed WS reached status/store work')
    monkeypatch.setattr(api, 'runtime', value, raising=False)
    monkeypatch.setattr(api.app, 'middleware_stack', None)
    monkeypatch.setattr(api.app, 'user_middleware', list(api.app.user_middleware))
    old_lifespan = api.app.router.lifespan_context
    app = api.parent_control_app(binding)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:18767') as client:
            assert (await client.get('/api/health')).status_code == 200
            assert (await client.options('/api/capture/start', headers={'Origin':'http://127.0.0.1:3000',
                'Access-Control-Request-Method':'POST'})).status_code == 503
            assert (await client.post('/api/runtime/activate', json={}, headers={'X-Proxy-Transcript':'update'})).status_code == 503
    try:
        asyncio.run(scenario())
        client = TestClient(app, base_url='http://127.0.0.1:18767')
        with pytest.raises(Exception) as refused:
            with client.websocket_connect('/api/ws', headers={'Host':'127.0.0.1:18767','Origin':'http://127.0.0.1:3000'}) as websocket:
                websocket.receive_json()
        assert getattr(refused.value, 'code', None) == 1013
        assert binding.grant is binding.task is None and value.standby
    finally:
        api.app.router.lifespan_context = old_lifespan
        api.app.state._state.pop('_parent_control', None)


@pytest.mark.parametrize('arguments,port', [([], 8766), (['--standby'], 8766),
    (['--standby', '--port', '18767'], 18767), (['--port', '0', '--shutdown-stdin'], 0)])
def test_existing_ordinary_main_contract_with_parent_control(arguments, port, monkeypatch, capsys):
    from backend.tests.test_runtime_bundle import main_lifecycle, test_ordinary_main_keeps_owned_socket_readiness_and_source_standby
    lifecycle = main_lifecycle.__wrapped__(monkeypatch)
    assert lifecycle.main is main
    test_ordinary_main_keeps_owned_socket_readiness_and_source_standby(lifecycle, monkeypatch, capsys, arguments, port)


def test_service_uses_real_binary_pipes_and_confirms_threads_before_stream_close(pipes, monkeypatch):
    stderr_read, stderr_write = os.pipe()
    stderr_stream = io.FileIO(stderr_read, 'rb')
    ended, stop = threading.Event(), threading.Event()
    order = []
    def child():
        try:
            assert writers.read_parent_frame(pipes.input) == b'TPC1|1|BIND\n'
            writers.write_parent_frame(pipes.output, b'TPC1|1|BOUND|18767\n')
            assert writers.read_parent_frame(pipes.input) == b'TPC1|2|ACTIVATE-IDLE\n'
            writers.write_parent_frame(pipes.output, b'TPC1|2|ACTIVE\n')
            assert stop.wait(2)
        finally:
            pipes.output.close()
            os.close(stderr_write)
            ended.set()
    thread = threading.Thread(target=child)
    class AuthoredOwner:
        def __init__(self, *a, **kw):
            assert kw['parent_control'] is True and kw['text'] is False
            self.process = SimpleNamespace(stdin=pipes.parent_write, stdout=pipes.parent_read, stderr=stderr_stream)
        def stop(self, timeout):
            order.append('separate-liveness-stop')
            assert not self.process.stdin.closed
            stop.set(); thread.join(timeout)
            assert ended.is_set()
        def close_streams(self):
            assert all(not worker.is_alive() for worker in self._parent_io_threads)
            order.append('close-after-actual-io-exit')
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr): stream.close()
    monkeypatch.setattr(host, 'OwnedProcess', AuthoredOwner)
    service = host.Service.__new__(host.Service)
    thread.start()
    try:
        host.Service.__init__(service, 'Owned API', ['authored-only'], cwd='.', env={},
            log=SimpleNamespace(write=lambda *a, **k: None), parent_control=True)
        assert service.wait_ready(threading.Event(), 1) == {'ready': True, 'port': 18767}
        assert service.activate_idle(threading.Event(), 1) == {'active': True}
        service.stop()
        assert order == ['separate-liveness-stop', 'close-after-actual-io-exit']
    finally:
        stop.set(); thread.join(2)
        if not stderr_stream.closed: stderr_stream.close()


def test_foreign_task_is_refused_while_designated_task_then_actual_sql_workers_finish_once(tmp_path, monkeypatch, pipes):
    from backend.tests.test_runtime_sql_lifetime import cohort
    generator = cohort.__wrapped__(tmp_path, monkeypatch)
    actual = next(generator)
    async def scenario():
        binding = writers.ParentControlBinding(pipes.input, pipes.output)
        gate = writers.RuntimeWriterGate(parent_control=binding)
        pipes.parent_write.write(b'TPC1|1|BIND\n'); binding.bind_input()
        value = actual.runtime
        assert type(value) is api.Runtime
        value._parent_control = binding; binding.attach_runtime(value)
        value.request_writers = gate
        assert type(value.request_barrier) is api.RequestBarrier
        value.standby = value.request_barrier.paused = True
        actual.running = False
        old_updates = value.start_updates
        value.start_updates = lambda **options: old_updates()
        binding.pin_initial()
        entered, release, stopping = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def designated(grant):
            entered.set(); await release.wait()
            await value.activate_handoff(api.CaptureHandoff(running=False), writers=True, parent_grant=grant)
        binding.start(18767, designated, stopping.set)
        try:
            assert await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read) == b'TPC1|1|BOUND|18767\n'
            pipes.parent_write.write(b'TPC1|2|ACTIVATE-IDLE\n')
            await asyncio.wait_for(entered.wait(), 1)
            before = list(actual.calls)
            foreign = asyncio.create_task(value.activate_handoff(api.CaptureHandoff(running=False),
                writers=True, parent_grant=binding.grant))
            with pytest.raises(writers.WritersQuiescing): await foreign
            assert not binding.task.done() and not release.is_set() and actual.calls == before
            assert not binding.active and not gate._accepting and binding._pools_step is None
            release.set(); await asyncio.wait_for(asyncio.shield(binding.task), 2)
            assert await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read) == b'TPC1|2|ACTIVE\n'
            actual.healthy()
            for record in (binding._pools_step, binding._admit_step):
                assert record.complete and record.entered and not record.active
                assert not record.thread.is_alive() and record.waiter.done() and record.error is None
            ticket = gate.capture_ticket(); gate.enter(ticket); gate.leave()
        finally:
            release.set()
            if binding.task is not None: await asyncio.wait_for(asyncio.shield(binding.task), 2)
            pipes.parent_write.close(); await asyncio.wait_for(stopping.wait(), 1)
            await asyncio.to_thread(binding.finish_io, 1)
    try: asyncio.run(scenario())
    finally:
        with pytest.raises(StopIteration): next(generator)


def test_fixed_worker_permissions_reject_other_task_thread_role_copy_and_reentry(pipes):
    async def scenario():
        binding = writers.ParentControlBinding(pipes.input, pipes.output)
        writers.RuntimeWriterGate(parent_control=binding)
        pipes.parent_write.write(b'TPC1|1|BIND\n'); binding.bind_input()
        value = initial_runtime(binding, pipes.directory)
        inside, release = threading.Event(), threading.Event()
        denied = []
        def pools():
            record = binding._pools_step
            for role, operation in [('wrong-role', value.admit_requests), ('reentry', value._resume_writer_pools)]:
                with pytest.raises(writers.WritersQuiescing):
                    operation(record.deadline, parent_grant=binding.grant, parent_step=record)
                denied.append(role)
            with pytest.raises(writers.WritersQuiescing):
                value._resume_writer_pools(record.deadline, parent_grant=binding.grant, parent_step=copy.copy(record))
            denied.append('copied-record')
            inside.set(); assert release.wait(2)
        value.capture.resume_workers = pools
        stopped = asyncio.Event()
        binding.start(18767, lambda grant: value.activate_handoff(api.CaptureHandoff(running=False),
            writers=True, parent_grant=grant), stopped.set)
        try:
            await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read)
            pipes.parent_write.write(b'TPC1|2|ACTIVATE-IDLE\n')
            assert await asyncio.to_thread(inside.wait, 1)
            record = binding._pools_step
            with pytest.raises(writers.WritersQuiescing):
                value._resume_writer_pools(record.deadline, parent_grant=binding.grant, parent_step=record)
            def foreign_thread():
                with pytest.raises(writers.WritersQuiescing):
                    value._resume_writer_pools(record.deadline, parent_grant=binding.grant, parent_step=record)
            await asyncio.to_thread(foreign_thread)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(record.waiter), .01)
            assert record.thread.is_alive() and record.active and not record.complete
            assert not record.waiter.done() and not binding.gate._accepting
            release.set(); await asyncio.wait_for(asyncio.shield(binding.task), 2)
            assert await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read) == b'TPC1|2|ACTIVE\n'
            assert not record.active and record.complete and not record.thread.is_alive()
            with pytest.raises(writers.WritersQuiescing):
                value._resume_writer_pools(record.deadline, parent_grant=binding.grant, parent_step=record)
            assert denied == ['wrong-role', 'reentry', 'copied-record']
        finally:
            release.set()
            if binding.task is not None: await asyncio.wait_for(asyncio.shield(binding.task), 2)
            pipes.parent_write.close(); await asyncio.wait_for(stopped.wait(), 1)
            await asyncio.to_thread(binding.finish_io, 1)
    asyncio.run(scenario())


def test_ordinary_http_route_fixture_succeeds_with_parent_control(monkeypatch):
    from backend.tests.test_runtime_handoff import test_runtime_activation_requires_local_action_and_ready_candidate
    test_runtime_activation_requires_local_action_and_ready_candidate(monkeypatch)


@pytest.mark.parametrize('change', ['none', 'actual-close', 'same-handle-new-lease', 'service-lease-replaced'])
def test_parent_ack_rechecks_actual_lease_object_held_handle_and_service(tmp_path, change):
    lease = host.ExclusiveFileLease(tmp_path / 'owned.lock')
    lease.acquire()
    other = host.ExclusiveFileLease(tmp_path / 'not-acquired.lock')
    value = host.DesktopHost.__new__(host.DesktopHost)
    value.lease, value.stop_requested = lease, threading.Event()
    service = host.Service.__new__(host.Service)
    service._parent_control, service._parent_lease, service._parent_lease_handle = True, lease, lease._handle
    value.services = {'Owned API': service}
    def activate(_stopping):
        if change == 'actual-close': lease.close()
        elif change == 'same-handle-new-lease':
            other._handle = lease._handle  # Explicit authored alias, not a product-race claim.
            value.lease = other
        elif change == 'service-lease-replaced': service._parent_lease = other
        return {'active': True}
    service.activate_idle = activate
    try:
        if change == 'none': assert value._activate_parent_idle('Owned API') == {'active': True}
        else:
            with pytest.raises(host.HostError): value._activate_parent_idle('Owned API')
        assert value.services['Owned API'] is service  # No reset/replacement/retry on refusal.
    finally:
        if other._handle is lease._handle: other._handle = None
        lease.close()


def test_final_admission_retirement_serializes_after_one_metadata_commit(pipes):
    async def scenario():
        binding = writers.ParentControlBinding(pipes.input, pipes.output)
        writers.RuntimeWriterGate(parent_control=binding)
        pipes.parent_write.write(b'TPC1|1|BIND\n'); binding.bind_input()
        value = initial_runtime(binding, pipes.directory)
        metadata_entered, release_metadata, retire_attempted, retired = (threading.Event() for _ in range(4))
        observed = []
        original = value._reading_registry.reopen_creation
        def metadata():
            # Authored pause at the existing metadata-only operation boundary;
            # production reopen_creation itself performs no blocking IO/SQL.
            metadata_entered.set(); assert release_metadata.wait(2)
            original()
        value._reading_registry.reopen_creation = metadata
        stopping = asyncio.Event()
        binding.start(18767, lambda grant: value.activate_handoff(api.CaptureHandoff(running=False),
            writers=True, parent_grant=grant), stopping.set)
        def retire():
            retire_attempted.set()
            binding.poison(OSError('authored-parent-loss'))
            observed.append((binding.active, binding.spent, value.request_barrier.paused))
            retired.set()
        observer = threading.Thread(target=retire)
        try:
            await asyncio.to_thread(writers.read_parent_frame, pipes.parent_read)
            pipes.parent_write.write(b'TPC1|2|ACTIVATE-IDLE\n')
            assert await asyncio.to_thread(metadata_entered.wait, 1)
            assert not binding.gate._accepting and not binding.active and value.request_barrier.paused
            observer.start()
            # These bounded test-only waits hold this test's loop turn so the
            # queued shutdown callback cannot obscure the exact lock ordering.
            assert retire_attempted.wait(1) and not retired.is_set()
            release_metadata.set()
            assert retired.wait(1)
            assert observed == [(True, True, False)]
            await asyncio.wait_for(asyncio.shield(binding.task), 2)
            with pytest.raises(writers.WritersQuiescing): binding.gate.capture_ticket()
            assert binding._admit_step.complete and not binding._admit_step.active
        finally:
            release_metadata.set()
            if observer.ident is not None: observer.join(2)
            assert not observer.is_alive()
            if binding.task is not None: await asyncio.wait_for(asyncio.shield(binding.task), 2)
            pipes.parent_write.close(); await asyncio.wait_for(stopping.wait(), 1)
            await asyncio.to_thread(binding.finish_io, 1)
    asyncio.run(scenario())
