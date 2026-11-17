"""Exercise actual desktop capture admission, publication and audio scheduling."""
import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from backend.models import CaptureRegion
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_audio_omission import record, TEXT
from backend.tests.test_player_speaker_capture import positioned
from backend.tests.test_subtitle_capture import fixture_service


@pytest.mark.parametrize('status', ['voiced', 'unknown'])
def test_text_only_desktop_scan_never_resolves_schedules_or_repairs_audio(tmp_path, status):
    data = tmp_path / 'nte'; data.mkdir()
    row = record('nte:authored:bridge', status=status)
    (data / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'nte', 'content_mode': 'text',
        'source_locale': 'en', 'records': [row]}), encoding='utf8')
    index = MultilingualTextIndex('nte', data)
    assert index.ready and index.capture_text_only and index.audio_count == 0
    service, _, scheduled, published = fixture_service(tmp_path, game='nte')
    service.game_indexes['nte'] = index
    def forbidden(*args, **kwargs): raise AssertionError('A text-only line requested original audio')
    service.game_voice_assets['nte'] = SimpleNamespace(has_variant=forbidden, schedule=forbidden)
    service.recorded_voice_assets = forbidden
    service._capture = lambda _: Image.new('RGB', (1000, 1000))
    service._ocr_image = lambda image, _: image
    region = CaptureRegion(left=0, top=0, width=1, height=1)
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1000, 1000), title='Authored text-only fixture')
    response = {'lines': [positioned(TEXT, .84)]}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    async def replay():
        service._event_loop = asyncio.get_running_loop()
        emitted = []
        for _ in range(3):
            emitted.extend(service._scan_pragmata(window, region, engine, 0, datetime.now(timezone.utc), 'nte').emitted_lines)
        assert len(emitted) == 1
        line = emitted[0]
        assert line.voice_status == status and line.is_requested_text_only
        assert not line.has_audio and not line.audio_pending
        assert not service._mapped_voice(index.match_lines([TEXT]))
        assert not service.repair_recorded_line(line)
        # A trusted new generation with unchanged text must pass both the
        # in-memory cooldown and database duplicate guard, without audio work.
        index.publisher_generation = 'authored-updated-generation'
        index.publisher_request_sha256 = 'a' * 64
        updated = []
        for _ in range(3):
            updated.extend(service._scan_pragmata(window, region, engine, 0, datetime.now(timezone.utc), 'nte').emitted_lines)
        assert len(updated) == 1 and updated[0].id != line.id
        assert updated[0].publisher_generation == index.publisher_generation
        await asyncio.sleep(.02)
    try:
        asyncio.run(replay())
        assert len(published) == 2 and not scheduled
        assert not published[0].audio_pending
    finally:
        service._executor.shutdown()
