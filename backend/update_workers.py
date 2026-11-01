"""Resource limits shared by game-data refreshes; OCR never takes this lock."""
from __future__ import annotations

import os
import subprocess
import threading
from .runtime_bundle import discover_layout
from .owned_process import OwnedProcess

INDEX_BUILD_LOCK = threading.Lock()


def stop_process(process) -> None:
    owner = getattr(process, '_toolkit_owner', None)
    if owner is not None:
        owner.stop()
        return
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        process.terminate()


def start_process(command, **options):
    # Keep ownership on the retained Popen object so existing communicate/wait
    # users cannot lose the descendant tree when the immediate child exits.
    options.pop('creationflags', None)
    owner = OwnedProcess(command, **options)
    owner.process._toolkit_owner = owner
    return owner.process


def subprocess_options() -> dict:
    environment = discover_layout().child_environment()
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        environment[name] = '1'
    return {
        'env': environment,
        'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                         | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0),
    }
