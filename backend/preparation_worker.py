"""Cancellation and publication ownership for one language preparation."""
from __future__ import annotations

from contextlib import contextmanager
import os
import signal
import subprocess
import tempfile
import time

from .windows_preparation_process import WindowsPreparationProcess


class PreparationCancelled(Exception):
    pass


class PreparationCleanupError(RuntimeError):
    pass


class PreparationJob:
    def __init__(self, owner, cancelled, key=None):
        self.owner = owner
        self.key = key
        # Never clear this event: a restarted monitor owns a different one.
        self.cancelled = cancelled

    def report(self, stage, message):
        self.checkpoint()
        if self.key is not None:
            with self.owner.lock:
                if self.current():
                    self.owner.jobs[self.key].update(stage=stage, message=message, stage_started=time.monotonic())

    def current(self):
        return self.owner.stop_event is self.cancelled and not self.cancelled.is_set()

    def checkpoint(self):
        if not self.current():
            raise PreparationCancelled()

    @contextmanager
    def publication(self):
        with self.owner._publication_lock:
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
        # The Windows bootstrap joins its owned job before spawning extraction.
        # POSIX workers retain their own session/process group.
        tree = WindowsPreparationProcess() if os.name == 'nt' else None
        process = None
        try:
            # Files avoid pipe deadlocks if an extraction tool inherits stdout.
            with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                if tree is None:
                    options['start_new_session'] = True
                with self.publication():
                    process = subprocess.Popen(tree.command(command) if tree else command,
                        cwd=cwd, stdout=stdout, stderr=stderr, **options)
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
            failure = None
            try:
                if process is not None:
                    if process.poll() is None:
                        if tree is not None:
                            process.kill()
                        else:
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    # Stop/reap the bootstrap before an empty job can prove
                    # shutdown: it must never join/spawn after that observation.
                    process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired) as error:
                failure = error
            if tree is not None:
                try:
                    tree.terminate()
                except (OSError, TimeoutError) as error:
                    failure = error
                finally:
                    try:
                        tree.close()
                    except OSError as error:
                        failure = error
            if failure is not None:
                raise PreparationCleanupError('Preparation process cleanup could not be confirmed; restart the companion.') from failure
