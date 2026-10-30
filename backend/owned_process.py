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
                 show_window=False):
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
                    self.process = subprocess.Popen([*bootstrap, '--parent-fd', str(read_fd), '--', *command],
                        pass_fds=(read_fd,), start_new_session=True, **options)
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
        except (ProcessLookupError, PermissionError, psutil.NoSuchProcess):
            continue
    return result


def _posix_bootstrap(parent_fd, command):
    if os.name == 'nt' or not hasattr(os, 'waitid') or not hasattr(os, 'WNOWAIT'):
        return 125
    # Neither this pipe nor the watchdog's ownership may leak into descendants.
    os.set_inheritable(parent_fd, False)
    child = subprocess.Popen(command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
                             start_new_session=True)
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
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5
        while _posix_group_members(child.pid):
            if time.monotonic() > deadline:
                return 125
            time.sleep(.05)
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                break
        return child.wait(timeout=1)
    finally:
        os.close(parent_fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent-fd', required=True, type=int)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A child command is required.')
    return _posix_bootstrap(args.parent_fd, command)


if __name__ == '__main__':
    raise SystemExit(main())
