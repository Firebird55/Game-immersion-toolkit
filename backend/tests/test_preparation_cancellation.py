"""Owned synthetic processes exercise the real builder's cancellation boundary."""
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from backend import api
from backend.language_preparation import LanguagePreparation
from backend.preparation_worker import PreparationJob
from backend.update_workers import INDEX_BUILD_LOCK


RUN_EXTRACTION = PreparationJob.run
SPAWN = subprocess.Popen


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(.005)
    assert predicate()


@pytest.fixture
def builder(tmp_path, monkeypatch):
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path / 'data')
    install = tmp_path / 'synthetic-install'
    install.mkdir()
    runtime = api.Runtime.__new__(api.Runtime)
    runtime.setup_install = lambda _: install
    adapter = SimpleNamespace(index_language=True, LANGUAGE_INDEX_VERSION=1, fingerprint=lambda _: 'fixture')
    monkeypatch.setattr('backend.game_assets.asset_adapter', lambda _: (adapter, None))
    activations = []
    manager = LanguagePreparation(runtime.build_language, lambda *args: activations.append(args),
        lambda *_: {'ready': True, 'audio_count': 1}, path=tmp_path / 'languages.json',
        supported=lambda _: ('en',), cancellable=True)
    runtime.languages = manager
    path = api.DATA_DIR / 'languages/beyond/en/textmap.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'format': 2, 'game': 'beyond', 'source_locale': 'en', 'records': [
        {'text_id': 'previous', 'source_locale': 'en', 'source_text': 'Previous complete line',
         'audio_locale': 'en', 'texts': {'en': 'Previous complete line'}, 'audio': None}]}), encoding='utf-8')
    from backend.multilingual_index import MultilingualTextIndex
    assert MultilingualTextIndex('beyond', path.parent).ready
    yield SimpleNamespace(runtime=runtime, manager=manager, path=path, original=path.read_bytes(), activations=activations, adapter=adapter)
    manager.close()


def synthetic_extraction(monkeypatch, tmp_path, *, blocked=False):
    """Replace only the extraction command; retain real Popen/kill/wait ownership."""
    started = tmp_path / 'child-started'
    processes = []
    def spawn(*args, **kwargs):
        process = SPAWN(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr('backend.preparation_worker.subprocess.Popen', spawn)
    def extract(job, command, **kwargs):
        output = command[command.index('--output') + 1]
        payload = {'format': 2, 'game': 'beyond', 'source_locale': 'en', 'records': [
            {'text_id': 'fixture', 'source_locale': 'en', 'source_text': 'Synthetic line',
             'audio_locale': 'en', 'texts': {'en': 'Synthetic line', 'nl': 'Synthetische regel'},
             'audio': None}]}
        script = ('import json, pathlib, time; '
                  f'pathlib.Path({str(started)!r}).write_text("ready"); '
                  + ('time.sleep(60); ' if blocked else '')
                  + f'pathlib.Path({output!r}).write_text({json.dumps(payload)!r})')
        return RUN_EXTRACTION(job, [sys.executable, '-c', script], **kwargs)
    monkeypatch.setattr(PreparationJob, 'run', extract)
    return started, processes


def test_close_kills_and_joins_owned_extraction_without_replacing_complete_index(builder, monkeypatch, tmp_path):
    started, processes = synthetic_extraction(monkeypatch, tmp_path, blocked=True)
    manager = builder.manager
    assert manager.request('beyond', 'en', 'nl', 'first')
    wait_for(started.exists)
    old_token = manager.stop_event
    begin = time.monotonic()
    manager.close(timeout=3)
    assert time.monotonic() - begin < 3
    assert processes[0].poll() is not None
    assert not manager._workers and old_token.is_set()
    assert builder.path.read_bytes() == builder.original
    assert not manager.path.exists() and not builder.activations
    assert not list(builder.path.parent.glob('language-*'))
    assert not manager.request('beyond', 'en', 'nl')
    requests = manager.path.with_suffix('.requests.json')
    assert json.loads(requests.read_text(encoding='utf-8')) == {
        'first': {'beyond': {'locale': 'en', 'target': 'nl'}}}

    synthetic_extraction(monkeypatch, tmp_path)
    restarted = LanguagePreparation(manager.build, manager.activate, manager.state,
        path=manager.path, supported=manager.supported, cancellable=True)
    builder.runtime.languages = restarted
    try:
        restarted.start()
        assert restarted.stop_event is not old_token and old_token.is_set()
        wait_for(lambda: restarted.selected('beyond', 'first') == 'en' and not restarted._workers)
        assert json.loads(builder.path.read_text())['records'][0]['source_text'] == 'Synthetic line'
        assert restarted.selected_target('beyond', 'en', 'first') == 'nl'
        assert builder.activations == [('beyond', 'en', 'first')]
        assert not requests.exists()
    finally:
        restarted.close()


def test_waiting_for_index_build_lock_is_cancellable_without_launching_process(builder, monkeypatch):
    monkeypatch.setattr(PreparationJob, 'run', lambda *_a, **_k: pytest.fail('A cancelled queued build must not spawn'))
    with INDEX_BUILD_LOCK:
        assert builder.manager.request('beyond', 'en', 'nl')
        builder.manager.close(timeout=1)
    assert not builder.manager._workers
    assert builder.path.read_bytes() == builder.original
    assert not builder.manager.path.exists()
    assert builder.manager.entries() == [('beyond', 'en', ('nl',))]
    builder.manager.remove('beyond', 'en')
    assert not builder.manager.entries()
    assert not builder.manager.path.with_suffix('.requests.json').exists()


def test_failed_quiesce_then_restart_cannot_publish_retired_candidate(builder, monkeypatch, tmp_path):
    synthetic_extraction(monkeypatch, tmp_path)
    entered, release = threading.Event(), threading.Event()
    fresh_entered, fresh_release = threading.Event(), threading.Event()
    publication = PreparationJob.publication
    old_token = builder.manager.stop_event
    @contextmanager
    def before_replace(job):
        # The first gate owns Popen; the second gate guards atomic replacement.
        if job.cancelled is old_token and any(builder.path.parent.glob('language-*/textmap.json')):
            entered.set()
            assert release.wait(5)
        with publication(job):
            yield
    monkeypatch.setattr(PreparationJob, 'publication', before_replace)
    manager = builder.manager
    build = manager.build
    def held_build(*args, job):
        if job.cancelled is not old_token:
            fresh_entered.set()
            assert fresh_release.wait(5)
        build(*args, job=job)
    manager.build = held_build
    try:
        assert manager.request('beyond', 'en', 'nl', 'first')
        assert entered.wait(3)
        old_worker = next(iter(manager._workers))
        begin = time.monotonic()
        with pytest.raises(TimeoutError, match='quiesce deadline'):
            manager.close(timeout=.05)
        assert time.monotonic() - begin < .5
        assert builder.path.read_bytes() == builder.original
        assert not manager.path.exists() and not builder.activations
        manager.start()
        assert manager.stop_event is not old_token and old_token.is_set()
        assert fresh_entered.wait(3)
        assert not manager.request('beyond', 'en', 'nl', 'second'), 'Coalesce onto the resumed build'
        release.set()
        old_worker.join(timeout=3)
        assert not old_worker.is_alive()
        assert builder.path.read_bytes() == builder.original
        assert not manager.path.exists() and not builder.activations
        assert manager.selected('beyond', 'first') is None
        assert manager.selected('beyond', 'second') is None
        fresh_release.set()
        wait_for(lambda: not manager._workers)
        assert manager.selected('beyond', 'first') == 'en'
        assert manager.selected('beyond', 'second') == 'en'
        assert builder.activations == [('beyond', 'en', 'first'), ('beyond', 'en', 'second')]
        assert manager.jobs[('beyond', 'en')]['state'] == 'ready'
    finally:
        release.set()
        fresh_release.set()


def test_cancel_during_state_read_prevents_metadata_and_activation(tmp_path):
    entered, release = threading.Event(), threading.Event()
    activated = []
    def state(*_):
        entered.set()
        assert release.wait(5)
        return {'ready': True}
    manager = LanguagePreparation(lambda *_: None, lambda *_: activated.append(True), state,
        path=tmp_path / 'languages.json')
    try:
        manager.request('cyberpunk', 'zh-Hans', 'en')
        assert entered.wait(1)
        with pytest.raises(TimeoutError):
            manager.close(timeout=.05)
        release.set()
        manager.close(timeout=1)
        assert not manager.path.exists() and not activated
    finally:
        release.set()
        manager.close()


def test_close_waits_for_activation_and_reports_deadline_instead_of_false_success(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def activate(*_):
        entered.set()
        assert release.wait(5)
    manager = LanguagePreparation(lambda *_: None, activate, lambda *_: {'ready': True},
        path=tmp_path / 'languages.json')
    try:
        manager.request('cyberpunk', 'zh-Hans', 'en')
        assert entered.wait(1)
        with pytest.raises(TimeoutError):
            manager.close(timeout=.05)
        release.set()
        manager.close(timeout=1)
        saved = manager.path.read_bytes()
        assert not manager._workers
        assert manager.path.read_bytes() == saved
    finally:
        release.set()
        manager.close()


def test_runtime_stop_awaits_worker_close_without_blocking_event_loop_and_propagates_failure():
    entered, release = threading.Event(), threading.Event()
    def close():
        entered.set()
        assert release.wait(2)
        raise TimeoutError('synthetic quiesce deadline')
    runtime = SimpleNamespace(_updates_started=True, languages=SimpleNamespace(close=close))
    async def run():
        task = asyncio.create_task(api.Runtime.stop_updates(runtime))
        try:
            await asyncio.to_thread(entered.wait, 1)
            assert entered.is_set() and not task.done()
            await asyncio.sleep(.01)
            release.set()
            with pytest.raises(TimeoutError, match='quiesce deadline'):
                await task
        finally:
            release.set()
    asyncio.run(run())
    assert not runtime._updates_started


def test_quiesce_failure_keeps_old_capture_active(monkeypatch):
    from fastapi.testclient import TestClient
    stopped = []
    async def fail():
        raise TimeoutError('synthetic quiesce deadline')
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(standby=False, quiesce=fail,
        capture=SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True), stop=lambda: stopped.append(True))), raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767', raise_server_exceptions=False)
    response = client.post('/api/runtime/quiesce', headers={'X-Proxy-Transcript': 'update'})
    assert response.status_code == 503
    assert not stopped


def test_close_cancels_every_parallel_language_worker_and_process(tmp_path, monkeypatch):
    processes = []
    def spawn(*args, **kwargs):
        child = SPAWN(*args, **kwargs)
        processes.append(child)
        return child
    monkeypatch.setattr('backend.preparation_worker.subprocess.Popen', spawn)
    def build(_game, locale, _targets, *, job):
        script = f'import pathlib, time; pathlib.Path({str(tmp_path / locale)!r}).touch(); time.sleep(60)'
        job.run([sys.executable, '-c', script], cwd=tmp_path, timeout=1800)
    manager = LanguagePreparation(build, lambda *_: pytest.fail('Cancelled work must not activate'),
        lambda *_: {'ready': True}, path=tmp_path / 'languages.json', supported=lambda _: ('en', 'nl'), cancellable=True)
    try:
        assert manager.request('beyond', 'en', 'nl')
        assert manager.request('beyond', 'nl', 'en')
        wait_for(lambda: (tmp_path / 'en').exists() and (tmp_path / 'nl').exists())
        manager.close(timeout=3)
        assert len(processes) >= 2 and all(process.poll() is not None for process in processes)
        assert not manager._workers and not manager.path.exists()
    finally:
        manager.close()


def test_extraction_timeout_reaps_child_and_reports_failure_without_metadata(tmp_path, monkeypatch):
    processes = []
    def spawn(*args, **kwargs):
        child = SPAWN(*args, **kwargs)
        processes.append(child)
        return child
    monkeypatch.setattr('backend.preparation_worker.subprocess.Popen', spawn)
    def build(_game, _locale, _targets, *, job):
        job.run([sys.executable, '-c', 'import time; time.sleep(60)'], cwd=tmp_path, timeout=.1)
    manager = LanguagePreparation(build, lambda *_: pytest.fail('Timed-out work must not activate'),
        lambda *_: {'ready': True}, path=tmp_path / 'languages.json', cancellable=True)
    try:
        manager.request('cyberpunk', 'zh-Hans', 'en')
        wait_for(lambda: not manager._workers)
        assert processes and all(process.poll() is not None for process in processes)
        assert manager.jobs[('cyberpunk', 'zh-Hans')]['state'] == 'error'
        assert not manager.path.exists()
    finally:
        manager.close()


def test_all_supported_language_adapters_have_owned_subprocess_builders():
    from backend.game_assets import asset_adapter
    from backend.languages import GAME_LOCALES
    assert all(callable(getattr(asset_adapter(game)[0], 'index_language', None)) for game in GAME_LOCALES)


def test_cancellable_builder_never_falls_back_to_an_unowned_legacy_updater(builder, monkeypatch):
    monkeypatch.setattr('backend.game_assets.asset_adapter', lambda _: (SimpleNamespace(), None))
    builder.runtime.update_manager = SimpleNamespace(check_once=lambda: pytest.fail('Unowned legacy build'))
    job = PreparationJob(builder.manager, builder.manager.stop_event)
    with pytest.raises(ValueError, match='cancellable language snapshot'):
        builder.runtime.build_language('zzz', 'zh-Hans', ('en',), job=job)
    assert builder.path.read_bytes() == builder.original


def test_first_monitor_start_preserves_foreground_preparation_in_standby(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    activated = []
    def build(*_, job):
        entered.set()
        assert release.wait(3)
        job.checkpoint()
    manager = LanguagePreparation(build, lambda *args: activated.append(args), lambda *_: {'ready': True},
        path=tmp_path / 'languages.json', cancellable=True)
    token = manager.stop_event
    scanned = threading.Event()
    refresh = manager.refresh_prepared
    def observed_refresh():
        refresh()
        scanned.set()
    monkeypatch.setattr(manager, 'refresh_prepared', observed_refresh)
    try:
        assert manager.request('cyberpunk', 'zh-Hans', 'en', 'owner')
        assert entered.wait(1)
        manager.start()
        assert scanned.wait(1), 'The initial monitor scan completes while foreground preparation is in flight'
        assert manager.stop_event is token and not token.is_set()
        release.set()
        wait_for(lambda: not manager._workers)
        assert manager.selected('cyberpunk', 'owner') == 'zh-Hans'
        assert activated == [('cyberpunk', 'zh-Hans', 'owner')]
    finally:
        release.set()
        manager.close()


def test_failed_quiesce_blocks_rollback_until_every_worker_is_joined(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.runtime_handoff import CaptureHandoff
    from backend.runtime_workers import RequestBarrier
    entered, release = threading.Event(), threading.Event()
    resumed, resume_release = threading.Event(), threading.Event()
    audio_restarts, activated, capture_events = [], [], []
    runtime = api.Runtime.__new__(api.Runtime)
    runtime.standby = False
    runtime._updates_started = True
    runtime._quiesce_task = runtime._handoff_state = None
    runtime.request_barrier = RequestBarrier()
    runtime.textmaps = runtime.pragmata = None
    runtime.hito = SimpleNamespace(close=lambda: None, resume=lambda: None)
    runtime.installation = SimpleNamespace(pause=lambda: None, resume=lambda: None)
    runtime.mobile_exports = SimpleNamespace(drain=lambda: None, resume=lambda: None)
    runtime.worker_pools = lambda: []
    runtime.repair_task = runtime.index_task = runtime.map_task = None
    runtime.update_manager = runtime.pragmata_updater = SimpleNamespace(close=lambda: None)
    runtime.game_updaters = {}
    runtime.game_indexes, runtime.warm_task = {}, None
    runtime.start_audio_repair = lambda: audio_restarts.append(True)
    running = [True]
    async def stop_capture():
        running[0] = False
        capture_events.append('stop')
    def start_capture():
        running[0] = True
        capture_events.append('start')
    runtime.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=running[0]),
        stop=stop_capture, start=start_capture,
        import_handoff=lambda state: capture_events.append(state.session_id),
        export_handoff=lambda active: CaptureHandoff(running=active, session_id='preserved'))
    def build(*_, job):
        if job.cancelled is old_token:
            entered.set()
            assert release.wait(5)
        else:
            resumed.set()
            assert resume_release.wait(5)
        job.checkpoint()
    manager = runtime.languages = LanguagePreparation(build, lambda *args: activated.append(args),
        lambda *_: {'ready': True}, path=tmp_path / 'languages.json', cancellable=True)
    manager.start()
    old_token = manager.stop_event
    close = manager.close
    monkeypatch.setattr(manager, 'close', lambda: close(timeout=.05))
    monkeypatch.setattr(api, 'runtime', runtime, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767', raise_server_exceptions=False)
    headers = {'X-Proxy-Transcript': 'update'}
    try:
        assert manager.request('cyberpunk', 'zh-Hans', 'en', 'first')
        assert entered.wait(1)
        assert client.post('/api/runtime/quiesce', headers=headers).status_code == 503
        assert old_token.is_set() and not runtime._updates_started
        assert running[0] and capture_events == []
        payload = {'running': True, 'session_id': 'preserved'}
        # An asyncio cancellation or a failed join cannot authorize another
        # generation of catalog writers, even when capture itself still runs.
        assert client.post('/api/runtime/activate', headers=headers, json=payload).status_code == 409
        assert manager.stop_event is old_token and not audio_restarts
        release.set()
        wait_for(lambda: not manager._workers)
        response = client.post('/api/runtime/quiesce', headers=headers)
        assert response.status_code == 200 and response.json()['running']
        assert capture_events == ['stop']
        response = client.post('/api/runtime/activate', headers=headers, json=response.json())
        assert response.status_code == 200
        assert runtime._updates_started and not runtime.standby
        assert manager.stop_event is not old_token and not manager.stop_event.is_set()
        assert audio_restarts == [True]
        assert capture_events == ['stop', 'preserved', 'start']
        monitor = manager.monitor
        assert monitor.is_alive() and resumed.wait(1)
        assert not manager.request('cyberpunk', 'zh-Hans', 'en', 'second')
        assert not activated and manager.selected('cyberpunk', 'first') is None
        resume_release.set()
        wait_for(lambda: not manager._workers)
        assert manager.selected('cyberpunk', 'first') == 'zh-Hans'
        assert manager.selected('cyberpunk', 'second') == 'zh-Hans'
        assert activated == [('cyberpunk', 'zh-Hans', 'first'), ('cyberpunk', 'zh-Hans', 'second')]
        assert client.post('/api/runtime/activate', headers=headers, json=payload).status_code == 200
        assert manager.monitor is monitor and audio_restarts == [True]
    finally:
        release.set()
        resume_release.set()
        close(timeout=2)
