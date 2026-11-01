"""Authored protocol checks; only the hosted frozen run establishes acceptance."""
import json
from types import SimpleNamespace

import pytest

from backend import main, preparation_probe as probe


def test_api_probe_uses_fixed_entrypoint_without_starting_game_services(monkeypatch):
    from backend import runtime_bundle
    layout = object()
    monkeypatch.setattr(main.sys, 'argv', ['api', '--preparation-probe', '--shutdown-stdin'])
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
    monkeypatch.setattr(main.uvicorn, 'Config', lambda *_a, **_k: pytest.fail('No game service initialization'))
    calls = []
    monkeypatch.setattr(probe, 'run', lambda *args: calls.append(args) or 7)
    assert main.main() == 7
    assert calls == [(layout, main.start_stdin_shutdown)]


def test_api_probe_requires_owned_shutdown_input(monkeypatch):
    monkeypatch.setattr(main.sys, 'argv', ['api', '--preparation-probe'])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 2


@pytest.mark.parametrize('failure', [None, 'source', 'closed-input', 'child', 'exception'])
def test_probe_requires_frozen_job_and_independent_control_handshake(monkeypatch, tmp_path, failure):
    emitted, jobs, callbacks = [], [], []
    stopped = [False]
    layout = SimpleNamespace(mode='source' if failure == 'source' else 'bundle', profile='runtime',
        executable=tmp_path/'GameImmersionToolkit', resource_root=tmp_path/'resources')
    def start(callback, *, ready):
        ready.set()
        def close():
            stopped[0] = True
            callback()
        callbacks.append(close)
        if failure == 'closed-input':
            close()
        return SimpleNamespace(is_alive=lambda: not stopped[0], join=lambda **_: None)
    class Job:
        def __init__(self, owner, cancelled):
            assert owner.stop_event is cancelled and not cancelled.is_set()
        def run(self, command, **options):
            jobs.append((command, options))
            if failure == 'exception':
                raise OSError('private game path and account details')
            return 1 if failure == 'child' else 0
    def emit(value, **_):
        report = json.loads(value)
        emitted.append(report)
        if report['stage'] == 'prepared':
            callbacks[0]()
    monkeypatch.setattr(probe, 'print', emit, raising=False)
    monkeypatch.setattr(probe, 'PreparationJob', Job)
    monkeypatch.setattr(probe, 'subprocess_options', lambda: {'env': {'authored': 'environment'}})
    monkeypatch.setattr(probe.time, 'sleep', lambda _: None)
    assert probe.run(layout, start) == (1 if failure else 0)
    if failure:
        assert emitted[-1]['stage'] == 'failed'
        assert 'private' not in json.dumps(emitted)
    else:
        assert [item['stage'] for item in emitted] == ['prepared', 'complete']
        assert emitted[0]['checks']['preparation_tree_drained'] is True
        assert jobs == [([str(layout.executable), '--runtime-diagnose'],
            {'cwd': layout.resource_root, 'timeout': 45, 'env': {'authored': 'environment'}})]
        assert stopped[0]
    if failure in {'source', 'closed-input'}:
        assert not jobs
