"""Exercise process-tree ownership, including the real Windows job boundary."""
import ctypes
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from backend.language_preparation import LanguagePreparation
from backend import preparation_worker as worker


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(.01)
    assert predicate()


def test_failed_tree_cleanup_remains_a_quiesce_failure_after_worker_exit_and_restart(tmp_path, monkeypatch):
    marker = tmp_path / 'started'
    closed = []
    class UnconfirmedTree:
        def command(self, command):
            return command
        def terminate(self):
            raise TimeoutError('Synthetic Windows job drain failure')
        def close(self):
            closed.append(True)
    monkeypatch.setattr(worker, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(worker, 'WindowsPreparationProcess', UnconfirmedTree)
    def build(*_, job):
        script = f'import pathlib,time; pathlib.Path({str(marker)!r}).touch(); time.sleep(60)'
        job.run([sys.executable, '-c', script], cwd=tmp_path, timeout=30)
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {'ready': True},
        path=tmp_path/'languages.json', cancellable=True)
    manager.request('cyberpunk', 'zh-Hans', 'en')
    wait_for(marker.exists)
    with pytest.raises(TimeoutError, match='cleanup could not be confirmed'):
        manager.close()
    assert not manager._workers and closed == [True]
    manager.start()
    assert not manager.request('cyberpunk', 'zh-Hans', 'en')
    with pytest.raises(TimeoutError, match='cleanup could not be confirmed'):
        manager.close()
    assert not manager._workers and not manager._monitors


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows Job Object boundary')
@pytest.mark.parametrize('parent_exits', [False, True])
def test_windows_job_reaps_extraction_child_and_grandchild(tmp_path, parent_exits, monkeypatch):
    marker = tmp_path / 'descendants.json'
    release = tmp_path / 'release-parent'
    grandchild = 'import time; time.sleep(60)'
    child = ('import json,os,pathlib,subprocess,sys,time; '
        f'p=subprocess.Popen([sys.executable,"-c",{grandchild!r}]); '
        f'pathlib.Path({str(marker)!r}).write_text(json.dumps([os.getpid(),p.pid])); time.sleep(60)')
    parent = ('import pathlib,subprocess,sys,time; '
        f'p=subprocess.Popen([sys.executable,"-c",{child!r}]); '
        f'release=pathlib.Path({str(release)!r}); '
        '\nwhile not release.exists(): time.sleep(.01)\n')
    def build(*_, job):
        job.run([sys.executable, '-c', parent], cwd=tmp_path, timeout=30)
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {'ready': True},
        path=tmp_path/'languages.json', cancellable=True)
    # Cancellation cannot depend on the old fallible taskkill subprocess.
    monkeypatch.setattr(subprocess, 'run', lambda *_a, **_k: pytest.fail('No taskkill fallback'))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32], ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes, kernel.WaitForSingleObject.restype = [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handles = []
    try:
        assert manager.request('cyberpunk', 'zh-Hans', 'en')
        wait_for(marker.exists)
        for pid in json.loads(marker.read_text()):
            handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
            assert handle
            handles.append(handle)
        if parent_exits:
            release.touch()
            wait_for(lambda: not manager._workers)
            assert manager.jobs[('cyberpunk', 'zh-Hans')]['state'] == 'ready'
        manager.close()
        assert not manager._workers
        assert all(kernel.WaitForSingleObject(handle, 0) == 0 for handle in handles)
    finally:
        manager.close()
        for handle in handles:
            kernel.CloseHandle(handle)


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows Job Object boundary')
def test_windows_cancellation_reaps_bootstrap_before_it_can_join_the_job(tmp_path, monkeypatch):
    marker, extracted = tmp_path/'bootstrap-started', tmp_path/'must-not-extract'
    original = worker.WindowsPreparationProcess.command
    def delayed(tree, command):
        wrapped = original(tree, command)
        script = ('import pathlib,runpy,sys,time; '
            f'pathlib.Path({str(marker)!r}).touch(); time.sleep(60); '
            f'sys.argv={wrapped[1:]!r}; runpy.run_path(sys.argv[0],run_name="__main__")')
        return [wrapped[0], '-c', script]
    monkeypatch.setattr(worker.WindowsPreparationProcess, 'command', delayed)
    def build(*_, job):
        script = f'import pathlib; pathlib.Path({str(extracted)!r}).touch()'
        job.run([sys.executable, '-c', script], cwd=tmp_path, timeout=30)
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {'ready': True},
        path=tmp_path/'languages.json', cancellable=True)
    try:
        manager.request('cyberpunk', 'zh-Hans', 'en')
        wait_for(marker.exists)
        manager.close()
        assert not manager._workers and not extracted.exists()
    finally:
        manager.close()


@pytest.mark.skipif(os.name != 'nt', reason='Windows venv redirector boundary')
def test_windows_venv_bootstrap_uses_the_retained_real_interpreter(tmp_path):
    import venv
    environment = tmp_path/'venv'
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment/'Scripts/python.exe'
    script = ('import json,sys; '
        'from backend.windows_preparation_process import WindowsPreparationProcess; '
        'tree=WindowsPreparationProcess(); '
        'print(json.dumps({"venv":sys.executable,"bootstrap":tree.command([sys.executable,"-c","pass"])[0]})); '
        'tree.close()')
    result = subprocess.run([str(python), '-c', script], check=True, capture_output=True, text=True, timeout=15)
    paths = json.loads(result.stdout)
    assert os.path.samefile(paths['venv'], python)
    assert not os.path.samefile(paths['bootstrap'], python)
