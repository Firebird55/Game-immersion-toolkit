"""Real owned Python subprocesses exercise output and cleanup boundaries."""
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from backend.capped_process import run_capped_stdout, CappedProcessError, CappedProcessCancelled


def run(tmp_path, code, **options):
    return run_capped_stdout([sys.executable, '-B', '-c', code], tmp_path/'staging.bin',
        limit=1024, cwd=tmp_path, env=dict(os.environ), cancelled=lambda: False,
        check=lambda: None, timeout=3, **options)


def test_exact_output_and_large_stderr_are_drained_with_bounded_retention(tmp_path):
    result = run(tmp_path, "import os; os.write(2,b'e'*1048576); os.write(1,b'x'*1024)", stderr_limit=17)
    assert result.bytes == 1024 and result.stderr == b'e'*17
    assert (tmp_path/'staging.bin').read_bytes() == b'x'*1024


@pytest.mark.parametrize('code,reason', [
    ("import os; os.write(1,b'x'*1025)", 'output_limit'),
    ("import os; os.write(1,b'prefix'); raise SystemExit(3)", 'exit_status'),
    ("pass", 'empty_output'),
])
def test_rejected_output_is_never_left_as_an_accepted_prefix(tmp_path, code, reason):
    with pytest.raises(CappedProcessError) as caught: run(tmp_path, code)
    assert caught.value.reason == reason and not (tmp_path/'staging.bin').exists()


def test_timeout_kills_waits_and_cleans_staging(tmp_path):
    started = time.monotonic()
    with pytest.raises(CappedProcessError) as caught:
        run_capped_stdout([sys.executable, '-B', '-c', "import time; print('prefix',flush=True); time.sleep(10)"],
            tmp_path/'staging.bin', limit=1024, cwd=tmp_path, env=dict(os.environ),
            cancelled=lambda: False, check=lambda: None, timeout=.15)
    assert caught.value.reason == 'timeout' and time.monotonic()-started < 5
    assert not (tmp_path/'staging.bin').exists()


def test_actual_running_process_cancellation_waits_and_preserves_previous_output(tmp_path):
    previous = tmp_path/'previous.mp3'; previous.write_bytes(b'old immutable MP3')
    signal = threading.Event(); timer = threading.Timer(.15, signal.set); timer.start()
    try:
        with pytest.raises(CappedProcessCancelled):
            run_capped_stdout([sys.executable, '-B', '-c', "import time; print('prefix',flush=True); time.sleep(10)"],
                tmp_path/'staging.bin', limit=1024, cwd=tmp_path, env=dict(os.environ),
                cancelled=signal.is_set, check=lambda: None, timeout=3)
    finally: timer.join()
    assert not (tmp_path/'staging.bin').exists() and previous.read_bytes() == b'old immutable MP3'


def test_existing_destination_cannot_be_replaced_even_on_success(tmp_path):
    path = tmp_path/'staging.bin'; path.write_bytes(b'existing bytes')
    with pytest.raises(FileExistsError): run(tmp_path, "print('new')")
    assert path.read_bytes() == b'existing bytes'


def test_context_guard_failure_kills_running_process_and_removes_staging(tmp_path):
    calls = 0
    def check():
        nonlocal calls
        calls += 1
        if calls > 3: raise RuntimeError('authored source/account cancellation')
    with pytest.raises(RuntimeError, match='source/account'):
        run_capped_stdout([sys.executable, '-B', '-c', "import time; print('prefix',flush=True); time.sleep(10)"],
            tmp_path/'staging.bin', limit=1024, cwd=tmp_path, env=dict(os.environ),
            cancelled=lambda: False, check=check, timeout=3)
    assert not (tmp_path/'staging.bin').exists()


@pytest.mark.parametrize('timeout', [float('nan'), float('inf'), -1, True])
def test_unbounded_or_invalid_timeout_cannot_start_a_process(tmp_path, timeout):
    with pytest.raises(ValueError):
        run_capped_stdout([sys.executable, '-B', '-c', 'pass'], tmp_path/'staging.bin',
            limit=1024, cwd=tmp_path, env=dict(os.environ), cancelled=lambda: False,
            check=lambda: None, timeout=timeout)
    assert not (tmp_path/'staging.bin').exists()
