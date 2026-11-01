"""Fixed frozen preparation startup check with no game or account inputs."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

from .preparation_worker import PreparationJob
from .update_workers import subprocess_options

SCHEMA = 'toolkit-frozen-preparation-probe-v1'


def run(layout, start_control_reader):
    """Exercise the same API reader and preparation launcher used by games."""
    phase = 'layout'
    try:
        if layout.mode != 'bundle' or layout.profile not in {'runtime', 'runtime-experiment'}:
            raise ValueError('Frozen runtime required')
        phase = 'control-reader'
        stopped, ready = threading.Event(), threading.Event()
        reader = start_control_reader(stopped.set, ready=ready)
        if not ready.wait(2):
            raise RuntimeError('Control reader did not start')
        # The signal is set immediately before readline; allow the actual
        # blocking read to enter before creating the preparation bootstrap.
        time.sleep(.05)
        if stopped.is_set() or not reader.is_alive():
            raise RuntimeError('Control input was not retained')
        phase = 'preparation'
        cancelled = threading.Event()
        owner = SimpleNamespace(stop_event=cancelled, _publication_lock=threading.RLock())
        result = PreparationJob(owner, cancelled).run(
            [str(layout.executable), '--runtime-diagnose'], cwd=layout.resource_root,
            timeout=45, **subprocess_options())
        if result != 0 or stopped.is_set() or not reader.is_alive():
            raise RuntimeError('Preparation or control ownership failed')
        # PreparationJob returns only after its bootstrap and descendants have
        # been reaped. A second handshake proves the independent API control
        # reader survived that cleanup and can still shut down normally.
        print(json.dumps({'schema': SCHEMA, 'stage': 'prepared', 'mode': 'bundle',
            'checks': {'preparation_completed': True, 'parent_control_retained': True,
                       'preparation_tree_drained': True}}), flush=True)
        phase = 'control-shutdown'
        if not stopped.wait(20):
            raise RuntimeError('Control shutdown did not arrive')
        reader.join(timeout=2)
        if reader.is_alive():
            raise RuntimeError('Control reader did not stop')
        print(json.dumps({'schema': SCHEMA, 'stage': 'complete', 'mode': 'bundle',
            'checks': {'control_shutdown': True}}), flush=True)
        return 0
    except Exception:
        # Never publish raw exceptions, roots, command arguments or user data.
        print(json.dumps({'schema': SCHEMA, 'stage': 'failed', 'phase': phase,
            'error': 'frozen-preparation-probe-failed'}), flush=True)
        return 1
