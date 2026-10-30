"""Real descendants catch parent-exit leaks that mocked Popen tests cannot."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

from backend.owned_process import OwnedProcess


def gone(pid, created):
    try:
        process = psutil.Process(pid)
        return process.create_time() != created or process.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def test_owned_descendant_stops_after_its_immediate_parent_exits():
    script = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); print(p.pid,flush=True)"
    owner = OwnedProcess([sys.executable, '-u', '-c', script], text=True)
    child_pid = int(owner.process.stdout.readline())
    created = psutil.Process(child_pid).create_time()
    try:
        owner.process.wait(timeout=10)
        owner.stop()
        assert gone(child_pid, created), 'An exited parent must not leave a writing descendant behind'
    finally:
        owner.stop()
        owner.close_streams()


def test_owner_death_closes_job_or_watchdog_liveness_pipe(tmp_path):
    info = tmp_path / 'owned.json'
    script = tmp_path / 'owner.py'
    script.write_text('''import json,sys,time
from backend.owned_process import OwnedProcess
p=OwnedProcess([sys.executable,'-u','-c','import os,time; print(os.getpid(),flush=True); time.sleep(120)'], text=True)
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'pid':int(p.process.stdout.readline())}))
time.sleep(120)
''', encoding='utf-8')
    root = Path(__file__).resolve().parents[2]
    owner = subprocess.Popen([sys.executable, str(script), str(info)], cwd=root,
        env={**os.environ, 'PYTHONPATH': str(root)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        deadline = time.monotonic() + 10
        while not info.exists() and time.monotonic() < deadline and owner.poll() is None:
            time.sleep(.05)
        assert info.exists(), owner.stderr.read() if owner.poll() is not None else 'Owner did not start'
        child_pid = json.loads(info.read_text())['pid']
        created = psutil.Process(child_pid).create_time()
        owner.kill()
        owner.wait(timeout=5)
        deadline = time.monotonic() + 10
        while not gone(child_pid, created) and time.monotonic() < deadline:
            time.sleep(.05)
        assert gone(child_pid, created), 'An unexpected host exit must stop its owned writer'
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
        owner.stdout.close()
        owner.stderr.close()


def test_text_child_protocol_is_utf8_on_windows():
    owner = OwnedProcess([sys.executable, '-u', '-c', "print('角色・你好',flush=True)"],
                         text=True, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    try:
        assert owner.process.stdout.readline().strip() == '角色・你好'
    finally:
        owner.stop()
        owner.close_streams()
