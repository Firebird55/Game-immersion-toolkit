"""Real Qt signal ordering with an authored owner; never native UI acceptance."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('mode', ['signal', 'before-quit', 'held-lease'])
def test_ui_records_owned_completion_before_native_quit(tmp_path, mode):
    program = r'''
import json, queue, sys, threading
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from backend import desktop_host_ui
from backend.desktop_ui_probe import DesktopUiProbe

desktop_host_ui.ensure_console = lambda: None
state = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
events = queue.Queue()
host = SimpleNamespace(layout=SimpleNamespace(mode='bundle', state_root=state),
    ready=threading.Event(), stop_requested=threading.Event(), finished=threading.Event(),
    open_requested=threading.Event(), show_logs_requested=threading.Event(),
    lease=SimpleNamespace(held=True), exit_code=0, browser=False, status='Starting',
    log=SimpleNamespace(events=events, write=events.put, close=lambda: None),
    open_browser=lambda _url: False)
def run():
    events.put('Authored owner starting')
    events.put('Authored owner ready')
    host.ready.set()
    if not host.stop_requested.wait(8):
        host.exit_code = 1
    if mode == 'held-lease':
        host.finished.set()
        threading.Event().wait(.7)
    host.lease.held = False
    host.finished.set()
host.run = run
application = QApplication([])
original_exec = application.exec
observed = []
quit_observed = []
held_observed = []
if mode != 'signal':
    # Deliberately remove the signal fallback. The real Qt refresh must retain
    # final ownership evidence before invoking the native quit operation.
    DesktopUiProbe.about_to_quit = lambda self: None
    original_quit = application.quit
    def quit_and_observe():
        value = json.loads((state / 'native-ui-probe.json').read_text())
        quit_observed.append(value['complete'] and value['checks'].get('owned_shutdown')
            and value['checks'].get('quit_action') and host.finished.is_set() and not host.lease.held)
        original_quit()
    application.quit = quit_and_observe
    timer = QTimer()
    def observe_held_owner():
        if host.finished.is_set() and host.lease.held:
            value = json.loads((state / 'native-ui-probe.json').read_text())
            held_observed.append(not value['complete'] and not quit_observed)
    timer.timeout.connect(observe_held_owner)
    timer.start(50)
def exec_and_observe():
    result = original_exec()
    # Inspect before run_ui can reach its post-exec finalizer.
    value = json.loads((state / 'native-ui-probe.json').read_text())
    assert value['complete'] and value['checks']['owned_shutdown']
    assert value['status'] == 'unavailable' and not value['passed']
    observed.append(True)
    return result
application.exec = exec_and_observe
assert desktop_host_ui.run_ui(host, probe=True) == 2
assert observed == [True]
if mode != 'signal':
    assert quit_observed == [True], quit_observed
if mode == 'held-lease':
    assert held_observed and all(held_observed), held_observed
'''
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    completed = subprocess.run([sys.executable, '-c', program, str(tmp_path), mode],
        cwd=Path(__file__).resolve().parents[2], env=environment,
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
    assert completed.returncode == 0, completed.stderr
