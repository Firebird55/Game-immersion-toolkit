"""Real descendants catch parent-exit leaks that mocked Popen tests cannot."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
import pytest

from backend.owned_process import OwnedProcess


def gone(pid, created):
    try:
        process = psutil.Process(pid)
        return process.create_time() != created or process.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def test_owned_descendant_stops_after_its_immediate_parent_exits():
    script = "import subprocess,sys,psutil,json; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); print(json.dumps([p.pid,psutil.Process(p.pid).create_time()]),flush=True)"
    owner = OwnedProcess([sys.executable, '-u', '-c', script], text=True)
    child_pid, created = json.loads(owner.process.stdout.readline())
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


def test_nested_owned_helpers_cannot_outlive_top_level_service_crash():
    leaf = 'import os,psutil,json,time; print(json.dumps([os.getpid(),psutil.Process().create_time()]),flush=True); time.sleep(120)'
    middle = ('import sys,time,json,os,psutil; from backend.owned_process import OwnedProcess; '
              f'p=OwnedProcess([sys.executable,"-u","-c",{leaf!r}],text=True); '
              'print(json.dumps([[os.getpid(),psutil.Process().create_time()],json.loads(p.process.stdout.readline())]),flush=True); time.sleep(120)')
    parent = ('import sys,os; from backend.owned_process import OwnedProcess; '
              f'p=OwnedProcess([sys.executable,"-u","-c",{middle!r}],text=True); '
              'print(p.process.stdout.readline().strip(),flush=True); os._exit(17)')
    root = Path(__file__).resolve().parents[2]
    owner = OwnedProcess([sys.executable, '-u', '-c', parent], text=True,
                         env={**os.environ, 'PYTHONPATH': str(root)}, independent_session=True)
    try:
        identities = json.loads(owner.process.stdout.readline())
        owner.process.wait(timeout=15)
        owner.stop()
        assert all(gone(*identity) for identity in identities), 'Nested helper escaped outer ownership'
    finally:
        owner.stop()
        owner.close_streams()


def test_parent_death_retains_installation_lease_until_descendants_stop(tmp_path):
    from backend.bundle_host import ExclusiveFileLease, HostProbeError
    lock_path, info_path = tmp_path / 'operation.lock', tmp_path / 'ready.json'
    root = Path(__file__).resolve().parents[2]
    leaf = 'import os,psutil,json,time; print(json.dumps([os.getpid(),psutil.Process().create_time()]),flush=True); time.sleep(120)'
    code = ('import sys,time,json; from pathlib import Path; '
            'from backend.bundle_host import ExclusiveFileLease; from backend.owned_process import OwnedProcess; '
            'lease=ExclusiveFileLease(Path(sys.argv[1])); lease.acquire(); '
            f'p=OwnedProcess([sys.executable,"-u","-c",{leaf!r}],text=True,retained_fds=lease.retained_descriptors()); '
            'Path(sys.argv[2]).write_text(p.process.stdout.readline()); time.sleep(120)')
    parent = subprocess.Popen([sys.executable, '-u', '-c', code, str(lock_path), str(info_path)],
        cwd=root, env={**os.environ, 'PYTHONPATH': str(root)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lease = ExclusiveFileLease(lock_path)
    try:
        deadline = time.monotonic() + 10
        while not info_path.exists() and parent.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert info_path.exists()
        identity = json.loads(info_path.read_text())
        parent.kill()
        parent.wait(timeout=5)
        while time.monotonic() < deadline:
            try:
                lease.acquire()
            except HostProbeError:
                time.sleep(.02)
                continue
            assert gone(*identity), 'A replacement acquired the lease before owned writer exit'
            break
        else:
            pytest.fail('Owned watchdog failed to release the lease after verified shutdown')
    finally:
        lease.close()
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        parent.stdout.close()
        parent.stderr.close()


@pytest.mark.skipif(os.name != 'nt', reason='Retained outer Windows Job after guardian failure')
def test_guardian_crash_still_leaves_host_with_verified_job_ownership(tmp_path):
    from backend.bundle_host import ExclusiveFileLease
    lease = ExclusiveFileLease(tmp_path / 'operation.lock')
    lease.acquire()
    leaf = 'import os,psutil,json,time; print(json.dumps([os.getpid(),psutil.Process().create_time()]),flush=True); time.sleep(120)'
    owner = OwnedProcess([sys.executable, '-u', '-c', leaf], text=True,
        independent_session=True, retained_fds=lease.retained_descriptors())
    try:
        identity = json.loads(owner.process.stdout.readline())
        owner.process.kill()
        owner.process.wait(timeout=5)
        owner.stop()
        assert gone(*identity), 'Guardian crash lost the retained descendant Job'
        assert lease.held
    finally:
        owner.stop()
        owner.close_streams()
        lease.close()
