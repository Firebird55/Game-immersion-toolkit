"""Retained process ownership for desktop services and their helper children.

Windows joins a kill-on-close job before launching the real command. POSIX uses
a watchdog and a private liveness pipe; it retains the unreaped group leader so
its process-group identity cannot be reused during descendant cleanup. Never
reconstruct ownership from a PID file or from a route record.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time


class OwnedProcess:
    def __init__(self, command, *, cwd=None, env=None, stdin=subprocess.PIPE,
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, visible_console=False,
                 show_window=False, independent_session=False, retained_fds=()):
        self.tree = None
        self._guardian = False
        self._control = None
        self._lock = threading.RLock()
        self.process = None
        try:
            options = dict(cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr,
                           text=text, bufsize=1 if text else -1)
            if text:
                options.update(encoding='utf-8', errors='replace')
            if os.name == 'nt' and (independent_session or retained_fds):
                # This guardian is outside its service Job. It keeps the actual
                # exclusive installation handle until every Job member's process
                # object has signaled, including after an abrupt host exit.
                import ctypes
                import msvcrt
                from .windows_preparation_process import _kernel, _check, WindowsPreparationProcess
                self.tree = WindowsPreparationProcess()
                image = ctypes.create_unicode_buffer(32768)
                if _check(_kernel().GetModuleFileNameW(None, image, len(image))) >= len(image):
                    raise OSError('Windows guardian image path was truncated.')
                bootstrap = [image.value, '--runtime-child', 'owned-process', '--'] if getattr(sys, 'frozen', False) else [image.value, str(Path(__file__).resolve())]
                read_fd, self._control = os.pipe()
                read_handle = msvcrt.get_osfhandle(read_fd)
                handles = (read_handle, *(int(value) for value in retained_fds))
                prior = [os.get_handle_inheritable(handle) for handle in handles]
                startup = subprocess.STARTUPINFO()
                startup.lpAttributeList = {'handle_list': list(handles)}
                try:
                    for handle in handles:
                        os.set_handle_inheritable(handle, True)
                    extra = [part for handle in retained_fds for part in ('--retain-handle', str(handle))]
                    self.process = subprocess.Popen([*bootstrap, '--windows-parent-handle', str(read_handle),
                        '--guardian-job', self.tree.name, *extra, '--', *command],
                        creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup, close_fds=True, **options)
                    self._guardian = True
                finally:
                    for handle, inherited in zip(handles, prior):
                        os.set_handle_inheritable(handle, inherited)
                    os.close(read_fd)
            elif os.name == 'nt':
                from .windows_preparation_process import WindowsPreparationProcess
                options['env'] = {**(os.environ if env is None else env),
                    'PROXY_TRANSCRIPT_CHILD_CONSOLE': '1' if visible_console else '0',
                    'PROXY_TRANSCRIPT_CHILD_SHOW_WINDOW': '1' if show_window else '0'}
                self.tree = WindowsPreparationProcess()
                self.process = subprocess.Popen(self.tree.command(command),
                    creationflags=subprocess.CREATE_NO_WINDOW, **options)
            else:
                read_fd, self._control = os.pipe()
                try:
                    if getattr(sys, 'frozen', False):
                        bootstrap = [sys.executable, '--runtime-child', 'owned-process', '--']
                    else:
                        bootstrap = [sys.executable, str(Path(__file__).resolve())]
                    # Nested helpers keep the outer watchdog's session identity;
                    # separate groups permit local cancellation without escaping
                    # the top-level crash/retirement barrier.
                    inherited = (os.environ if env is None else env).get('PROXY_TRANSCRIPT_OWNED_SESSION')
                    nested = not independent_session and inherited == str(os.getsid(0))
                    retained = tuple(int(fd) for fd in retained_fds)
                    extra = [part for fd in retained for part in ('--retain-fd', str(fd))]
                    self.process = subprocess.Popen([*bootstrap, '--parent-fd', str(read_fd), *extra, '--', *command],
                        pass_fds=(read_fd, *retained), start_new_session=not nested,
                        **({'process_group': 0} if nested else {}), **options)
                finally:
                    os.close(read_fd)
        except BaseException:
            if self.tree:
                self.tree.close()
            if self._control is not None:
                os.close(self._control)
                self._control = None
            raise

    def poll(self):
        return self.process.poll()

    def stop(self, timeout=10):
        """Cooperate first, then verify tree exit before releasing ownership.

        A timeout retains the ownership object and raises. Callers must not
        start a replacement, release their instance lease or claim a drain.
        """
        with self._lock:
            deadline = time.monotonic() + timeout
            process = self.process
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    pass
            if self._guardian:
                if self._control is not None:
                    os.close(self._control)
                    self._control = None
                process.wait(timeout=max(.01, deadline - time.monotonic()))
                if self.tree is not None:
                    self.tree.terminate(timeout=max(.01, deadline - time.monotonic()))
                    self.tree.close()
                    self.tree = None
            elif os.name == 'nt':
                try:
                    process.wait(timeout=min(1, timeout / 3))
                except subprocess.TimeoutExpired:
                    process.kill()  # The retained Popen bootstrap, not a recorded PID.
                    process.wait(timeout=max(.01, deadline - time.monotonic()))
                if self.tree is not None:
                    self.tree.terminate(timeout=max(.01, deadline - time.monotonic()))
                    self.tree.close()
                    self.tree = None
            else:
                if self._control is not None:
                    os.close(self._control)
                    self._control = None
                # The watchdog also performs this cleanup after parent death.
                # Do not kill it before it has verified its child's group exit.
                process.wait(timeout=max(.01, deadline - time.monotonic()))
                if process.returncode == 125 or process.returncode < 0:
                    raise RuntimeError('Owned process descendants could not be verified stopped.')
            return process.returncode

    def close_streams(self):
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def _posix_group_members(group):
    import psutil
    result = []
    for process in psutil.process_iter(['pid', 'status']):
        try:
            if os.getpgid(process.pid) == group and process.info['status'] != psutil.STATUS_ZOMBIE:
                result.append(process.pid)
        except (ProcessLookupError, psutil.NoSuchProcess):
            continue
    return result


def _posix_session_groups(session):
    """The retained session leader prevents this ownership ID being reused."""
    import psutil
    groups = set()
    for process in psutil.process_iter(['pid', 'status']):
        try:
            if (process.pid != os.getpid() and os.getsid(process.pid) == session
                    and process.info['status'] != psutil.STATUS_ZOMBIE):
                group = os.getpgid(process.pid)
                if group == session:
                    raise RuntimeError('A child joined the ownership watchdog group.')
                groups.add(group)
        except (ProcessLookupError, psutil.NoSuchProcess):
            continue
    return groups


def _posix_bootstrap(parent_fd, command, retained_fds=()):
    if os.name == 'nt' or not hasattr(os, 'waitid') or not hasattr(os, 'WNOWAIT'):
        return 125
    # Neither this pipe nor the watchdog's ownership may leak into descendants.
    os.set_inheritable(parent_fd, False)
    for descriptor in retained_fds:
        os.set_inheritable(descriptor, False)
    session = os.getsid(0)
    owns_session = session == os.getpid()
    environment = {**os.environ, 'PROXY_TRANSCRIPT_OWNED_SESSION': str(session)}
    child = subprocess.Popen(command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
                             process_group=0, env=environment)
    interrupted = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: interrupted.set())
    try:
        while not interrupted.is_set():
            if os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
                break  # Retain the zombie PID until its group has been drained.
            readable, _, _ = select.select([parent_fd], [], [], .1)
            if readable and not os.read(parent_fd, 1):
                break
        deadline = time.monotonic() + 1
        notice = time.monotonic() + 5
        while True:
            try:
                groups = (_posix_session_groups(session) if owns_session else
                          {child.pid} if _posix_group_members(child.pid) else set())
                if not groups:
                    return child.wait(timeout=1)
                for group in groups:
                    try:
                        os.killpg(group, signal.SIGTERM if time.monotonic() < deadline else signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            except (OSError, RuntimeError):
                # Retain the session and inherited installation lock if any
                # descendant's lifetime is unknown. Never authorize replacement
                # by exiting the watchdog while that uncertainty remains.
                pass
            if time.monotonic() >= notice:
                print('Owned helper cleanup is still pending; installation ownership is retained.', file=sys.stderr, flush=True)
                notice = time.monotonic() + 30
            time.sleep(.05)
    finally:
        os.close(parent_fd)
        for descriptor in retained_fds:
            os.close(descriptor)


def _windows_guardian(parent_handle, command, retained_handles=(), job_name=None):
    if os.name != 'nt':
        return 125
    import msvcrt
    # Both host and guardian retain the outer Job. The guardian joins before
    # spawning anything. If the guardian itself crashes, the still-live host
    # can verify every descendant (including a not-yet-ready inner bootstrap).
    # If the host crashes, the guardian still owns the Job and exclusive lease.
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.windows_preparation_process import _kernel, _check
    kernel = _kernel()
    outer = _check(kernel.OpenJobObjectW(0x1F003F, False, job_name))
    _check(kernel.AssignProcessToJobObject(outer, kernel.GetCurrentProcess()))
    # The source bootstrap runs as a file before importing third-party code.
    # This import uses the package's ordinary Job implementation, not recursion
    # into another guardian (independent_session=False, no retained handles).
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.owned_process import OwnedProcess as JobChild
    for handle in (parent_handle, *retained_handles):
        os.set_handle_inheritable(handle, False)
    parent_fd = msvcrt.open_osfhandle(parent_handle, os.O_RDONLY | os.O_BINARY)
    owner_gone = threading.Event()
    def watch_parent():
        try:
            os.read(parent_fd, 1)
        finally:
            os.close(parent_fd)
            owner_gone.set()
    watcher = threading.Thread(target=watch_parent, name='host-liveness', daemon=True)
    watcher.start()
    child = None
    try:
        child = JobChild(command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
        while child.poll() is None and not owner_gone.wait(.1):
            pass
        while True:
            try:
                result = child.stop(timeout=10)
                return result if result != 125 else 1
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                print('Windows service descendants are still stopping; installation ownership is retained.', file=sys.stderr, flush=True)
                time.sleep(1)
    finally:
        # A constructor failure cannot have an unowned application command:
        # join-before-spawn ensures its Job still owns every successful spawn.
        if child is not None:
            child.close_streams()
        for handle in retained_handles:
            _check(_kernel().CloseHandle(handle))
        _check(kernel.CloseHandle(outer))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent-fd', type=int)
    parser.add_argument('--windows-parent-handle', type=int)
    parser.add_argument('--retain-fd', action='append', type=int, default=[])
    parser.add_argument('--retain-handle', action='append', type=int, default=[])
    parser.add_argument('--guardian-job')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A child command is required.')
    if os.name == 'nt':
        if args.windows_parent_handle is None or args.parent_fd is not None or args.retain_fd or not args.guardian_job:
            parser.error('Windows guardian requires its private parent handle.')
        return _windows_guardian(args.windows_parent_handle, command, args.retain_handle, args.guardian_job)
    if args.parent_fd is None or args.windows_parent_handle is not None or args.retain_handle:
        parser.error('POSIX guardian requires its private parent descriptor.')
    return _posix_bootstrap(args.parent_fd, command, args.retain_fd)


if __name__ == '__main__':
    raise SystemExit(main())
