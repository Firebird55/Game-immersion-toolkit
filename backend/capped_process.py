"""Run an explicitly supplied tool with a hard parent-owned output limit.

The caller owns tool provenance, input validation and final atomic publication.
The child receives no output filename; only this writer can grow the staging
file. Cancellation and failure remove that file without touching prior output.
"""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import subprocess
import threading
import time


BLOCK = 64 * 1024


class CappedProcessError(RuntimeError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class CappedProcessCancelled(CappedProcessError):
    def __init__(self):
        super().__init__('cancelled')


@dataclass(frozen=True)
class CappedOutput:
    bytes: int
    stderr: bytes


def run_capped_stdout(command, destination, *, limit, cwd, env, cancelled,
                      check, timeout=90, stderr_limit=BLOCK):
    """Write complete stdout or fail; never publish an accepted prefix.

    stdout/stderr are drained concurrently with bounded memory. Only stderr's
    first ``stderr_limit`` bytes are retained; excess diagnostics are discarded.
    This is an output-disk bound, not a child-process memory/CPU sandbox.
    """
    if (type(limit) is not int or limit <= 0 or type(stderr_limit) is not int
            or stderr_limit < 0 or type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError('Positive explicit process output/time bounds are required')
    destination = Path(destination)
    check()
    if cancelled():
        raise CappedProcessCancelled()
    # Exclusive creation prevents replacement/truncation of any existing file.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    process = None
    threads = []
    accepted = False
    errors = []
    failed = threading.Event()
    retained_stderr = bytearray()
    written = 0
    try:
        with os.fdopen(descriptor, 'wb') as output:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

            def drain_stdout():
                nonlocal written
                try:
                    while True:
                        raw = process.stdout.read(BLOCK)
                        if not raw:
                            break
                        if written + len(raw) > limit:
                            raise CappedProcessError('output_limit')
                        output.write(raw)
                        written += len(raw)
                except BaseException as error:
                    errors.append(error)
                    failed.set()

            def drain_stderr():
                try:
                    while True:
                        raw = process.stderr.read(BLOCK)
                        if not raw:
                            break
                        retained_stderr.extend(raw[:max(0, stderr_limit-len(retained_stderr))])
                except BaseException as error:
                    errors.append(error)
                    failed.set()

            threads = [threading.Thread(target=drain_stdout, daemon=True),
                       threading.Thread(target=drain_stderr, daemon=True)]
            for thread in threads:
                thread.start()
            started = time.monotonic()
            try:
                while True:
                    check()
                    if cancelled():
                        raise CappedProcessCancelled()
                    if failed.is_set():
                        raise errors[0]
                    if time.monotonic()-started >= timeout:
                        raise CappedProcessError('timeout')
                    if process.poll() is not None and all(not thread.is_alive() for thread in threads):
                        break
                    failed.wait(.02)
                if errors:
                    raise errors[0]
                if process.returncode:
                    raise CappedProcessError('exit_status')
                if not written:
                    raise CappedProcessError('empty_output')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                for thread in threads:
                    thread.join(timeout=5)
                if any(thread.is_alive() for thread in threads):
                    raise CappedProcessError('incomplete_output')
                process.stdout.close()
                process.stderr.close()
            output.flush()
        check()
        if cancelled():
            raise CappedProcessCancelled()
        if written > limit or destination.stat().st_size != written:
            raise CappedProcessError('output_size_changed')
        accepted = True
        return CappedOutput(written, bytes(retained_stderr))
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if not accepted:
            destination.unlink(missing_ok=True)
