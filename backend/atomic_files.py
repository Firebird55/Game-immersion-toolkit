"""Bounded Windows sharing retries without removing the last published file."""
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


def replace(source, destination):
    sharing_retry(lambda: os.replace(source, destination))


def remove(path):
    sharing_retry(lambda: path.unlink(missing_ok=True))


def write_bytes(path, data):
    """Stage private bytes beside their target; preserve it on any failure.

    Callers own path/link and content validation. This is the small staging
    primitive used by publisher readers, without desktop tool discovery.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        staged = Path(folder) / 'download'
        staged.write_bytes(data)
        replace(staged, path)
