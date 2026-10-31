"""Bounded Windows sharing retries without removing the last published file."""
import os
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
