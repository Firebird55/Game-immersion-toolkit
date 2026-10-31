"""Admitted SQLite operation scopes, not physical-resource or copy authority."""
from __future__ import annotations

from contextlib import contextmanager
import math
import threading
import time

from .runtime_writers import RuntimeWriterGate


class SqliteOperationLifetime:
    """One owner group; retain failed objects only, never successful connections."""
    def __init__(self, subject, *, close_error, poisoned_error, fence_type, label):
        self.subject = subject
        self._close_error, self._poisoned_error = close_error, poisoned_error
        self._fence_type, self._label = fence_type, label
        self.failures = []
        self.failure_lock = threading.Lock()
        self.gate = RuntimeWriterGate()
        self.serialization = threading.Lock()
        self.epoch = 0
        self.fence = None

    def require_clean(self, deadline=None):
        if deadline is None:
            self.failure_lock.acquire()
        else:
            self._acquire(self.failure_lock, deadline)
        try:
            if self.failures:
                failure = self.failures[0]
                raise self._poisoned_error(failure) from failure
        finally:
            self.failure_lock.release()

    @contextmanager
    def operation(self):
        self.require_clean()
        self.gate.enter()
        try:
            self.require_clean()
            yield
        finally:
            # The caller exits its actual transaction/close scope first.
            self.gate.leave()

    @contextmanager
    def transaction(self, connection):
        body_error = transaction_error = None
        try:
            try:
                with connection:
                    try:
                        yield connection
                    except BaseException as error:
                        body_error = error
                        raise
            except BaseException as error:
                if error is not body_error:
                    transaction_error = error
                raise
        finally:
            try:
                connection.close()
            except BaseException as close_error:
                failure = self._close_error(self.subject, connection, body_error, transaction_error, close_error)
                with self.failure_lock:
                    self.failures.append(failure)
                cause = transaction_error if transaction_error is not None else body_error if body_error is not None else close_error
                raise failure from cause

    def _acquire(self, lock, deadline):
        remaining = min(threading.TIMEOUT_MAX, max(0.0, deadline-time.monotonic()))
        if not lock.acquire(timeout=remaining):
            raise TimeoutError(self._label+' freeze has not finished.')

    def check_locked(self, fence):
        self.require_clean()
        with self.gate._condition:
            if (type(fence) is not self._fence_type or self.fence is not fence
                    or fence._lifetime_subject is not self.subject or fence._epoch != self.epoch
                    or self.gate._accepting or self.gate._active):
                raise ValueError(self._label+' fence is no longer current.')

    def check(self, fence):
        with self.serialization:
            self.check_locked(fence)

    def freeze(self, timeout):
        if type(timeout) not in {int, float}:
            raise ValueError(self._label+' freeze requires a finite timeout.')
        try:
            duration = float(timeout)
        except OverflowError:
            raise ValueError(self._label+' freeze requires a finite timeout.') from None
        if not math.isfinite(duration) or not 0 <= duration <= threading.TIMEOUT_MAX:
            raise ValueError(self._label+' freeze requires a finite timeout.')
        deadline = time.monotonic()+duration
        self._acquire(self.serialization, deadline)
        try:
            self.require_clean(deadline)
            gate = self.gate
            self._acquire(gate._condition, deadline)
            try:
                gate.stop_admission()
            finally:
                gate._condition.release()
            while True:
                # Condition.wait can reacquire its RLock without a deadline.
                # Keep every entry and rest inside this one monotonic budget.
                self._acquire(gate._condition, deadline)
                try:
                    if gate._accepting:
                        raise ValueError(self._label+' admission reopened during freeze.')
                    if not gate._active:
                        self.require_clean(deadline)
                        if duration and time.monotonic() > deadline:
                            raise TimeoutError(self._label+' freeze has not finished.')
                        if self.fence is None:
                            self.fence = self._fence_type(self.subject, self.epoch)
                        fence = self.fence
                        if (type(fence) is not self._fence_type or fence._lifetime_subject is not self.subject
                                or fence._epoch != self.epoch):
                            raise ValueError(self._label+' fence is no longer current.')
                        return fence
                finally:
                    gate._condition.release()
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(self._label+' freeze has not finished.')
                time.sleep(min(.01, remaining))
        finally:
            self.serialization.release()

    def resume(self, fence):
        with self.serialization:
            self.check_locked(fence)
            self.fence = None
            self.epoch += 1
            self.gate.resume()
