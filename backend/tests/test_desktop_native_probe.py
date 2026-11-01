"""Native report/privacy contracts; these unit tests do not accept a frozen app."""
from importlib.util import module_from_spec, spec_from_file_location
import json
import io
from pathlib import Path
import threading
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
    monkeypatch.setenv('XAUTHORITY', str(tmp_path / 'owned-display-cookie'))
    env = probe.child_environment(tmp_path)
    assert not any(value == 'private-value' for value in env.values())
    assert Path(env['HOME']) == tmp_path / 'home'
    assert Path(env['LOCALAPPDATA']) == tmp_path / 'local'
    assert Path(env['XAUTHORITY']) == tmp_path / 'owned-display-cookie'


def test_inventory_hash_binds_exact_file_and_directory_lists():
    value = {'files': [{'path': 'app', 'bytes': 1, 'sha256': 'a' * 64}], 'directories': []}
    before = probe.inventory_identity(value)
    value['directories'].append('extra')
    assert probe.inventory_identity(value) != before


@pytest.mark.parametrize('error', ['native-ui-timeout', 'private-account-key'])
def test_ui_report_keeps_only_fixed_failure_codes(tmp_path, error):
    state = tmp_path / 'state'
    state.mkdir()
    (state / 'native-ui-probe.json').write_text(json.dumps({
        'schema': 'toolkit-desktop-ui-observation-v1', 'mode': 'bundle',
        'status': 'failed', 'passed': False, 'checks': {'default_browser_request': True},
        'error': error,
    }))
    host = SimpleNamespace(user=tmp_path, process=SimpleNamespace(returncode=1),
        wait=lambda *_a, **_k: None, verify_stopped=lambda _timeout: None)
    value = probe.check_ui(host, 15)
    assert value['passed'] is False and value['browser_navigation'] == 'unverified'
    assert value.get('error') == ('native-ui-timeout' if error == 'native-ui-timeout' else None)


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
    monkeypatch.setattr(probe, 'check_preparation', lambda *_a: None)
    monkeypatch.setattr(probe.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(returncode=0, stdout='{"mode":"bundle"}'))
    class FailedHost:
        def __init__(self, *_a):
            pass
        def wait(self, *_a):
            raise probe.ProbeFailure('authored-failure')
        def cleanup(self):
            raise RuntimeError('private cleanup diagnostics')
        def public_observation(self):
            raise RuntimeError('private observation diagnostics')
    monkeypatch.setattr(probe, 'FrozenHost', FailedHost)
    output = tmp_path / 'result.json'
    assert probe.probe(tmp_path, provenance, output, 15) == 1
    value = json.loads(output.read_text())
    assert value['error'] == 'authored-failure' and value['cleanup_error'] == 'probe-cleanup-incomplete'
    assert value['passed'] is False and 'private cleanup diagnostics' not in capsys.readouterr().out
    assert value['observation_error'] == 'host-observation-unavailable'
    assert 'private observation diagnostics' not in output.read_text()


@pytest.mark.parametrize('failure', [None, 'early-eof', 'child-failed', 'unfrozen', 'missing-check', 'non-boolean', 'no-shutdown'])
def test_frozen_preparation_handshake_requires_both_stages_and_drains_owner(monkeypatch, tmp_path, failure):
    prepared = {'schema': 'toolkit-frozen-preparation-probe-v1', 'mode': 'bundle', 'stage': 'prepared',
        'checks': {'preparation_completed': True, 'parent_control_retained': True, 'preparation_tree_drained': True}}
    complete = {'schema': 'toolkit-frozen-preparation-probe-v1', 'mode': 'bundle', 'stage': 'complete',
        'checks': {'control_shutdown': True}}
    if failure == 'unfrozen':
        prepared['mode'] = 'source'
    if failure == 'missing-check':
        del prepared['checks']['preparation_tree_drained']
    if failure == 'non-boolean':
        prepared['checks']['preparation_tree_drained'] = 1
    values = [] if failure == 'early-eof' else [prepared]
    if failure != 'no-shutdown':
        values.append(complete)
    process = SimpleNamespace(stdout=io.StringIO(''.join(json.dumps(value)+'\n' for value in values)),
        stdin=io.StringIO(), wait=lambda **_: 1 if failure == 'child-failed' else 0)
    calls, cleanup = [], []
    def own(command, **options):
        calls.append((command, options))
        return SimpleNamespace(process=process, stop=lambda **_: cleanup.append('drained'),
            close_streams=lambda: cleanup.append('closed'))
    monkeypatch.setattr(probe, 'OwnedProcess', own)
    executable = tmp_path/'GameImmersionToolkit'
    if failure:
        with pytest.raises(probe.ProbeFailure):
            probe.check_preparation(executable, tmp_path, {}, 15)
    else:
        probe.check_preparation(executable, tmp_path, {}, 15)
        assert process.stdin.getvalue() == 'shutdown\n'
    assert cleanup == ['drained', 'closed']
    command, options = calls[0]
    assert command == [str(executable), '--runtime-child', 'api', '--', '--preparation-probe', '--shutdown-stdin']
    assert options['stdin'] == probe.subprocess.PIPE
    assert Path(options['env']['PROXY_TRANSCRIPT_DATA_ROOT']).parent == tmp_path


def test_ui_missing_observation_has_a_fixed_public_failure_code(tmp_path):
    host = SimpleNamespace(user=tmp_path, process=SimpleNamespace(returncode=0),
        wait=lambda *_a, **_k: None, verify_stopped=lambda _timeout: None)
    with pytest.raises(probe.ProbeFailure, match='^missing-frozen-ui-observation$'):
        probe.check_ui(host, 15)


def test_incomplete_ui_observation_cannot_pass_even_if_host_exits_zero(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    value = {'schema': 'toolkit-desktop-ui-observation-v1', 'mode': 'bundle',
        'status': 'failed', 'passed': False, 'complete': False, 'phase': 'stopping',
        'checks': {'status_window': True}, 'error': 'native-ui-timeout',
        'browser_diagnostics': {'browser': {'1': 'waiting-reader'},
            'http': {'document': 200, 'snapshot': 'private token'}, 'private-key': 'secret'}}
    path = state / 'native-ui-probe.json'
    path.write_text(json.dumps(value))
    host = SimpleNamespace(user=tmp_path, process=SimpleNamespace(returncode=0),
        wait=lambda *_a, **_k: None, verify_stopped=lambda _timeout: None)
    result = probe.check_ui(host, 15)
    assert result['status'] == 'failed' and not result['observation_complete']
    assert result['checks']['status_window'] and result['error'] == 'native-ui-timeout'
    assert result['observation_phase'] == 'stopping'
    assert result['browser_diagnostics'] == {'browser': {'1': 'waiting-reader'}, 'http': {'document': 200}}
    value.update(status='passed', passed=True)
    path.write_text(json.dumps(value))
    with pytest.raises(probe.ProbeFailure, match='invalid-frozen-ui-observation'):
        probe.check_ui(host, 15)


def test_process_log_observation_keeps_only_fixed_diagnostic_codes():
    host = probe.FrozenHost.__new__(probe.FrozenHost)
    host.port, host.diagnostics = None, set()
    host.stdout_closed = threading.Event()
    host.process = SimpleNamespace(poll=lambda: -6, stdout=io.StringIO(
        'private account key and /private/profile\n'
        'Traceback (most recent call last):\n'
        'Fatal Python error: private details\n'
        '[Host] Transcript ready at http://127.0.0.1:12345.\n'))
    host._read()
    assert host.stdout_closed.is_set()
    assert host.public_observation() == {'exit_code': -6, 'ready_socket_reported': True,
        'log_diagnostics': ['python-fatal-error', 'python-traceback']}
    assert 'private' not in json.dumps(host.public_observation())
