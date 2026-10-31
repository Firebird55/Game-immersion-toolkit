"""Retained suspended creation ordering; Windows cases use an authored leaf only."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from backend import windows_preparation_process as module


class Kernel:
    def __init__(self):
        self.error, self.events, self.owner = 122, [], None
        self.live, self.previous, self.member = True, 1, True
        self.create_ok, self.unexpected_outputs, self.query_error = True, False, None
        self.close_errors = {}
        self.timeout = False
        self.processes, self.threads = set(), set()
        self.expected_flags = 0x08080404

    def InitializeProcThreadAttributeList(self, attributes, count, flags, size):
        assert count == 1 and flags == 0
        if attributes is None:
            size._obj.value = 128; self.error = 122
            return 0
        self.attributes = attributes
        self.events.append('attributes-initialized')
        return 1

    def UpdateProcThreadAttribute(self, attributes, flags, attribute, jobs, size, previous, result):
        assert attributes is self.attributes and flags == 0 and attribute == 0x2000d
        assert list(jobs._obj) == [100] and size == ctypes.sizeof(wintypes.HANDLE)
        assert previous is None and result is None
        self.events.append('job-list-set')
        return 1

    def DeleteProcThreadAttributeList(self, attributes):
        assert attributes is self.attributes
        self.events.append('attributes-deleted')

    def CreateProcessW(self, image, command, process_security, thread_security, inherit, flags, env, cwd, startup, information):
        child = self.owner.created_children[-1]
        assert information._obj is child._information
        assert not information._obj.process and not information._obj.thread
        assert process_security is None and thread_security is None and inherit is False
        assert flags == self.expected_flags
        assert startup._obj.startup.cb == ctypes.sizeof(module._StartupInfoEx)
        assert startup._obj.attributes == ctypes.addressof(self.attributes)
        assert startup._obj.startup.flags == 0
        assert all(getattr(startup._obj.startup, name) is None for name in ('stdin', 'stdout', 'stderr'))
        assert image == sys.executable and command.value.startswith('"' + image + '"' if ' ' in image else image)
        assert 'OWNED=漢字' in ''.join(env) and Path(cwd).is_absolute()
        self.events.append('created-into-registered-record')
        if self.create_ok or self.unexpected_outputs:
            process = 201 + len(self.processes)*100
            information._obj.process, information._obj.thread = process, process+1
            self.processes.add(process); self.threads.add(process+1)
        self.error = 2
        return self.create_ok

    def IsProcessInJob(self, process, job, member):
        assert process in self.processes and job == 100
        self.events.append('membership-checked')
        if self.query_error is not None:
            self.error = self.query_error
            return 0
        member._obj.value = self.member
        return 1

    def ResumeThread(self, handle):
        assert handle in self.threads
        self.events.append('resume')
        return self.previous

    def WaitForSingleObject(self, handle, timeout):
        assert handle in self.processes
        self.events.append('wait-process')
        return 258 if self.live else 0

    def TerminateProcess(self, handle, status):
        assert handle in self.processes and status == 1
        self.events.append('terminate-created-process')
        if not self.timeout:
            self.live = False
        return 1

    def QueryInformationJobObject(self, handle, kind, pointer, size, length):
        assert handle == 100 and not self.live
        if kind == 3:
            pointer._obj.assigned = pointer._obj.count = 0
        else:
            pointer._obj.active_processes = 0
        self.events.append('job-drained')
        return 1

    def CloseHandle(self, handle):
        self.events.append(('close', handle))
        if handle in self.close_errors:
            self.error = self.close_errors[handle]
            return 0
        return 1

    def GetHandleInformation(self, handle, flags):
        self.events.append(('flags', handle))
        flags._obj.value = 2
        return 1


@pytest.fixture
def owned(monkeypatch):
    kernel = Kernel()
    owner = module.WindowsPreparationProcess.__new__(module.WindowsPreparationProcess)
    owner.kernel, owner._handle, owner._created_children = kernel, 100, []
    owner._ownership_unconfirmed = owner._admission_closed = False
    kernel.owner = owner
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: kernel.error, raising=False)
    monkeypatch.setattr(ctypes, 'WinError', lambda code: OSError(code, 'authored native failure'), raising=False)
    return owner, kernel


def create(owner, tmp_path):
    return owner.create_suspended([sys.executable, '-I', 'owned writer 漢字.py'], cwd=tmp_path, env={'OWNED': '漢字'})


def test_creation_record_and_job_are_retained_before_one_resume_then_signal_before_close(owned, tmp_path):
    owner, kernel = owned
    child = create(owner, tmp_path)
    assert owner.created_children == (child,)
    assert (child.process_handle, child.thread_handle) == (201, 202)
    assert kernel.events[:4] == ['attributes-initialized', 'job-list-set', 'created-into-registered-record', 'membership-checked']
    assert kernel.events[-1] == 'attributes-deleted' and 'resume' not in kernel.events
    with pytest.raises(OSError, match='exit must be confirmed'):
        owner.close()
    assert not any(isinstance(event, tuple) and event[0] == 'close' for event in kernel.events)
    # Early close freezes further admission. Use a fresh owner for resume below.
    assert not child.closed and owner.handle == 100


def test_detached_mode_keeps_registration_job_no_inheritance_and_signal_before_close(owned, tmp_path):
    owner, kernel = owned
    kernel.expected_flags = 0x0008040c
    child = owner.create_suspended([sys.executable, '-I', 'owned writer 漢字.py'], cwd=tmp_path,
        env={'OWNED': '漢字'}, detached_console=True)
    assert owner.created_children == (child,) and not child.resumed
    assert kernel.events[:4] == ['attributes-initialized', 'job-list-set', 'created-into-registered-record', 'membership-checked']
    child.resume_once()
    with pytest.raises(OSError, match='exit must be confirmed'): owner.close()
    assert not any(isinstance(event, tuple) and event[0] == 'close' for event in kernel.events)
    owner.terminate(timeout=1); owner.close()
    assert child.resumed and child.exited and child.closed and owner.handle is None


@pytest.mark.parametrize('invalid', [None, 0, 1, 'detached', 0x00000008])
def test_detached_mode_rejects_non_boolean_inputs_before_native_creation(owned, tmp_path, invalid):
    owner, kernel = owned
    with pytest.raises(ValueError, match='explicit Boolean'):
        owner.create_suspended([sys.executable], cwd=tmp_path, env={'OWNED': '漢字'}, detached_console=invalid)
    assert not owner.created_children and not kernel.events and owner.handle == 100


def test_resume_once_and_confirmed_drain_close_keep_same_creation_handles(owned, tmp_path):
    owner, kernel = owned
    child = create(owner, tmp_path)
    child.resume_once()
    assert child.resumed and kernel.events.count('resume') == 1
    with pytest.raises(OSError, match='already attempted'):
        child.resume_once()
    owner.terminate(timeout=1)
    assert child.exited and not child.closed
    owner.close()
    assert child.closed and owner.handle is None
    assert kernel.events[-3:] == [('close', 202), ('close', 201), ('close', 100)]
    assert kernel.events.index('terminate-created-process') < kernel.events.index('job-drained')
    assert kernel.events.index('job-drained') < kernel.events.index(('close', 202))
    before = list(kernel.events); owner.close()
    assert kernel.events == before


@pytest.mark.parametrize('previous', [0, 2, 0xffffffff])
def test_unexpected_suspend_count_never_causes_second_resume(owned, tmp_path, previous):
    owner, kernel = owned
    child = create(owner, tmp_path); kernel.previous = previous
    with pytest.raises(OSError): child.resume_once()
    before = list(kernel.events)
    with pytest.raises(OSError): child.resume_once()
    assert kernel.events == before and not child.resumed
    with pytest.raises(OSError): create(owner, tmp_path)


@pytest.mark.parametrize('unexpected_outputs', [False, True])
def test_failed_creation_never_adopts_unconfirmed_outputs_or_loses_registered_record(owned, tmp_path, unexpected_outputs):
    owner, kernel = owned
    kernel.create_ok, kernel.unexpected_outputs = False, unexpected_outputs
    with pytest.raises(OSError): create(owner, tmp_path)
    assert len(owner.created_children) == 1
    child = owner.created_children[0]
    assert not child.created and 'resume' not in kernel.events
    before = list(kernel.events)
    if unexpected_outputs:
        for operation in (lambda: child.process_handle, owner.close, owner.terminate):
            with pytest.raises(OSError): operation()
        assert kernel.events == before
    else:
        owner.close()
        assert kernel.events[-1] == ('close', 100)


def test_postcreation_membership_refusal_preserves_real_creation_handles_for_cleanup(owned, tmp_path):
    owner, kernel = owned; kernel.member = False
    with pytest.raises(OSError, match='selected Job'): create(owner, tmp_path)
    child, = owner.created_children
    assert child.created and (child.process_handle, child.thread_handle) == (201, 202)
    with pytest.raises(OSError): child.resume_once()
    owner.terminate(timeout=1); owner.close()
    assert child.exited and child.closed and 'resume' not in kernel.events


def test_postcreation_python_failure_keeps_creation_record_for_bounded_cleanup(owned, tmp_path, monkeypatch):
    owner, kernel = owned
    def unavailable(*_): raise ValueError('authored post-create parser failure')
    monkeypatch.setattr(kernel, 'IsProcessInJob', unavailable)
    with pytest.raises(ValueError): create(owner, tmp_path)
    child, = owner.created_children
    assert child.created and child.process_handle == 201 and child.thread_handle == 202
    with pytest.raises(OSError): child.resume_once()
    owner.terminate(timeout=1); owner.close()
    assert child.closed and 'resume' not in kernel.events


def test_attribute_cleanup_failure_cannot_lose_already_created_handles(owned, tmp_path, monkeypatch):
    owner, kernel = owned
    def unavailable(*_): raise OSError('authored attribute cleanup failure')
    monkeypatch.setattr(kernel, 'DeleteProcThreadAttributeList', unavailable)
    with pytest.raises(OSError): create(owner, tmp_path)
    child, = owner.created_children
    assert child.created and child.process_handle == 201
    with pytest.raises(OSError): child.resume_once()
    owner.terminate(timeout=1); owner.close()
    assert child.closed


def test_invalid_membership_handle_poison_blocks_query_terminate_and_close_without_reuse(owned, tmp_path):
    owner, kernel = owned; kernel.query_error = 6
    with pytest.raises(OSError): create(owner, tmp_path)
    child, = owner.created_children
    before = list(kernel.events)
    for operation in (lambda: owner.handle, lambda: child.process_handle, lambda: child.thread_handle,
                      child.resume_once, lambda: child.stop_and_wait(time.monotonic()+1), owner.close, owner.terminate):
        with pytest.raises(OSError): operation()
    assert kernel.events == before


def test_one_child_poison_blocks_every_sibling_exposure_and_native_operation(owned, tmp_path):
    owner, kernel = owned
    first = create(owner, tmp_path)
    # A second, distinct retained creation object; do not adopt or reopen IDs.
    second = create(owner, tmp_path)
    assert (second.process_handle, second.thread_handle) == (301, 302)
    owner.terminate(timeout=1)
    kernel.close_errors[202] = 6
    with pytest.raises(OSError): first.close_after_exit()
    before = list(kernel.events)
    for operation in (lambda: second.process_handle, lambda: second.thread_handle,
                      second.resume_once, lambda: second.stop_and_wait(time.monotonic()+1),
                      second.close_after_exit, owner.close, owner.terminate):
        with pytest.raises(OSError): operation()
    assert kernel.events == before
    assert not first.closed and not second.closed


@pytest.mark.parametrize('error', [6, 5])
@pytest.mark.parametrize('failed_handle', [201, 202])
def test_child_close_failure_retains_protected_handles_or_poisons_stale_values(owned, tmp_path, error, failed_handle):
    owner, kernel = owned; child = create(owner, tmp_path)
    owner.terminate(timeout=1); kernel.close_errors[failed_handle] = error
    with pytest.raises(OSError): owner.close()
    assert not child.closed and child.exited
    if error == 5:
        if failed_handle == 202:
            assert child.thread_handle == 202
        else:
            assert child.process_handle == 201
            with pytest.raises(OSError, match='already closed'): _ = child.thread_handle
        del kernel.close_errors[failed_handle]
        owner.close()
        assert child.closed and owner.handle is None
    else:
        before = list(kernel.events)
        for operation in (owner.close, owner.terminate, lambda: child.thread_handle, lambda: child.process_handle):
            with pytest.raises(OSError): operation()
        assert kernel.events == before and ('flags', failed_handle) not in kernel.events


def test_writer_wait_timeout_keeps_same_handles_and_never_closes_job_early(owned, tmp_path):
    owner, kernel = owned; child = create(owner, tmp_path); kernel.timeout = True
    with pytest.raises(TimeoutError): owner.terminate(timeout=.01)
    with pytest.raises(OSError): owner.close()
    assert child.process_handle == 201 and child.thread_handle == 202 and not child.exited
    assert not any(isinstance(event, tuple) and event[0] == 'close' for event in kernel.events)
    kernel.timeout = False
    owner.terminate(timeout=1); owner.close()
    assert child.closed


class AttemptObservedLock:
    """Expose contender arrival while retaining real RLock serialization."""
    def __init__(self, contender):
        self.lock = threading.RLock()
        self.contender = contender
        self.attempted = threading.Event()

    def __enter__(self):
        if threading.current_thread().name == self.contender:
            self.attempted.set()
        self.lock.acquire()
        return self

    def __exit__(self, *_):
        self.lock.release()


def background(name, operation):
    result = []
    def run():
        try: result.append(operation())
        except BaseException as error: result.append(error)
    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread, result


def joined(thread):
    thread.join(timeout=3)
    assert not thread.is_alive(), 'Authored lifecycle interleaving did not complete'


@pytest.mark.parametrize('action', ['terminate', 'close'])
def test_native_creation_owns_job_lifetime_until_concurrent_drain_or_close_can_enter(owned, tmp_path, monkeypatch, action):
    owner, kernel = owned
    owner._lifecycle_lock = lock = AttemptObservedLock('contending-lifecycle')
    entered, release = threading.Event(), threading.Event()
    original = kernel.UpdateProcThreadAttribute
    def held_attributes(*args):
        result = original(*args)
        entered.set()
        assert release.wait(timeout=3)
        return result
    monkeypatch.setattr(kernel, 'UpdateProcThreadAttribute', held_attributes)
    creator, created = background('creator', lambda: create(owner, tmp_path))
    contender = None
    try:
        assert entered.wait(timeout=3)
        contender, outcome = background('contending-lifecycle', lambda: getattr(owner, action)())
        assert lock.attempted.wait(timeout=3)
        # The Job-list references the live owner while the registry is still
        # empty. Neither empty-job drainage nor Job close may pass this point.
        assert ('close', 100) not in kernel.events and 'job-drained' not in kernel.events
    finally:
        release.set(); joined(creator)
        if contender is not None: joined(contender)
    assert len(created) == 1 and not isinstance(created[0], BaseException)
    child = created[0]
    if action == 'terminate':
        assert outcome == [None] and child.exited
    else:
        assert isinstance(outcome[0], OSError) and 'exit must be confirmed' in str(outcome[0])
        assert not child.exited and ('close', 100) not in kernel.events
        owner.terminate(timeout=1)
    owner.close()


def test_empty_registry_drain_atomically_refuses_later_native_creation(owned, tmp_path, monkeypatch):
    owner, kernel = owned; kernel.live = False
    owner._lifecycle_lock = lock = AttemptObservedLock('contending-create')
    entered, release = threading.Event(), threading.Event()
    original = kernel.QueryInformationJobObject
    def held_query(*args):
        entered.set(); assert release.wait(timeout=3)
        return original(*args)
    monkeypatch.setattr(kernel, 'QueryInformationJobObject', held_query)
    drainer, drained = background('drainer', owner.terminate)
    creator = None
    try:
        assert entered.wait(timeout=3)
        creator, created = background('contending-create', lambda: create(owner, tmp_path))
        assert lock.attempted.wait(timeout=3)
        assert 'created-into-registered-record' not in kernel.events
    finally:
        release.set(); joined(drainer)
        if creator is not None: joined(creator)
    assert drained == [None] and isinstance(created[0], OSError)
    assert 'created-into-registered-record' not in kernel.events and not owner.created_children
    owner.close()


def test_job_close_completes_before_waiting_create_can_observe_a_recycled_value(owned, tmp_path, monkeypatch):
    owner, kernel = owned
    owner._lifecycle_lock = lock = AttemptObservedLock('contending-create')
    entered, release = threading.Event(), threading.Event()
    original = kernel.CloseHandle
    def held_close(handle):
        assert handle == 100
        entered.set(); assert release.wait(timeout=3)
        return original(handle)
    monkeypatch.setattr(kernel, 'CloseHandle', held_close)
    closer, closed = background('closer', owner.close)
    creator = None
    try:
        assert entered.wait(timeout=3)
        creator, created = background('contending-create', lambda: create(owner, tmp_path))
        assert lock.attempted.wait(timeout=3)
        assert 'attributes-initialized' not in kernel.events
    finally:
        release.set(); joined(closer)
        if creator is not None: joined(creator)
    assert closed == [None] and isinstance(created[0], OSError)
    assert owner.handle is None and not owner.created_children
    assert kernel.events == [('close', 100)]


@pytest.mark.parametrize('first', ['resume', 'drain'])
def test_resume_and_drain_have_one_serialized_admission_order(owned, tmp_path, monkeypatch, first):
    owner, kernel = owned; child = create(owner, tmp_path)
    owner._lifecycle_lock = lock = AttemptObservedLock('contending-action')
    entered, release = threading.Event(), threading.Event()
    if first == 'resume':
        original = kernel.ResumeThread
        def held(*args):
            result = original(*args); entered.set(); assert release.wait(timeout=3)
            kernel.events.append('resume-returned')
            return result
        monkeypatch.setattr(kernel, 'ResumeThread', held)
        first_action, second_action = child.resume_once, owner.terminate
    else:
        original = kernel.QueryInformationJobObject
        def held(*args):
            entered.set(); assert release.wait(timeout=3)
            return original(*args)
        monkeypatch.setattr(kernel, 'QueryInformationJobObject', held)
        first_action, second_action = owner.terminate, child.resume_once
    leader, leading = background('leading-action', first_action)
    contender = None
    try:
        assert entered.wait(timeout=3)
        contender, following = background('contending-action', second_action)
        assert lock.attempted.wait(timeout=3)
    finally:
        release.set(); joined(leader)
        if contender is not None: joined(contender)
    assert leading == [None] and child.exited
    if first == 'resume':
        assert following == [None]
        assert kernel.events.index('resume-returned') < kernel.events.index('terminate-created-process')
    else:
        assert isinstance(following[0], OSError) and 'resume' not in kernel.events
    owner.close()


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows suspended process/Job/retained-handle contract')
@pytest.mark.parametrize('guardian_before_resume', [False, True])
@pytest.mark.parametrize('detached_console', [False, True])
def test_windows_authored_leaf_writer_stays_owned_after_guardian_loss(tmp_path, guardian_before_resume, detached_console):
    # The test process is the living keeper. No venv redirector, frozen
    # bootloader, hidden-child registration or production writer claim.
    kernel = module._kernel()
    image = ctypes.create_unicode_buffer(32768)
    length = kernel.GetModuleFileNameW(None, image, len(image))
    assert 0 < length < len(image)
    assert ctypes.sizeof(module._StartupInfoEx) == 112 and ctypes.sizeof(module._ProcessInformation) == 24
    env = {name: os.environ[name] for name in ('SystemRoot', 'WINDIR') if name in os.environ}
    env.update({'TEMP': str(tmp_path), 'TMP': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1'})
    script = tmp_path / 'owned writer 漢字.py'
    marker = tmp_path / 'authored-write.txt'
    script.write_text('from pathlib import Path\nimport sys,time\nPath(sys.argv[1]).write_text("authored")\nwhile True: time.sleep(.05)\n')
    contender = tmp_path / 'fixed lease observer.py'
    contender.write_text('''import ctypes,sys
from ctypes import wintypes
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
k.CreateFileW.restype=wintypes.HANDLE
k.CloseHandle.argtypes=[wintypes.HANDLE]
h=k.CreateFileW(sys.argv[1],0xc0000000,0,None,4,0x80,None)
if h==ctypes.c_void_p(-1).value:
    sys.exit(32 if ctypes.get_last_error()==32 else 99)
sys.exit(0 if k.CloseHandle(h) else 99)
''')
    def observe(path):
        result = subprocess.run([image.value, '-I', '-B', str(contender), str(path)], cwd=tmp_path, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
        assert result.returncode in (0, 32)
        return result.returncode
    from backend.bundle_host import ExclusiveFileLease
    paths = (tmp_path / 'legacy/data/companion-operation.lock', tmp_path / 'private-target/host-v1/migration-runtime.lock')
    owner = module.WindowsPreparationProcess()
    child, guardian, leases = None, None, []
    try:
        for path in paths:
            path.parent.mkdir(parents=True)
            assert observe(path) == 0
            lease = ExclusiveFileLease(path); lease.acquire(); leases.append(lease)
        guardian = subprocess.Popen([image.value, '-I', '-B', '-c', 'import time; time.sleep(60)'], cwd=tmp_path,
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        child = owner.create_suspended([image.value, '-I', '-B', str(script), str(marker)], cwd=tmp_path,
            env=env, detached_console=detached_console)
        assert child.process_handle and child.thread_handle and not marker.exists()
        assert all(observe(path) == 32 for path in paths)
        member = wintypes.BOOL()
        assert kernel.IsProcessInJob(child.process_handle, owner.handle, ctypes.byref(member)) and member.value
        if detached_console:
            assert owner._process_ids(time.monotonic()+3) == [child._information.process_id]
        if not guardian_before_resume:
            child.resume_once()
            deadline = time.monotonic()+5
            while not marker.exists() and time.monotonic() < deadline: time.sleep(.01)
            assert marker.read_text() == 'authored'
            if detached_console:
                assert owner._process_ids(time.monotonic()+3) == [child._information.process_id]
        guardian.kill(); guardian.wait(timeout=5)
        assert all(observe(path) == 32 for path in paths)
        if detached_console:
            assert owner._process_ids(time.monotonic()+3) == [child._information.process_id]
        owner.terminate(timeout=5)
        assert child.exited and kernel.WaitForSingleObject(child.process_handle, 0) == 0
        assert all(observe(path) == 32 for path in paths)
        if guardian_before_resume: assert not marker.exists()
        owner.close()
        assert child.closed
    finally:
        if guardian is not None and guardian.poll() is None: guardian.kill(); guardian.wait(timeout=5)
        if any(not item.closed for item in owner.created_children): owner.terminate(timeout=5)
        owner.close()
        # Unknown cleanup exits by exception before releasing either lease.
        for lease in reversed(leases): lease.close()
    assert all(observe(path) == 0 for path in paths)
