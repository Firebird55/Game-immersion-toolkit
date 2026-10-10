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


def test_persistent_pragmata_worker_does_not_block_other_game_indexes():
    runtime = Runtime.__new__(Runtime)
    calls = []
    runtime.update_manager = SimpleNamespace(state="ready")
    runtime.pragmata_updater = SimpleNamespace(start=lambda: calls.append("pragmata"),
        status=lambda: {"state": "idle"}, _thread=SimpleNamespace(is_alive=lambda: True))
    runtime.game_updaters = {"cyberpunk": SimpleNamespace(start=lambda: calls.append("cyberpunk"))}
    asyncio.run(asyncio.wait_for(runtime.start_indexes_in_order(), timeout=1))
    assert calls == ["pragmata", "cyberpunk"]
