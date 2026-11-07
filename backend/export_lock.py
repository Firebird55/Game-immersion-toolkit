"""An OS-owned lock shared by all manual and automatic export subprocesses."""
from dataclasses import dataclass
import os
from pathlib import Path
import threading


@dataclass(eq=False, repr=False)
class _ExportStream:
    stream: object = None
    close_attempted: bool = False
    acquire_error: BaseException | None = None
    close_error: BaseException | None = None


class ExportLockCleanupError(RuntimeError):
    """Private actual-stream/error retention; never a retry-close instruction."""
    def __init__(self, owner, failure):
        super().__init__('Export lock cleanup remains unconfirmed.')
        self.owner, self.failure = owner, failure


class ExportLock:
    def __init__(self, path):
        self.path, self.stream = Path(path), None
        self._lock = threading.Lock()
        self._record = self._operation = self._failure = None

    def _require_healthy(self):
        if self._failure is not None:
            raise ExportLockCleanupError(self, self._failure) from self._failure.close_error

    def require_healthy(self):
        with self._lock:
            self._require_healthy()

    def require_released(self):
        with self._lock:
            self._require_healthy()
            if self._operation is not None or self._record is not None:
                raise RuntimeError('Export lock work or release is still owned.')

    def _close_record(self, record):
        with self._lock:
            self._require_healthy()
            if (self._record is not record or self._operation is not record
                    or record.stream is None or record.close_attempted):
                raise RuntimeError('Export lock cleanup ownership differs.')
            record.close_attempted = True
        try:
            record.stream.close()
        except BaseException as error:
            with self._lock:
                record.close_error = error
                self._failure = record
                self._require_healthy()  # Fresh wrapper; do not re-raise/grow the retained error.
        with self._lock:
            self.stream = self._record = None

    def acquire(self):
        with self._lock:
            self._require_healthy()
            if self._operation is not None or self._record is not None:
                return False  # Never overwrite an already-held or opening stream.
            record = _ExportStream()
            self._record = self._operation = record
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            stream = self.path.open('a+b')
            # Retain the actual returned object before seek/write/flush/locking,
            # including cleanup after an unsuccessful acquisition.
            record.stream = stream
            with self._lock:
                self.stream = stream
            try:
                if stream.seek(0, 2) == 0:
                    stream.write(b'0')
                    stream.flush()
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                record.acquire_error = error
                self._close_record(record)
                return False
            except BaseException as error:
                record.acquire_error = error
                self._close_record(record)
                raise
            return True
        finally:
            with self._lock:
                if record.stream is None:
                    self._record = None  # The factory did not return a resource.
                self._operation = None

    def close(self):
        with self._lock:
            self._require_healthy()
            if self._operation is not None:
                raise RuntimeError('Export lock work or release is still owned.')
            record = self._record
            if record is None:
                return
            self._operation = record
        try:
            self._close_record(record)
        finally:
            with self._lock:
                self._operation = None
