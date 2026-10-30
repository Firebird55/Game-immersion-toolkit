"""A Windows job owns preparation descendants before extraction can begin.

The parent retains the kill-on-close job handle. A tiny bootstrap joins that job
before launching the requested command, closing the usual spawn/assign race.
Only documented Win32 APIs are used. Process IDs come from this job, and each
retained process handle is checked for membership before it can be terminated.
"""
from __future__ import annotations

from contextlib import ExitStack
import ctypes
from ctypes import wintypes
import math
from pathlib import Path
import subprocess
import sys
import time
import uuid


class _BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
        ('flags', wintypes.DWORD), ('minimum_working_set', ctypes.c_size_t),
        ('maximum_working_set', ctypes.c_size_t), ('active_process_limit', wintypes.DWORD),
        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
        ('read_operations', 'write_operations', 'other_operations', 'read_bytes', 'write_bytes', 'other_bytes')]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', _BasicLimits), ('io', _IoCounters), ('process_memory', ctypes.c_size_t),
        ('job_memory', ctypes.c_size_t), ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in ('user_time', 'kernel_time', 'period_user_time', 'period_kernel_time')] + [
        (name, wintypes.DWORD) for name in ('page_faults', 'total_processes', 'active_processes', 'terminated_processes')]


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    functions = {
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'OpenJobObjectW': ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        'QueryInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'IsProcessInJob': ([wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        'TerminateProcess': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'GetCurrentProcess': ([], wintypes.HANDLE),
        'GetModuleFileNameW': ([wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD], wintypes.DWORD),
        'SetDllDirectoryW': ([wintypes.LPCWSTR], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in functions.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    return kernel


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


class WindowsPreparationProcess:
    def __init__(self):
        self.kernel = _kernel()
        self.name = 'ProxyTranscriptPreparation-' + uuid.uuid4().hex
        self.handle = _check(self.kernel.CreateJobObjectW(None, self.name))
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
            _check(self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        except BaseException:
            self.close()
            raise

    def command(self, command):
        # venv python.exe can be a redirector that launches another interpreter.
        # The stdlib-only bootstrap must be the retained Popen process itself;
        # use this process's real executable image, retaining the venv command
        # for the actual extraction inside the job.
        image = ctypes.create_unicode_buffer(32768)
        length = _check(self.kernel.GetModuleFileNameW(None, image, len(image)))
        if length >= len(image):
            raise OSError('Windows preparation interpreter path was truncated.')
        if getattr(sys, 'frozen', False):
            # A bootloader cannot execute this module's .py path. Dispatch the
            # stdlib bootstrap in the real executable, retaining join-before-
            # spawn and all parent-owned Job Object cleanup below.
            return [image.value, '--runtime-child', 'windows-bootstrap', '--', self.name, *command]
        return [image.value, str(Path(__file__).resolve()), self.name, *command]

    def _process_ids(self, deadline):
        capacity = 64
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError('Windows preparation descendants did not stop.')
            class ProcessIds(ctypes.Structure):
                _fields_ = [('assigned', wintypes.DWORD), ('count', wintypes.DWORD),
                    ('process_ids', ctypes.c_size_t * capacity)]
            processes = ProcessIds()
            result = self.kernel.QueryInformationJobObject(self.handle, 3,
                ctypes.byref(processes), ctypes.sizeof(processes), None)
            if not result and ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
                _check(result)
            if result and processes.count == processes.assigned:
                return list(processes.process_ids[:processes.count])
            capacity = max(capacity * 2, processes.assigned)

    def _wait(self, handle, deadline):
        remaining_ms = max(0, math.ceil((deadline - time.monotonic()) * 1000))
        result = self.kernel.WaitForSingleObject(handle, remaining_ms)
        if result == 0:  # WAIT_OBJECT_0: the process object is signaled.
            return
        if result == 258:  # WAIT_TIMEOUT
            raise TimeoutError('Windows preparation descendants did not stop.')
        if result == 0xffffffff:  # WAIT_FAILED
            _check(False)
        raise OSError('Unexpected Windows preparation process wait result.')

    def terminate(self, timeout=3):
        # The caller has already reaped the bootstrap, so it cannot join/spawn
        # after an empty-job observation. Do not mass-terminate first: job
        # accounting may reach zero before the process objects are signaled.
        deadline = time.monotonic() + timeout
        while True:
            process_ids = self._process_ids(deadline)
            if not process_ids:
                accounting = _Accounting()
                _check(self.kernel.QueryInformationJobObject(self.handle, 1,
                    ctypes.byref(accounting), ctypes.sizeof(accounting), None))
                if accounting.active_processes == 0:
                    return
                continue
            with ExitStack() as handles:
                owned = []
                # Retain the whole snapshot before stopping any member. A
                # parent's shutdown may also cause its children to exit.
                for pid in process_ids:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Windows preparation descendants did not stop.')
                    handle = self.kernel.OpenProcess(0x101001, False, pid)
                    # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION | TERMINATE
                    if not handle and ctypes.get_last_error() == 87:
                        continue  # ERROR_INVALID_PARAMETER: the process exited.
                    _check(handle)
                    handles.callback(lambda handle=handle: _check(self.kernel.CloseHandle(handle)))
                    member = wintypes.BOOL()
                    _check(self.kernel.IsProcessInJob(handle, self.handle, ctypes.byref(member)))
                    if member.value:
                        owned.append(handle)
                    elif self.kernel.WaitForSingleObject(handle, 0) != 0:
                        # Membership alone cannot distinguish PID reuse from
                        # an exit still completing. Never terminate that handle.
                        raise OSError('Windows preparation process ownership could not be confirmed.')
                for handle in owned:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Windows preparation descendants did not stop.')
                    if not self.kernel.TerminateProcess(handle, 1):
                        error = ctypes.get_last_error()
                        if error != 5:  # Already exited processes report ACCESS_DENIED.
                            raise ctypes.WinError(error)
                    self._wait(handle, deadline)
            # A member may have spawned after the snapshot but before its
            # termination. Its descendants remain in the job for the next pass.

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            _check(self.kernel.CloseHandle(handle))


def _bootstrap(name, command):
    kernel = _kernel()
    handle = _check(kernel.OpenJobObjectW(1, False, name))  # JOB_OBJECT_ASSIGN_PROCESS
    try:
        _check(kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()))
    finally:
        _check(kernel.CloseHandle(handle))
    # A failed assignment exits before spawning anything. The parent owns the
    # remaining handle, including if cancellation races with this bootstrap.
    # PyInstaller's DLL directory is inherited across process creation. Restore
    # Windows' ordinary native search before an external helper is spawned;
    # its own app directory and named OS/CRT prerequisites remain explicit.
    _check(kernel.SetDllDirectoryW(None))
    return subprocess.call(command, creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == '__main__':
    raise SystemExit(_bootstrap(sys.argv[1], sys.argv[2:]))
