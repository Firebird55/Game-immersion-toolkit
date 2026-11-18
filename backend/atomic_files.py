"""Bounded Windows sharing retries without removing the last published file."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import time


def sharing_retry(operation, timeout=1):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return operation()
        except PermissionError as error:
            if (os.name != 'nt' or getattr(error, 'winerror', None) not in {5, 32, 33}
                    or time.monotonic() >= deadline):
                raise
            time.sleep(.02)


def replace(source, destination, *, check=None):
    def publish():
        if check is not None:
            check()
        os.replace(source, destination)

    sharing_retry(publish)


def remove(path):
    sharing_retry(lambda: path.unlink(missing_ok=True))


@contextmanager
def stage_file(path):
    """Provide a fresh temporary path beside the target and clean it up."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        yield Path(folder) / 'download'


def write_bytes(path, data, *, check=None):
    """Stage private bytes beside their target and preserve it on failure."""
    path = Path(path)
    with stage_file(path) as staged:
        staged.write_bytes(data)
        replace(staged, path, check=check)
