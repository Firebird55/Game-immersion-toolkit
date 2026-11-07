import asyncio
import threading
from types import SimpleNamespace

from backend.api import Runtime
from backend.pragmata_updates import PragmataUpdateManager
import pytest


def test_pragmata_keeps_checking_while_companion_is_open(tmp_path, monkeypatch):
    manager = PragmataUpdateManager(tmp_path, None, None, interval=.02)
    checked_twice = threading.Event()
    calls = []
    def check():
        calls.append(True)
        if len(calls) == 2:
            checked_twice.set()
    monkeypatch.setattr(manager, "_run", check)
    manager.start()
    try:
        assert checked_twice.wait(2), "Only the startup check ran"
    finally:
        manager.close()
    assert not manager._thread.is_alive()


def test_startup_only_starts_the_prepared_language_monitor():
    runtime = Runtime.__new__(Runtime)
    calls = []
    runtime._updates_started = False
    runtime.languages = SimpleNamespace(start=lambda: calls.append('prepared'))
    runtime.start_audio_repair = lambda: calls.append('repair')
    runtime.update_manager = SimpleNamespace(start=lambda: calls.append('unexpected-all-zzz'))
    runtime.pragmata_updater = SimpleNamespace(start=lambda: calls.append('unexpected-all-pragmata'))
    runtime.game_updaters = {'cyberpunk': SimpleNamespace(start=lambda: calls.append('unexpected-all-cyberpunk'))}
    runtime.start_updates()
    runtime.start_updates()
    assert calls == ['prepared', 'repair']


def test_startup_starts_account_independent_mobile_rules_once():
    runtime = Runtime.__new__(Runtime)
    calls = []
    runtime._updates_started = False
    runtime.languages = SimpleNamespace(start=lambda: calls.append('languages'))
    runtime.automatic_exports = SimpleNamespace(start=lambda: calls.append('exports'))
    runtime.start_audio_repair = lambda: calls.append('repair')
    runtime.start_updates()
    runtime.start_updates()
    assert calls == ['languages', 'exports', 'repair']


@pytest.mark.parametrize('failed_thread', ['prepared-language-updates', 'toolkit-release-updates', 'automatic-mobile-export'])
def test_stop_after_partial_update_start_allows_a_clean_restart(tmp_path, monkeypatch, failed_thread):
    from backend.automatic_mobile_export import AutomaticMobileExports
    from backend.language_preparation import LanguagePreparation
    from backend.toolkit_update import ToolkitUpdater

    monkeypatch.delenv('PROXY_TRANSCRIPT_HOST_MANAGED', raising=False)
    runtime = Runtime.__new__(Runtime)
    runtime._updates_started = False
    runtime.languages = LanguagePreparation(None, None, None, path=tmp_path/'languages.json')
    runtime.toolkit_updater = ToolkitUpdater(tmp_path)
    runtime.toolkit_updater.status = lambda: {'enabled': False}
    runtime.automatic_exports = AutomaticMobileExports(tmp_path, home=tmp_path/'exports')
    runtime.repair_task = runtime.map_task = runtime.index_task = None
    runtime.update_manager = runtime.pragmata_updater = SimpleNamespace(close=lambda: None)
    runtime.game_updaters = {}
    repairs = []
    runtime.start_audio_repair = lambda: repairs.append(True)
    start = threading.Thread.start

    def fail_start(thread):
        if thread.name == failed_thread:
            # These two owners publish before startup returns. A concurrent
            # close must refuse while the published Thread is still unstarted.
            owner = {'toolkit-release-updates': runtime.toolkit_updater,
                     'automatic-mobile-export': runtime.automatic_exports}.get(thread.name)
            if owner is not None:
                with pytest.raises(RuntimeError, match='before it is started'):
                    owner.close()
            raise RuntimeError('authored thread startup failure')
        start(thread)

    def threads():
        return [thread for thread in (runtime.languages.monitor, runtime.toolkit_updater.thread,
                runtime.automatic_exports.thread) if thread is not None]

    try:
        with monkeypatch.context() as fault:
            fault.setattr(threading.Thread, 'start', fail_start)
            with pytest.raises(RuntimeError, match='authored thread startup failure'):
                runtime.start_updates()
        first = threads()
        asyncio.run(runtime.stop_updates())
        assert not any(thread.is_alive() for thread in first) and not repairs
        runtime.start_updates()
        assert len(threads()) == 3 and all(thread.is_alive() for thread in threads())
        assert repairs == [True]
    finally:
        asyncio.run(runtime.stop_updates())


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_initial_producer_failure_shuts_down_constructed_runtime(monkeypatch, cleanup_fails):
    from backend import api

    calls = []
    startup_error = RuntimeError('authoritative startup failure')
    cleanup_error = TimeoutError('worker cleanup incomplete')
    def start_updates():
        calls.append('start')
        raise startup_error
    async def quiesce():
        calls.append('quiesce')
        if cleanup_fails:
            raise cleanup_error
    async def close_capture():
        calls.append('capture')
    async def step(operation, deadline, *, blocking):
        operation()
    runtime = SimpleNamespace(capture_language_ready=lambda game: False, standby=False, warm_task=None,
        start_updates=start_updates, quiesce=quiesce, capture=SimpleNamespace(close=close_capture),
        _handoff_step=step, _reading_registry=SimpleNamespace(shutdown=lambda deadline: calls.append('readers')),
        worker_pools=lambda: [SimpleNamespace(shutdown=lambda wait: calls.append('pool'))])
    monkeypatch.setattr(api, 'Runtime', lambda: runtime)
    monkeypatch.setattr(api, 'runtime', runtime, raising=False)
    async def run():
        async with api.lifespan(api.app):
            pytest.fail('Startup must not admit requests after a producer failed.')
    with pytest.raises(RuntimeError) as failed:
        asyncio.run(run())
    assert failed.value is startup_error
    if cleanup_fails:
        assert failed.value.__cause__ is cleanup_error and calls == ['start', 'quiesce']
    else:
        assert calls == ['start', 'quiesce', 'capture', 'readers', 'pool']


@pytest.mark.parametrize('standby', [False, True])
def test_startup_with_prepared_zzz_uses_multilingual_index_without_legacy_reload(tmp_path, monkeypatch, standby):
    from backend import api
    from backend.multilingual_index import MultilingualTextIndex
    calls = []
    async def warmup():
        calls.append('warm')
    async def stop():
        pass
    legacy_path = tmp_path / 'zh_base.json'
    legacy_path.write_text('{}')
    runtime = SimpleNamespace(
        capture_language_ready=lambda _: True, textmaps=MultilingualTextIndex('zzz', tmp_path),
        _legacy_zzz_index=SimpleNamespace(file_path=lambda _: legacy_path),
        start_map_prepare=lambda: calls.append('legacy-reload'), standby=standby, warm_task=None,
        start_updates=lambda: calls.append('updates'), settings=SimpleNamespace(get=lambda: SimpleNamespace(auto_start=False)),
        installation=SimpleNamespace(completed=True), capture=SimpleNamespace(warmup=warmup, close=stop),
        mobile_exports=SimpleNamespace(cancel_all=lambda: None), stop_updates=stop,
        quiesce=stop, worker_pools=lambda: [],
        hito=SimpleNamespace(close=lambda: None), _legacy_zzz_voice=SimpleNamespace(close=lambda: None),
        _legacy_pragmata_voice=SimpleNamespace(close=lambda: None), _readers={},
        _legacy_game_voices=[], game_voice_assets={}, _locale_voices={}, map_task=None)
    reader_shutdowns = []
    runtime._reading_registry = SimpleNamespace(shutdown=lambda deadline: reader_shutdowns.append(deadline))
    runtime._handoff_drains = []
    runtime._handoff_step = lambda operation, deadline, **options: Runtime._handoff_step(
        runtime, operation, deadline, **options)
    monkeypatch.setattr(api, 'runtime', runtime, raising=False)
    monkeypatch.setattr(api, 'Runtime', lambda: runtime)
    async def lifecycle():
        async with api.lifespan(api.app):
            if runtime.warm_task:
                await runtime.warm_task
    asyncio.run(lifecycle())
    assert calls == ['warm' if standby else 'updates']
    assert len(reader_shutdowns) == 1 and all(task.done() for task in runtime._handoff_drains)


def test_legacy_refresh_keeps_its_index_after_a_language_switch(tmp_path):
    from backend.multilingual_index import MultilingualTextIndex
    calls = []
    async def broadcast(event):
        calls.append(event['textmaps'])
    active = MultilingualTextIndex('zzz', tmp_path)
    runtime = SimpleNamespace(textmaps=active, standby=True,
        _legacy_zzz_index=SimpleNamespace(prepare=lambda **_: calls.append('legacy'), set_message=lambda _: None),
        hub=SimpleNamespace(broadcast=broadcast))
    before = active.status()
    asyncio.run(Runtime.prepare_maps(runtime))
    assert calls == ['legacy', before]
    assert active.status() == before
