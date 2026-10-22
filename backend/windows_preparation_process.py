"""A Windows job owns preparation descendants before extraction can begin.

The parent retains the kill-on-close job handle. A tiny bootstrap joins that job
before launching the requested command, closing the usual spawn/assign race.
Only documented Win32 job-object APIs are used; no PID enumeration or taskkill.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
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
        'TerminateJobObject': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        'GetCurrentProcess': ([], wintypes.HANDLE),
        'GetModuleFileNameW': ([wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD], wintypes.DWORD),
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
        return [image.value, str(Path(__file__).resolve()), self.name, *command]

    def terminate(self, timeout=3):
        _check(self.kernel.TerminateJobObject(self.handle, 1))
        deadline = time.monotonic() + timeout
        while True:
            accounting = _Accounting()
            _check(self.kernel.QueryInformationJobObject(self.handle, 1,
                ctypes.byref(accounting), ctypes.sizeof(accounting), None))
            if accounting.active_processes == 0:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError('Windows preparation descendants did not stop.')
            time.sleep(.01)

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
    return subprocess.call(command, creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == '__main__':
    raise SystemExit(_bootstrap(sys.argv[1], sys.argv[2:]))
