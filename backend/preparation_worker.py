"""Cancellation and publication ownership for one language preparation."""
from __future__ import annotations

from contextlib import contextmanager
import os
import signal
import subprocess
import tempfile
import time


class PreparationCancelled(Exception):
    pass


class PreparationJob:
    def __init__(self, owner, cancelled):
        self.owner = owner
        # Never clear this event: a restarted monitor owns a different one.
        self.cancelled = cancelled

    def current(self):
        return self.owner.stop_event is self.cancelled and not self.cancelled.is_set()

    def checkpoint(self):
        if not self.current():
            raise PreparationCancelled()

    @contextmanager
    def publication(self):
        with self.owner.lock:
            self.checkpoint()
            yield

    @contextmanager
    def acquire(self, lock):
        while not lock.acquire(timeout=.05):
            self.checkpoint()
        try:
            self.checkpoint()
            yield
        finally:
            lock.release()

    def run(self, command, *, cwd, timeout, **options):
        """Keep ownership until the extraction process has exited and been reaped."""
        self.checkpoint()
        # Files avoid pipe deadlocks if an extraction tool inherits stdout.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            if os.name != 'nt':
                options['start_new_session'] = True
            with self.publication():
                process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr, **options)
            try:
                deadline = time.monotonic() + timeout
                while True:
                    self.checkpoint()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, timeout)
                    try:
                        result = process.wait(timeout=min(.05, remaining))
                        self.checkpoint()
                        return result
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if process.poll() is None:
                    if os.name == 'nt':
                        # Popen retains the owned process handle while taskkill
                        # terminates its extraction-tool descendants as well.
                        try:
                            subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                                capture_output=True, timeout=1,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                    else:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    if process.poll() is None:
                        process.kill()
                # A close deadline expiring here is a failed quiesce, not a
                # successful handoff with an untracked extraction process.
                process.wait()
