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
        hito=SimpleNamespace(close=lambda: None), _legacy_zzz_voice=SimpleNamespace(close=lambda: None),
        _legacy_pragmata_voice=SimpleNamespace(close=lambda: None), _readers={},
        _legacy_game_voices=[], game_voice_assets={}, _locale_voices={}, map_task=None)
    monkeypatch.setattr(api, 'runtime', runtime, raising=False)
    monkeypatch.setattr(api, 'Runtime', lambda: runtime)
    async def lifecycle():
        async with api.lifespan(api.app):
            if runtime.warm_task:
                await runtime.warm_task
    asyncio.run(lifecycle())
    assert calls == ['warm' if standby else 'updates']


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
