"""Real Qt signal ordering with an authored owner; never native UI acceptance."""
import os
from pathlib import Path
import subprocess
import sys


def test_ui_records_quit_signal_before_application_exec_returns(tmp_path):
    program = r'''
import json, queue, sys, threading
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from backend import desktop_host_ui

desktop_host_ui.ensure_console = lambda: None
state = Path(sys.argv[1]).resolve()
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
    host.lease.held = False
    host.finished.set()
host.run = run
application = QApplication([])
original_exec = application.exec
observed = []
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
'''
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    completed = subprocess.run([sys.executable, '-c', program, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2], env=environment,
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
    assert completed.returncode == 0, completed.stderr
