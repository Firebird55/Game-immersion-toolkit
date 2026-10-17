import asyncio
import threading
from types import SimpleNamespace

from backend.api import Runtime
from backend.pragmata_updates import PragmataUpdateManager


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
