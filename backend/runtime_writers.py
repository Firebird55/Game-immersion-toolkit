"""Request admission and actual drain for runtime handoff.

This is one producer boundary, not native process ownership or permission to
copy stores. Runtime.quiesce_writers also settles its registered background
producers before returning the existing capture handoff.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
import asyncio
import os
import queue
import stat

class WritersQuiescing(RuntimeError):
    pass


@dataclass(frozen=True, eq=False, repr=False)
class RuntimeAdmissionTicket:
    """Opaque process-local gate/epoch binding, never copy or root authority."""
    _gate: RuntimeWriterGate
    _epoch: object


_UNTICKETED = object()


def read_parent_frame(stream):
    """One bounded binary frame; EOF is distinct from a partial/invalid frame."""
    frame = bytearray()
    while len(frame) < 128:
        byte = stream.read(1)
        if type(byte) is not bytes or len(byte) > 1:
            raise WritersQuiescing('Invalid parent control stream.')
        if not byte:
            if not frame:
                return None
            raise WritersQuiescing('Incomplete parent control frame.')
        frame.extend(byte)
        if byte == b'\n':
            if any(value < 32 or value > 126 for value in frame[:-1]):
                raise WritersQuiescing('Invalid parent control encoding.')
            return bytes(frame)
    raise WritersQuiescing('Parent control frame exceeds its bound.')


def write_parent_frame(stream, frame):
    if (type(frame) is not bytes or not frame.endswith(b'\n') or not 1 < len(frame) <= 128
            or any(value < 32 or value > 126 for value in frame[:-1])):
        raise WritersQuiescing('Invalid parent control output.')
    if stream.write(frame) != len(frame):
        raise OSError('Incomplete parent control write.')
    stream.flush()


@dataclass(frozen=True, eq=False, repr=False)
class _ParentIdleGrant:
    binding: ParentControlBinding
    runtime: object
    gate: RuntimeWriterGate
    command: object


@dataclass(eq=False, repr=False)
class _ParentWorker:
    binding: object
    grant: object
    runtime: object
    gate: object
    role: str
    method: object
    deadline: float
    thread: object = None
    waiter: object = None
    launch: object = None
    start_attempted: bool = False
    active: bool = False
    entered: bool = False
    complete: bool = False
    result: object = None
    error: BaseException | None = None


class ParentControlBinding:
    """Fixed initial-idle source experiment; no copied metadata is authority.

    The reader retains its command before scheduling on the one ASGI loop.
    Actual activation/IO objects and original failures remain held on timeout.
    Retained SQL handoff and subsequent reopen operations are not supported.
    """
    def __init__(self, reader, writer, *, stream_owners=()):
        self.reader, self.writer, self.stream_owners = reader, writer, stream_owners
        self.gate = self.runtime = self.initial = self.command = self.grant = self.task = None
        self.errors = []
        self.retired = self.active = self.spent = False
        self._state = 'new'
        self._lock = threading.RLock()
        self._output = queue.Queue(maxsize=2)
        self._reader_thread = self._writer_thread = None
        self._loop = self._shutdown = self._loop_thread = None
        self._activation_entered = False
        self._pools_step = self._admit_step = None
        self._pools_method = self._admit_method = None
        for stream in (reader, writer):
            if stream.isatty() or not stat.S_ISFIFO(os.fstat(stream.fileno()).st_mode):
                raise WritersQuiescing('Parent control requires actual binary pipes.')
            os.set_inheritable(stream.fileno(), False)
        if reader is writer:
            raise WritersQuiescing('Parent control endpoints must be distinct.')

    def bind_input(self):
        if self._state != 'new' or read_parent_frame(self.reader) != b'TPC1|1|BIND\n':
            raise WritersQuiescing('Expected the initial parent bind frame.')
        self._state = 'input-bound'

    def attach_runtime(self, runtime):
        if self.runtime is not None or self._state != 'input-bound' or self.gate is None:
            raise WritersQuiescing('Parent Runtime ownership changed.')
        self.runtime = runtime  # Before any fallible service constructor.

    def pin_initial(self):
        r = self.runtime
        self.initial = (r.capture, r.request_barrier, r.request_barrier._idle,
            r._reading_registry, r._handoff_lock, r._handoff_drains, self.gate._epoch)
        self.require_initial()
        self._pools_method = type(r)._resume_writer_pools.__get__(r, type(r))
        self._admit_method = type(r).admit_requests.__get__(r, type(r))

    def require_initial(self):
        r, f = self.runtime, self.initial
        if (r is None or f is None or getattr(r, '_parent_control', None) is not self
                or r.request_writers is not self.gate or self.gate._parent_control is not self
                or r.capture is not f[0] or r.request_barrier is not f[1] or r.request_barrier._idle is not f[2]
                or r._reading_registry is not f[3] or r._handoff_lock is not f[4]
                or r._handoff_drains is not f[5] or r._handoff_drains or self.gate._epoch is not f[6]
                or r._sql_handoff is not None or r._writer_handoff or r._quiesce_task is not None
                or r._request_stop is not None or r._handoff_state is not None or not r.standby
                or r._updates_started or r.capture.snapshot().running is not False
                or self.gate._accepting or self.gate._active
                or r.request_barrier.paused is not True or r.request_barrier._active
                or not r.request_barrier._idle.is_set()):
            raise WritersQuiescing('Parent activation requires the genuine initial idle cohort.')

    def _require_grant_locked(self, grant, runtime):
        if (self.retired or self.spent or grant is not self.grant or type(grant) is not _ParentIdleGrant
                or grant.binding is not self or grant.runtime is not runtime or runtime is not self.runtime
                or grant.gate is not self.gate or runtime.request_writers is not self.gate
                or self.gate._parent_control is not self or grant.command is not self.command
                or not isinstance(self.task, asyncio.Task) or self.task.done() or self._state != 'activating'):
            raise WritersQuiescing('Parent transition grant is unavailable.')

    def require_grant(self, grant, runtime):
        with self._lock:
            self._require_grant_locked(grant, runtime)
            try:
                loop, task = asyncio.get_running_loop(), asyncio.current_task()
            except RuntimeError:
                loop = task = None
            if loop is not self._loop or task is not self.task or threading.current_thread() is not self._loop_thread:
                raise WritersQuiescing('Only the retained activation Task may perform this transition.')

    def begin_activation(self, grant, runtime):
        self.require_grant(grant, runtime)
        self.require_initial()  # Recheck after a held Task obtains its operation lock.
        with self._lock:
            self._require_grant_locked(grant, runtime)
            if self._activation_entered:
                raise WritersQuiescing('Parent activation entry was already used.')
            self._activation_entered = True

    def _prepare_worker(self, grant, runtime, deadline, role):
        self.require_grant(grant, runtime)
        if not self._activation_entered:
            raise WritersQuiescing('Parent activation has not entered its actual operation.')
        if role == 'pools':
            if self._pools_step is not None:
                raise WritersQuiescing('Parent pool operation was already retained.')
            method = self._pools_method
        elif role == 'admit':
            if (self._admit_step is not None or self._pools_step is None
                    or not self._pools_step.complete or self._pools_step.error is not None
                    or self._pools_step.thread.is_alive()):
                raise WritersQuiescing('Parent pool operation has not actually finished.')
            method = self._admit_method
        else:
            raise WritersQuiescing('Unsupported parent operation.')
        record = _ParentWorker(self, grant, runtime, self.gate, role, method, deadline)
        if role == 'pools': self._pools_step = record
        else: self._admit_step = record
        record.launch = asyncio.Event()

        def execute():
            try:
                remaining = max(0, deadline-time.monotonic())
                if not self._lock.acquire(timeout=min(threading.TIMEOUT_MAX, remaining)):
                    raise TimeoutError('Parent worker metadata is still owned.')
                try:
                    self._require_grant_locked(grant, runtime)
                    if threading.current_thread() is not record.thread or not record.start_attempted or record.complete:
                        raise WritersQuiescing('Parent worker creation identity changed.')
                    record.active = True
                finally:
                    self._lock.release()
                record.result = method(deadline, parent_grant=grant, parent_step=record)
            except BaseException as error:
                record.error = error  # Original worker failure, never formatted or retried.
            finally:
                # This exact Thread is the only result/completion producer.
                # Retire permission before notification and before Thread exit.
                record.active = False
                record.complete = True

        async def wait_actual_worker():
            await record.launch.wait()
            while not record.complete or record.thread.is_alive():
                await asyncio.sleep(.005)
            if record.error is not None:
                raise record.error
            return record.result

        record.thread = threading.Thread.__new__(threading.Thread)
        threading.Thread.__init__(record.thread, target=execute, name='parent-'+role+'-operation', daemon=False)
        record.waiter = asyncio.create_task(wait_actual_worker(), name='parent-'+role+'-waiter')
        return record

    def prepare_pools(self, grant, runtime, deadline):
        return self._prepare_worker(grant, runtime, deadline, 'pools')

    def prepare_admission(self, grant, runtime, deadline):
        return self._prepare_worker(grant, runtime, deadline, 'admit')

    def launch_worker(self, grant, runtime, record):
        self.require_grant(grant, runtime)
        if (type(record) is not _ParentWorker or record.binding is not self or record.grant is not grant
                or record.start_attempted or (record is not self._pools_step and record is not self._admit_step)):
            raise WritersQuiescing('Parent operation cannot be launched again.')
        record.start_attempted = True
        try:
            record.thread.start()
        except BaseException as error:
            if record.error is None: record.error = error
            self.poison(error)  # Actual creation object retained; no retry/query inference.
            raise
        finally:
            record.launch.set()

    def _require_worker_locked(self, grant, runtime, record, role):
        self._require_grant_locked(grant, runtime)
        expected = self._pools_step if role == 'pools' else self._admit_step if role == 'admit' else None
        method = self._pools_method if role == 'pools' else self._admit_method if role == 'admit' else None
        if (type(record) is not _ParentWorker or record is not expected or record.binding is not self
                or record.grant is not grant or record.runtime is not runtime or record.gate is not self.gate
                or record.method is not method or method.__self__ is not runtime
                or not isinstance(record.waiter, asyncio.Task) or record.waiter.done()
                or threading.current_thread() is not record.thread or not record.active or record.complete):
            raise WritersQuiescing('Parent worker execution ownership differs.')

    def require_worker(self, grant, runtime, record, role):
        deadline = record.deadline if type(record) is _ParentWorker else time.monotonic()
        if not self._lock.acquire(timeout=min(threading.TIMEOUT_MAX, max(0, deadline-time.monotonic()))):
            raise TimeoutError('Parent worker metadata remains owned.')
        try:
            self._require_worker_locked(grant, runtime, record, role)
            if record.entered:
                raise WritersQuiescing('Parent worker method entry was already used.')
            record.entered = True
        finally:
            self._lock.release()

    def lock_admission(self, grant, runtime, record, deadline):
        # Caller already owns the actual gate condition: gate -> parent order.
        if not self._lock.acquire(timeout=min(threading.TIMEOUT_MAX, max(0, deadline-time.monotonic()))):
            raise TimeoutError('Parent admission metadata remains owned.')
        try:
            self._require_worker_locked(grant, runtime, record, 'admit')
            if not record.entered:
                raise WritersQuiescing('Parent admission method entry is missing.')
            if time.monotonic() > deadline:
                raise TimeoutError('Parent admission deadline expired.')
        except BaseException:
            self._lock.release()
            raise

    def require_work(self, runtime=None):
        with self._lock:
            if (self.retired or not self.active or self._state != 'active' or self.runtime is None
                    or getattr(self.runtime, '_parent_control', None) is not self
                    or self.runtime.request_writers is not self.gate
                    or (runtime is not None and runtime is not self.runtime)):
                raise WritersQuiescing('Parent-controlled work is not admitted.')

    def poison(self, error):
        with self._lock:
            if not self.errors or self.errors[-1] is not error:
                self.errors.append(error)
            self.retired = True
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_on_loop)
            except BaseException as dispatch_error:
                self.errors.append(dispatch_error)

    def _stop_on_loop(self):
        self.gate.stop_admission()
        self._shutdown()

    def _emit(self, frame):
        try:
            self._output.put_nowait(frame)
        except BaseException as error:
            self.poison(error)
            raise

    def start(self, port, action, shutdown):
        self.require_initial()
        if self._state != 'input-bound' or type(port) is not int or not 1024 < port < 65536 or port in (3000, 8766):
            raise WritersQuiescing('Parent listener binding is unavailable.')
        self._loop, self._shutdown, self._state = asyncio.get_running_loop(), shutdown, 'bound'
        self._loop_thread = threading.current_thread()

        def write():
            try:
                while True:
                    frame = self._output.get()
                    if frame is None:
                        return
                    write_parent_frame(self.writer, frame)
            except BaseException as error:
                self.poison(error)

        def read():
            try:
                while True:
                    frame = read_parent_frame(self.reader)
                    with self._lock:
                        if frame != b'TPC1|2|ACTIVATE-IDLE\n' or self.command is not None or self.retired:
                            raise WritersQuiescing('Parent control is closed or out of sequence.')
                        self.command = command = object()
                    self._loop.call_soon_threadsafe(self._schedule, command, action)
            except BaseException as error:
                self.poison(error)

        self._writer_thread = threading.Thread(target=write, name='parent-control-output', daemon=True)
        self._reader_thread = threading.Thread(target=read, name='parent-control-input', daemon=True)
        self._writer_thread.start()
        self._emit(b'TPC1|1|BOUND|' + str(port).encode('ascii') + b'\n')
        self._reader_thread.start()

    def finish_io(self, timeout):
        deadline = time.monotonic()+timeout
        try:
            self._output.put_nowait(None)
            for thread in (self._reader_thread, self._writer_thread):
                if thread is not None:
                    thread.join(max(0, deadline-time.monotonic()))
                    if thread.is_alive():
                        raise TimeoutError('Parent control IO remains owned; no stream was closed.')
        except BaseException as error:
            self.poison(error)
            raise
        # These are inherited process endpoints; this method establishes only
        # actual reader/writer completion, never closes them to unblock IO.

    def _schedule(self, command, action):
        try:
            self.require_initial()  # Before grant/task or opener effects.
            if (type(command) is not object or command is not self.command or self.retired
                    or self._state != 'bound' or self.task is not None):
                raise WritersQuiescing('Parent activation command changed.')
            grant = self.grant = _ParentIdleGrant(self, self.runtime, self.gate, command)
            launch = asyncio.Event()

            async def activate():
                await launch.wait()  # Even an eager task cannot outrun retention.
                try:
                    self.require_grant(grant, self.runtime)
                    await action(grant)
                    self.require_work(self.runtime)
                    self._emit(b'TPC1|2|ACTIVE\n')
                except BaseException as error:
                    self.poison(error)
                    self._emit(b'TPC1|2|REFUSED|activation\n')

            self._state = 'activating'
            self.task = asyncio.create_task(activate(), name='parent-idle-activation')
            launch.set()
        except BaseException as error:
            self.poison(error)
            self._emit(b'TPC1|2|REFUSED|binding\n')


class QuiesceableExecutor(Executor):
    """Keep actual worker/callback ownership across a bounded handoff wait."""
    def __init__(self, max_workers, *, thread_name_prefix=''):
        self._options = {'max_workers': max_workers, 'thread_name_prefix': thread_name_prefix}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(**self._options)
        self._accepting = True
        self._closed = False
        self._drained = self._drain_error = self._drain_thread = None

    def submit(self, function, /, *args, **kwargs):
        with self._lock:
            if not self._accepting:
                raise WritersQuiescing('This runtime worker is quiescing.')
            return self._pool.submit(function, *args, **kwargs)

    def shutdown(self, wait=True, *, cancel_futures=False):
        with self._lock:
            self._accepting = False
            self._closed = True
            pool = self._pool
        pool.shutdown(wait=wait, cancel_futures=cancel_futures)

    def drain(self):
        """Wait for actual workers/callbacks; cancelling a caller does not stop them."""
        self.quiesce(None)

    def quiesce(self, timeout):
        with self._lock:
            if self._drained is None:
                self._accepting = False
                event = self._drained = threading.Event()
                pool = self._pool
                def drain():
                    try:
                        # Worker exit follows its Future callbacks. A done
                        # future or cancelled asyncio waiter alone is weaker.
                        pool.shutdown(wait=True, cancel_futures=False)
                    except BaseException as error:
                        self._drain_error = error
                    finally:
                        event.set()
                self._drain_thread = threading.Thread(target=drain, name='runtime-worker-drain', daemon=True)
                self._drain_thread.start()
            event = self._drained
        if not event.wait(None if timeout is None else min(threading.TIMEOUT_MAX, max(0, timeout))):
            raise TimeoutError('Runtime worker/callback cleanup has not finished.')
        if self._drain_error is not None:
            raise TimeoutError('Runtime worker cleanup could not be confirmed.') from self._drain_error

    def resume(self):
        with self._lock:
            if self._closed:
                raise RuntimeError('This runtime worker has been permanently closed.')
            if self._drained is None:
                return
            if not self._drained.is_set() or self._drain_error is not None:
                raise TimeoutError('Runtime worker cleanup is still incomplete; retry recovery.')
            self._pool = ThreadPoolExecutor(**self._options)
            self._accepting = True
            self._drained = self._drain_error = self._drain_thread = None


class RuntimeWriterGate:
    def __init__(self, *, closed_candidate=False, parent_control=None):
        if type(closed_candidate) is not bool:
            raise TypeError('Closed candidate mode must be a boolean.')
        self._condition = threading.Condition()
        self._closed_candidate = closed_candidate
        self._accepting = not closed_candidate
        self._active = 0
        self._epoch = object()
        self._parent_control = self._parent_pin = parent_control
        if parent_control is not None:
            if type(parent_control) is not ParentControlBinding or closed_candidate or parent_control.gate is not None:
                raise WritersQuiescing('Parent control gate binding differs.')
            parent_control.gate = self
            self._accepting = False

    @property
    def closed_candidate(self):
        return self._closed_candidate

    def require_reopenable(self):
        if self._parent_control is not self._parent_pin:
            raise WritersQuiescing('Parent gate binding changed.')
        if self._closed_candidate:
            raise WritersQuiescing('This experimental candidate cannot admit work or activate.')

    def capture_ticket(self):
        with self._condition:
            self.require_reopenable()
            if self._parent_control is not None:
                self._parent_control.require_work()
            if not self._accepting:
                raise WritersQuiescing('Runtime handoff is stopping writers. Retry after activation or recovery.')
            return RuntimeAdmissionTicket(self, self._epoch)

    def enter(self, ticket=_UNTICKETED):
        with self._condition:
            self.require_reopenable()
            if self._parent_control is not None:
                self._parent_control.require_work()
            if not self._accepting:
                raise WritersQuiescing('Runtime handoff is stopping writers. Retry after activation or recovery.')
            if ticket is not _UNTICKETED and (type(ticket) is not RuntimeAdmissionTicket
                    or ticket._gate is not self or ticket._epoch is not self._epoch):
                raise WritersQuiescing('This runtime operation belongs to a retired admission epoch.')
            self._active += 1

    def leave(self):
        with self._condition:
            if not self._active:
                raise RuntimeError('Unbalanced runtime request writer scope.')
            self._active -= 1
            self._condition.notify_all()

    def stop_admission(self):
        with self._condition:
            self._accepting = False
            self._epoch = object()  # Retire queued pre-stop work even after resume.

    def wait_drained(self, timeout):
        deadline = time.monotonic() + max(0, timeout)
        with self._condition:
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Active runtime requests have not finished; handoff is unavailable.')
                self._condition.wait(min(threading.TIMEOUT_MAX, remaining))

    def resume(self, *, parent_grant=None):
        with self._condition:
            self.require_reopenable()
            if self._parent_control is not None:
                raise WritersQuiescing('Direct parent gate reopening is not supported.')
            self._accepting = True


class RuntimeWriterMiddleware:
    # These operations do not mutate stores, or are the explicit local handoff
    # control path. In particular, reading/lookup/status/setup GETs are *not*
    # assumed read-only: they may publish caches or finish native pickers.
    _control = {'/api/health', '/api/runtime/ready', '/api/runtime/quiesce', '/api/runtime/activate'}

    def __init__(self, app, current_runtime):
        self.app, self.current_runtime = app, current_runtime

    async def __call__(self, scope, receive, send):
        current = self.current_runtime()
        gate = getattr(current, 'request_writers', None)
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        try:
            parent = getattr(current, '_parent_control', None)
            if parent is None and getattr(gate, '_parent_control', None) is not None:
                raise WritersQuiescing('Parent middleware binding is missing.')
            if parent is not None:
                if type(parent) is not ParentControlBinding or parent.runtime is not current or parent.gate is not gate or gate._parent_control is not parent:
                    raise WritersQuiescing('Parent middleware binding changed.')
                if scope.get('path') == '/api/runtime/activate':
                    raise WritersQuiescing('Parent activation requires its retained input command.')
            pinned = getattr(current, '_candidate_writer_gate', None)
            if pinned is not None and (type(pinned) is not RuntimeWriterGate
                    or not pinned.closed_candidate or gate is not pinned):
                raise WritersQuiescing('Experimental candidate gate ownership changed.')
            controls = {'/api/health', '/api/runtime/ready'} if gate is not None and gate.closed_candidate else self._control
            if parent is not None and not parent.active:
                controls = {'/api/health', '/api/runtime/ready'}
            bypass = scope.get('path') in controls or gate is None
            if not bypass:
                gate.enter()
        except WritersQuiescing as error:
            from starlette.responses import JSONResponse
            await JSONResponse({'detail': str(error)}, status_code=503, headers={'Retry-After': '1'})(scope, receive, send)
            return
        if bypass:
            await self.app(scope, receive, send)
            return
        try:
            # Pure ASGI scope includes body/stream completion, unlike a
            # call_next middleware that can return before response work ends.
            await self.app(scope, receive, send)
        finally:
            gate.leave()
