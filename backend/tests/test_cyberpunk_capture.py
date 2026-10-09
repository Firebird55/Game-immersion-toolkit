import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.tests.test_subtitle_capture import fixture_service


@pytest.mark.parametrize("mapped", [True, False])
@pytest.mark.parametrize("game", ["cyberpunk", "wuwa", "witcher3"])
def test_local_game_routes_to_its_own_original_voice_and_preserves_retry(tmp_path, mapped, game):
    service, match, scheduled, published = fixture_service(tmp_path, game=game, mapped=mapped)
    service.game_indexes = {game: service.textmaps}
    service.textmaps.audio_count = 1
    service.game_voice_assets = {game: service.voice_assets}
    service.voice_assets = SimpleNamespace(has_variant=lambda *_: True,
        schedule=lambda *_: pytest.fail("Cyberpunk must never use ZZZ's audio adapter"))
    async def run():
        service._event_loop = asyncio.get_running_loop()
        window = SimpleNamespace(bounds=(0, 0, 1920, 1080), title="Cyberpunk 2077")
        for _ in range(2):
            service._scan_pragmata(window, service.settings.get().cyberpunk_region,
                service._engine, 0, datetime.now(timezone.utc), game=game)
        await asyncio.sleep(.02)
        assert service.transcript.count() == int(mapped)
        if mapped:
            assert published[-1].game == game and published[-1].audio_pending
            scheduled[0][2](published[-1].id, None, False)
            await asyncio.sleep(.02)
            saved = service.transcript.get(published[-1].id)
            assert saved.voiced and not saved.has_audio
            assert service.repair_recorded_line(saved)
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()
