"""Native report/privacy contracts; these unit tests do not accept a frozen app."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = spec_from_file_location('desktop_native_probe', Path(__file__).resolve().parents[2] / 'scripts/probe-desktop-host.py')
probe = module_from_spec(spec)
spec.loader.exec_module(probe)


def test_runtime_roles_do_not_confuse_guardian_embedded_command_with_api():
    assert probe.child_kind(['app', '--runtime-child', 'owned-process', '--', 'app', '--runtime-child', 'api', '--']) == 'owned-process'
    assert probe.child_kind(['app', '--runtime-child', 'api', '--', '--port', '0']) == 'api'
    assert probe.child_kind(['app', '--runtime-child', 'api']) is None


def test_observation_owns_service_workers_but_never_the_default_browser(monkeypatch, tmp_path):
    class Process:
        def __init__(self, pid, executable, arguments, children=()):
            self.pid, self.executable, self.arguments, self.descendants = pid, executable, arguments, children
        def create_time(self): return 1
        def exe(self): return str(self.executable)
        def cmdline(self): return self.arguments
        def children(self, recursive=False): return self.descendants
    executable = tmp_path / 'runtime.exe'
    codec = Process(4, tmp_path / 'codec.exe', [])
    service = Process(2, executable, ['runtime', '--runtime-child', 'api', '--'], [codec])
    browser = Process(3, tmp_path / 'browser.exe', ['browser', 'http://localhost'])
    host = probe.FrozenHost.__new__(probe.FrozenHost)
    host.executable, host.identity = executable, Process(1, executable, [], [service, browser, codec])
    host.observed, host.service_processes = {}, {}
    monkeypatch.setattr(probe, 'alive', lambda _p: True)
    assert {process.pid for process in host.observe()} == {2, 4}
    assert {process.pid for process in host.service_processes.values()} == {2}
    assert browser not in host.observed.values()


def test_child_environment_drops_credentials_and_developer_runtime(monkeypatch, tmp_path):
    for name in ('PYTHONPATH', 'PYTHONHOME', 'API_KEY', 'PROXY_TRANSCRIPT_ACCOUNT_KEY', 'BROWSER'):
        monkeypatch.setenv(name, 'private-value')
    env = probe.child_environment(tmp_path)
    assert not any(value == 'private-value' for value in env.values())
    assert Path(env['HOME']) == tmp_path / 'home'
    assert Path(env['LOCALAPPDATA']) == tmp_path / 'local'


def test_inventory_hash_binds_exact_file_and_directory_lists():
    value = {'files': [{'path': 'app', 'bytes': 1, 'sha256': 'a' * 64}], 'directories': []}
    before = probe.inventory_identity(value)
    value['directories'].append('extra')
    assert probe.inventory_identity(value) != before


def test_public_identity_rejects_path_shaped_build_id():
    with pytest.raises(probe.ProbeFailure, match='invalid-artifact-identity'):
        probe.public_identity({'profile': 'runtime', 'build_id': '/private/account-key'})


def test_failed_probe_report_does_not_include_paths_or_exception_details(tmp_path, capsys):
    report_path = tmp_path / 'result.json'
    assert probe.probe(tmp_path, tmp_path / 'private-account-key', report_path, 15) == 1
    value = report_path.read_text()
    assert 'private-account-key' not in value and str(tmp_path) not in value
    assert json.loads(value)['passed'] is False
    assert json.loads(capsys.readouterr().out)['checks'] == {}


def test_native_probe_rejects_lease_release_while_service_still_lives(monkeypatch, tmp_path):
    host = probe.FrozenHost.__new__(probe.FrozenHost)
    host.user = tmp_path
    host.service_processes = {(42, 1): object()}
    host.wait = lambda predicate, *_a, **_k: predicate()
    closed = []
    monkeypatch.setattr(probe, 'alive', lambda _p: True)
    monkeypatch.setattr(probe, 'ExclusiveFileLease', lambda _p: SimpleNamespace(acquire=lambda: None, close=lambda: closed.append(True)))
    with pytest.raises(probe.ProbeFailure, match='frozen-lease-released-before-services-stopped'):
        host.verify_stopped(5)
    assert closed == [True]


def test_cleanup_failure_cannot_hide_original_probe_failure_or_report(monkeypatch, tmp_path, capsys):
    receipt = dict(source_commit='a' * 40, build_id='test', profile='runtime', version='1.2.3', files=[], directories=[])
    provenance = tmp_path / 'receipt.json'
    provenance.write_text(json.dumps(receipt))
    monkeypatch.setattr(probe, 'validate', lambda *_a, **_k: None)
    monkeypatch.setattr(probe, 'executable_target', lambda _p: 'windows-x64')
    monkeypatch.setattr(probe, 'digest', lambda _p: 'b' * 64)
    monkeypatch.setattr(probe.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(returncode=0, stdout='{"mode":"bundle"}'))
    class FailedHost:
        def __init__(self, *_a):
            pass
        def wait(self, *_a):
            raise probe.ProbeFailure('authored-failure')
        def cleanup(self):
            raise RuntimeError('private cleanup diagnostics')
    monkeypatch.setattr(probe, 'FrozenHost', FailedHost)
    output = tmp_path / 'result.json'
    assert probe.probe(tmp_path, provenance, output, 15) == 1
    value = json.loads(output.read_text())
    assert value['error'] == 'authored-failure' and value['cleanup_error'] == 'probe-cleanup-incomplete'
    assert value['passed'] is False and 'private cleanup diagnostics' not in capsys.readouterr().out
