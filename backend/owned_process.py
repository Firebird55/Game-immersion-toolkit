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
        self._control = None
        self._lock = threading.RLock()
        self.process = None
        try:
            options = dict(cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr,
                           text=text, bufsize=1 if text else -1)
            if text:
                options.update(encoding='utf-8', errors='replace')
            if os.name == 'nt':
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
            if os.name == 'nt':
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent-fd', required=True, type=int)
    parser.add_argument('--retain-fd', action='append', type=int, default=[])
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A child command is required.')
    return _posix_bootstrap(args.parent_fd, command, args.retain_fd)


if __name__ == '__main__':
    raise SystemExit(main())
