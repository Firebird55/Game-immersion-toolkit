"""Deterministic Win32 cleanup races; native process tests remain authoritative."""
import ctypes

import pytest

from backend.windows_preparation_process import WindowsPreparationProcess


class Kernel:
    def __init__(self, *, late_child=False, wait_result=0, stale_pid=False):
        self.members = {10, 20}
        self.signaled = {pid: False for pid in self.members}
        self.opened, self.closed, self.terminated, self.waited = [], [], [], []
        self.late_child, self.wait_result, self.stale_pid = late_child, wait_result, stale_pid

    def QueryInformationJobObject(self, _job, kind, pointer, _size, _length):
        info = pointer._obj
        if kind == 1:
            info.active_processes = len(self.members)
        else:
            assert kind == 3
            ids = sorted(self.members)
            info.assigned = len(ids)
            info.count = min(len(info.process_ids), len(ids))
            info.process_ids[:info.count] = ids[:info.count]
        return 1

    def OpenProcess(self, access, inherit, pid):
        assert access == 0x101001 and not inherit
        self.opened.append(pid)
        return pid

    def IsProcessInJob(self, handle, _job, result):
        if self.stale_pid and handle == 20:
            self.members.remove(handle)  # Enumeration raced with exit/PID reuse.
            result._obj.value = False
        else:
            result._obj.value = handle in self.members
        return 1

    def TerminateJobObject(self, _job, _code):
        # The old implementation mistook accounting zero for kernel completion.
        self.members.clear()
        return 1

    def TerminateProcess(self, handle, _code):
        assert handle in self.members
        self.terminated.append(handle)
        self.members.remove(handle)
        if self.late_child and handle == 10:
            self.members.add(30)
            self.signaled[30] = False
        return 1

    def WaitForSingleObject(self, handle, timeout):
        if timeout:
            self.waited.append(handle)
            self.signaled[handle] = self.wait_result == 0
            return self.wait_result
        return 0 if self.signaled[handle] else 258

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1


def tree(kernel):
    instance = WindowsPreparationProcess.__new__(WindowsPreparationProcess)
    instance.kernel, instance.handle = kernel, 100
    return instance


def test_bootstrap_clears_inherited_frozen_dll_directory_before_native_spawn(monkeypatch):
    from backend import windows_preparation_process as module
    from types import SimpleNamespace
    calls = []
    kernel = SimpleNamespace(OpenJobObjectW=lambda *_: 1, GetCurrentProcess=lambda: 2,
        AssignProcessToJobObject=lambda *_: calls.append('join') or 1,
        CloseHandle=lambda *_: 1, SetDllDirectoryW=lambda path: calls.append(('dll-directory', path)) or 1)
    monkeypatch.setattr(module, '_kernel', lambda: kernel)
    monkeypatch.setattr(module.subprocess, 'CREATE_NO_WINDOW', 0x8000000, raising=False)
    def spawn(command, **kwargs):
        assert calls == ['join', ('dll-directory', None)]
        assert command == ['owned.exe'] and kwargs['creationflags'] == 0x8000000
        assert kwargs['stdin'] is module.sys.stdin
        assert kwargs['stdout'] is module.sys.stdout
        assert kwargs['stderr'] is module.sys.stderr
        return 0
    monkeypatch.setattr(module.subprocess, 'call', spawn)
    assert module._bootstrap('owned-job', ['owned.exe']) == 0


def test_job_accounting_zero_is_not_process_completion():
    kernel = Kernel()
    tree(kernel).terminate()
    assert kernel.waited == [10, 20]
    assert all(kernel.signaled.values())
    assert sorted(kernel.opened) == sorted(kernel.closed) == [10, 20]


def test_failed_job_close_retains_exact_handle_until_explicit_retry(monkeypatch):
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 6, raising=False)
    monkeypatch.setattr(ctypes, 'WinError', lambda error: OSError(error, 'authored close failure'), raising=False)
    kernel = Kernel()
    attempts = []
    def close(handle):
        attempts.append(handle)
        return len(attempts) > 1
    monkeypatch.setattr(kernel, 'CloseHandle', close)
    owner = tree(kernel)
    exact_handle = owner.handle
    with pytest.raises(OSError, match='authored close failure'):
        owner.close()
    assert owner.handle is exact_handle and attempts == [exact_handle]
    owner.close()
    assert owner.handle is None and attempts == [exact_handle, exact_handle]
    owner.close()
    assert attempts == [exact_handle, exact_handle]


def test_drain_reenumerates_child_spawned_before_parent_termination():
    kernel = Kernel(late_child=True)
    tree(kernel).terminate()
    assert kernel.terminated == kernel.waited == [10, 20, 30]
    assert all(kernel.signaled.values()) and not kernel.members
    assert sorted(kernel.opened) == sorted(kernel.closed) == [10, 20, 30]


def test_drain_never_terminates_a_reused_pid_outside_the_job():
    kernel = Kernel(stale_pid=True)
    with pytest.raises(OSError, match='ownership could not be confirmed'):
        tree(kernel).terminate()
    assert kernel.terminated == kernel.waited == []
    assert sorted(kernel.opened) == sorted(kernel.closed) == [10, 20]


def test_drain_timeout_closes_all_retained_handles_and_fails():
    kernel = Kernel(wait_result=258)
    with pytest.raises(TimeoutError, match='descendants did not stop'):
        tree(kernel).terminate()
    assert sorted(kernel.opened) == sorted(kernel.closed) == [10, 20]


def test_drain_wait_failure_is_not_reported_as_completion(monkeypatch):
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 6, raising=False)
    monkeypatch.setattr(ctypes, 'WinError', lambda error: OSError(error, 'invalid handle'), raising=False)
    kernel = Kernel(wait_result=0xffffffff)
    with pytest.raises(OSError, match='invalid handle'):
        tree(kernel).terminate()
    assert sorted(kernel.opened) == sorted(kernel.closed) == [10, 20]


@pytest.mark.parametrize('more_data_error', [False, True])
def test_drain_resizes_a_truncated_job_process_list(monkeypatch, more_data_error):
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 234, raising=False)
    kernel = Kernel()
    original = kernel.QueryInformationJobObject
    def query(job, kind, pointer, size, length):
        result = original(job, kind, pointer, size, length)
        if more_data_error and kind == 3 and pointer._obj.count < pointer._obj.assigned:
            return 0
        return result
    kernel.QueryInformationJobObject = query
    kernel.members = set(range(1, 131))
    kernel.signaled = {pid: False for pid in kernel.members}
    tree(kernel).terminate()
    assert len(kernel.waited) == 130 and all(kernel.signaled.values())
    assert sorted(kernel.opened) == sorted(kernel.closed)


def test_exited_process_during_open_is_not_a_cleanup_failure(monkeypatch):
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 87, raising=False)
    kernel = Kernel()
    original = kernel.OpenProcess
    def open_process(access, inherit, pid):
        if pid == 20:
            kernel.members.remove(pid)
            kernel.signaled[pid] = True
            return 0
        return original(access, inherit, pid)
    kernel.OpenProcess = open_process
    tree(kernel).terminate()
    assert kernel.terminated == kernel.waited == kernel.closed == [10]
    assert all(kernel.signaled.values())


@pytest.mark.parametrize('wait_result', [0, 258])
def test_already_terminating_access_denied_requires_same_handle_completion(monkeypatch, wait_result):
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 5, raising=False)
    kernel = Kernel(wait_result=wait_result)
    def already_terminating(handle, _code):
        kernel.members.remove(handle)
        return 0
    kernel.TerminateProcess = already_terminating
    if wait_result:
        with pytest.raises(TimeoutError, match='descendants did not stop'):
            tree(kernel).terminate()
    else:
        tree(kernel).terminate()
        assert all(kernel.signaled.values())
    assert sorted(kernel.opened) == sorted(kernel.closed) == [10, 20]
