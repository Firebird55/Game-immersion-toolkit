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
import threading
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


class _StartupInfo(ctypes.Structure):
    _fields_ = [('cb', ctypes.c_uint32), ('reserved', wintypes.LPWSTR),
        ('desktop', wintypes.LPWSTR), ('title', wintypes.LPWSTR)] + [
        (name, ctypes.c_uint32) for name in ('x', 'y', 'width', 'height', 'columns', 'rows', 'fill', 'flags')] + [
        ('show', wintypes.WORD), ('reserved_size', wintypes.WORD), ('reserved_data', ctypes.c_void_p),
        ('stdin', wintypes.HANDLE), ('stdout', wintypes.HANDLE), ('stderr', wintypes.HANDLE)]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [('startup', _StartupInfo), ('attributes', ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [('process', wintypes.HANDLE), ('thread', wintypes.HANDLE),
        ('process_id', ctypes.c_uint32), ('thread_id', ctypes.c_uint32)]


class _SuspendedChild:
    """Only genuine CreateProcess outputs; never constructed from a PID record."""
    def __init__(self, owner):
        self.owner = owner
        self._information = _ProcessInformation()
        self.created = self.exited = self.closed = self.resumed = False
        self._poisoned = self._resume_attempted = self._admitted = False

    def _require_handles(self):
        self.owner._require_owned()
        if self._poisoned:
            raise OSError('Suspended writer ownership is unconfirmed.')
        if not self.created or self.closed:
            raise OSError('Suspended writer creation handles are unavailable.')

    def _poison(self):
        self._poisoned = True
        self.owner._admission_closed = True
        self.owner._ownership_unconfirmed = True

    @property
    def process_handle(self):
        with self.owner._lifecycle:
            self._require_handles()
            handle = self._information.process
            if not handle:
                raise OSError('Suspended writer process handle is already closed.')
            return handle

    @property
    def thread_handle(self):
        with self.owner._lifecycle:
            self._require_handles()
            handle = self._information.thread
            if not handle:
                raise OSError('Suspended writer thread handle is already closed.')
            return handle

    def resume_once(self):
        with self.owner._lifecycle:
            return self._resume_once()

    def _resume_once(self):
        self._require_handles()
        self.owner._require_owned()
        if self.owner._admission_closed or not self._admitted or self._resume_attempted:
            raise OSError('Suspended writer admission is closed or resume was already attempted.')
        self._resume_attempted = True
        try:
            previous = self.owner.kernel.ResumeThread(self.thread_handle)
        except BaseException:
            self._poison()
            raise
        if previous != 1:
            self.owner._admission_closed = True
            if previous == 0xffffffff:
                error = ctypes.get_last_error()
                self._poison()
                raise ctypes.WinError(error)
            raise OSError('Suspended writer suspend count was not exactly one.')
        self.resumed = True

    def stop_and_wait(self, deadline):
        with self.owner._lifecycle:
            return self._stop_and_wait(deadline)

    def _stop_and_wait(self, deadline):
        self._require_handles()
        self.owner._admission_closed = True
        kernel, handle = self.owner.kernel, self.process_handle
        try:
            result = kernel.WaitForSingleObject(handle, 0)
        except BaseException:
            self._poison()
            raise
        if result == 258:
            try:
                terminated = kernel.TerminateProcess(handle, 1)
            except BaseException:
                self._poison()
                raise
            if not terminated:
                error = ctypes.get_last_error()
                if error != 5:
                    self._poison()
                    raise ctypes.WinError(error)
            try:
                result = kernel.WaitForSingleObject(handle, max(0, math.ceil((deadline-time.monotonic())*1000)))
            except BaseException:
                self._poison()
                raise
        if result == 0:
            self.exited = True
            return
        if result == 258:
            raise TimeoutError('Retained suspended writer did not exit.')
        self._poison()
        raise OSError('Retained suspended writer exit observation is unconfirmed.')

    def close_after_exit(self):
        with self.owner._lifecycle:
            return self._close_after_exit()

    def _close_after_exit(self):
        if self.closed:
            return
        self._require_handles()
        self.owner._admission_closed = True
        if not self.exited:
            raise OSError('Retained suspended writer exit must be confirmed before close.')
        for name in ('thread', 'process'):
            handle = getattr(self._information, name)
            if not handle:
                continue
            try:
                closed = self.owner.kernel.CloseHandle(handle)
            except BaseException:
                self._poison()
                raise
            if not closed:
                error = ctypes.get_last_error()
                flags = wintypes.DWORD()
                retryable = False
                if error == 5:
                    try:
                        retryable = bool(self.owner.kernel.GetHandleInformation(handle, ctypes.byref(flags)) and flags.value & 2)
                    except BaseException:
                        self._poison()
                        raise
                if not retryable:
                    self._poison()
                raise ctypes.WinError(error)
            setattr(self._information, name, None)
        self.closed = True


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
        'GetHandleInformation': ([wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        'InitializeProcThreadAttributeList': ([ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)], wintypes.BOOL),
        'UpdateProcThreadAttribute': ([ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL),
        'DeleteProcThreadAttributeList': ([ctypes.c_void_p], None),
        'CreateProcessW': ([wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL,
            wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(_StartupInfoEx), ctypes.POINTER(_ProcessInformation)], wintypes.BOOL),
        'ResumeThread': ([wintypes.HANDLE], ctypes.c_uint32),
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
        self._lifecycle_lock = threading.RLock()
        self.kernel = _kernel()
        self.name = 'ProxyTranscriptPreparation-' + uuid.uuid4().hex
        self._ownership_unconfirmed = False
        self._created_children = []
        self._admission_closed = False
        self._handle = _check(self.kernel.CreateJobObjectW(None, self.name))
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
            _check(self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        except BaseException:
            self.close()
            raise

    @property
    def handle(self):
        # A stale raw value could have been recycled for an unrelated object.
        # Do not expose it to external membership queries or cleanup callers.
        with self._lifecycle:
            if getattr(self, '_ownership_unconfirmed', False):
                raise OSError('Windows preparation job ownership is unconfirmed; restart the companion.')
            return self._handle

    def _require_owned(self):
        handle = self.handle
        if not handle:
            raise OSError('Windows preparation job is already closed.')
        return handle

    @property
    def _lifecycle(self):
        # Normal construction initializes the lock before native ownership.
        # setdefault also keeps existing __new__-based native fixtures coherent.
        lock = getattr(self, '_lifecycle_lock', None)
        if lock is None:
            lock = self.__dict__.setdefault('_lifecycle_lock', threading.RLock())
        return lock

    @property
    def created_children(self):
        with self._lifecycle:
            return tuple(getattr(self, '_created_children', ()))

    def create_suspended(self, command, *, cwd, env, detached_console=False):
        """Serialize direct suspended creation with resume, drain and close."""
        with self._lifecycle:
            return self._create_suspended(command, cwd=cwd, env=env, detached_console=detached_console)

    def _create_suspended(self, command, *, cwd, env, detached_console=False):
        """Opt-in direct creation: the actual writer, not its legacy bootstrap.

        Callers supply fixed authored inputs and retain this owner through all
        cleanup. This primitive supplies no keeper, IPC or production admission.
        """
        job = self._require_owned()
        if getattr(self, '_admission_closed', False):
            raise OSError('Suspended writer admission is closed.')
        if type(detached_console) is not bool:
            raise ValueError('Detached console selection must be an explicit Boolean.')
        if (not isinstance(command, (list, tuple)) or not command
                or any(not isinstance(value, str) or '\0' in value for value in command)
                or not Path(command[0]).is_absolute() or not Path(cwd).is_absolute()
                or not isinstance(env, dict) or not env
                or any(not isinstance(k, str) or not k or '=' in k or '\0' in k
                       or not isinstance(v, str) or '\0' in v for k, v in env.items())
                or len({key.casefold() for key in env}) != len(env)):
            raise ValueError('Suspended writer needs explicit executable, arguments, directory and environment.')
        command_line = subprocess.list2cmdline(command)
        if len(command_line.encode('utf-16-le')) // 2 >= 32767:
            raise ValueError('Suspended writer command exceeds the Windows limit.')
        environment = ctypes.create_unicode_buffer('\0'.join(k+'='+v for k, v in sorted(env.items(), key=lambda item: item[0].casefold()))+'\0\0')
        kernel, size = self.kernel, ctypes.c_size_t()
        first = kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        if first or ctypes.get_last_error() != 122 or not 0 < size.value <= 65536:
            raise OSError('Windows process attribute sizing is unavailable.')
        attributes = ctypes.create_string_buffer(size.value)
        _check(kernel.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)))
        child = None
        try:
            jobs = (wintypes.HANDLE * 1)(job)
            _check(kernel.UpdateProcThreadAttribute(attributes, 0, 0x0002000d, ctypes.byref(jobs), ctypes.sizeof(jobs), None, None))
            startup = _StartupInfoEx()
            startup.startup.cb = ctypes.sizeof(startup)
            startup.attributes = ctypes.cast(attributes, ctypes.c_void_p)
            child = _SuspendedChild(self)
            if not hasattr(self, '_created_children'):
                self._created_children = []
            self._created_children.append(child)  # Own the same output record before the native call.
            try:
                # Only the fixed keeper experiment opts in; default/source
                # behavior stays CREATE_NO_WINDOW. No arbitrary flag mask.
                flags = 0x00080404 | (0x00000008 if detached_console else 0x08000000)
                result = kernel.CreateProcessW(command[0], ctypes.create_unicode_buffer(command_line), None, None,
                    False, flags, environment, str(cwd), ctypes.byref(startup), ctypes.byref(child._information))
            except BaseException:
                child._poison()
                raise
            if not result:
                error = ctypes.get_last_error()
                if child._information.process or child._information.thread:
                    child._poison()  # Failed creation outputs are never adopted as valid handles.
                else:
                    child.closed = True
                raise ctypes.WinError(error)
            child.created = True
            if any(handle in (None, 0, ctypes.c_void_p(-1).value) for handle in (child._information.process, child._information.thread)):
                child._poison()
                raise OSError('Windows writer creation handles are incomplete.')
            member = wintypes.BOOL()
            if not kernel.IsProcessInJob(child.process_handle, self.handle, ctypes.byref(member)):
                error = ctypes.get_last_error()
                if error == 6:
                    child._poison()
                    self._ownership_unconfirmed = True
                raise ctypes.WinError(error)
            if not member.value:
                raise OSError('Created suspended writer is not in its selected Job.')
            observed = kernel.WaitForSingleObject(child.process_handle, 0)
            if observed != 258:
                if observed == 0:
                    child.exited = True
                else:
                    child._poison()
                raise OSError('Created suspended writer is not confirmed live.')
            child._admitted = True
            return child
        except BaseException:
            self._admission_closed = True
            raise
        finally:
            try:
                kernel.DeleteProcThreadAttributeList(attributes)
            except BaseException:
                self._admission_closed = True
                raise

    def command(self, command):
        self._require_owned()
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
        self._require_owned()
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
        self._require_owned()
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
        with self._lifecycle:
            self._admission_closed = True
            return self._terminate(timeout)

    def _terminate(self, timeout):
        self._require_owned()
        # The caller has already reaped the bootstrap, so it cannot join/spawn
        # after an empty-job observation. Do not mass-terminate first: job
        # accounting may reach zero before the process objects are signaled.
        deadline = time.monotonic() + timeout
        for child in self.created_children:
            if child.created and not child.closed:
                child.stop_and_wait(deadline)
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
        with self._lifecycle:
            self._admission_closed = True
            return self._close()

    def _close(self):
        handle = self.handle
        if not handle:
            return
        self._require_owned()
        for child in self.created_children:
            child.close_after_exit()
        try:
            closed = self.kernel.CloseHandle(handle)
        except Exception as error:
            self._ownership_unconfirmed = True
            raise OSError('Windows preparation job close outcome is unconfirmed.') from error
        except BaseException:
            self._ownership_unconfirmed = True
            raise
        if closed:
            self._handle = None
            return
        error = ctypes.get_last_error()
        # Only an evidenced protected handle remains eligible for retry. In
        # particular ERROR_INVALID_HANDLE must never be probed or closed again:
        # its numeric value might already identify an unrelated object.
        retryable = False
        if error == 5:  # ERROR_ACCESS_DENIED
            flags = wintypes.DWORD()
            try:
                retryable = bool(self.kernel.GetHandleInformation(handle, ctypes.byref(flags))
                    and flags.value & 2)  # HANDLE_FLAG_PROTECT_FROM_CLOSE
            except Exception as failure:
                self._ownership_unconfirmed = True
                raise OSError('Windows preparation job close outcome is unconfirmed.') from failure
            except BaseException:
                self._ownership_unconfirmed = True
                raise
        if not retryable:
            self._ownership_unconfirmed = True
        raise ctypes.WinError(error)


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
    # CREATE_NO_WINDOW must still receive the bootstrap's redirected handles.
    # Leaving every stream as None bypasses Popen's explicit handle setup.
    return subprocess.call(command, stdin=sys.stdin, stdout=sys.stdout,
        stderr=sys.stderr, creationflags=subprocess.CREATE_NO_WINDOW)


if __name__ == '__main__':
    raise SystemExit(_bootstrap(sys.argv[1], sys.argv[2:]))
