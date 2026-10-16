"""Resource limits shared by game-data refreshes; OCR never takes this lock."""
from __future__ import annotations

import os
import subprocess
import threading

INDEX_BUILD_LOCK = threading.Lock()


def stop_process(process) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        process.terminate()


def subprocess_options() -> dict:
    environment = dict(os.environ)
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        environment[name] = '1'
    return {
        'env': environment,
        'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                         | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0),
    }
